"""
IS Claim Automation Dashboard
Run:  python dashboard_is_claim.py
Opens automatically at http://localhost:5000
"""

import sys, os

def _check(pkg, install_name=None):
    try:
        __import__(pkg)
    except ImportError:
        n = install_name or pkg
        print(f"  Missing package '{n}'. Installing...")
        os.system(f'"{sys.executable}" -m pip install {n} -q')

_check("flask")

from flask import Flask, render_template_string, request, jsonify, Response
import subprocess, threading, queue, json, time, webbrowser, socket, re, urllib.request, stat

app = Flask(__name__)

BASE_DIR          = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH       = os.path.join(BASE_DIR, "IS_Claim_V1.py")
DRAFT_SCRIPT_PATH = os.path.join(BASE_DIR, "IS_Claim_Draft_V1.py")

try:
    from config import NGROK_AUTH_TOKEN, NGROK_STATIC_DOMAIN
except ImportError:
    NGROK_AUTH_TOKEN    = ""
    NGROK_STATIC_DOMAIN = ""

RECORD_FIELDS = [
    "record_no","farmer_name","account_no","loan_app_no",
    "sanction_date","loan_sanctioned_amt","max_withdrawal",
    "max_allowed_claim","applicable_is","interest_days",
    "status","failure_reason",
]

state = {
    "running":    False,
    "process":    None,
    "log_queue":  queue.Queue(),
    "summary":    {"processed": 0, "success": 0, "failed": 0},
    "end_date":   "",
    "tunnel_proc": None,
    "records":    [],       # list of dicts, one per processed record
    "csv_ready":  False,    # True once CSV_DATA_END received
    "csv_data":   "",       # raw CSV string from script
}

# ─── HTML ────────────────────────────────────────────────────────────────────
HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>IS Claim Dashboard</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet"/>
<style>
body{background:#f0f4f8;font-family:'Segoe UI',sans-serif;}
.navbar{background:linear-gradient(90deg,#1a4b8c,#2d6fd4);}
.card{border:none;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);}
.card-header{border-radius:12px 12px 0 0!important;font-weight:600;}
.sc{border-radius:12px;color:#fff;padding:16px 18px;}
.sc-total{background:linear-gradient(135deg,#2d6fd4,#1a4b8c);}
.sc-ok   {background:linear-gradient(135deg,#198754,#0f5132);}
.sc-fail {background:linear-gradient(135deg,#dc3545,#842029);}
.sc .num{font-size:2rem;font-weight:700;line-height:1;}
.sc .lbl{font-size:.77rem;opacity:.85;margin-top:3px;}
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(45,111,212,.55);}
  50%{box-shadow:0 0 0 12px rgba(45,111,212,0);}}
.btn-ready{animation:pulse 1.5s ease-in-out 5;}
.btn-go{background:#2d6fd4;border:none;font-size:1rem;}
.btn-go:hover{background:#1a4b8c;}
.btn-go:disabled{background:#9ab8e8;cursor:not-allowed;}
.btn-stop{background:#dc3545;border:none;}
#logBox{background:#1e1e1e;color:#d4d4d4;font-family:'Consolas',monospace;
  font-size:.78rem;border-radius:8px;height:420px;overflow-y:auto;
  padding:10px;white-space:pre-wrap;word-break:break-all;}
.ls{color:#4ec9b0;}.le{color:#f44747;}.lw{color:#dcdcaa;}.li{color:#9cdcfe;}
.date-input{max-width:220px;font-size:1rem;padding:.5rem .75rem;}
</style>
</head>
<body>

<nav class="navbar navbar-dark px-4 py-2 mb-3">
  <span class="navbar-brand fw-bold fs-6">
    <i class="bi bi-file-earmark-check-fill me-2"></i>IS Claim Automation Dashboard
    <span class="badge bg-primary ms-2" style="font-size:.65rem;vertical-align:middle;">V1</span>
  </span>
  <span class="text-white-50 small">
    fasalrin.gov.in — IS/PRI Claim Application
    &nbsp;|&nbsp;
    <a id="urlLink" href="#" class="text-white-50 text-decoration-none small"></a>
  </span>
</nav>

<div class="container-fluid px-4">

<!-- ── Row 1: Config + Stats ── -->
<div class="row g-3 mb-3">

  <!-- Config card -->
  <div class="col-lg-5">
    <div class="card h-100">
      <div class="card-header bg-white border-bottom">
        <i class="bi bi-sliders me-2 text-primary"></i>Configuration
      </div>
      <div class="card-body d-flex flex-column">

        <div class="mb-4">
          <label class="form-label fw-semibold">
            <i class="bi bi-calendar3 me-1 text-primary"></i>
            Interest Cycle End / Rollover Date
            <span class="text-danger">*</span>
          </label>
          <input type="text" id="endDate" class="form-control date-input"
                 placeholder="DD/MM/YYYY" maxlength="10"
                 oninput="formatDateInput(this)"/>
          <div class="form-text text-muted">
            e.g. 03/03/2026 — used for all records
          </div>
        </div>

        <div class="alert alert-info py-2 px-3 small mb-4">
          <i class="bi bi-info-circle-fill me-1"></i>
          <strong>No Excel needed.</strong> All other data (Sanction Date, Loan Amount)
          is read automatically from the portal.
        </div>

        <div class="mt-auto">
          <button id="btnRun" class="btn btn-go text-white fw-bold w-100 py-3"
                  onclick="startAuto('pending')" disabled
                  style="font-size:1.1rem;letter-spacing:.03em;">
            <i class="bi bi-play-circle-fill me-2"></i>Start — PENDING Records
          </button>
          <button id="btnDraft" class="btn fw-bold w-100 py-2 mt-2 text-white"
                  onclick="startAuto('draft')" disabled
                  style="background:linear-gradient(135deg,#fd7e14,#c55a00);border:none;font-size:1rem;">
            <i class="bi bi-send-fill me-2"></i>Submit — DRAFT Records
          </button>
          <button id="btnStop"
                  class="btn btn-stop text-white fw-bold w-100 py-3 d-none mt-2"
                  onclick="stopAuto()" style="font-size:1.1rem;">
            <i class="bi bi-stop-circle-fill me-2"></i>Stop Automation
          </button>
          <p id="runHint" class="text-muted small text-center mb-0 mt-2">
            <i class="bi bi-arrow-up me-1"></i>Enter date above to enable
          </p>
        </div>

      </div>
    </div>
  </div>

  <!-- Stats -->
  <div class="col-lg-7">
    <div class="row g-3">
      <div class="col-6 col-md-4">
        <div class="sc sc-total h-100">
          <div class="num" id="sT">0</div>
          <div class="lbl"><i class="bi bi-people-fill me-1"></i>Processed</div>
        </div>
      </div>
      <div class="col-6 col-md-4">
        <div class="sc sc-ok h-100">
          <div class="num" id="sS">0</div>
          <div class="lbl"><i class="bi bi-check-circle-fill me-1"></i>Successful</div>
        </div>
      </div>
      <div class="col-6 col-md-4">
        <div class="sc sc-fail h-100">
          <div class="num" id="sF">0</div>
          <div class="lbl"><i class="bi bi-x-circle-fill me-1"></i>Failed</div>
        </div>
      </div>
      <div class="col-12 mt-2">
        <div class="card">
          <div class="card-body py-3">
            <div class="d-flex justify-content-between small text-muted mb-1">
              <span>Progress</span><span id="progTxt">0 processed</span>
            </div>
            <div class="progress" style="height:10px;border-radius:8px;">
              <div id="progBar" class="progress-bar bg-primary"
                   style="width:0%;transition:width .4s;"></div>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ── Log ── -->
<div class="row g-3 mb-3">
  <div class="col-12">
    <div class="card">
      <div class="card-header bg-dark text-white d-flex justify-content-between align-items-center">
        <span><i class="bi bi-terminal-fill me-2"></i>Live Log</span>
        <button class="btn btn-outline-light btn-sm py-0 px-2" onclick="clearLog()">
          <i class="bi bi-trash3"></i> Clear
        </button>
      </div>
      <div class="card-body p-2">
        <div id="logBox">Waiting for automation to start…
</div>
      </div>
    </div>
  </div>
</div>

<!-- ── Results Table + Download ── -->
<div class="row g-3 mb-4" id="resultsSection" style="display:none!important;">
  <div class="col-12">
    <div class="card">
      <div class="card-header bg-white border-bottom d-flex justify-content-between align-items-center">
        <span><i class="bi bi-table me-2 text-primary"></i>Results — <span id="resultCount">0</span> records</span>
        <a id="btnDownload" href="/download" class="btn btn-success btn-sm fw-semibold" download>
          <i class="bi bi-download me-1"></i>Download CSV
        </a>
      </div>
      <div class="card-body p-0" style="overflow-x:auto;max-height:320px;overflow-y:auto;">
        <table class="table table-sm table-striped table-hover mb-0" style="font-size:.78rem;">
          <thead class="table-dark sticky-top">
            <tr>
              <th>#</th><th>Farmer Name</th><th>Account No</th>
              <th>Sanction Date</th><th>Loan Amt</th>
              <th>Max Withdrawal</th><th>Max Allowed</th><th>Applicable IS</th>
              <th>Status</th><th>Failure Reason</th>
            </tr>
          </thead>
          <tbody id="resultsTbody"></tbody>
        </table>
      </div>
    </div>
  </div>
</div>

</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
document.getElementById('urlLink').textContent = window.location.href;
document.getElementById('urlLink').href = window.location.href;

function formatDateInput(inp) {
  var v = inp.value.replace(/[^\d]/g, '');
  if (v.length > 2) v = v.slice(0,2) + '/' + v.slice(2);
  if (v.length > 5) v = v.slice(0,5) + '/' + v.slice(5);
  inp.value = v.slice(0,10);
  validateDate();
}

function validateDate() {
  var val = document.getElementById('endDate').value.trim();
  var ok = /^\d{2}\/\d{2}\/\d{4}$/.test(val);
  var stopped = document.getElementById('btnStop').classList.contains('d-none');
  document.getElementById('btnRun').disabled   = !ok || !stopped;
  document.getElementById('btnDraft').disabled = !ok || !stopped;
  if (ok) {
    document.getElementById('runHint').innerHTML =
      '<i class="bi bi-check-circle-fill text-success me-1"></i>Ready — choose PENDING or DRAFT above';
  } else {
    document.getElementById('runHint').innerHTML =
      '<i class="bi bi-arrow-up me-1"></i>Enter a valid date (DD/MM/YYYY) to enable';
  }
}

// Log
let autoScroll = true;
const lb = document.getElementById('logBox');
lb.addEventListener('scroll', () => {
  autoScroll = lb.scrollTop + lb.clientHeight >= lb.scrollHeight - 30;
});

function appendLog(t) {
  const s = document.createElement('span');
  t = t || '';
  if      (/SUBMITTED successfully|saved successfully|✅/.test(t)) s.className = 'ls';
  else if (/ERROR on record|❌|Fatal|Browser connection/.test(t))  s.className = 'le';
  else if (/WARNING|⚠|auto-continuing/.test(t))                   s.className = 'lw';
  else if (/Record \d+|─|PROCESSING|Login detected/.test(t))      s.className = 'li';
  s.textContent = t + '\n';
  lb.appendChild(s);
  if (autoScroll) lb.scrollTop = lb.scrollHeight;
}
function clearLog() { lb.innerHTML = ''; }

// Summary
function updateSummary(s) {
  if (!s) return;
  document.getElementById('sT').textContent = s.processed || 0;
  document.getElementById('sS').textContent = s.success   || 0;
  document.getElementById('sF').textContent = s.failed    || 0;
  var pct = s.processed > 0 ? Math.min(100, Math.round((s.success + s.failed) / Math.max(s.processed,1) * 100)) : 0;
  document.getElementById('progBar').style.width = pct + '%';
  document.getElementById('progTxt').textContent = (s.processed || 0) + ' processed';
}

// SSE
let es = null;
function startStream() {
  if (es) es.close();
  es = new EventSource('/stream');
  es.onmessage = e => {
    try {
      const d = JSON.parse(e.data);
      if (d.type === 'log')     appendLog(d.text);
      if (d.type === 'summary') updateSummary(d.summary);
      if (d.type === 'record_update') addOrUpdateRow(d.record);
      if (d.type === 'csv_ready') {
        document.getElementById('btnDownload').href = '/download?t=' + Date.now();
      }
      if (d.type === 'done') {
        appendLog('\n══ Automation finished ══\n');
        document.getElementById('btnStop').classList.add('d-none');
        document.getElementById('btnRun').classList.remove('d-none');
        document.getElementById('btnDraft').classList.remove('d-none');
        document.getElementById('btnRun').disabled = false;
        document.getElementById('btnDraft').disabled = false;
        document.getElementById('runHint').innerHTML =
          '<i class="bi bi-check2-all text-success me-1"></i>Finished — click above to run again';
        if (es) { es.close(); es = null; }
        // Load latest records from server
        fetch('/records').then(r=>r.json()).then(d=>{
          d.records.forEach(addOrUpdateRow);
        });
      }
    } catch(err) {}
  };
  es.onerror = () => {};
}

function startAuto(mode) {
  var date = document.getElementById('endDate').value.trim();
  if (!/^\d{2}\/\d{2}\/\d{4}$/.test(date)) {
    alert('Please enter a valid date in DD/MM/YYYY format');
    return;
  }
  var isDraft = (mode === 'draft');
  var endpoint = isDraft ? '/start_draft' : '/start';
  var label = isDraft ? 'DRAFT Submit' : 'IS Claim Automation (PENDING)';
  clearLog();
  appendLog('Starting ' + label + '...\n');
  appendLog('Interest Cycle End Date: ' + date + '\n');
  document.getElementById('btnRun').classList.add('d-none');
  document.getElementById('btnDraft').classList.add('d-none');
  document.getElementById('btnStop').classList.remove('d-none');
  document.getElementById('runHint').innerHTML =
    '<i class="bi bi-hourglass-split me-1 text-warning"></i>Running — do not close this window';

  fetch(endpoint, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({end_date: date})
  })
  .then(r => r.json())
  .then(d => {
    if (d.error) {
      alert('Error: ' + d.error);
      document.getElementById('btnStop').classList.add('d-none');
      document.getElementById('btnRun').classList.remove('d-none');
      document.getElementById('btnDraft').classList.remove('d-none');
      document.getElementById('btnRun').disabled = false;
      document.getElementById('btnDraft').disabled = false;
      return;
    }
    startStream();
  })
  .catch(e => {
    alert('Start failed: ' + e);
    document.getElementById('btnStop').classList.add('d-none');
    document.getElementById('btnRun').classList.remove('d-none');
    document.getElementById('btnDraft').classList.remove('d-none');
  });
}

// Results table
const _rows = {};
function addOrUpdateRow(r) {
  document.getElementById('resultsSection').style.removeProperty('display');
  const tbody = document.getElementById('resultsTbody');
  const statusBadge = r.status === 'SUBMITTED'
    ? '<span class="badge bg-success">SUBMITTED</span>'
    : r.status === 'FAILED'
      ? '<span class="badge bg-danger">FAILED</span>'
      : '<span class="badge bg-secondary">' + (r.status||'...') + '</span>';
  const html = `<td>${r.record_no}</td>
    <td>${r.farmer_name||'—'}</td>
    <td><small>${r.account_no||'—'}</small></td>
    <td>${r.sanction_date||'—'}</td>
    <td>₹${r.loan_sanctioned_amt||'—'}</td>
    <td>₹${r.max_withdrawal||'—'}</td>
    <td>₹${r.max_allowed_claim||'—'}</td>
    <td>₹${r.applicable_is||'—'}</td>
    <td>${statusBadge}</td>
    <td class="text-danger small">${r.failure_reason||''}</td>`;
  if (_rows[r.record_no]) {
    _rows[r.record_no].innerHTML = html;
  } else {
    const tr = document.createElement('tr');
    tr.innerHTML = html;
    tbody.appendChild(tr);
    _rows[r.record_no] = tr;
  }
  document.getElementById('resultCount').textContent = Object.keys(_rows).length;
}

function stopAuto() {
  if (!confirm('Stop the automation?')) return;
  fetch('/stop', {method: 'POST'}).then(() => {
    appendLog('\nStopped by user.\n');
    document.getElementById('btnStop').classList.add('d-none');
    document.getElementById('btnRun').classList.remove('d-none');
    document.getElementById('btnDraft').classList.remove('d-none');
    document.getElementById('btnRun').disabled = false;
    document.getElementById('btnDraft').disabled = false;
    document.getElementById('runHint').innerHTML =
      '<i class="bi bi-stop-circle text-danger me-1"></i>Stopped — enter date and click above to run again';
  });
}
</script>
</body>
</html>
"""


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/start", methods=["POST"])
def start():
    if state["running"]:
        return jsonify({"error": "Already running — stop first"})
    if not os.path.exists(SCRIPT_PATH):
        return jsonify({"error": f"Script not found: {SCRIPT_PATH}"})

    body = request.get_json(force=True) or {}
    end_date = (body.get("end_date") or "").strip()
    if not end_date:
        return jsonify({"error": "Interest Cycle End Date is required"})

    state["end_date"]  = end_date
    state["running"]   = True
    state["summary"]   = {"processed": 0, "success": 0, "failed": 0}
    state["records"]   = []
    state["csv_ready"] = False
    state["csv_data"]  = ""
    state["_csv_collecting"] = False

    while not state["log_queue"].empty():
        try: state["log_queue"].get_nowait()
        except: pass

    def _run():
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", SCRIPT_PATH, end_date],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=BASE_DIR,
            )
            state["process"] = proc
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if not line:
                    continue

                # ── CSV block collection ──────────────────────────────────────
                if line == "CSV_DATA_START":
                    state["_csv_collecting"] = True
                    state["csv_data"] = ""
                    continue
                if line == "CSV_DATA_END":
                    state["_csv_collecting"] = False
                    state["csv_ready"] = True
                    state["log_queue"].put(json.dumps({"type": "csv_ready"}))
                    continue
                if state.get("_csv_collecting"):
                    state["csv_data"] += line + "\n"
                    continue

                # ── RECORD_DATA lines — parsed for per-record tracking ────────
                if line.startswith("RECORD_DATA|"):
                    parts = line.split("|")[1:]  # strip prefix
                    rec = {}
                    for i, field in enumerate(RECORD_FIELDS):
                        rec[field] = parts[i] if i < len(parts) else ""
                    # Update existing record or append new
                    updated = False
                    for existing in state["records"]:
                        if existing.get("record_no") == rec.get("record_no"):
                            existing.update(rec)
                            updated = True
                            break
                    if not updated:
                        state["records"].append(rec)
                    state["log_queue"].put(json.dumps({"type": "record_update", "record": rec}))
                    continue

                state["log_queue"].put(json.dumps({"type": "log", "text": line}))

                # Record counter: "Record X/Y"
                m = re.search(r'Record\s+(\d+)/(\d+)', line)
                if m:
                    try:
                        idx = int(m.group(1))
                        state["summary"]["processed"] = idx
                        state["log_queue"].put(json.dumps({
                            "type": "summary", "summary": dict(state["summary"])}))
                    except:
                        pass

                # Success
                if "SUBMITTED successfully" in line:
                    state["summary"]["success"] = state["summary"].get("success", 0) + 1
                    state["log_queue"].put(json.dumps({
                        "type": "summary", "summary": dict(state["summary"])}))

                # Error
                if re.search(r'ERROR on record\s+\d+', line):
                    state["summary"]["failed"] = state["summary"].get("failed", 0) + 1
                    state["log_queue"].put(json.dumps({
                        "type": "summary", "summary": dict(state["summary"])}))

            proc.wait()
        except Exception as e:
            state["log_queue"].put(json.dumps({"type": "log", "text": f"Runner error: {e}"}))
        finally:
            state["running"] = False
            state["process"] = None
            state["log_queue"].put(json.dumps({"type": "done"}))

    threading.Thread(target=_run, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/start_draft", methods=["POST"])
def start_draft():
    if state["running"]:
        return jsonify({"error": "Already running — stop first"})
    if not os.path.exists(DRAFT_SCRIPT_PATH):
        return jsonify({"error": f"Draft script not found: {DRAFT_SCRIPT_PATH}"})

    body = request.get_json(force=True) or {}
    end_date = (body.get("end_date") or "").strip()
    if not end_date:
        return jsonify({"error": "Interest Cycle End Date is required"})

    state["end_date"]  = end_date
    state["running"]   = True
    state["summary"]   = {"processed": 0, "success": 0, "failed": 0}
    state["records"]   = []
    state["csv_ready"] = False
    state["csv_data"]  = ""
    state["_csv_collecting"] = False

    while not state["log_queue"].empty():
        try: state["log_queue"].get_nowait()
        except: pass

    def _run_draft():
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", DRAFT_SCRIPT_PATH, end_date],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                cwd=BASE_DIR,
            )
            state["process"] = proc
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if not line:
                    continue
                if line == "CSV_DATA_START":
                    state["_csv_collecting"] = True
                    state["csv_data"] = ""
                    continue
                if line == "CSV_DATA_END":
                    state["_csv_collecting"] = False
                    state["csv_ready"] = True
                    state["log_queue"].put(json.dumps({"type": "csv_ready"}))
                    continue
                if state.get("_csv_collecting"):
                    state["csv_data"] += line + "\n"
                    continue
                if line.startswith("RECORD_DATA|"):
                    parts = line.split("|")[1:]
                    rec = {}
                    for i, field in enumerate(RECORD_FIELDS):
                        rec[field] = parts[i] if i < len(parts) else ""
                    updated = False
                    for existing in state["records"]:
                        if existing.get("record_no") == rec.get("record_no"):
                            existing.update(rec); updated = True; break
                    if not updated:
                        state["records"].append(rec)
                    state["log_queue"].put(json.dumps({"type": "record_update", "record": rec}))
                    continue
                state["log_queue"].put(json.dumps({"type": "log", "text": line}))
                m = re.search(r'Draft Record\s+(\d+)/(\d+)', line)
                if m:
                    try:
                        state["summary"]["processed"] = int(m.group(1))
                        state["log_queue"].put(json.dumps({"type": "summary", "summary": dict(state["summary"])}))
                    except: pass
                if "SUBMITTED successfully" in line:
                    state["summary"]["success"] = state["summary"].get("success", 0) + 1
                    state["log_queue"].put(json.dumps({"type": "summary", "summary": dict(state["summary"])}))
                if re.search(r'ERROR on draft record\s+\d+', line):
                    state["summary"]["failed"] = state["summary"].get("failed", 0) + 1
                    state["log_queue"].put(json.dumps({"type": "summary", "summary": dict(state["summary"])}))
            proc.wait()
        except Exception as e:
            state["log_queue"].put(json.dumps({"type": "log", "text": f"Runner error: {e}"}))
        finally:
            state["running"] = False
            state["process"] = None
            state["log_queue"].put(json.dumps({"type": "done"}))

    threading.Thread(target=_run_draft, daemon=True).start()
    return jsonify({"ok": True})


@app.route("/stop", methods=["POST"])
def stop():
    p = state.get("process")
    if p:
        try: p.terminate()
        except: pass
    state["running"] = False
    state["log_queue"].put(json.dumps({"type": "done"}))
    return jsonify({"ok": True})


@app.route("/stream")
def stream():
    def _gen():
        while True:
            try:
                msg = state["log_queue"].get(timeout=25)
                yield f"data: {msg}\n\n"
                if json.loads(msg).get("type") == "done":
                    break
            except queue.Empty:
                yield 'data: {"type":"heartbeat"}\n\n'
    return Response(
        _gen(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route("/ping")
def ping():
    return jsonify({"ok": True})


@app.route("/download")
def download():
    import csv, io as _io
    from flask import make_response
    # Use CSV emitted by script if available, else build from state["records"]
    if state.get("csv_data"):
        csv_str = state["csv_data"]
    else:
        out = _io.StringIO()
        writer = csv.DictWriter(out, fieldnames=RECORD_FIELDS, extrasaction="ignore")
        writer.writeheader()
        for rec in state["records"]:
            writer.writerow(rec)
        csv_str = out.getvalue()

    end_date_safe = state.get("end_date", "").replace("/", "-")
    filename = f"IS_Claim_Results_{end_date_safe}.csv"
    resp = make_response(csv_str)
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


@app.route("/records")
def records():
    return jsonify({"records": state["records"], "csv_ready": state.get("csv_ready", False)})


# ─── Tunnel helpers ───────────────────────────────────────────────────────────
def _get_cloudflared_exe():
    exe = os.path.join(BASE_DIR, "cloudflared.exe")
    if os.path.exists(exe):
        return exe
    print("  Downloading cloudflared.exe (one-time) ...")
    urls = [
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
    ]
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    urllib.request.install_opener(opener)
    for url in urls:
        try:
            urllib.request.urlretrieve(url, exe)
            if os.path.getsize(exe) > 1_000_000:
                os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
                print("  cloudflared.exe downloaded")
                return exe
        except Exception as e:
            print(f"  Download failed: {e}")
    try: os.remove(exe)
    except: pass
    return None


def _start_cloudflared(port):
    import subprocess as sp
    exe = _get_cloudflared_exe()
    if not exe:
        return None
    result = {"url": None}
    def _run():
        try:
            proc = sp.Popen(
                [exe, "tunnel", "--url", f"http://localhost:{port}"],
                stdout=sp.PIPE, stderr=sp.STDOUT, text=True)
            state["tunnel_proc"] = proc
            for line in proc.stdout:
                m = re.search(r'https://[\w\-]+\.trycloudflare\.com', line)
                if m:
                    result["url"] = m.group(0)
                    return
        except Exception as e:
            print(f"  cloudflared error: {e}")
    t = threading.Thread(target=_run, daemon=True)
    t.start(); t.join(timeout=30)
    return result["url"]


def _find_free_port(start=5000, tries=5):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", p)); return p
            except OSError:
                continue
    return start


def _get_local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    PORT      = _find_free_port(5000)
    LOCAL_IP  = _get_local_ip()
    LOCAL_URL = f"http://localhost:{PORT}"
    LAN_URL   = f"http://{LOCAL_IP}:{PORT}"

    print()
    print("  Starting Cloudflare tunnel ...")
    PUBLIC_URL = _start_cloudflared(PORT)

    print()
    print("=" * 68)
    print("  IS CLAIM AUTOMATION DASHBOARD  —  V1")
    print("=" * 68)
    print(f"  This PC only    →  {LOCAL_URL}")
    print(f"  Same WiFi/LAN   →  {LAN_URL}")
    if PUBLIC_URL:
        print(f"  Mobile/any net  →  {PUBLIC_URL}")
    else:
        print("  Tunnel failed — use local URL")
    print()
    print("  Keep this terminal open. Press Ctrl+C to stop.")
    print("=" * 68)
    print()

    threading.Thread(
        target=lambda: (time.sleep(2), webbrowser.open(LOCAL_URL)),
        daemon=True
    ).start()

    app.run(debug=False, host="0.0.0.0", port=PORT, threaded=True)

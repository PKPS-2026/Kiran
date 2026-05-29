"""
KCC Loan Automation Dashboard
Run:  python dashboard.py
Opens automatically at http://localhost:5000  (or 5001 / 5002 if port busy)
"""

# ── dependency check ──────────────────────────────────────────────────────────
import sys, os

def _check(pkg, install_name=None):
    try:
        __import__(pkg)
    except ImportError:
        n = install_name or pkg
        print(f"  ⚠  Missing package '{n}'. Installing...")
        os.system(f'"{sys.executable}" -m pip install {n} -q')

_check("flask")
_check("pandas")
_check("openpyxl")

# ── imports ───────────────────────────────────────────────────────────────────
from flask import Flask, render_template_string, request, jsonify, Response
import pandas as pd
import subprocess, threading, queue, json, time, io, webbrowser, socket, re, tempfile

app = Flask(__name__)

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
# Save to a separate file so it never conflicts with loans.xlsx open in Excel
UPLOAD_PATH = os.path.join(BASE_DIR, "loans_upload.xlsx")
SCRIPT_PATH = os.path.join(BASE_DIR, "PR_V3.py")

# ── ngrok config — loaded from config.py (gitignored, stays local) ───────────
try:
    from config import NGROK_AUTH_TOKEN, NGROK_STATIC_DOMAIN
except ImportError:
    NGROK_AUTH_TOKEN    = ""
    NGROK_STATIC_DOMAIN = ""

REQUIRED_COLUMNS = [
    "Aadhar Number",
    "Loan Disbursal Date",
    "Max Withdrawal Amount (INR)",
]
OPTIONAL_COLUMNS = [
    "Account Number",
    "Loan Repayment Date",
    "Beneficiary Name",
]

state = {
    "records":   [],
    "running":   False,
    "process":   None,
    "statuses":  {},
    "log_queue": queue.Queue(),
    "summary":   {"total": 0, "success": 0, "failed": 0, "skipped": 0, "pending": 0},
}

# ─── HTML ────────────────────────────────────────────────────────────────────
HTML = r"""
<!doctype html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width,initial-scale=1"/>
<title>KCC Loan Dashboard</title>
<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet"/>
<link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet"/>
<style>
body{background:#f0f4f8;font-family:'Segoe UI',sans-serif;}
.navbar{background:linear-gradient(90deg,#1a6b3c,#2d9e5f);}
.card{border:none;border-radius:12px;box-shadow:0 2px 12px rgba(0,0,0,.08);}
.card-header{border-radius:12px 12px 0 0!important;font-weight:600;}

/* tabs */
.nav-tabs .nav-link{border:none;color:#555;padding:.45rem 1rem;}
.nav-tabs .nav-link.active{border-bottom:3px solid #2d9e5f;color:#1a6b3c;font-weight:700;background:transparent;}

/* drop zone */
#dropzone{border:2px dashed #2d9e5f;border-radius:10px;padding:30px 20px;
  text-align:center;cursor:pointer;transition:.2s;background:#fff;}
#dropzone:hover,.drag-over{background:#e8f8ef!important;border-color:#1a6b3c!important;}
#dropzone i{font-size:2.6rem;color:#2d9e5f;}

/* paste area */
#pasteArea{font-size:.8rem;resize:vertical;min-height:120px;}

/* column chips */
.chip{display:inline-flex;align-items:center;gap:4px;padding:3px 10px;
  border-radius:20px;font-size:.73rem;font-weight:600;margin:2px;}
.chip-ok{background:#d1fae5;color:#065f46;}
.chip-miss{background:#fee2e2;color:#991b1b;}

/* stat cards */
.sc{border-radius:12px;color:#fff;padding:16px 18px;}
.sc-total{background:linear-gradient(135deg,#2d9e5f,#1a6b3c);}
.sc-ok   {background:linear-gradient(135deg,#198754,#0f5132);}
.sc-fail {background:linear-gradient(135deg,#dc3545,#842029);}
.sc-pend {background:linear-gradient(135deg,#fd7e14,#9c4a00);}
.sc-skip {background:linear-gradient(135deg,#6c757d,#343a40);}
.sc .num{font-size:1.9rem;font-weight:700;line-height:1;}
.sc .lbl{font-size:.77rem;opacity:.85;margin-top:3px;}

/* run button pulse */
@keyframes pulse{0%,100%{box-shadow:0 0 0 0 rgba(45,158,95,.55);}
  50%{box-shadow:0 0 0 12px rgba(45,158,95,0);}}
.btn-ready{animation:pulse 1.5s ease-in-out 5;}
.btn-go{background:#2d9e5f;border:none;font-size:1rem;}
.btn-go:hover{background:#1a6b3c;}
.btn-go:disabled{background:#9ec9b3;cursor:not-allowed;}
.btn-stop{background:#dc3545;border:none;}

/* table */
#recTable{font-size:.85rem;}
#recTable thead th{background:#1a6b3c;color:#fff;position:sticky;top:0;z-index:1;}
.twrap{max-height:350px;overflow-y:auto;border-radius:0 0 12px 12px;}
.bp {background:#fd7e14!important;}
.bpr{background:#0d6efd!important;animation:blink 1s infinite;}
.bs {background:#198754!important;}
.bf {background:#dc3545!important;}
.bsk{background:#6c757d!important;}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.35}}

/* log */
#logBox{background:#1e1e1e;color:#d4d4d4;font-family:'Consolas',monospace;
  font-size:.78rem;border-radius:8px;height:300px;overflow-y:auto;
  padding:10px;white-space:pre-wrap;word-break:break-all;}
.ls{color:#4ec9b0;}.le{color:#f44747;}.lw{color:#dcdcaa;}.li{color:#9cdcfe;}
</style>
</head>
<body>

<nav class="navbar navbar-dark px-4 py-2 mb-3">
  <span class="navbar-brand fw-bold fs-6">
    <i class="bi bi-bank2 me-2"></i>KCC Loan Automation Dashboard
    <span class="badge bg-success ms-2" style="font-size:.65rem;vertical-align:middle;">V3</span>
  </span>
  <span class="text-white-50 small">fasalrin.gov.in &nbsp;|&nbsp;
    <a id="urlLink" href="#" class="text-white-50 text-decoration-none small"></a>
  </span>
</nav>

<div class="container-fluid px-4">

<!-- ── Row 1 : Input + Run ── -->
<div class="row g-3 mb-3">

  <!-- Input card (upload / paste + validation + RUN button all in one place) -->
  <div class="col-lg-5">
    <div class="card h-100">
      <div class="card-header bg-white p-0 border-bottom">
        <ul class="nav nav-tabs px-3 pt-2" id="inputTabs">
          <li class="nav-item">
            <button class="nav-link active" id="tab-file" onclick="switchTab('file')">
              <i class="bi bi-file-earmark-excel-fill text-success me-1"></i>Upload File
            </button>
          </li>
          <li class="nav-item">
            <button class="nav-link" id="tab-paste" onclick="switchTab('paste')">
              <i class="bi bi-clipboard-data text-primary me-1"></i>Paste from Excel
            </button>
          </li>
        </ul>
      </div>
      <div class="card-body d-flex flex-column">

        <!-- File pane -->
        <div id="pane-file">
          <div id="dropzone" onclick="document.getElementById('fileInput').click()">
            <i class="bi bi-cloud-upload-fill" id="dzIcon"></i>
            <p class="mt-2 mb-1 fw-semibold" id="dzText">Drag &amp; Drop or Click to Upload</p>
            <p class="text-muted small mb-0" id="dzSub">Supports .xlsx / .xls</p>
          </div>
          <input type="file" id="fileInput" accept=".xlsx,.xls"
                 class="d-none" onchange="uploadFile(this.files[0])"/>
        </div>

        <!-- Paste pane -->
        <div id="pane-paste" class="d-none">
          <p class="text-muted small mb-2">
            <i class="bi bi-info-circle-fill text-primary me-1"></i>
            In Excel: select all rows <strong>including the header row</strong>
            → <kbd>Ctrl+C</kbd> → click below → <kbd>Ctrl+V</kbd> → click <strong>Load Data</strong>
          </p>
          <textarea id="pasteArea" class="form-control"
            placeholder="Paste Excel data here (Ctrl+V)…"></textarea>
          <button class="btn btn-primary w-100 mt-2 fw-semibold py-2"
                  onclick="loadPaste()">
            <i class="bi bi-check2-circle me-1"></i>Load Data
          </button>
        </div>

        <!-- Validation panel -->
        <div id="validPanel" class="mt-3 d-none">
          <hr class="my-2"/>
          <div class="d-flex align-items-center gap-2 mb-2 flex-wrap">
            <span id="vIcon" class="fs-5"></span>
            <span id="vTitle" class="fw-semibold small"></span>
            <span class="badge bg-secondary ms-auto" id="vRows"></span>
          </div>
          <div id="vChips"></div>
          <div id="vWarn" class="alert alert-warning py-2 px-3 small mt-2 d-none mb-0">
            <i class="bi bi-exclamation-triangle-fill me-1"></i>
            <span id="vWarnMsg"></span>
          </div>
        </div>

        <!-- ── RUN button lives right here, below the file ── -->
        <div class="mt-auto pt-3" id="runArea">
          <button id="btnRun"
                  class="btn btn-go text-white fw-bold w-100 py-3"
                  onclick="startAuto()" disabled
                  style="font-size:1.15rem;letter-spacing:.03em;">
            <i class="bi bi-play-circle-fill me-2"></i>Run Automation
          </button>
          <button id="btnStop"
                  class="btn btn-stop text-white fw-bold w-100 py-3 d-none"
                  onclick="stopAuto()"
                  style="font-size:1.15rem;">
            <i class="bi bi-stop-circle-fill me-2"></i>Stop Automation
          </button>
          <p id="runHint" class="text-muted small text-center mb-0 mt-2">
            <i class="bi bi-arrow-up-circle me-1"></i>Upload or paste data above to enable
          </p>
        </div>

      </div>
    </div>
  </div>

  <!-- Stats cards (right column — numbers only, no button) -->
  <div class="col-lg-7">
    <div class="row g-3">
      <div class="col-6 col-md-4"><div class="sc sc-total h-100">
        <div class="num" id="sT">0</div>
        <div class="lbl"><i class="bi bi-people-fill me-1"></i>Total</div>
      </div></div>
      <div class="col-6 col-md-4"><div class="sc sc-ok h-100">
        <div class="num" id="sS">0</div>
        <div class="lbl"><i class="bi bi-check-circle-fill me-1"></i>Successful</div>
      </div></div>
      <div class="col-6 col-md-4"><div class="sc sc-fail h-100">
        <div class="num" id="sF">0</div>
        <div class="lbl"><i class="bi bi-x-circle-fill me-1"></i>Failed</div>
      </div></div>
      <div class="col-6 col-md-4"><div class="sc sc-pend h-100">
        <div class="num" id="sP">0</div>
        <div class="lbl"><i class="bi bi-clock-fill me-1"></i>Pending</div>
      </div></div>
      <div class="col-6 col-md-4"><div class="sc sc-skip h-100">
        <div class="num" id="sSk">0</div>
        <div class="lbl"><i class="bi bi-skip-forward-fill me-1"></i>Skipped</div>
      </div></div>
      <div class="col-6 col-md-4"><div class="sc h-100" style="background:linear-gradient(135deg,#0d6efd,#084298);">
        <div class="num" id="sFail2">—</div>
        <div class="lbl"><i class="bi bi-activity me-1"></i>Running</div>
      </div></div>
    </div>
  </div>
</div>

<!-- ── Progress ── -->
<div class="mb-3">
  <div class="d-flex justify-content-between small text-muted mb-1">
    <span>Progress</span><span id="progTxt">0 / 0</span>
  </div>
  <div class="progress" style="height:9px;border-radius:8px;">
    <div id="progBar" class="progress-bar bg-success" style="width:0%;transition:width .4s;"></div>
  </div>
</div>

<!-- ── Row 2: Table + Log ── -->
<div class="row g-3 mb-4">
  <div class="col-lg-7">
    <div class="card">
      <div class="card-header bg-white d-flex justify-content-between align-items-center">
        <span><i class="bi bi-table me-2 text-success"></i>Records</span>
        <span class="badge bg-secondary" id="tblCnt">0 rows</span>
      </div>
      <div class="card-body p-0">
        <div class="twrap">
          <table class="table table-hover table-bordered mb-0" id="recTable">
            <thead><tr>
              <th>#</th><th>Beneficiary</th><th>Aadhaar</th>
              <th>Account</th><th>Amount</th><th>Disbursal</th><th>Status</th>
            </tr></thead>
            <tbody id="recBody">
              <tr><td colspan="7" class="text-center text-muted py-5">
                <i class="bi bi-inbox fs-3 d-block mb-2 text-muted"></i>
                Upload a file or paste Excel data to see records
              </td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <div class="col-lg-5">
    <div class="card h-100">
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

</div><!-- /container -->

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
// ── constants ─────────────────────────────────────────────────────────────
const RCOLS = [
  'Aadhar Number',
  'Loan Disbursal Date',
  'Max Withdrawal Amount (INR)'
];
const OCOLS = [
  'Account Number','Loan Repayment Date','Beneficiary Name'
];

// ── URL display ───────────────────────────────────────────────────────────
document.getElementById('urlLink').textContent = window.location.href;
document.getElementById('urlLink').href = window.location.href;

// ── Tab switch ────────────────────────────────────────────────────────────
function switchTab(tab) {
  ['file','paste'].forEach(t => {
    document.getElementById('pane-'+t).classList.toggle('d-none', t !== tab);
    document.getElementById('tab-'+t).classList.toggle('active',  t === tab);
  });
  document.getElementById('validPanel').classList.add('d-none');
}

// ── Drag & drop ───────────────────────────────────────────────────────────
const dz = document.getElementById('dropzone');
dz.addEventListener('dragover',  e => { e.preventDefault(); dz.classList.add('drag-over'); });
dz.addEventListener('dragleave', ()  => dz.classList.remove('drag-over'));
dz.addEventListener('drop', e => {
  e.preventDefault();
  dz.classList.remove('drag-over');
  const f = e.dataTransfer.files[0];
  if (f) uploadFile(f);
});

// ── Upload file ───────────────────────────────────────────────────────────
function uploadFile(file) {
  if (!file) return;
  document.getElementById('dzText').textContent = '⏳ Reading ' + file.name + '…';
  const form = new FormData();
  form.append('file', file);
  fetch('/upload', { method: 'POST', body: form })
    .then(r => r.json())
    .then(d => {
      if (d.error) {
        alert('❌ Upload error:\n' + d.error);
        document.getElementById('dzText').textContent = 'Drag & Drop or Click to Upload';
        return;
      }
      document.getElementById('dzIcon').className = 'bi bi-file-earmark-check-fill text-success';
      document.getElementById('dzText').textContent = '✅ ' + file.name;
      document.getElementById('dzSub').textContent  = d.rows + ' records loaded — click to change';
      applyResult(d, '📂 ' + file.name);
    })
    .catch(e => alert('Upload failed: ' + e));
}

// ── Paste from Excel ──────────────────────────────────────────────────────
function loadPaste() {
  const raw = document.getElementById('pasteArea').value.trim();
  if (!raw) {
    alert('Please paste Excel data first.\n\nIn Excel: select rows including header → Ctrl+C → click in the text area → Ctrl+V → click Load Data.');
    return;
  }
  fetch('/paste', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ data: raw })
  })
    .then(r => r.json())
    .then(d => {
      if (d.error) { alert('❌ Parse error:\n' + d.error); return; }
      applyResult(d, '📋 Pasted data');
    })
    .catch(e => alert('Paste failed: ' + e));
}

// ── After successful load ─────────────────────────────────────────────────
function applyResult(d, label) {
  showValidation(d, label);
  renderTable(d.records);
  updateSummary(d.summary);
}

// ── Validation display ────────────────────────────────────────────────────
function showValidation(d, label) {
  const found = d.columns_found   || [];
  const miss  = d.columns_missing || [];
  document.getElementById('validPanel').classList.remove('d-none');
  document.getElementById('vRows').textContent = (d.rows || 0) + ' records';
  // Required columns (green=found, red=missing)
  const reqChips = RCOLS.map(c => {
    const ok = found.includes(c);
    return `<span class="chip ${ok ? 'chip-ok' : 'chip-miss'}">
      <i class="bi bi-${ok ? 'check-circle-fill' : 'x-circle-fill'}"></i>${c}</span>`;
  });
  // Optional columns (green=found, grey=not present — no error)
  const optChips = OCOLS.map(c => {
    const ok = found.includes(c);
    return ok ? `<span class="chip chip-ok">
      <i class="bi bi-check-circle-fill"></i>${c}</span>` : '';
  });
  document.getElementById('vChips').innerHTML = reqChips.join('') + optChips.join('');
  if (miss.length === 0) {
    document.getElementById('vIcon').textContent  = '✅';
    document.getElementById('vTitle').textContent = label + ' — Format OK!';
    document.getElementById('vWarn').classList.add('d-none');
    enableRunButton(d.rows);
  } else {
    document.getElementById('vIcon').textContent  = '⚠️';
    document.getElementById('vTitle').textContent = label + ' — Missing columns';
    document.getElementById('vWarn').classList.remove('d-none');
    document.getElementById('vWarnMsg').textContent = 'Missing: ' + miss.join(', ');
    // Still enable button (missing cols are non-fatal, script will handle them)
    enableRunButton(d.rows);
  }
}

function enableRunButton(rows) {
  const btn = document.getElementById('btnRun');
  btn.disabled = false;
  btn.innerHTML = '<i class="bi bi-play-circle-fill me-2"></i>▶  Run Automation  (' + (rows || 0) + ' records)';
  btn.classList.add('btn-ready');
  document.getElementById('runHint').innerHTML =
    '<i class="bi bi-check-circle-fill text-success me-1"></i>' +
    (rows || 0) + ' records ready &mdash; click the button above to start';
  document.getElementById('sFail2').textContent = 'Ready';
  setTimeout(() => btn.classList.remove('btn-ready'), 8000);
}

// ── Table ─────────────────────────────────────────────────────────────────
function renderTable(recs) {
  if (!recs || !recs.length) return;
  document.getElementById('tblCnt').textContent = recs.length + ' rows';
  document.getElementById('recBody').innerHTML = recs.map((r, i) => `
    <tr id="rw${i}">
      <td class="text-muted fw-bold">${i + 1}</td>
      <td>${r.name || '—'}</td>
      <td class="font-monospace small">${r.aadhaar || '—'}</td>
      <td>${r.account || '—'}</td>
      <td>${r.amount ? '₹' + Number(r.amount).toLocaleString('en-IN') : '—'}</td>
      <td>${r.disbursal || '—'}</td>
      <td id="st${i}"><span class="badge bp">Pending</span></td>
    </tr>`).join('');
}

function setRowStatus(i, s) {
  const el = document.getElementById('st' + i);
  if (!el) return;
  const map = {
    pending:    'bp Pending',
    processing: 'bpr Processing…',
    success:    'bs ✅ Done',
    failed:     'bf ❌ Failed',
    skipped:    'bsk ⏭ Skipped'
  };
  const [cls, ...rest] = (map[s] || 'bp ' + s).split(' ');
  el.innerHTML = `<span class="badge ${cls}">${rest.join(' ')}</span>`;
  if (s === 'processing')
    document.getElementById('rw' + i)
      ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Summary ───────────────────────────────────────────────────────────────
function updateSummary(s) {
  if (!s) return;
  document.getElementById('sT').textContent  = s.total   || 0;
  document.getElementById('sS').textContent  = s.success || 0;
  document.getElementById('sF').textContent  = s.failed  || 0;
  document.getElementById('sP').textContent  = s.pending || 0;
  document.getElementById('sSk').textContent = s.skipped || 0;
  const done  = (s.success || 0) + (s.failed || 0) + (s.skipped || 0);
  const total = Math.max(s.total || 1, 1);
  document.getElementById('progBar').style.width = Math.round(done / total * 100) + '%';
  document.getElementById('progTxt').textContent = done + ' / ' + total;
}

// ── Log ───────────────────────────────────────────────────────────────────
let autoScroll = true;
const lb = document.getElementById('logBox');
lb.addEventListener('scroll', () => {
  autoScroll = lb.scrollTop + lb.clientHeight >= lb.scrollHeight - 30;
});
function appendLog(t) {
  const s = document.createElement('span');
  t = t || '';
  if      (/saved successfully|✅|✓|Selected '/.test(t))                  s.className = 'ls';
  else if (/ERROR on record|❌|Fatal|Browser connection lost/.test(t))     s.className = 'le';
  else if (/SKIPPED record/.test(t))                                        s.className = 'bsk'; // grey
  else if (/WARNING|⚠|manually|auto-continuing|auto-select failed/.test(t))s.className = 'lw';
  else if (/Record \d+\/\d+|─|RESIDENTIAL|Financial|Activity|PROCESSING/.test(t)) s.className = 'li';
  s.textContent = t + '\n';
  lb.appendChild(s);
  if (autoScroll) lb.scrollTop = lb.scrollHeight;
}
function clearLog() { lb.innerHTML = ''; }

// ── SSE stream ────────────────────────────────────────────────────────────
let es = null;
function startStream() {
  if (es) es.close();
  es = new EventSource('/stream');
  es.onmessage = e => {
    try {
      const d = JSON.parse(e.data);
      if (d.type === 'log')     appendLog(d.text);
      if (d.type === 'status')  setRowStatus(d.idx, d.status);
      if (d.type === 'summary') updateSummary(d.summary);
      if (d.type === 'done') {
        appendLog('\n══ Automation finished ══\n');
        const btn = document.getElementById('btnRun');
        btn.disabled = false;
        btn.classList.remove('d-none');
        document.getElementById('btnStop').classList.add('d-none');
        document.getElementById('runHint').innerHTML =
          '<i class="bi bi-check2-all text-success me-1"></i>Finished — click above to run again';
        document.getElementById('sFail2').textContent = 'Done';
        if (es) { es.close(); es = null; }
      }
    } catch(err) {}
  };
  es.onerror = () => { /* reconnect silently */ };
}

// ── Start / Stop ──────────────────────────────────────────────────────────
function startAuto() {
  clearLog();
  appendLog('🚀 Starting automation…\n');
  const btn  = document.getElementById('btnRun');
  const stop = document.getElementById('btnStop');
  btn.classList.add('d-none');
  stop.classList.remove('d-none');
  document.getElementById('runHint').innerHTML =
    '<i class="bi bi-hourglass-split me-1 text-warning"></i>Running — do not close this window';
  document.getElementById('sFail2').textContent = '●';
  fetch('/start', { method: 'POST' })
    .then(r => r.json())
    .then(d => {
      if (d.error) {
        alert('❌ ' + d.error);
        btn.disabled = false;
        btn.classList.remove('d-none');
        stop.classList.add('d-none');
        document.getElementById('runHint').innerHTML =
          '<i class="bi bi-exclamation-triangle-fill text-danger me-1"></i>' + d.error;
        return;
      }
      startStream();
    })
    .catch(e => {
      alert('Start failed: ' + e);
      btn.disabled = false;
      btn.classList.remove('d-none');
      stop.classList.add('d-none');
    });
}

function stopAuto() {
  if (!confirm('Stop the automation?')) return;
  fetch('/stop', { method: 'POST' }).then(() => {
    appendLog('\n⛔ Stopped by user.\n');
    document.getElementById('btnStop').classList.add('d-none');
    const btn = document.getElementById('btnRun');
    btn.disabled = false;
    btn.classList.remove('d-none');
    document.getElementById('runHint').innerHTML =
      '<i class="bi bi-stop-circle text-danger me-1"></i>Stopped — click above to run again';
    document.getElementById('sFail2').textContent = 'Stopped';
  });
}
</script>
</body>
</html>
"""

# ─── Helpers ─────────────────────────────────────────────────────────────────
def mask_aadhaar(a):
    s = str(a).replace(".0", "").strip()
    return "*" * (len(s) - 4) + s[-4:] if len(s) > 4 else s


def build_summary():
    st = state["statuses"]
    total = len(state["records"])
    ok  = sum(1 for v in st.values() if v == "success")
    fl  = sum(1 for v in st.values() if v == "failed")
    sk  = sum(1 for v in st.values() if v == "skipped")
    s = {"total": total, "success": ok, "failed": fl,
         "skipped": sk, "pending": max(total - ok - fl - sk, 0)}
    state["summary"] = s
    return s


def parse_df_to_records(df):
    cm = {
        "Aadhar Number":           "AadhaarNumber",
        "Account Number":          "AccountNumber",
        "Loan Disbursal Date":     "DisbursementDate",
        "Loan Repayment Date":     "RepaymentDate",
        "Max Withdrawal Amount (INR)": "LoanAmount",
        "Beneficiary Name":        "BeneficiaryName",
    }
    df2 = df.rename(columns={k: v for k, v in cm.items() if k in df.columns})
    recs = []
    for _, row in df2.iterrows():
        aad = str(row.get("AadhaarNumber", "")).replace(".0", "").strip()
        amt = ""
        try:
            raw = row.get("LoanAmount", "")
            if raw not in ("", "nan", None):
                amt = str(int(float(str(raw))))
        except:
            pass
        disb = row.get("DisbursementDate", "")
        if hasattr(disb, "strftime"):
            disb = disb.strftime("%d/%m/%Y")
        recs.append({
            "name":     str(row.get("BeneficiaryName", "")).strip() or "—",
            "aadhaar":  mask_aadhaar(aad) if aad else "—",
            "account":  str(row.get("AccountNumber", "")).replace(".0", "").strip() or "—",
            "amount":   amt,
            "disbursal": str(disb) if disb not in ("", "nan") else "—",
        })
    return recs


def validate_cols(df):
    all_known = REQUIRED_COLUMNS + OPTIONAL_COLUMNS
    found   = [c for c in all_known if c in df.columns]
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]  # only required matter
    return found, missing


def init_state_from_df(df):
    # Always write to a brand-new temp file in the OS temp directory.
    # This is guaranteed to never conflict with any Excel-locked file.
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".xlsx", prefix="kcc_loans_")
    os.close(tmp_fd)                          # close the raw fd; openpyxl will reopen
    df.to_excel(tmp_path, index=False, engine="openpyxl")

    # Clean up previous temp file if any
    old = state.get("save_path")
    if old and old != tmp_path:
        try: os.remove(old)
        except: pass

    state["save_path"] = tmp_path
    state["records"]   = parse_df_to_records(df)
    state["statuses"]  = {i: "pending" for i in range(len(state["records"]))}
    return build_summary()


# ─── Routes ──────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(HTML)


@app.route("/upload", methods=["POST"])
def upload():
    f = request.files.get("file")
    if not f:
        return jsonify({"error": "No file provided"})
    try:
        df = pd.read_excel(f, engine="openpyxl")
        found, missing = validate_cols(df)
        summary = init_state_from_df(df)
        return jsonify({
            "rows": len(df),
            "records": state["records"],
            "summary": summary,
            "columns_found": found,
            "columns_missing": missing,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/paste", methods=["POST"])
def paste():
    try:
        body = request.get_json(force=True) or {}
        raw  = (body.get("data") or "").strip()
        if not raw:
            return jsonify({"error": "No data received — paste Excel rows including header"})

        # TSV parse (Excel Ctrl+C produces tab-separated values)
        df = pd.read_csv(io.StringIO(raw), sep="\t", dtype=str,
                         engine="python").fillna("")

        # Try numeric conversion per column (non-destructive)
        for col in df.columns:
            try:
                converted = pd.to_numeric(df[col], errors="coerce")
                if converted.notna().mean() > 0.5:   # >50 % numeric → convert
                    df[col] = converted.where(converted.notna(), df[col])
            except:
                pass

        found, missing = validate_cols(df)
        summary = init_state_from_df(df)
        return jsonify({
            "rows": len(df),
            "records": state["records"],
            "summary": summary,
            "columns_found": found,
            "columns_missing": missing,
        })
    except Exception as e:
        return jsonify({"error": str(e)})


@app.route("/start", methods=["POST"])
def start():
    if state["running"]:
        return jsonify({"error": "Already running — stop first"})
    if not state["records"]:
        return jsonify({"error": "No data loaded — upload a file or paste data first"})
    if not os.path.exists(SCRIPT_PATH):
        return jsonify({"error": f"Script not found: {SCRIPT_PATH}"})

    state["statuses"] = {i: "pending" for i in range(len(state["records"]))}
    state["running"]  = True

    # Flush log queue
    while not state["log_queue"].empty():
        try: state["log_queue"].get_nowait()
        except: pass

    def _run():
        try:
            proc = subprocess.Popen(
                [sys.executable, "-u", SCRIPT_PATH, state.get("save_path", UPLOAD_PATH)],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=BASE_DIR,
            )
            state["process"] = proc
            cur = [0]
            for line in iter(proc.stdout.readline, ""):
                line = line.rstrip()
                if not line:
                    continue
                state["log_queue"].put(json.dumps({"type": "log", "text": line}))

                # ── V3 log patterns ──────────────────────────────────────────
                # Record header:  "  Record 2/10  |  MALAPPA MADHAPPA HUDEDAR"
                m = re.search(r'Record\s+(\d+)/\d+', line)
                if m:
                    try:
                        idx = int(m.group(1)) - 1
                        cur[0] = idx
                        state["statuses"][idx] = "processing"
                        state["log_queue"].put(json.dumps({"type": "status", "idx": idx, "status": "processing"}))
                        state["log_queue"].put(json.dumps({"type": "summary", "summary": build_summary()}))
                    except:
                        pass

                # Success:  "  Record 2 saved successfully!"
                if "saved successfully" in line or "SUBMITTED" in line:
                    state["statuses"][cur[0]] = "success"
                    state["log_queue"].put(json.dumps({"type": "status", "idx": cur[0], "status": "success"}))
                    state["log_queue"].put(json.dumps({"type": "summary", "summary": build_summary()}))

                # Skipped:  "  SKIPPED record 2: Aadhaar …"
                ms = re.search(r'SKIPPED record\s+(\d+)', line)
                if ms:
                    try:
                        sidx = int(ms.group(1)) - 1
                        state["statuses"][sidx] = "skipped"
                        state["log_queue"].put(json.dumps({"type": "status", "idx": sidx, "status": "skipped"}))
                        state["log_queue"].put(json.dumps({"type": "summary", "summary": build_summary()}))
                    except:
                        pass

                # Error:    "  ERROR on record 2: …"
                me = re.search(r'ERROR on record\s+(\d+)', line)
                if me:
                    try:
                        eidx = int(me.group(1)) - 1
                        state["statuses"][eidx] = "failed"
                        state["log_queue"].put(json.dumps({"type": "status", "idx": eidx, "status": "failed"}))
                        state["log_queue"].put(json.dumps({"type": "summary", "summary": build_summary()}))
                    except:
                        pass
            proc.wait()
        except Exception as e:
            state["log_queue"].put(json.dumps({"type": "log", "text": f"❌ Runner error: {e}"}))
        finally:
            state["running"] = False
            state["process"] = None
            state["log_queue"].put(json.dumps({"type": "done"}))

    threading.Thread(target=_run, daemon=True).start()
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


# ─── Entry point ─────────────────────────────────────────────────────────────
def _find_free_port(start=5000, tries=5):
    for p in range(start, start + tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    return start


def _get_local_ip():
    """Return the LAN IP of this machine (e.g. 192.168.x.x)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except:
        return "127.0.0.1"


def _get_cloudflared_exe():
    """
    Return path to cloudflared.exe — auto-download on first run if missing.
    If download is blocked by firewall, user can manually place the file in the PRI folder.
    """
    import urllib.request, stat
    exe = os.path.join(BASE_DIR, "cloudflared.exe")
    if os.path.exists(exe):
        return exe

    print("  ⏳  Downloading cloudflared.exe (one-time, ~35 MB) ...")
    urls = [
        "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe",
        "https://objects.githubusercontent.com/github-production-release-asset-2e65be/232609078/cloudflared-windows-amd64.exe",
    ]
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler())
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    urllib.request.install_opener(opener)

    for url in urls:
        try:
            urllib.request.urlretrieve(url, exe)
            if os.path.getsize(exe) > 1_000_000:   # must be > 1 MB to be valid
                os.chmod(exe, os.stat(exe).st_mode | stat.S_IEXEC)
                print("  ✅  cloudflared.exe downloaded")
                return exe
        except Exception as e:
            print(f"  ⚠  Download attempt failed: {e}")

    # Clean up partial download
    try: os.remove(exe)
    except: pass

    print()
    print("  ⚠  Auto-download blocked by network/firewall.")
    print("  👉  Manual fix — download this file on your MOBILE and transfer to PC:")
    print("      https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe")
    print(f"      Save it as:  {exe}")
    print("      Then restart dashboard.py")
    print()
    return None


def _start_cloudflared(port):
    """Cloudflare Quick Tunnel — most reliable free public tunnel."""
    exe = _get_cloudflared_exe()
    if not exe:
        return None
    result = {"url": None}

    def _run():
        try:
            proc = subprocess.Popen(
                [exe, "tunnel", "--url", f"http://localhost:{port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            state["tunnel_proc"] = proc
            for line in proc.stdout:
                m = re.search(r'https://[\w\-]+\.trycloudflare\.com', line)
                if m:
                    result["url"] = m.group(0)
                    return
        except Exception as e:
            print(f"  ⚠  cloudflared error: {e}")

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    t.join(timeout=30)
    return result["url"]


def _start_ngrok(port):
    """ngrok tunnel — uses static domain + auth token if configured."""
    try:
        from pyngrok import ngrok as _ngrok, conf as _conf
        if NGROK_AUTH_TOKEN:
            _conf.get_default().auth_token = NGROK_AUTH_TOKEN
        if NGROK_STATIC_DOMAIN:
            tunnel = _ngrok.connect(port, "http", hostname=NGROK_STATIC_DOMAIN)
        else:
            tunnel = _ngrok.connect(port, "http")
        return tunnel.public_url
    except ImportError:
        print("  ⚠  pyngrok not installed — run:  pip install pyngrok")
        return None
    except Exception as e:
        print(f"  ⚠  ngrok error: {e}")
        return None


if __name__ == "__main__":
    PORT     = _find_free_port(5000)
    LOCAL_IP = _get_local_ip()

    LOCAL_URL = f"http://localhost:{PORT}"
    LAN_URL   = f"http://{LOCAL_IP}:{PORT}"

    # ── 1. ngrok with static domain (permanent URL — configure above) ─────────
    if NGROK_AUTH_TOKEN and NGROK_STATIC_DOMAIN:
        print()
        print(f"  ⏳  Starting ngrok tunnel  →  https://{NGROK_STATIC_DOMAIN} ...")
        PUBLIC_URL = _start_ngrok(PORT)
    else:
        PUBLIC_URL = None

    # ── 2. Cloudflare Quick Tunnel (auto-downloads exe, random URL) ───────────
    if not PUBLIC_URL:
        print()
        print("  ⏳  Starting Cloudflare tunnel ...")
        PUBLIC_URL = _start_cloudflared(PORT)

    # ── 3. Last resort: ngrok without static domain ───────────────────────────
    if not PUBLIC_URL and NGROK_AUTH_TOKEN:
        print("  ⚠  Cloudflare failed — trying ngrok ...")
        PUBLIC_URL = _start_ngrok(PORT)

    print()
    print("=" * 68)
    print("  ✅  KCC LOAN AUTOMATION DASHBOARD  —  V3")
    print("=" * 68)
    print(f"  💻  This PC only      →  {LOCAL_URL}")
    print(f"  📡  Same WiFi / LAN   →  {LAN_URL}")
    if PUBLIC_URL:
        print(f"  🌍  Mobile / any net  →  {PUBLIC_URL}")
        print()
        print(f"       ↑  Open this on any phone or laptop — bookmark it!")
    else:
        print()
        print("  🌍  Tunnel failed. Check internet connection and restart.")
    print()
    print("  • Keep this terminal open while others are using the dashboard")
    print("  • Press Ctrl+C to stop")
    print("=" * 68)
    print()

    def _open():
        time.sleep(2)
        try:
            webbrowser.open(LOCAL_URL)
        except:
            pass

    threading.Thread(target=_open, daemon=True).start()

    # Bind to 0.0.0.0 so LAN + tunnel traffic can reach Flask
    app.run(debug=False, host="0.0.0.0", port=PORT, threaded=True)

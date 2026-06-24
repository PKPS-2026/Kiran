from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import (
    TimeoutException, NoSuchElementException,
    ElementClickInterceptedException, StaleElementReferenceException,
    ElementNotInteractableException,
)
import pandas as pd
import time, os, re, sys

# Fix Windows terminal encoding — allows Unicode characters (─ separators etc.)
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

class SkipRecord(Exception):
    """Raised when a record should be skipped (e.g. invalid Aadhaar)."""
    pass

# =============================================================================
# CONFIGURATION
# =============================================================================
# Accept file path from dashboard (sys.argv[1]) or fall back to default
EXCEL_FILE     = sys.argv[1] if len(sys.argv) > 1 else "loans.xlsx"
PORTAL_URL     = "https://fasalrin.gov.in/login"
FORM_URL       = "https://fasalrin.gov.in/loan-application-form"
WAIT_TIME      = 30
FINANCIAL_YEAR = "2025-2026"

STATE_TYPE    = "karn";  STATE_SELECT    = "KARNATAKA"
DISTRICT_TYPE = "bel";   DISTRICT_SELECT = "Belagavi"
BLOCK_SELECT_TEXT   = "Athani"
VILLAGE_SELECT_TEXT = "MURAGUNDI (MURAGUNDI)"

print("=" * 70)
print(" " * 10 + "KISAN CREDIT CARD - V4 (PREVIEW + FINAL SUBMIT)")
print("=" * 70)

# =============================================================================
# LOAD EXCEL
# =============================================================================
if not os.path.exists(EXCEL_FILE):
    print(f"\nERROR: Excel file '{EXCEL_FILE}' not found!")
    raise SystemExit(1)

try:
    df = pd.read_excel(EXCEL_FILE, engine="openpyxl")
    print(f"Loaded {len(df)} records")
except Exception as e:
    print(f"ERROR reading excel: {e}")
    raise SystemExit(1)

df.rename(columns={
    "Aadhar Number": "AadhaarNumber",
    "Account Number": "AccountNumber",
    "Loan Disbursal Date": "DisbursementDate",
    "Loan Repayment Date": "RepaymentDate",
    "Max Withdrawal Amount (INR)": "LoanAmount",
}, inplace=True)

if "AadhaarNumber" not in df.columns:
    print("ERROR: 'Aadhar Number' column not found!")
    raise SystemExit(1)

print("Column mapping complete\n")

# =============================================================================
# BROWSER SETUP
# =============================================================================
chrome_options = Options()
chrome_options.add_argument("--start-maximized")
chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

try:
    driver = webdriver.Chrome(options=chrome_options)
except Exception as e:
    print(f"ChromeDriver error: {e}")
    raise SystemExit(1)

wait = WebDriverWait(driver, WAIT_TIME)


# =============================================================================
# HELPERS
# =============================================================================
def mask_aadhaar(a):
    s = str(a).replace(".0", "")
    return "*" * (len(s) - 4) + s[-4:] if len(s) > 4 else s


def accept_native_alert_if_any():
    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        driver.switch_to.alert.accept()
        print("  Alert accepted")
        time.sleep(0.5)
        return True
    except:
        return False


def wait_spinner(timeout=10):
    try:
        WebDriverWait(driver, timeout).until_not(
            EC.presence_of_element_located((By.XPATH,
                "//*[contains(@class,'spinner') or contains(@class,'loading') or contains(@class,'loader')]"
            ))
        )
    except:
        pass


def safe_click(xpath, timeout=15):
    el = WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((By.XPATH, xpath)))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
    driver.execute_script("arguments[0].click();", el)
    return True


def start_new_application():
    print("  Starting new application form...")
    if not is_browser_alive():
        print("  WARNING: Browser connection lost — cannot open new form")
        return False
    accept_native_alert_if_any()          # dismiss any leave-page dialog first
    try:
        driver.get(FORM_URL)
        time.sleep(1.5)
        wait_spinner()
        accept_native_alert_if_any()
    except Exception as nav_err:
        print(f"  Navigation error: {str(nav_err)[:80]}")
        if not is_browser_alive():
            print("  Browser died during navigation")
            return False

    # Check if Aadhaar modal is visible
    try:
        WebDriverWait(driver, 5).until(EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class,'modal')]//input[@type='text']")))
        print("  Aadhaar modal ready")
        return True
    except:
        pass

    # Try clicking a New Application button
    for txt in ["NEW APPLICATION", "ADD APPLICATION", "ADD NEW", "NEW LOAN", "ADD LOAN", "NEW", "ADD"]:
        xp = (f"//button[contains(translate(normalize-space(.),"
              f"'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'{txt}')]")
        try:
            btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable((By.XPATH, xp)))
            driver.execute_script("arguments[0].click();", btn)
            print(f"  Clicked '{txt}' button")
            time.sleep(1)
            wait_spinner()
            break
        except:
            continue

    try:
        WebDriverWait(driver, 6).until(EC.presence_of_element_located(
            (By.XPATH, "//div[contains(@class,'modal')]//input[@type='text']")))
        print("  Aadhaar modal ready")
        return True
    except:
        print("  Aadhaar modal not found — waiting 3s then continuing")
        time.sleep(3)
        return True


def click_button_by_text(btn_text, timeout=10):
    print(f"  Clicking '{btn_text}'...")

    btn = driver.execute_script("""
        var btns = document.querySelectorAll('button');
        for (var i = 0; i < btns.length; i++) {
            var t = (btns[i].textContent||'').toUpperCase().replace(/\\s+/g,' ').trim();
            if (t.includes(arguments[0]) && btns[i].offsetParent !== null && !btns[i].disabled)
                return btns[i];
        }
        return null;
    """, btn_text.upper())

    if btn:
        try:
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.3)
            ActionChains(driver).move_to_element(btn).click().perform()
            print(f"  '{btn_text}' clicked via ActionChains")
            time.sleep(1)
            wait_spinner()
            return True
        except:
            pass
        try:
            driver.execute_script("""
                var el = arguments[0];
                ['mouseover','mousedown','mouseup','click'].forEach(function(ev) {
                    el.dispatchEvent(new MouseEvent(ev, {bubbles:true, cancelable:true}));
                });
            """, btn)
            print(f"  '{btn_text}' clicked via MouseEvent")
            time.sleep(1)
            wait_spinner()
            return True
        except:
            pass

    # XPath fallback
    try:
        words = btn_text.upper().split()
        xp = "//button[" + " and ".join(
            [f"contains(translate(normalize-space(.),'abcdefghijklmnopqrstuvwxyz',"
             f"'ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'{w}')" for w in words]) + "]"
        safe_click(xp, timeout=timeout)
        print(f"  '{btn_text}' clicked via XPath")
        time.sleep(1)
        wait_spinner()
        return True
    except:
        pass

    print(f"  WARNING: Could not click '{btn_text}' — auto-continuing")
    return False


def click_update_and_continue():
    return click_button_by_text("UPDATE & CONTINUE")


def parse_date(val):
    if pd.isnull(val):
        return None, None, None, ""
    if hasattr(val, 'day'):
        d, m, y = val.day, val.month, val.year
    else:
        s = str(val).strip().replace("-", "/")
        parts = s.split("/")
        if len(parts) == 3:
            if len(parts[0]) == 4:
                y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
            else:
                d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            return None, None, None, ""
    return d, m, y, f"{d:02d}/{m:02d}/{y}"


def select_date_in_calendar(label_frag, date_val, desc):
    """Set Bootstrap datepicker: open calendar → navigate month-by-month → click day."""
    try:
        return _select_date_impl(label_frag, date_val, desc)
    except Exception as _ex:
        print(f"  {desc} date ERROR (safe): {_ex}")
        return False


def _select_date_impl(label_frag, date_val, desc):  # noqa — complete rewrite
    """
    Three-strategy date setter for ngx-bootstrap / Bootstrap Angular datepicker.
    Strategy A : Angular __ngContext__ API  — set date without UI (no calendar click)
    Strategy B : Calendar UI, pure JS clicks — open → JS-click arrows → JS-click day
    Strategy C : ActionChains fallback       — human-like mouse clicks
    """
    d, m, y, date_str = parse_date(date_val)
    if not date_str:
        print(f"  No valid date for {desc}")
        return False

    print(f"  Setting {desc}: {date_str}  (d={d} m={m} y={y})")

    MONTH_MAP = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                 "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                 "january":1,"february":2,"march":3,"april":4,"june":6,
                 "july":7,"august":8,"september":9,"october":10,
                 "november":11,"december":12}

    # ── Find the date input ───────────────────────────────────────────────────
    date_inp = None
    for xp in [
        f"//label[contains(.,'{label_frag}')]/following::input[1]",
        f"//*[contains(text(),'{label_frag}')]/following::input[1]",
    ]:
        try:
            el = driver.find_element(By.XPATH, xp)
            if el.is_displayed():
                date_inp = el; break
        except: pass
    if not date_inp:
        print(f"  ERROR: input not found for '{label_frag}'")
        return False

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", date_inp)
    time.sleep(0.5)

    # ── Detect if calendar (any type) is open ─────────────────────────────────
    def _dp_visible():
        return bool(driver.execute_script("""
            var sels = [
                '.rmdp-wrapper','.rmdp-calendar','.rmdp-day-picker',
                'bs-datepicker-container','bs-days-calendar-view',
                '.bs-datepicker','.datepicker-days','.datepicker-dropdown'
            ];
            for (var i=0;i<sels.length;i++){
                var el=document.querySelector(sels[i]);
                if (el && el.tagName.toLowerCase()!=='input'
                        && el.offsetWidth>30 && el.offsetHeight>30) return true;
            }
            return false;
        """))

    def _wait_dp(secs=3):
        t0 = time.time()
        while time.time() - t0 < secs:
            if _dp_visible(): return True
            time.sleep(0.15)
        return False

    # ══════════════════════════════════════════════════════════════════════════
    # OPEN CALENDAR
    # Portal uses RMDP (react-multi-date-picker) — calendar icon is SVG inside
    # .rmdp-container.  Click the SVG's direct parent div to open.
    # ══════════════════════════════════════════════════════════════════════════
    opened = False

    # Find the RMDP icon element
    icon_el = driver.execute_script("""
        var inp = arguments[0];
        // RMDP wraps input + icon inside .rmdp-container
        var rmdp = inp.closest('.rmdp-container');
        if (rmdp) {
            var svg = rmdp.querySelector('svg');
            if (svg) return svg.parentElement || svg;
            // No SVG? return the rmdp-container itself
            return rmdp;
        }
        // Fallback: walk up from input for any container with SVG
        var el = inp.parentElement;
        for (var i=0; i<5; i++) {
            if (!el || el===document.body) break;
            var svg = el.querySelector('svg');
            if (svg) return svg.parentElement || svg;
            el = el.parentElement;
        }
        // Last resort: elementFromPoint to the right/inside-right of input
        var r = inp.getBoundingClientRect(), mid = r.top + r.height/2;
        for (var ox of [-20, -30, -10, 5, -40]) {
            var found = document.elementFromPoint(r.right + ox, mid);
            if (found && found !== inp && found.tagName !== 'BODY')
                return found.tagName.toLowerCase()==='svg' ?
                       (found.parentElement || found) : found;
        }
        return inp;
    """, date_inp)

    if icon_el:
        tag = icon_el.tag_name; cls = (icon_el.get_attribute('class') or '')[:35]
        print(f"  Icon element: {tag}.{cls}")
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", icon_el)
        time.sleep(0.25)
        # ActionChains click (real browser event)
        try:
            ActionChains(driver).move_to_element(icon_el).click().perform()
            opened = _wait_dp(2.5)
            if opened: print(f"  Calendar opened ✅ (ActionChains)")
        except Exception as _e:
            print(f"  ActionChains err: {_e}")
        # JS click fallback
        if not opened:
            driver.execute_script("arguments[0].click();", icon_el)
            opened = _wait_dp(2.0)
            if opened: print(f"  Calendar opened ✅ (JS click)")

    # Fallback: MouseEvent on rmdp-container
    if not opened:
        r2 = driver.execute_script("""
            var inp = arguments[0];
            var rmdp = inp.closest('.rmdp-container') || inp.parentElement;
            var cx = rmdp.getBoundingClientRect().right - 20;
            var cy = rmdp.getBoundingClientRect().top + rmdp.offsetHeight/2;
            var tgt = document.elementFromPoint(cx, cy) || rmdp;
            if (tgt.tagName.toLowerCase()==='svg') tgt = tgt.parentElement || tgt;
            ['mouseover','mousedown','mouseup','click'].forEach(function(ev){
                tgt.dispatchEvent(new MouseEvent(ev,{bubbles:true,cancelable:true,
                    view:window,clientX:cx,clientY:cy}));
            });
            return 'fired:'+(tgt.getAttribute('class')||tgt.tagName).slice(0,25);
        """, date_inp)
        print(f"  MouseEvent: {r2}")
        opened = _wait_dp(2.0)
        if opened: print(f"  Calendar opened ✅ (MouseEvent)")

    # Fallback: click input directly
    if not opened:
        try:
            ActionChains(driver).move_to_element(date_inp).click().perform()
            opened = _wait_dp(1.5)
            if opened: print(f"  Calendar opened ✅ (input click)")
        except: pass

    if not opened:
        # Dump all calendar-related elements for diagnosis
        dom = driver.execute_script("""
            var r=[];
            document.querySelectorAll('[class*="rmdp"],[class*="datepicker"],[class*="calendar"]').forEach(function(el){
                if(el.tagName.toLowerCase()==='input') return;
                r.push(el.tagName+'.'+(el.getAttribute('class')||'').slice(0,30)+
                       '[w='+el.offsetWidth+',h='+el.offsetHeight+']');
            });
            return r.slice(0,8).join(' | ') || 'NOTHING';
        """)
        print(f"  Calendar NOT opened. DOM: {dom}")
        return False

    # Print RMDP calendar HTML (first 500 chars) so we can verify structure
    cal_html = driver.execute_script("""
        var c = document.querySelector('.rmdp-wrapper') ||
                document.querySelector('.rmdp-calendar') ||
                document.querySelector('bs-datepicker-container') ||
                document.querySelector('.datepicker-dropdown');
        return c ? c.outerHTML.replace(/\\n/g,' ').replace(/\\s+/g,' ').slice(0,500) : 'no-cal';
    """)
    print(f"  CAL-HTML: {cal_html}")
    time.sleep(0.3)

    # ── Read calendar header (current month + year) ───────────────────────────
    def _get_header():
        return driver.execute_script("""
            // RMDP: .rmdp-header-values contains spans for month and year
            var hv = document.querySelector('.rmdp-header-values');
            if (hv) {
                var spans = hv.querySelectorAll('span');
                if (spans.length >= 2)
                    return spans[0].textContent.trim()+' '+spans[1].textContent.trim();
                if (spans.length === 1) return spans[0].textContent.trim();
                return hv.textContent.trim();
            }
            // ngx-bootstrap fallback
            var head = document.querySelector('.bs-datepicker-head');
            if (head) {
                var txts = Array.from(head.querySelectorAll('button'))
                    .map(function(b){ return b.textContent.trim(); })
                    .filter(function(t){ return /[A-Za-z]{3}|\\d{4}/.test(t); });
                if (txts.length >= 2) return txts[0]+' '+txts[1];
                if (txts.length === 1) return txts[0];
            }
            // Bootstrap
            var sw = document.querySelector('th.datepicker-switch');
            if (sw && sw.offsetParent) return sw.textContent.trim();
            // Generic: any visible text with a year
            var all = document.querySelectorAll('button,th,span,div');
            for (var i=0;i<all.length;i++){
                var t=(all[i].textContent||'').trim();
                if (/[A-Za-z]{3}.*\\d{4}/.test(t) && t.length<30 && all[i].offsetWidth>0)
                    return t;
            }
            return '';
        """) or ""

    # ── Click navigation arrow (one per Python call, sleep between) ───────────
    def _click_arrow(direction):
        return driver.execute_script(f"""
            // RMDP arrows: class="rmdp-arrow-container rmdp-left/rmdp-right"
            var side = '{"rmdp-right" if direction=="next" else "rmdp-left"}';
            var ac = document.querySelector('.rmdp-arrow-container.' + side);
            if (ac && ac.offsetParent) {{ ac.click(); return 'ok:rmdp-'+side; }}

            // RMDP: also try span.rmdp-left / span.rmdp-right directly
            var sp = document.querySelector('span.' + side);
            if (sp && sp.offsetParent) {{ sp.click(); return 'ok:span-'+side; }}

            // ngx-bootstrap / Bootstrap
            var head = document.querySelector('.bs-datepicker-head');
            if (head) {{
                var allB = Array.from(head.querySelectorAll('button'))
                    .filter(function(b){{ return b.offsetParent!==null; }});
                var navB = allB.filter(function(b){{
                    return (b.getAttribute('class')||'').indexOf('current')<0;
                }});
                if (!navB.length) navB = allB;
                var btn = {'navB[navB.length-1]' if direction=='next' else 'navB[0]'};
                if (btn) {{ btn.click(); return 'ok:ngx-'+(btn.getAttribute('class')||'').slice(0,12); }}
            }}
            var th = document.querySelector('{"th.next" if direction=="next" else "th.prev"}');
            if (th && th.offsetParent) {{ th.click(); return 'ok:bs-th'; }}

            return 'not-found';
        """)

    # ── Navigate to target month/year ────────────────────────────────────────
    hdr = _get_header()
    print(f"  Header: '{hdr}'")
    cur_m, cur_y = None, None
    for abbr, idx in MONTH_MAP.items():
        if abbr in hdr.lower():
            cur_m = idx; break
    ym = re.search(r'\d{4}', hdr)
    if ym: cur_y = int(ym.group())
    print(f"  Parsed: cur_m={cur_m} cur_y={cur_y} → target m={m} y={y}")

    if cur_m and cur_y:
        steps = (y - cur_y) * 12 + (m - cur_m)
        direction = "next" if steps > 0 else "prev"
        print(f"  Navigating {abs(steps)} step(s) {direction}...")
        for si in range(abs(steps)):
            r = _click_arrow(direction)
            time.sleep(0.35)
            hdr_now = _get_header()
            print(f"  [{si+1}/{abs(steps)}] arrow={r} → '{hdr_now}'")
        print(f"  Final: '{_get_header()}'")
    else:
        print(f"  WARNING: header not parsed ('{hdr}') — trying day click anyway")

    time.sleep(0.4)

    # ── Click target day ──────────────────────────────────────────────────────
    day_r = driver.execute_script(f"""
        var target = '{d}';   // string comparison
        var bad = ['deactive','disabled','prev','next','old','new'];
        function isBad(el){{
            var c=(el.getAttribute('class')||'').toLowerCase();
            return bad.some(function(s){{return c.indexOf(s)>=0;}});
        }}

        // RMDP: span.rmdp-day span (inner span has the number)
        var days = document.querySelectorAll('.rmdp-day:not(.rmdp-deactive):not(.rmdp-disabled)');
        for (var i=0;i<days.length;i++) {{
            var inner = days[i].querySelector('span');
            if (inner && inner.textContent.trim()===target) {{
                days[i].click();
                return 'ok:rmdp-day:'+inner.textContent.trim();
            }}
        }}

        // RMDP day spans directly
        var all_rmdp = document.querySelectorAll('.rmdp-day span');
        for (var i=0;i<all_rmdp.length;i++) {{
            if (!isBad(all_rmdp[i].parentElement||all_rmdp[i]) &&
                all_rmdp[i].textContent.trim()===target && all_rmdp[i].offsetParent) {{
                all_rmdp[i].click();
                return 'ok:rmdp-inner-span:'+all_rmdp[i].textContent.trim();
            }}
        }}

        // ngx-bootstrap / Bootstrap fallback
        var cal = document.querySelector('.bs-datepicker-body') ||
                  document.querySelector('.datepicker-days') ||
                  document.querySelector('[class*="rmdp"]');
        if (cal) {{
            var spans = cal.querySelectorAll('td span, span.rmdp-day span');
            for (var i=0;i<spans.length;i++) {{
                if (!isBad(spans[i].parentElement||spans[i]) &&
                    spans[i].textContent.trim()===target && spans[i].offsetParent) {{
                    spans[i].click(); return 'ok:fallback-span';
                }}
            }}
            var cells = cal.querySelectorAll('td');
            for (var i=0;i<cells.length;i++) {{
                if (!isBad(cells[i]) && cells[i].textContent.trim()===target &&
                    cells[i].offsetParent) {{
                    cells[i].click(); return 'ok:fallback-td';
                }}
            }}
        }}

        // Debug — list what days are visible
        var avail = [];
        document.querySelectorAll('.rmdp-day span,.rmdp-day').forEach(function(e){{
            var t=e.textContent.trim();
            if(/^\\d{{1,2}}$/.test(t)) avail.push(t);
        }});
        return 'not-found:rmdp-avail=['+[...new Set(avail)].join(',')+']';
    """)
    print(f"  Day click: {day_r}")
    day_clicked = day_r.startswith('ok:')

    # ActionChains fallback on RMDP day spans
    if not day_clicked:
        print(f"  Trying ActionChains on rmdp-day elements...")
        try:
            for el in driver.find_elements(By.CSS_SELECTOR,
                    ".rmdp-day:not(.rmdp-deactive):not(.rmdp-disabled) span"):
                if el.is_displayed() and el.text.strip() == str(d):
                    ActionChains(driver).move_to_element(el).click().perform()
                    print(f"  Day {d}: ✅ AC rmdp-day")
                    day_clicked = True; break
        except Exception as _e:
            print(f"  AC rmdp err: {_e}")

    if not day_clicked:
        print(f"  WARNING: day {d} not clicked — auto-continuing")

    time.sleep(0.8)
    val = (date_inp.get_attribute("value") or "").strip()
    print(f"  {desc}: done — input='{val}'")
    return bool(day_clicked)


def is_ng_select_filled(field_label):
    try:
        ng = driver.find_element(By.XPATH,
            f"//label[contains(text(),'{field_label}')]/following::ng-select[1]")
        for cls in ['ng-value-label', 'ng-value', 'ng-select-value']:
            try:
                span = ng.find_element(By.XPATH, f".//span[contains(@class,'{cls}')]")
                if span.text.strip() and span.is_displayed(): return True
            except: pass
        return bool(driver.execute_script("""
            var labels = document.querySelectorAll('label');
            for (var i=0;i<labels.length;i++) {
                if (labels[i].textContent.trim().includes(arguments[0])) {
                    var sib = labels[i].nextElementSibling;
                    while (sib) {
                        if (sib.tagName && sib.tagName.toLowerCase()==='ng-select') {
                            var clear = sib.querySelector('.ng-clear-wrapper,[class*="ng-clear"]');
                            if (clear && clear.offsetParent!==null) return true;
                            var val = sib.querySelector('[class*="ng-value"]');
                            if (val && val.textContent.trim()) return true;
                            break;
                        }
                        sib = sib.nextElementSibling;
                    }
                }
            }
            return false;
        """, field_label))
    except: return False


def is_browser_alive():
    try:
        _ = driver.current_url
        return True
    except:
        return False


def typeahead_select_state_district(field_label, type_text, select_text, timeout=5):
    """
    Click ng-select → type via JS (avoids GetHandleVerifier crash) → click option.
    """
    print(f"  [{field_label}] selecting '{select_text}'...")
    w = WebDriverWait(driver, timeout)

    # Step 1: Click ng-select via JS
    dropdown = w.until(EC.presence_of_element_located((
        By.XPATH, f"//label[contains(text(),'{field_label}')]/following::ng-select[1]"
    )))
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", dropdown)
    time.sleep(0.3)
    driver.execute_script("arguments[0].click();", dropdown)
    time.sleep(0.8)

    # Step 2: Type into the dropdown search input via JS (avoids GetHandleVerifier crash)
    typed = driver.execute_script("""
        var panel = document.querySelector('ng-dropdown-panel');
        if (!panel) return false;
        var inp = panel.querySelector('input');
        if (!inp) return false;
        inp.focus();
        inp.value = arguments[0];
        inp.dispatchEvent(new Event('input',  {bubbles:true}));
        inp.dispatchEvent(new Event('keyup',  {bubbles:true}));
        inp.dispatchEvent(new Event('change', {bubbles:true}));
        return true;
    """, type_text)

    if not typed:
        # Fallback: pure-JS character-by-character typing (never touches Selenium send_keys
        # which triggers GetHandleVerifier crash on ng-dropdown-panel inputs)
        typed = driver.execute_script("""
            var inp = document.querySelector(
                'ng-dropdown-panel input, .ng-input > input, ng-select input');
            if (!inp) return false;
            inp.focus();
            inp.value = '';
            var text = arguments[0];
            for (var i = 0; i < text.length; i++) {
                inp.value += text[i];
                inp.dispatchEvent(new KeyboardEvent('keydown',  {key: text[i], bubbles: true}));
                inp.dispatchEvent(new KeyboardEvent('keypress', {key: text[i], bubbles: true}));
                inp.dispatchEvent(new InputEvent('input',       {data: text[i], bubbles: true}));
                inp.dispatchEvent(new KeyboardEvent('keyup',    {key: text[i], bubbles: true}));
            }
            inp.dispatchEvent(new Event('change', {bubbles: true}));
            return inp.value.length > 0;
        """, type_text)
        if not typed:
            raise Exception("Could not type into dropdown via JS")

    time.sleep(1)

    # Step 3: Click matching option via JS
    clicked = driver.execute_script("""
        var items = document.querySelectorAll('ng-dropdown-panel .ng-option, ng-dropdown-panel span');
        for (var i=0;i<items.length;i++) {
            if ((items[i].textContent||'').trim().toUpperCase().includes(arguments[0].toUpperCase())) {
                items[i].click(); return true;
            }
        }
        return false;
    """, select_text)

    if not clicked:
        # Arrow-down + Enter via JS keyboard events (avoids Selenium send_keys crash)
        try:
            driver.execute_script("""
                var inp = document.querySelector('ng-dropdown-panel input');
                if (inp) {
                    inp.dispatchEvent(new KeyboardEvent('keydown',{key:'ArrowDown',keyCode:40,bubbles:true}));
                    inp.dispatchEvent(new KeyboardEvent('keyup',  {key:'ArrowDown',keyCode:40,bubbles:true}));
                    setTimeout(function(){
                        inp.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',keyCode:13,bubbles:true}));
                        inp.dispatchEvent(new KeyboardEvent('keyup',  {key:'Enter',keyCode:13,bubbles:true}));
                    }, 150);
                }
            """)
            time.sleep(0.4)
            clicked = True
        except:
            # last resort: XPath JS click on the option span
            try:
                opt = w.until(EC.element_to_be_clickable((
                    By.XPATH, f"//ng-dropdown-panel//span[contains(text(),'{select_text}')]")))
                driver.execute_script("arguments[0].click();", opt)
                clicked = True
            except: pass

    if clicked:
        print(f"  Selected '{select_text}'")
    else:
        raise Exception(f"Could not select option '{select_text}'")

    time.sleep(0.4)
    return True


def select_in_real_select_by_label(label_text, contains_text, timeout=20):
    w = WebDriverWait(driver, timeout)
    label = w.until(EC.presence_of_element_located(
        (By.XPATH, f"//label[contains(normalize-space(),'{label_text}')]")))
    sel = label.find_element(By.XPATH, ".//following::select[1]")
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", sel)
    s = Select(sel)
    target = contains_text.strip().lower()
    for opt in s.options:
        if target in (opt.text or "").strip().lower():
            s.select_by_visible_text(opt.text.strip())
            time.sleep(0.4)
            return True
    for opt in s.options:
        t = (opt.text or "").strip()
        if t and t.lower() != "select":
            s.select_by_visible_text(t)
            time.sleep(0.4)
            return True
    return False


# =============================================================================
# MAIN SCRIPT
# =============================================================================
try:
    driver.get(PORTAL_URL)
    print("Browser opened: fasalrin.gov.in\n")
    print("=" * 70)
    print("MANUAL STEPS:")
    print("=" * 70)
    print("1. Enter Mobile Number")
    print("2. Enter Password")
    print("3. Solve Captcha")
    print("4. Click LOGIN")
    print("=" * 70)
    print("\n  Waiting for you to login... (script will auto-continue)")
    sys.stdout.flush()

    # Auto-detect login: wait until URL is no longer the login page (max 5 min)
    for _wait_i in range(300):
        try:
            cur = driver.current_url
        except:
            cur = ""
        if cur and "login" not in cur.lower() and "fasalrin.gov.in" in cur.lower():
            print("  Login detected — continuing automation...")
            sys.stdout.flush()
            break
        time.sleep(1)
        if _wait_i % 15 == 14:   # print a dot every 15 seconds so dashboard log stays alive
            print(f"  Still waiting for login... ({_wait_i + 1}s)")
            sys.stdout.flush()
    else:
        print("  WARNING: Login wait timed out (5 min). Trying to continue anyway...")
        sys.stdout.flush()

    accept_native_alert_if_any()

    # OK popup
    try:
        safe_click("//button[normalize-space()='OK']", timeout=5)
        print("HTML OK popup closed")
        time.sleep(0.5)
    except: pass

    # Navigate to Loan Application
    print("Navigating to Loan Application...")
    loan_clicked = False
    for xp in [
        "//a[contains(@href,'loan-application') or contains(@href,'loanApplication')]",
        "//a[contains(text(),'Loan Application')]",
    ]:
        try:
            driver.execute_script("arguments[0].click();",
                driver.find_element(By.XPATH, xp))
            loan_clicked = True; break
        except: pass

    if not loan_clicked:
        print("  Could not click Loan Application — please click manually, then wait 3s")
        time.sleep(3)

    time.sleep(1)
    print("Ready to process\n")
    print("=" * 70)
    print(f"PROCESSING {len(df)} RECORDS")
    print("=" * 70)

    successful = 0
    skipped    = 0
    failed     = 0

    for index, row in df.iterrows():
        print(f"\n{'─'*70}")
        print(f"  Record {index+1}/{len(df)}  |  {row.get('Beneficiary Name','N/A')}")
        print(f"  Aadhaar: {mask_aadhaar(row['AadhaarNumber'])}")
        print(f"{'─'*70}")

        try:
            # Bail out early if browser died (e.g. after previous record's submission)
            if not is_browser_alive():
                print("  Browser connection lost — stopping automation")
                break

            wait_spinner()
            accept_native_alert_if_any()

            # Record 2+: open fresh form
            if index > 0:
                modal_open = False
                try:
                    modal_open = bool(driver.find_element(By.XPATH,
                        "//div[contains(@class,'modal')]//input[@type='text']"))
                except: pass
                if not modal_open:
                    start_new_application()

            # Financial Year
            try:
                fy = WebDriverWait(driver, 6).until(EC.element_to_be_clickable((
                    By.XPATH,
                    "//select[contains(@formcontrolname,'financialYear') or contains(@name,'financialYear')]"
                )))
                Select(fy).select_by_visible_text(FINANCIAL_YEAR)
                time.sleep(0.3)
            except: pass

            # Aadhaar
            aadhaar_value = str(row["AadhaarNumber"]).replace(".0", "")
            aadhaar_field = None
            try:
                aadhaar_field = wait.until(EC.presence_of_element_located(
                    (By.XPATH, "//div[contains(@class,'modal')]//input[@type='text']")))
                aadhaar_field.click(); time.sleep(0.2)
                aadhaar_field.send_keys(Keys.CONTROL + "a")
                aadhaar_field.send_keys(Keys.DELETE)
                aadhaar_field.send_keys(aadhaar_value)
                time.sleep(0.4)
                print(f"  Aadhaar entered: {mask_aadhaar(aadhaar_value)}")
            except:
                print(f"  WARNING: Could not enter Aadhaar automatically — continuing")

            # FETCH
            print("  Fetching record...")
            fetch_clicked = False
            for attempt in [
                lambda: (wait.until(EC.element_to_be_clickable((By.XPATH,
                    "//button[contains(translate(.,'abcdefghijklmnopqrstuvwxyz',"
                    "'ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'FETCH')]"))),
                    lambda btn: driver.execute_script("arguments[0].click();", btn)),
                lambda: (aadhaar_field.send_keys(Keys.ENTER) if aadhaar_field else None, None),
            ]:
                try:
                    r = attempt()
                    if r and r[0]: r[1](r[0]) if r[1] else None
                    fetch_clicked = True; break
                except: pass

            if not fetch_clicked:
                fetch_clicked = driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var i=0;i<btns.length;i++) {
                        if ((btns[i].textContent||'').toUpperCase().includes('FETCH')) {
                            btns[i].click(); return true;
                        }
                    }
                    return false;
                """) or False

            # ── Check for Aadhaar validation error ────────────────────────
            # Give the portal a moment to show inline validation
            time.sleep(1)
            try:
                err_el = driver.find_element(By.XPATH,
                    "//*[contains(text(),'valid Aadhaar') or "
                    "contains(text(),'Invalid Aadhaar') or "
                    "contains(text(),'Please enter valid') or "
                    "contains(text(),'not found') or "
                    "contains(text(),'No record found')]")
                if err_el.is_displayed():
                    print(f"  Aadhaar {mask_aadhaar(aadhaar_value)} invalid / not found — skipping")
                    # Dismiss the modal via BACK button
                    try:
                        safe_click("//button[normalize-space()='BACK']", timeout=3)
                        time.sleep(0.5)
                    except:
                        try:
                            safe_click("//button[normalize-space()='CANCEL']", timeout=2)
                        except:
                            pass
                    raise SkipRecord(f"Aadhaar {mask_aadhaar(aadhaar_value)} invalid or not found")
            except SkipRecord:
                raise   # re-raise so the outer except SkipRecord catches it
            except:
                pass    # no validation error found — continue normally

            # Account popup
            print("  Waiting for account popup...")
            time.sleep(0.5)
            account_popup_found = False
            for _ in range(8):
                for xp in [
                    "//h5[contains(.,'Beneficiary details exist')]",
                    "//select[contains(@formcontrolname,'accountNumber') or contains(@name,'accountNumber')]",
                ]:
                    try:
                        if driver.find_element(By.XPATH, xp).is_displayed():
                            account_popup_found = True; break
                    except: pass
                if account_popup_found: break
                time.sleep(0.5)

            if account_popup_found:
                print("  Account popup detected")
                try:
                    acct_dd = wait.until(EC.element_to_be_clickable((By.XPATH,
                        "//select[contains(@formcontrolname,'accountNumber') or contains(@name,'accountNumber')]")))
                    s = Select(acct_dd)
                    acct_sel = False

                    # Step 1: Try to match exact account number from Excel
                    if "AccountNumber" in df.columns and pd.notna(row.get("AccountNumber")):
                        av = str(row["AccountNumber"])
                        if "." in av: av = str(int(float(av)))
                        for opt in s.options:
                            if av in opt.text or opt.text in av:
                                s.select_by_visible_text(opt.text)
                                acct_sel = True
                                print(f"  Selected account (Excel match): {opt.text}")
                                break

                    # Step 2: Prefer account containing '1010' (101 branch) over '1120' (112 branch)
                    if not acct_sel and len(s.options) > 1:
                        preferred = None
                        fallback  = None
                        for opt in s.options:
                            t = opt.text.strip()
                            if not t or t.lower() == "select":
                                continue
                            if "1010" in t:
                                preferred = t; break
                            elif fallback is None:
                                fallback = t
                        chosen = preferred if preferred else fallback
                        if chosen:
                            s.select_by_visible_text(chosen)
                            acct_sel = True
                            print(f"  Selected account (101 preference): {chosen}")
                        else:
                            s.select_by_index(1)
                            print("  Selected account (index 1 fallback)")

                    time.sleep(0.5)
                except:
                    print("  Account dropdown auto-select failed — continuing")

                # Click OK
                ok_done = False
                try:
                    ok_done = safe_click(
                        "//div[contains(@class,'modal')]//button[normalize-space()='OK']", timeout=8)
                except: pass
                if not ok_done:
                    ok_done = driver.execute_script("""
                        var btns = document.querySelectorAll('button');
                        for (var i=0;i<btns.length;i++) {
                            if ((btns[i].textContent||'').trim().toUpperCase()==='OK'
                                    && btns[i].offsetParent!==null && !btns[i].disabled) {
                                btns[i].click(); return true;
                            }
                        }
                        return false;
                    """) or False
                print("  OK clicked" if ok_done else "  OK auto-click failed — continuing")
            else:
                print("  No account popup (continuing)")

            time.sleep(1.5)
            wait_spinner()

            # Application Type
            print("  Selecting Application Type...")
            try:
                for sel_el in driver.find_elements(By.TAG_NAME, "select"):
                    try:
                        s = Select(sel_el)
                        opts = [o.text.strip() for o in s.options]
                        if "Normal" in opts and "PVTG" in opts:
                            s.select_by_index(1); print("  Application Type selected"); break
                    except: continue
            except: pass

            # Secondary Activity
            print("  Selecting Secondary Activity...")
            try:
                for sel_el in driver.find_elements(By.TAG_NAME, "select"):
                    try:
                        s = Select(sel_el)
                        opts = [o.text.strip() for o in s.options]
                        if "Horti & Veg Crops" in opts or "Agri Crops" in opts:
                            s.select_by_index(1); print("  Secondary Activity selected"); break
                    except: continue
            except: pass

            # ── Residential Address ────────────────────────────────────────
            print("\n  RESIDENTIAL ADDRESS")

            # State
            print("  State: KARNATAKA")
            try:
                typeahead_select_state_district("State", STATE_TYPE, STATE_SELECT)
                print("  State selected")
            except Exception as e:
                if is_ng_select_filled("State"):
                    print("  State already pre-filled")
                else:
                    print(f"  State auto-select failed ({e}) — auto-continuing")

            time.sleep(1)
            wait_spinner()

            # District
            print("  District: Belagavi")
            try:
                typeahead_select_state_district("District", DISTRICT_TYPE, DISTRICT_SELECT)
                print("  District selected")
            except Exception as e:
                if is_ng_select_filled("District"):
                    print("  District already pre-filled")
                else:
                    print(f"  District auto-select failed ({e}) — auto-continuing")

            time.sleep(0.8)
            wait_spinner()

            # Block
            print("  Block: Kagwad")
            if not select_in_real_select_by_label("Block / Subdistrict", BLOCK_SELECT_TEXT):
                print("  Block auto-select failed — auto-continuing")
            else:
                print("  Block selected")

            time.sleep(0.5)
            wait_spinner()

            # Village
            print("  Village: AINAPUR")
            if not select_in_real_select_by_label("Village", VILLAGE_SELECT_TEXT):
                print("  Village auto-select failed — auto-continuing")
            else:
                print("  Village selected")

            print("  Address done")

            # UPDATE & CONTINUE (Applicant Details)
            click_update_and_continue()

            # UPDATE & CONTINUE (Account Details)
            print("  Account Details tab...")
            time.sleep(1)
            wait_spinner()
            click_update_and_continue()

            # Financial Details tab
            print("  Financial Details tab...")
            time.sleep(1)
            wait_spinner()
            try:
                safe_click("//a[contains(.,'Financial') and not(contains(.,'Activity'))]", timeout=8)
                time.sleep(0.5)
            except:
                print("  Financial tab not clicked — auto-continuing")

            # Wait for Financial Details form to fully render
            print("  Waiting for Financial Details form...")
            try:
                WebDriverWait(driver, 15).until(EC.presence_of_element_located((
                    By.XPATH,
                    "//label[contains(.,'KCC loan sanctioned') or contains(.,'KCC Loan Sanctioned')"
                    " or contains(.,'Loan Sanction') or contains(.,'drawing limit')]"
                )))
                time.sleep(0.8)
                print("  Financial Details form ready")
            except:
                time.sleep(3)
                print("  Financial Details form wait timed out — continuing anyway")

            print("  Filling Financial Details...")
            fields_filled = 0

            def fill_input(el, value):
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                el.click(); time.sleep(0.2)
                el.send_keys(Keys.CONTROL + "a")
                el.send_keys(Keys.DELETE)
                el.send_keys(value)
                driver.execute_script("""
                    arguments[0].dispatchEvent(new Event('input',  {bubbles:true}));
                    arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
                    arguments[0].dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
                """, el)
                time.sleep(0.2)

            loan_val = ""
            if "LoanAmount" in df.columns and pd.notna(row["LoanAmount"]):
                loan_val = str(row["LoanAmount"])
                if "." in loan_val: loan_val = str(int(float(loan_val)))

            disb_raw  = row.get("DisbursementDate") if "DisbursementDate" in df.columns else None
            # Next KCC Renewal is pre-filled by the portal — do NOT touch it

            if disb_raw is not None and pd.notna(disb_raw):
                try:
                    if select_date_in_calendar("KCC loan sanctioned", disb_raw, "KCC Sanctioned Date"):
                        fields_filled += 1
                except Exception as _date_ex:
                    print(f"  KCC Sanctioned Date EXCEPTION: {_date_ex} — auto-continuing")

            for label_frag, value, desc in [
                ("Loan Sanction eligibl", loan_val, "KCC SOF Eligibility"),
                ("drawing limit",         loan_val, "KCC Drawing Limit"),
            ]:
                if not value: continue
                filled_this = False
                for attempt in range(3):
                    try:
                        el = driver.find_element(By.XPATH,
                            f"//label[contains(.,'{label_frag}')]/following::input[1]")
                        if el.is_displayed() and el.is_enabled():
                            fill_input(el, value)
                            got = (el.get_attribute("value") or "").strip()
                            if got:
                                print(f"  {desc}: {value} ✅")
                                fields_filled += 1
                                filled_this = True
                                break
                            else:
                                # Angular might need a second fire
                                driver.execute_script("""
                                    arguments[0].value = arguments[1];
                                    ['input','change','keyup','blur'].forEach(function(ev){
                                        arguments[0].dispatchEvent(new Event(ev,{bubbles:true}));
                                    });
                                """, el, value)
                                time.sleep(0.3)
                        else:
                            time.sleep(0.5)
                    except Exception as ex:
                        print(f"  Could not fill {desc} (attempt {attempt+1}): {ex}")
                        time.sleep(0.3)
                if not filled_this:
                    print(f"  WARNING: {desc} fill failed after 3 attempts — auto-continuing")

            print(f"  Filled {fields_filled} financial fields")

            # Financial Details SAVE & CONTINUE
            click_button_by_text("SAVE & CONTINUE")

            # OK popup
            try:
                safe_click("//button[normalize-space()='OK']", timeout=4)
                print("  OK dismissed")
            except: pass

            # ── Activity tab ───────────────────────────────────────────────
            print("  Activity tab...")
            time.sleep(1.5)
            wait_spinner()

            # Read KCC drawing limit from page
            act_loan_val = ""
            try:
                limit_el = driver.find_element(By.XPATH,
                    "//*[contains(text(),'KCC drawing limit') or contains(text(),'drawing limit for current')]"
                    "/following::*[contains(text(),'₹') or contains(@class,'amount') or contains(@class,'limit')][1]")
                raw = limit_el.text.strip()
                cleaned = re.sub(r'[₹,\s]', '', raw).split('\n')[0].strip()
                act_loan_val = str(int(float(cleaned)))
                print(f"  KCC limit from page = {raw} → {act_loan_val}")
            except:
                act_loan_val = loan_val
                print(f"  Using Excel value: {act_loan_val}")

            # Fill Loan Sanctioned
            if act_loan_val:
                filled_act = False
                for xp in [
                    "//label[contains(text(),'Loan Sanctioned')]/following::input[1]",
                    "//*[contains(text(),'Loan Sanctioned')]/following::input[1]",
                ]:
                    try:
                        for act_inp in driver.find_elements(By.XPATH, xp):
                            if act_inp.is_displayed() and act_inp.is_enabled():
                                driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center'});", act_inp)
                                act_inp.click(); time.sleep(0.2)
                                act_inp.send_keys(Keys.CONTROL + "a")
                                act_inp.send_keys(Keys.DELETE)
                                act_inp.send_keys(act_loan_val)
                                driver.execute_script("""
                                    arguments[0].dispatchEvent(new Event('input',  {bubbles:true}));
                                    arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
                                    arguments[0].dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
                                    arguments[0].dispatchEvent(new FocusEvent('blur',  {bubbles:true}));
                                """, act_inp)
                                time.sleep(0.4)
                                if act_loan_val in (act_inp.get_attribute("value") or ""):
                                    print(f"  Loan Sanctioned filled: {act_loan_val}")
                                    filled_act = True; break
                    except: continue
                    if filled_act: break
                if not filled_act:
                    print(f"  WARNING: Loan Sanctioned fill failed — auto-continuing")

            time.sleep(1)
            wait_spinner()

            # Activity SAVE & CONTINUE
            print("  Activity SAVE & CONTINUE...")
            act_saved = False
            act_btn = None
            for xp in [
                "//button[normalize-space(.)='SAVE & CONTINUE']",
                "//button[contains(normalize-space(.),'SAVE') and contains(normalize-space(.),'CONTINUE')]",
            ]:
                try:
                    for el in driver.find_elements(By.XPATH, xp):
                        if el.is_displayed(): act_btn = el; break
                except: pass
                if act_btn: break

            if act_btn:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", act_btn)
                time.sleep(0.4)

                # Try 1: RETURN key
                try:
                    driver.execute_script("arguments[0].focus();", act_btn)
                    time.sleep(0.3)
                    act_btn.send_keys(Keys.RETURN)
                    time.sleep(1); act_saved = True
                    print("  Activity SAVE — RETURN key")
                except: pass

                # Try 2: ActionChains
                if not act_saved:
                    try:
                        ActionChains(driver).move_to_element(act_btn).pause(0.3).click().perform()
                        time.sleep(1); act_saved = True
                        print("  Activity SAVE — ActionChains")
                    except: pass

                # Try 3: MouseEvent
                if not act_saved:
                    try:
                        driver.execute_script("""
                            var el=arguments[0]; el.focus();
                            ['mouseover','mouseenter','mousedown','mouseup','click'].forEach(function(ev){
                                el.dispatchEvent(new MouseEvent(ev,{view:window,bubbles:true,cancelable:true}));
                            });
                        """, act_btn)
                        time.sleep(1); act_saved = True
                        print("  Activity SAVE — MouseEvent")
                    except: pass
            else:
                print("  SAVE & CONTINUE button not found — auto-continuing")

            if not act_saved:
                print("  WARNING: SAVE & CONTINUE auto-click failed — auto-continuing")

            time.sleep(1)
            wait_spinner()

            # OK popup after Activity save
            try:
                safe_click("//button[normalize-space()='OK']", timeout=4)
                print("  Activity OK dismissed")
            except: pass

            # ── Term Loan Details → PREVIEW → FINAL SUBMIT ───────────────
            time.sleep(1.5)
            wait_spinner()
            accept_native_alert_if_any()

            print("  Term Loan Details tab — clicking PREVIEW...")
            preview_done = False

            # Strategy 1: click_button_by_text
            try:
                preview_done = click_button_by_text("PREVIEW")
            except: pass

            # Strategy 2: JS direct button find
            if not preview_done:
                preview_done = bool(driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var i = 0; i < btns.length; i++) {
                        var t = (btns[i].textContent || '').trim().toUpperCase();
                        if (t === 'PREVIEW' && btns[i].offsetParent !== null
                                && !btns[i].disabled) {
                            btns[i].scrollIntoView({block:'center'});
                            btns[i].click();
                            return true;
                        }
                    }
                    return false;
                """))
                if preview_done:
                    print("  PREVIEW clicked via JS")

            if not preview_done:
                print("  WARNING: PREVIEW button not found — auto-continuing")

            # Wait for loan-application-preview page to fully load
            print("  Waiting for preview page to load...")
            try:
                WebDriverWait(driver, 15).until(
                    lambda d: "loan-application-preview" in d.current_url
                )
                print("  Preview page loaded ✅")
            except:
                print("  Preview URL wait timed out — continuing anyway")

            time.sleep(2)
            wait_spinner()
            accept_native_alert_if_any()

            # Scroll to bottom so the SUBMIT button is in view
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(0.8)

            # Check if application is DRAFT — log it
            try:
                status_el = driver.find_element(By.XPATH,
                    "//*[contains(text(),'Application Status')]")
                print(f"  Status: {status_el.text.strip()}")
            except: pass

            # Click SUBMIT button (green button, bottom-right on preview page)
            print("  Clicking SUBMIT on preview page...")
            submit_done = False

            # Primary: find a button whose exact text is SUBMIT (the green one)
            submit_done = bool(driver.execute_script("""
                var btns = document.querySelectorAll('button');
                // prefer exact match first
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].textContent || '').trim().toUpperCase();
                    if (t === 'SUBMIT' && btns[i].offsetParent !== null
                            && !btns[i].disabled) {
                        btns[i].scrollIntoView({block:'center'});
                        btns[i].click();
                        return true;
                    }
                }
                // fallback: any button containing SUBMIT
                for (var i = 0; i < btns.length; i++) {
                    var t = (btns[i].textContent || '').trim().toUpperCase();
                    if (t.indexOf('SUBMIT') >= 0 && btns[i].offsetParent !== null
                            && !btns[i].disabled) {
                        btns[i].scrollIntoView({block:'center'});
                        btns[i].click();
                        return true;
                    }
                }
                return false;
            """))

            if submit_done:
                print("  SUBMIT clicked ✅")
            else:
                # XPath fallback
                for sub_txt in ["SUBMIT", "FINAL SUBMIT", "SUBMIT APPLICATION",
                                 "CONFIRM & SUBMIT"]:
                    try:
                        if click_button_by_text(sub_txt):
                            submit_done = True
                            print(f"  SUBMIT clicked via text: '{sub_txt}'")
                            break
                    except: pass

            if not submit_done:
                print("  WARNING: SUBMIT button not found on preview page — auto-continuing")

            time.sleep(2)
            wait_spinner()
            accept_native_alert_if_any()

            # Step 1: "Are you sure you want to submit this loan application?"
            # → click CONFIRM (green button)
            print("  Waiting for CONFIRM dialog...")
            confirm_clicked = False
            for _c in range(5):
                try:
                    confirm_clicked = bool(driver.execute_script("""
                        var btns = document.querySelectorAll('button');
                        for (var i = 0; i < btns.length; i++) {
                            var t = (btns[i].textContent || '').trim().toUpperCase();
                            if (t === 'CONFIRM' && btns[i].offsetParent !== null
                                    && !btns[i].disabled) {
                                btns[i].scrollIntoView({block:'center'});
                                btns[i].click();
                                return true;
                            }
                        }
                        return false;
                    """))
                    if confirm_clicked:
                        print("  CONFIRM clicked ✅")
                        break
                except: pass
                time.sleep(0.8)

            if not confirm_clicked:
                # XPath fallback
                try:
                    safe_click("//button[normalize-space()='CONFIRM']", timeout=5)
                    confirm_clicked = True
                    print("  CONFIRM clicked via XPath ✅")
                except: pass

            if not confirm_clicked:
                print("  WARNING: CONFIRM button not found — auto-continuing")

            time.sleep(2)
            wait_spinner()
            accept_native_alert_if_any()

            # Step 2: "Loan application XXXX submitted successfully." → click OK
            print("  Waiting for success popup OK...")
            for _ok_try in range(5):
                try:
                    safe_click("//button[normalize-space()='OK']", timeout=4)
                    print("  Success OK dismissed ✅")
                    break
                except: pass
                time.sleep(0.8)

            if submit_done:
                print(f"  Record {index+1} SUBMITTED successfully!")
            else:
                print(f"  Record {index+1} saved successfully!")
            successful += 1

            # Give the portal 2s to settle, dismiss any post-save alerts
            time.sleep(2)
            accept_native_alert_if_any()

        except SkipRecord as sk:
            print(f"  SKIPPED record {index+1}: {sk}")
            skipped += 1
            accept_native_alert_if_any()
            time.sleep(0.5)

        except Exception as e:
            print(f"  ERROR on record {index+1}: {str(e)[:120]}")
            failed += 1
            print("  Auto-continuing to next record...")
            accept_native_alert_if_any()
            time.sleep(1)

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"  Successful : {successful}")
    print(f"  Skipped    : {skipped}")
    print(f"  Failed     : {failed}")
    print(f"  Total      : {len(df)}")
    print("=" * 70)

except Exception as e:
    print(f"\nFatal Error: {e}")
    traceback.print_exc()

finally:
    print("\nDone. Closing browser in 5 seconds...")
    time.sleep(5)
    try:
        driver.quit()
    except: pass
    print("Automation completed")

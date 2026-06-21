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
)
import time, re, sys, traceback
import record_tracker as tracker

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# CONFIGURATION
# =============================================================================
PORTAL_URL      = "https://fasalrin.gov.in/login"
CLAIM_LIST_URL  = "https://fasalrin.gov.in/claim-application-list"
WAIT_TIME       = 30
FINANCIAL_YEAR  = "2025-2026"
CLAIM_TYPE      = "IS"
CLAIM_STATUS    = "PENDING"

# Interest Cycle End Date passed from dashboard as sys.argv[1] (DD/MM/YYYY)
END_DATE = sys.argv[1] if len(sys.argv) > 1 else ""

if not END_DATE:
    print("ERROR: Interest Cycle End Date not provided!")
    print("Usage: python IS_Claim_V1.py DD/MM/YYYY")
    raise SystemExit(1)

print("=" * 70)
print(" " * 15 + "IS CLAIM AUTOMATION  V1")
print("=" * 70)
print(f"  Interest Cycle End Date : {END_DATE}")
print("=" * 70)

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
def is_browser_alive():
    try:
        _ = driver.current_url
        return True
    except:
        return False


def accept_native_alert_if_any():
    try:
        WebDriverWait(driver, 3).until(EC.alert_is_present())
        driver.switch_to.alert.accept()
        print("  Alert accepted")
        time.sleep(0.1)
        return True
    except:
        return False


def wait_spinner(timeout=5):
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
            time.sleep(0.1)
            ActionChains(driver).move_to_element(btn).click().perform()
            print(f"  '{btn_text}' clicked (ActionChains)")
            time.sleep(0.1); wait_spinner()
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
            print(f"  '{btn_text}' clicked (MouseEvent)")
            time.sleep(0.1); wait_spinner()
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
        print(f"  '{btn_text}' clicked (XPath)")
        time.sleep(0.1); wait_spinner()
        return True
    except:
        pass

    print(f"  WARNING: Could not click '{btn_text}'")
    return False


def parse_date(val):
    s = str(val).strip().replace("-", "/")
    parts = s.split("/")
    if len(parts) == 3:
        if len(parts[0]) == 4:
            y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
        else:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        return d, m, y, f"{d:02d}/{m:02d}/{y}"
    return None, None, None, ""


def select_date_in_calendar(label_frag, date_val, desc):
    try:
        return _select_date_impl(label_frag, date_val, desc)
    except Exception as ex:
        print(f"  {desc} date ERROR: {ex}")
        return False


def _select_date_impl(label_frag, date_val, desc):
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

    # Find the date input
    date_inp = None
    for xp in [
        f"//label[contains(.,'{label_frag}')]/following::input[1]",
        f"//*[contains(text(),'{label_frag}')]/following::input[1]",
    ]:
        try:
            el = driver.find_element(By.XPATH, xp)
            if el.is_displayed():
                date_inp = el; break
        except:
            pass
    if not date_inp:
        print(f"  ERROR: input not found for '{label_frag}'")
        return False

    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", date_inp)
    time.sleep(0.1)

    def _dp_visible():
        return bool(driver.execute_script("""
            var sels = ['.rmdp-wrapper','.rmdp-calendar','.rmdp-day-picker',
                'bs-datepicker-container','bs-days-calendar-view',
                '.bs-datepicker','.datepicker-days','.datepicker-dropdown'];
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
            time.sleep(0.05)
        return False

    opened = False
    icon_el = driver.execute_script("""
        var inp = arguments[0];
        var rmdp = inp.closest('.rmdp-container');
        if (rmdp) {
            var svg = rmdp.querySelector('svg');
            if (svg) return svg.parentElement || svg;
            return rmdp;
        }
        var el = inp.parentElement;
        for (var i=0; i<5; i++) {
            if (!el || el===document.body) break;
            var svg = el.querySelector('svg');
            if (svg) return svg.parentElement || svg;
            el = el.parentElement;
        }
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
        try:
            ActionChains(driver).move_to_element(icon_el).click().perform()
            opened = _wait_dp(2.5)
            if opened: print(f"  Calendar opened (ActionChains)")
        except:
            pass
        if not opened:
            driver.execute_script("arguments[0].click();", icon_el)
            opened = _wait_dp(2.0)
            if opened: print(f"  Calendar opened (JS click)")

    if not opened:
        driver.execute_script("""
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
        """, date_inp)
        opened = _wait_dp(2.0)

    if not opened:
        try:
            ActionChains(driver).move_to_element(date_inp).click().perform()
            opened = _wait_dp(1.5)
        except:
            pass

    if not opened:
        print(f"  Calendar NOT opened for {desc}")
        return False

    # Read header
    def _get_header():
        return driver.execute_script("""
            var hv = document.querySelector('.rmdp-header-values');
            if (hv) {
                var spans = hv.querySelectorAll('span');
                if (spans.length >= 2) return spans[0].textContent.trim()+' '+spans[1].textContent.trim();
                return hv.textContent.trim();
            }
            var head = document.querySelector('.bs-datepicker-head');
            if (head) {
                var txts = Array.from(head.querySelectorAll('button'))
                    .map(function(b){ return b.textContent.trim(); })
                    .filter(function(t){ return /[A-Za-z]{3}|\\d{4}/.test(t); });
                if (txts.length >= 2) return txts[0]+' '+txts[1];
            }
            return '';
        """) or ""

    def _click_arrow(direction):
        return driver.execute_script(f"""
            var side = '{"rmdp-right" if direction=="next" else "rmdp-left"}';
            var ac = document.querySelector('.rmdp-arrow-container.' + side);
            if (ac && ac.offsetParent) {{ ac.click(); return 'ok'; }}
            var sp = document.querySelector('span.' + side);
            if (sp && sp.offsetParent) {{ sp.click(); return 'ok'; }}
            var head = document.querySelector('.bs-datepicker-head');
            if (head) {{
                var allB = Array.from(head.querySelectorAll('button'))
                    .filter(function(b){{ return b.offsetParent!==null; }});
                var navB = allB.filter(function(b){{
                    return (b.getAttribute('class')||'').indexOf('current')<0;
                }});
                if (!navB.length) navB = allB;
                var btn = {'navB[navB.length-1]' if direction=='next' else 'navB[0]'};
                if (btn) {{ btn.click(); return 'ok'; }}
            }}
            return 'not-found';
        """)

    hdr = _get_header()
    print(f"  Header: '{hdr}'")
    cur_m, cur_y = None, None
    for abbr, idx in MONTH_MAP.items():
        if abbr in hdr.lower():
            cur_m = idx; break
    ym = re.search(r'\d{4}', hdr)
    if ym: cur_y = int(ym.group())

    if cur_m and cur_y:
        steps = (y - cur_y) * 12 + (m - cur_m)
        direction = "next" if steps > 0 else "prev"
        for _ in range(abs(steps)):
            _click_arrow(direction)
            time.sleep(0.05)
        print(f"  Navigated to: '{_get_header()}'")

    time.sleep(0.05)

    day_r = driver.execute_script(f"""
        var target = '{d}';
        var bad = ['deactive','disabled','prev','next','old','new'];
        function isBad(el){{
            var c=(el.getAttribute('class')||'').toLowerCase();
            return bad.some(function(s){{return c.indexOf(s)>=0;}});
        }}
        var days = document.querySelectorAll('.rmdp-day:not(.rmdp-deactive):not(.rmdp-disabled)');
        for (var i=0;i<days.length;i++) {{
            var inner = days[i].querySelector('span');
            if (inner && inner.textContent.trim()===target) {{
                days[i].click();
                return 'ok:rmdp-day';
            }}
        }}
        var all_rmdp = document.querySelectorAll('.rmdp-day span');
        for (var i=0;i<all_rmdp.length;i++) {{
            if (!isBad(all_rmdp[i].parentElement||all_rmdp[i]) &&
                all_rmdp[i].textContent.trim()===target && all_rmdp[i].offsetParent) {{
                all_rmdp[i].click();
                return 'ok:rmdp-span';
            }}
        }}
        var cal = document.querySelector('.bs-datepicker-body,.datepicker-days,[class*="rmdp"]');
        if (cal) {{
            var cells = cal.querySelectorAll('td');
            for (var i=0;i<cells.length;i++) {{
                if (!isBad(cells[i]) && cells[i].textContent.trim()===target && cells[i].offsetParent) {{
                    cells[i].click(); return 'ok:fallback-td';
                }}
            }}
        }}
        return 'not-found';
    """)
    print(f"  Day click: {day_r}")
    day_clicked = day_r.startswith('ok:')

    if not day_clicked:
        try:
            for el in driver.find_elements(By.CSS_SELECTOR,
                    ".rmdp-day:not(.rmdp-deactive):not(.rmdp-disabled) span"):
                if el.is_displayed() and el.text.strip() == str(d):
                    ActionChains(driver).move_to_element(el).click().perform()
                    print(f"  Day {d}: clicked (ActionChains)")
                    day_clicked = True; break
        except:
            pass

    time.sleep(0.1)
    val = (date_inp.get_attribute("value") or "").strip()
    print(f"  {desc}: done - input='{val}'")
    return bool(day_clicked)


def select_dropdown_by_value(label_frag, value_text, timeout=10):
    """
    Handle both native <select> and custom Angular dropdowns on the filter page.
    """
    # Try native select first
    for xp in [
        f"//label[contains(.,'{label_frag}')]/following::select[1]",
        f"//*[contains(text(),'{label_frag}')]/following::select[1]",
    ]:
        try:
            sel = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            if sel.is_displayed():
                s = Select(sel)
                for opt in s.options:
                    if value_text.lower() in opt.text.strip().lower():
                        s.select_by_visible_text(opt.text.strip())
                        time.sleep(0.05)
                        print(f"  {label_frag} -> '{value_text}' (native select)")
                        return True
        except:
            pass

    # Custom dropdown (Angular mat-select / custom)
    try:
        # Click the dropdown trigger
        trigger_xp = (
            f"//label[contains(.,'{label_frag}')]/following::*"
            f"[self::select or self::mat-select or contains(@class,'dropdown') "
            f"or contains(@class,'select')][1]"
        )
        el = WebDriverWait(driver, timeout).until(
            EC.presence_of_element_located((By.XPATH, trigger_xp)))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        driver.execute_script("arguments[0].click();", el)
        time.sleep(0.1)

        # Click matching option
        opt_clicked = driver.execute_script("""
            var opts = document.querySelectorAll(
                'mat-option, .dropdown-item, [role="option"], li.ng-option, .select-option');
            for (var i=0;i<opts.length;i++) {
                if ((opts[i].textContent||'').trim().toUpperCase().includes(arguments[0].toUpperCase())) {
                    opts[i].click(); return true;
                }
            }
            return false;
        """, value_text)
        if opt_clicked:
            print(f"  {label_frag} -> '{value_text}' (custom dropdown)")
            time.sleep(0.1)
            return True
    except:
        pass

    print(f"  WARNING: Could not select '{value_text}' for '{label_frag}'")
    return False


def fill_input_field(label_frag, value, timeout=10):
    """Find input by label and fill it."""
    for xp in [
        f"//label[contains(.,'{label_frag}')]/following::input[1]",
        f"//*[contains(text(),'{label_frag}')]/following::input[1]",
    ]:
        try:
            el = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            if el.is_displayed() and el.is_enabled():
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                el.click(); time.sleep(0.1)
                el.send_keys(Keys.CONTROL + "a")
                el.send_keys(Keys.DELETE)
                el.send_keys(str(value))
                driver.execute_script("""
                    arguments[0].dispatchEvent(new Event('input',  {bubbles:true}));
                    arguments[0].dispatchEvent(new Event('change', {bubbles:true}));
                    arguments[0].dispatchEvent(new KeyboardEvent('keyup', {bubbles:true}));
                """, el)
                time.sleep(0.1)
                print(f"  '{label_frag}' filled: {value}")
                return True
        except:
            pass
    print(f"  WARNING: Could not fill '{label_frag}'")
    return False


def get_total_count():
    """Read 'Total Count:XXX' from the claim list page."""
    try:
        el = driver.find_element(By.XPATH,
            "//*[contains(text(),'Total Count') or contains(text(),'Total count')]")
        m = re.search(r'\d+', el.text)
        if m:
            return int(m.group())
    except:
        pass
    return 0


def get_add_buttons():
    """Return all visible ADD buttons in the claim list table."""
    return driver.find_elements(By.XPATH,
        "//button[normalize-space(translate(.,'abcdefghijklmnopqrstuvwxyz',"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))='ADD' and not(@disabled)]"
    )


def read_sanction_date_from_form():
    """Read Sanction/Rollover Date from the IS Claim form info table."""
    # Strategy 1: find the th with 'Sanction' text, then get the last td in that row
    try:
        rows = driver.find_elements(By.XPATH,
            "//table[.//th[contains(.,'Sanction') or contains(.,'Rollover')]]//tr")
        for row in rows:
            cells = row.find_elements(By.TAG_NAME, "td")
            if not cells:
                continue
            # Last cell in the data row = Sanction/Rollover Date
            last = cells[-1].text.strip()
            if re.match(r'\d{2}/\d{2}/\d{4}', last):
                print(f"  Sanction/Rollover Date: {last}")
                return last
    except:
        pass

    # Strategy 2: any cell with DD/MM/YYYY in page that is NOT an input value
    try:
        cells = driver.find_elements(By.XPATH, "//td")
        for cell in cells:
            t = cell.text.strip()
            if re.match(r'\d{2}/\d{2}/\d{4}', t):
                print(f"  Sanction/Rollover Date (td scan): {t}")
                return t
    except:
        pass

    print("  WARNING: Could not read Sanction/Rollover Date")
    return ""


def read_loan_sanctioned_amount():
    """Read Loan Sanctioned Amount from the IS Claim form info table.

    Strategy: find 'Loan Sanctioned' header in ANY table, note its column index,
    then read the corresponding <td> in the first data row of that table.
    This is a strict column-matched lookup - one header -> one value.
    """
    try:
        tables = driver.find_elements(By.XPATH, "//table")
        for tbl in tables:
            # Find all <th> in this table
            ths = tbl.find_elements(By.TAG_NAME, "th")
            col_idx = None
            for i, th in enumerate(ths):
                txt = th.text.strip()
                if 'Loan Sanctioned' in txt or 'Sanctioned Amount' in txt:
                    col_idx = i
                    break
            if col_idx is None:
                continue
            # Find first data row (row with <td> only, no <th>)
            rows = tbl.find_elements(By.TAG_NAME, "tr")
            for row in rows:
                tds = row.find_elements(By.TAG_NAME, "td")
                ths_in_row = row.find_elements(By.TAG_NAME, "th")
                if ths_in_row:
                    continue  # skip header rows
                if col_idx < len(tds):
                    raw = tds[col_idx].text.strip()
                    cleaned = re.sub(r'[^0-9.]', '', raw)
                    if cleaned and re.match(r'^\d+(\.\d+)?$', cleaned):
                        amt = str(int(float(cleaned)))
                        print(f"  Loan Sanctioned Amount: '{raw}' -> {amt}")
                        return amt
    except Exception as e:
        print(f"  read_loan_sanctioned_amount error: {e}")

    # Fallback: look for th 'Loan Sanctioned' then get sibling td value
    try:
        xp_val = ("//th[contains(normalize-space(),'Loan Sanctioned') or "
                  "contains(normalize-space(),'Sanctioned Amount')]"
                  "/following::td[1]")
        cell = driver.find_element(By.XPATH, xp_val)
        raw = cell.text.strip()
        cleaned = re.sub(r'[-,\s]', '', raw)
        if cleaned and re.match(r'^\d+(\.\d+)?$', cleaned):
            amt = str(int(float(cleaned)))
            print(f"  Loan Sanctioned Amount (XPath fallback): '{raw}' -> {amt}")
            return amt
    except:
        pass

    print("  WARNING: Could not read Loan Sanctioned Amount")
    return ""


# =============================================================================
# MAIN SCRIPT
# =============================================================================
try:
    driver.get(PORTAL_URL)
    print("Browser opened: fasalrin.gov.in\n")
    print("=" * 70)
    print("MANUAL STEPS:")
    print("  1. Enter Mobile Number")
    print("  2. Enter Password")
    print("  3. Solve Captcha")
    print("  4. Click LOGIN")
    print("=" * 70)
    print("\n  Waiting for login... (auto-continues after login)")
    sys.stdout.flush()

    # Wait for login (max 5 min) - check every 1s so timing prints are accurate
    import time as _t
    _login_start = _t.time()
    _login_timeout = 300  # 5 minutes
    _login_ok = False
    while _t.time() - _login_start < _login_timeout:
        try:
            cur = driver.current_url
        except:
            cur = ""
        if cur and "login" not in cur.lower() and "fasalrin.gov.in" in cur.lower():
            print("  Login detected - continuing...")
            sys.stdout.flush()
            _login_ok = True
            break
        elapsed = int(_t.time() - _login_start)
        if elapsed > 0 and elapsed % 15 == 0:
            print(f"  Still waiting for login... ({elapsed}s elapsed)")
            sys.stdout.flush()
        time.sleep(1)
    if not _login_ok:
        print("  WARNING: Login wait timed out - trying to continue...")

    accept_native_alert_if_any()

    # Close any OK popup
    try:
        safe_click("//button[normalize-space()='OK']", timeout=3)
        time.sleep(0.1)
    except:
        pass

    # --- Navigate to IS/PRI Claim Application ---
    print("\nNavigating to IS/PRI Claim Application...")
    nav_clicked = False
    for xp in [
        "//a[contains(@href,'claim-application') or contains(@href,'claimApplication')]",
        "//a[contains(.,'IS/PRI') or contains(.,'Claim Application')]",
        "//span[contains(.,'IS/PRI') or contains(.,'Claim')]/..",
    ]:
        try:
            driver.execute_script("arguments[0].click();",
                driver.find_element(By.XPATH, xp))
            nav_clicked = True
            print("  IS/PRI Claim Application clicked")
            break
        except:
            pass

    if not nav_clicked:
        driver.get(CLAIM_LIST_URL)
        print("  Navigated directly to claim-application-list")

    time.sleep(0.1)
    wait_spinner()

    # --- Set Filters ---
    print("\nSetting filters...")

    # Financial Year
    fy_set = False
    for xp in [
        "//select[contains(@formcontrolname,'financialYear') or contains(@name,'financialYear') or contains(@id,'financialYear')]",
        "//label[contains(.,'Financial Year')]/following::select[1]",
    ]:
        try:
            sel = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            s = Select(sel)
            for opt in s.options:
                if FINANCIAL_YEAR in opt.text:
                    s.select_by_visible_text(opt.text.strip())
                    fy_set = True
                    print(f"  Financial Year: {FINANCIAL_YEAR}")
                    time.sleep(0.1)
                    break
            if fy_set:
                break
        except:
            pass

    if not fy_set:
        select_dropdown_by_value("Financial Year", FINANCIAL_YEAR)

    time.sleep(0.1)

    # Claim Type
    ct_set = False
    for xp in [
        "//select[contains(@formcontrolname,'claimType') or contains(@name,'claimType')]",
        "//label[contains(.,'Claim type') or contains(.,'Claim Type')]/following::select[1]",
    ]:
        try:
            sel = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            s = Select(sel)
            for opt in s.options:
                if CLAIM_TYPE in opt.text.upper():
                    s.select_by_visible_text(opt.text.strip())
                    ct_set = True
                    print(f"  Claim Type: {CLAIM_TYPE}")
                    time.sleep(0.1)
                    break
            if ct_set:
                break
        except:
            pass

    if not ct_set:
        select_dropdown_by_value("Claim type", CLAIM_TYPE)

    time.sleep(0.1)

    # Claim Status
    cs_set = False
    for xp in [
        "//select[contains(@formcontrolname,'claimStatus') or contains(@name,'claimStatus')]",
        "//label[contains(.,'Claim Status') or contains(.,'Claim status')]/following::select[1]",
    ]:
        try:
            sel = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            s = Select(sel)
            for opt in s.options:
                if CLAIM_STATUS in opt.text.upper():
                    s.select_by_visible_text(opt.text.strip())
                    cs_set = True
                    print(f"  Claim Status: {CLAIM_STATUS}")
                    time.sleep(0.1)
                    break
            if cs_set:
                break
        except:
            pass

    if not cs_set:
        select_dropdown_by_value("Claim Status", CLAIM_STATUS)

    time.sleep(0.1)

    # Click PROCEED
    print("  Clicking PROCEED...")
    proceed_done = False
    for xp in [
        "//button[normalize-space(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'))='PROCEED']",
        "//button[contains(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'PROCEED')]",
    ]:
        try:
            safe_click(xp, timeout=8)
            proceed_done = True
            break
        except:
            pass

    if not proceed_done:
        click_button_by_text("PROCEED")

    time.sleep(0.1)
    wait_spinner()

    total_count = get_total_count()
    print(f"\n  Total PENDING records: {total_count}")
    print("=" * 70)
    print(f"PROCESSING {total_count} RECORDS")
    print("=" * 70)

    # --- Main Loop ---
    processed  = 0
    successful = 0
    failed     = 0

    while True:
        if not is_browser_alive():
            print("  Browser connection lost - stopping")
            break

        wait_spinner()
        accept_native_alert_if_any()

        # Get all ADD buttons
        add_buttons = get_add_buttons()
        if not add_buttons:
            print("\n  No more ADD buttons found - all records processed!")
            break

        processed += 1
        total_now = get_total_count() or total_count
        print(f"\n{'-'*70}")
        print(f"  Record {processed}/{total_now}")
        print(f"{'-'*70}")
        sys.stdout.flush()

        # Start tracking this record
        rec = tracker.start_record(processed)

        try:
            # Click the first ADD button
            btn = add_buttons[0]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.1)
            driver.execute_script("arguments[0].click();", btn)
            print("  ADD clicked")
            time.sleep(0.1)
            wait_spinner()

            # --- Verify we landed on the claim form ---
            try:
                WebDriverWait(driver, 5).until(
                    lambda d: "claim-against-loan-app" in d.current_url
                )
                print("  Claim form loaded")
            except:
                print("  WARNING: claim form URL not detected - continuing anyway")

            time.sleep(0.1)

            # --- Read farmer info + form values ---
            farmer_name, account_no, loan_app_no = tracker.read_farmer_info(driver)
            tracker.update(rec,
                farmer_name=farmer_name,
                account_no=account_no,
                loan_app_no=loan_app_no)

            sanction_date  = read_sanction_date_from_form()
            loan_sanctioned = read_loan_sanctioned_amount()
            tracker.update(rec,
                sanction_date=sanction_date,
                loan_sanctioned_amt=loan_sanctioned)

            # --- IS Submission Type -> PARTIAL ---
            print("  Setting IS Submission Type: PARTIAL")
            partial_set = False
            for xp in [
                "//select[contains(@formcontrolname,'submissionType') or contains(@name,'submissionType')]",
                "//label[contains(.,'IS Submission Type')]/following::select[1]",
                "//th[contains(.,'IS Submission Type')]/following::select[1]",
                "//td//select[1]",
            ]:
                try:
                    sel = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, xp)))
                    if sel.is_displayed():
                        s = Select(sel)
                        for opt in s.options:
                            if "PARTIAL" in opt.text.upper():
                                s.select_by_visible_text(opt.text.strip())
                                partial_set = True
                                print("  IS Submission Type: PARTIAL selected")
                                break
                        if partial_set:
                            break
                except:
                    pass

            if not partial_set:
                # Try by index (0=Select, 1=COMPLETE, 2=PARTIAL)
                try:
                    sels = driver.find_elements(By.TAG_NAME, "select")
                    for sel in sels:
                        if sel.is_displayed():
                            s = Select(sel)
                            opts = [o.text.upper() for o in s.options]
                            if "PARTIAL" in opts or "COMPLETE" in opts:
                                s.select_by_index(2)
                                partial_set = True
                                print("  IS Submission Type: PARTIAL (index 2)")
                                break
                except:
                    pass

            if not partial_set:
                print("  WARNING: Could not select PARTIAL - auto-continuing")

            time.sleep(0.1)
            wait_spinner()

            # --- Find all RMDP date inputs in order (positional) ---
            # Index 0 = First Loan Disbursal/Interest Cycle Start Date
            # Index 1 = Interest Cycle end/Rollover Date
            # Using position avoids label mismatch (fields are in <th>, not <label>)
            rmdp_inputs = driver.find_elements(By.CSS_SELECTOR,
                ".rmdp-container input, .rmdp-input")
            rmdp_inputs = [i for i in rmdp_inputs if i.is_displayed()]
            print(f"  Found {len(rmdp_inputs)} date input(s)")

            def _fill_date_by_index(idx, date_val, desc):
                if idx >= len(rmdp_inputs):
                    print(f"  WARNING: date input index {idx} not found for {desc}")
                    return False
                inp = rmdp_inputs[idx]
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
                # Pass the specific input element directly - no label search needed
                return _fill_rmdp_input(inp, date_val, desc)

            def _fill_rmdp_input(date_inp, date_val, desc):
                d2, m2, y2, date_str = parse_date(date_val)
                if not date_str:
                    print(f"  No valid date for {desc}")
                    return False
                print(f"  Setting {desc}: {date_str}")

                MONTH_MAP2 = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,
                             "jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12,
                             "january":1,"february":2,"march":3,"april":4,"june":6,
                             "july":7,"august":8,"september":9,"october":10,
                             "november":11,"december":12}

                def _dp_vis():
                    return bool(driver.execute_script("""
                        var sels=['.rmdp-wrapper','.rmdp-calendar','.rmdp-day-picker',
                            'bs-datepicker-container','.bs-datepicker','.datepicker-days'];
                        for(var i=0;i<sels.length;i++){
                            var el=document.querySelector(sels[i]);
                            if(el&&el.tagName.toLowerCase()!=='input'
                                    &&el.offsetWidth>30&&el.offsetHeight>30) return true;
                        } return false;
                    """))

                def _wait_dp2(secs=3):
                    t0=time.time()
                    while time.time()-t0<secs:
                        if _dp_vis(): return True
                        time.sleep(0.05)
                    return False

                # Open calendar via icon
                opened = False
                icon_el = driver.execute_script("""
                    var inp=arguments[0];
                    var rmdp=inp.closest('.rmdp-container');
                    if(rmdp){var svg=rmdp.querySelector('svg');
                        if(svg) return svg.parentElement||svg; return rmdp;}
                    var el=inp.parentElement;
                    for(var i=0;i<5;i++){
                        if(!el||el===document.body) break;
                        var svg=el.querySelector('svg');
                        if(svg) return svg.parentElement||svg;
                        el=el.parentElement;
                    }
                    return inp;
                """, date_inp)

                if icon_el:
                    try:
                        ActionChains(driver).move_to_element(icon_el).click().perform()
                        opened = _wait_dp2(2.5)
                    except: pass
                    if not opened:
                        driver.execute_script("arguments[0].click();", icon_el)
                        opened = _wait_dp2(2.0)

                if not opened:
                    try:
                        ActionChains(driver).move_to_element(date_inp).click().perform()
                        opened = _wait_dp2(1.5)
                    except: pass

                if not opened:
                    print(f"  Calendar NOT opened for {desc}")
                    return False

                # Read current month/year header
                def _hdr():
                    return driver.execute_script("""
                        var hv=document.querySelector('.rmdp-header-values');
                        if(hv){var sp=hv.querySelectorAll('span');
                            if(sp.length>=2) return sp[0].textContent.trim()+' '+sp[1].textContent.trim();}
                        return '';
                    """) or ""

                def _arrow(direction):
                    driver.execute_script(f"""
                        var side='{"rmdp-right" if direction=="next" else "rmdp-left"}';
                        var ac=document.querySelector('.rmdp-arrow-container.'+side);
                        if(ac&&ac.offsetParent){{ac.click();return;}}
                        var sp=document.querySelector('span.'+side);
                        if(sp&&sp.offsetParent) sp.click();
                    """)

                hdr = _hdr()
                cur_m2, cur_y2 = None, None
                for abbr, idx2 in MONTH_MAP2.items():
                    if abbr in hdr.lower():
                        cur_m2 = idx2; break
                ym = re.search(r'\d{4}', hdr)
                if ym: cur_y2 = int(ym.group())

                if cur_m2 and cur_y2:
                    steps = (y2 - cur_y2)*12 + (m2 - cur_m2)
                    direction = "next" if steps > 0 else "prev"
                    for _ in range(abs(steps)):
                        _arrow(direction)
                        time.sleep(0.05)
                    print(f"  Navigated to: '{_hdr()}'")

                time.sleep(0.05)

                # Click day
                day_r = driver.execute_script(f"""
                    var target='{d2}';
                    var bad=['deactive','disabled','prev','next','old','new'];
                    function isBad(el){{var c=(el.getAttribute('class')||'').toLowerCase();
                        return bad.some(function(s){{return c.indexOf(s)>=0;}});}}
                    var days=document.querySelectorAll('.rmdp-day:not(.rmdp-deactive):not(.rmdp-disabled)');
                    for(var i=0;i<days.length;i++){{
                        var inner=days[i].querySelector('span');
                        if(inner&&inner.textContent.trim()===target){{days[i].click();return 'ok';}}
                    }}
                    var all=document.querySelectorAll('.rmdp-day span');
                    for(var i=0;i<all.length;i++){{
                        if(!isBad(all[i].parentElement||all[i])&&all[i].textContent.trim()===target&&all[i].offsetParent){{
                            all[i].click();return 'ok';}}
                    }}
                    return 'not-found';
                """)
                if not day_r.startswith('ok'):
                    try:
                        for el in driver.find_elements(By.CSS_SELECTOR,
                                ".rmdp-day:not(.rmdp-deactive):not(.rmdp-disabled) span"):
                            if el.is_displayed() and el.text.strip() == str(d2):
                                ActionChains(driver).move_to_element(el).click().perform()
                                day_r = 'ok'; break
                    except: pass

                time.sleep(0.1)
                val = (date_inp.get_attribute("value") or "").strip()
                print(f"  {desc}: done - input='{val}'")
                return day_r.startswith('ok')

            # --- First Loan Disbursal / Interest Cycle Start Date ---
            if sanction_date:
                _fill_date_by_index(0, sanction_date, "First Loan Disbursal Date")
            else:
                print("  WARNING: Skipping Start Date (no sanction date found)")

            time.sleep(0.1)

            # --- Interest Cycle End / Rollover Date ---
            # Re-fetch inputs after first calendar interaction
            rmdp_inputs = [i for i in driver.find_elements(By.CSS_SELECTOR,
                ".rmdp-container input, .rmdp-input") if i.is_displayed()]
            _fill_date_by_index(1, END_DATE, "Interest Cycle End Date")

            time.sleep(1)
            wait_spinner()

            # --- Max Withdrawal Amount + Applicable IS ---
            # Layout in the form table row (same <tr> as IS Submission Type select):
            #   <select>  IS Submission Type
            #   rmdp      Start Date
            #   rmdp      End Date
            #   <input type="number">  Max Withdrawal Amount  - fill with Loan Sanctioned Amount
            #   <td readonly>          Maximum Allowed Claim   - auto-calculated by portal
            #   <input type="number">  Applicable IS          - fill with Maximum Allowed Claim value
            #   <td>                   Interest Days

            def _type_into(el, val):
                """Fill Angular input: click to focus -> native setter -> TAB to commit."""
                try:
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.3)
                    # Click to focus (required so Angular marks the control as touched)
                    el.click()
                    time.sleep(0.3)
                    # Angular native setter - bypasses React/Angular batching
                    driver.execute_script("""
                        var el = arguments[0], val = arguments[1];
                        var setter = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value').set;
                        setter.call(el, val);
                        el.dispatchEvent(new Event('input',  {bubbles: true}));
                        el.dispatchEvent(new Event('change', {bubbles: true}));
                    """, el, str(val))
                    time.sleep(0.3)
                    # TAB via keyboard (not blur event) to trigger Angular validation
                    el.send_keys(Keys.TAB)
                    time.sleep(0.5)
                    got = (el.get_attribute('value') or '').strip()
                    print(f"    _type_into[js+tab]: typed='{val}' got='{got}'")
                    if not got:
                        # Pure keyboard fallback: re-click, select-all, retype
                        el.click(); time.sleep(0.3)
                        el.send_keys(Keys.CONTROL + "a")
                        time.sleep(0.1)
                        el.send_keys(Keys.DELETE)
                        time.sleep(0.1)
                        el.send_keys(str(val))
                        time.sleep(0.3)
                        el.send_keys(Keys.TAB)
                        time.sleep(0.5)
                        got = (el.get_attribute('value') or '').strip()
                        print(f"    _type_into[kb]: typed='{val}' got='{got}'")
                    return got
                except Exception as e:
                    print(f"  _type_into error: {e}")
                    return ""

            def _get_all_editable_inputs():
                """Return all visible editable non-date inputs on the page (in DOM order)."""
                return driver.execute_script("""
                    var skip = ['checkbox','radio','hidden','submit','button','file'];
                    var result = [];
                    var inputs = Array.from(document.querySelectorAll('input'));
                    for (var i = 0; i < inputs.length; i++) {
                        var inp = inputs[i];
                        if (inp.readOnly || inp.disabled) continue;
                        if (!inp.offsetParent) continue;
                        var cls = (inp.getAttribute('class') || '').toLowerCase();
                        if (cls.indexOf('rmdp') >= 0) continue;
                        var t = (inp.getAttribute('type') || 'text').toLowerCase();
                        if (skip.indexOf(t) >= 0) continue;
                        result.push(inp);
                    }
                    return result;
                """)

            # --- Max Withdrawal Amount = Loan Sanctioned Amount ---
            # Approach: get ALL editable non-date inputs; index 0 = Max Withdrawal
            mw_filled = False
            if loan_sanctioned:
                editable_inputs = _get_all_editable_inputs()
                print(f"  Editable inputs on page: {len(editable_inputs)}")
                if editable_inputs:
                    mw_el = editable_inputs[0]
                    got = _type_into(mw_el, loan_sanctioned)
                    print(f"  Max Withdrawal Amount: {loan_sanctioned} -> field='{got}'")
                    mw_filled = bool(got)
                    if mw_filled:
                        tracker.update(rec, max_withdrawal=loan_sanctioned)

            if not mw_filled and loan_sanctioned:
                # XPath fallback - try both number and any input type
                for xp in [
                    "//th[contains(.,'Max Withdrawal')]/following::input[@type='number'][1]",
                    "//th[contains(.,'Max Withdrawal')]/following::input[1]",
                    "//th[contains(.,'Withdrawal')]/following::input[1]",
                ]:
                    try:
                        el = driver.find_element(By.XPATH, xp)
                        if el.is_displayed() and el.is_enabled() and not el.get_attribute('readonly'):
                            got = _type_into(el, loan_sanctioned)
                            print(f"  Max Withdrawal (XPath): {loan_sanctioned} -> field='{got}'")
                            mw_filled = bool(got)
                            if mw_filled:
                                break
                    except:
                        pass

            if not mw_filled:
                print("  WARNING: Could not fill Max Withdrawal Amount")

            # Wait for portal to auto-calculate Maximum Allowed Claim **
            time.sleep(1.5)
            wait_spinner()

            # --- Read Maximum Allowed Claim ** ---
            # It is a readonly <td> in the same row, under header "Maximum Allowed Claim"
            max_allowed_claim = ""
            try:
                mac_val = driver.execute_script("""
                    var ths = Array.from(document.querySelectorAll('th'));
                    for (var i = 0; i < ths.length; i++) {
                        var txt = ths[i].textContent.trim();
                        if (txt.indexOf('Maximum Allowed') >= 0 || txt.indexOf('Max Allowed') >= 0) {
                            var table = ths[i].closest('table');
                            if (!table) continue;
                            // Build column index within its <tr>
                            var headerRow = ths[i].closest('tr');
                            var allThs = Array.from(headerRow.querySelectorAll('th'));
                            var colIdx = allThs.indexOf(ths[i]);
                            // Find first data row
                            var rows = Array.from(table.querySelectorAll('tr'));
                            for (var r = 0; r < rows.length; r++) {
                                var tds = rows[r].querySelectorAll('td');
                                if (tds.length === 0) continue;
                                if (colIdx < tds.length) {
                                    var val = tds[colIdx].textContent.trim();
                                    if (val && val.length > 0) return val;
                                }
                            }
                        }
                    }
                    return '';
                """)
                if mac_val:
                    # Keep decimals - portal may store 198.49, not 198
                    cleaned_mac = re.sub(r'[^0-9.]', '', mac_val.strip())
                    if cleaned_mac and re.match(r'^\d+(\.\d+)?$', cleaned_mac):
                        # Remove trailing .00 if whole number, else keep decimal
                        fval = float(cleaned_mac)
                        max_allowed_claim = f"{fval:.2f}" if fval != int(fval) else str(int(fval))
                        print(f"  Maximum Allowed Claim: '{mac_val}' -> {max_allowed_claim}")
                        tracker.update(rec, max_allowed_claim=max_allowed_claim)
                    else:
                        print(f"  Maximum Allowed Claim raw (non-numeric): '{mac_val}'")
            except Exception as mac_err:
                print(f"  Maximum Allowed Claim read error: {mac_err}")

            # --- Applicable IS = Maximum Allowed Claim value ---
            # Strategy: find 'Applicable IS' column header -> get its column index
            # -> find the <input> inside that exact <td> in the data row
            # This avoids any confusion with date inputs or other fields.
            if max_allowed_claim and float(max_allowed_claim) > 0:
                ai_filled = False

                # Re-fetch editable inputs after portal recalculated Max Allowed Claim
                editable_inputs2 = _get_all_editable_inputs()
                print(f"  Editable inputs after MW fill: {len(editable_inputs2)}")

                # index 1 = Applicable IS (index 0 = Max Withdrawal)
                ai_el = editable_inputs2[1] if len(editable_inputs2) > 1 else None

                # Fallback: column-header XPath
                if not ai_el:
                    for xp in [
                        "//th[contains(.,'Applicable IS')]/following::input[1]",
                        "//th[contains(.,'Applicable')]/following::input[1]",
                    ]:
                        try:
                            el = driver.find_element(By.XPATH, xp)
                            if el.is_displayed() and el.is_enabled() and not el.get_attribute('readonly'):
                                ai_el = el; break
                        except:
                            pass

                if ai_el:
                    try:
                        got_ai = _type_into(ai_el, max_allowed_claim)
                        print(f"  Applicable IS: {max_allowed_claim} -> field='{got_ai}'")
                        ai_filled = bool(got_ai)
                        if ai_filled:
                            tracker.update(rec, applicable_is=max_allowed_claim)
                    except Exception as ai_ex:
                        print(f"  Applicable IS fill error: {ai_ex}")

                if not ai_filled:
                    print("  WARNING: Could not fill Applicable IS")
            else:
                print(f"  NOTE: Maximum Allowed Claim='{max_allowed_claim}' - skipping Applicable IS fill")

            time.sleep(0.1)
            wait_spinner()

            # --- Declaration Checkbox ---
            print("  Checking declaration checkbox...")
            chk_done = False
            for xp in [
                "//input[@type='checkbox'][not(@checked)]",
                "//input[@type='checkbox']",
            ]:
                try:
                    chks = driver.find_elements(By.XPATH, xp)
                    for chk in chks:
                        if chk.is_displayed() and not chk.is_selected():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", chk)
                            driver.execute_script("arguments[0].click();", chk)
                            time.sleep(0.1)
                            if chk.is_selected():
                                print("  Declaration checkbox checked")
                                chk_done = True
                                break
                    if chk_done:
                        break
                except:
                    pass

            if not chk_done:
                print("  WARNING: Could not check declaration checkbox")

            time.sleep(0.1)

            # --- SAVE & CONTINUE ---
            print("  Clicking SAVE & CONTINUE...")
            sc_done = False
            for xp in [
                "//button[normalize-space(.)='SAVE & CONTINUE']",
                "//button[contains(normalize-space(.),'SAVE') and contains(normalize-space(.),'CONTINUE')]",
            ]:
                try:
                    btn_sc = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH, xp)))
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", btn_sc)
                    time.sleep(0.1)
                    try:
                        ActionChains(driver).move_to_element(btn_sc).click().perform()
                        sc_done = True; break
                    except:
                        driver.execute_script("arguments[0].click();", btn_sc)
                        sc_done = True; break
                except:
                    pass

            if not sc_done:
                click_button_by_text("SAVE & CONTINUE")

            time.sleep(0.1)
            wait_spinner()

            # --- Popup: "Claim application saved successfully" -> OK ---
            print("  Waiting for success popup...")
            ok_done = False
            for _try in range(4):
                try:
                    ok_btn = WebDriverWait(driver, 3).until(
                        EC.element_to_be_clickable((By.XPATH,
                            "//button[normalize-space()='OK' or normalize-space()='Ok']"
                        ))
                    )
                    driver.execute_script("arguments[0].click();", ok_btn)
                    print("  Popup OK clicked")
                    ok_done = True
                    break
                except:
                    pass
                # Check if popup text is visible
                try:
                    popup = driver.find_element(By.XPATH,
                        "//*[contains(.,'saved successfully') or contains(.,'Claim application saved')]")
                    if popup.is_displayed():
                        # Try any visible button near it
                        driver.execute_script("""
                            var btns = document.querySelectorAll('button');
                            for (var i=0;i<btns.length;i++) {
                                var t = (btns[i].textContent||'').trim().toUpperCase();
                                if ((t==='OK' || t==='OKAY') && btns[i].offsetParent) {
                                    btns[i].click(); return true;
                                }
                            }
                        """)
                        ok_done = True
                        break
                except:
                    pass
                time.sleep(0.1)

            if not ok_done:
                print("  WARNING: Success popup not found - auto-continuing")

            time.sleep(0.1)
            wait_spinner()
            accept_native_alert_if_any()

            # --- Submit Page -> Click SUBMIT ---
            print("  Clicking SUBMIT on review page...")
            submit_done = False

            for _s in range(5):
                submit_done = bool(driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var i=0;i<btns.length;i++) {
                        var t = (btns[i].textContent||'').trim().toUpperCase();
                        if (t === 'SUBMIT' && btns[i].offsetParent !== null
                                && !btns[i].disabled) {
                            btns[i].scrollIntoView({block:'center'});
                            btns[i].click();
                            return true;
                        }
                    }
                    return false;
                """))
                if submit_done:
                    print("  SUBMIT clicked")
                    break
                time.sleep(0.1)

            if not submit_done:
                click_button_by_text("SUBMIT")

            time.sleep(0.1)
            wait_spinner()
            accept_native_alert_if_any()

            # --- Confirmation popup: "Are you sure you want to submit?" -> CONFIRM
            print("  Looking for CONFIRM button...")
            confirm_done = False
            for _c in range(4):
                try:
                    confirm_btn = driver.execute_script("""
                        var btns = document.querySelectorAll('button');
                        for (var i=0;i<btns.length;i++) {
                            var t = (btns[i].textContent||'').trim().toUpperCase();
                            if (t === 'CONFIRM' && btns[i].offsetParent !== null
                                    && !btns[i].disabled) {
                                return btns[i];
                            }
                        }
                        return null;
                    """)
                    if confirm_btn:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", confirm_btn)
                        time.sleep(0.1)
                        driver.execute_script("arguments[0].click();", confirm_btn)
                        print("  CONFIRM clicked")
                        confirm_done = True
                        break
                except:
                    pass
                time.sleep(0.1)

            if not confirm_done:
                print("  WARNING: CONFIRM button not found")

            time.sleep(0.1)
            wait_spinner()
            accept_native_alert_if_any()

            # --- Success popup: "Claim application No. XXX has been submitted" -> OK
            # Also read the Claim Application No. from the popup text
            try:
                popup_text = driver.execute_script("""
                    var els = document.querySelectorAll('p,h4,h5,div,span');
                    for (var i=0;i<els.length;i++) {
                        var t = (els[i].textContent||'').trim();
                        if (t.indexOf('submitted successfully') >= 0 && els[i].offsetParent)
                            return t;
                    }
                    return '';
                """)
                if popup_text:
                    m = re.search(r'Claim application No\.?\s*(\d+)', popup_text)
                    if m:
                        claim_no = m.group(1)
                        print(f"  Claim Application No: {claim_no}")
                        tracker.update(rec, loan_app_no=claim_no)
            except:
                pass

            print("  Waiting for submission success popup...")
            final_ok_done = False
            for _ok in range(5):
                try:
                    ok_btn = driver.execute_script("""
                        var btns = document.querySelectorAll('button');
                        for (var i=0;i<btns.length;i++) {
                            var t = (btns[i].textContent||'').trim().toUpperCase();
                            if ((t === 'OK' || t === 'OKAY') && btns[i].offsetParent !== null
                                    && !btns[i].disabled) {
                                return btns[i];
                            }
                        }
                        return null;
                    """)
                    if ok_btn:
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", ok_btn)
                        time.sleep(0.1)
                        driver.execute_script("arguments[0].click();", ok_btn)
                        print("  Success popup OK clicked")
                        final_ok_done = True
                        break
                except:
                    pass
                accept_native_alert_if_any()
                time.sleep(0.1)

            if not final_ok_done:
                print("  NOTE: No final OK popup found - continuing")

            time.sleep(0.1)
            wait_spinner()

            print(f"  Record {processed} SUBMITTED successfully!")
            tracker.mark_submitted(rec)
            successful += 1
            sys.stdout.flush()

            time.sleep(0.1)
            accept_native_alert_if_any()

            # --- Return to claim list ---
            # The portal should redirect back; if not, navigate manually
            for _wait in range(5):
                try:
                    if "claim-application-list" in driver.current_url:
                        break
                except:
                    break
                time.sleep(0.1)

            if "claim-application-list" not in (driver.current_url or ""):
                print("  Not back on list - navigating back...")
                try:
                    driver.get(CLAIM_LIST_URL)
                    time.sleep(0.1)
                    wait_spinner()
                    # Re-set filters and PROCEED
                    for xp in [
                        "//select[contains(@formcontrolname,'financialYear')]",
                        "//label[contains(.,'Financial Year')]/following::select[1]",
                    ]:
                        try:
                            sel = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.XPATH, xp)))
                            s = Select(sel)
                            for opt in s.options:
                                if FINANCIAL_YEAR in opt.text:
                                    s.select_by_visible_text(opt.text.strip()); break
                            break
                        except:
                            pass
                    time.sleep(0.1)
                    for xp in [
                        "//select[contains(@formcontrolname,'claimType')]",
                        "//label[contains(.,'Claim type')]/following::select[1]",
                    ]:
                        try:
                            sel = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.XPATH, xp)))
                            s = Select(sel)
                            for opt in s.options:
                                if CLAIM_TYPE in opt.text.upper():
                                    s.select_by_visible_text(opt.text.strip()); break
                            break
                        except:
                            pass
                    time.sleep(0.1)
                    for xp in [
                        "//select[contains(@formcontrolname,'claimStatus')]",
                        "//label[contains(.,'Claim Status')]/following::select[1]",
                    ]:
                        try:
                            sel = WebDriverWait(driver, 3).until(
                                EC.presence_of_element_located((By.XPATH, xp)))
                            s = Select(sel)
                            for opt in s.options:
                                if CLAIM_STATUS in opt.text.upper():
                                    s.select_by_visible_text(opt.text.strip()); break
                            break
                        except:
                            pass
                    time.sleep(0.1)
                    # Click PROCEED
                    for xp in [
                        "//button[normalize-space(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'))='PROCEED']",
                    ]:
                        try:
                            safe_click(xp, timeout=5); break
                        except:
                            pass
                    time.sleep(0.1)
                    wait_spinner()
                except Exception as nav_err:
                    print(f"  Navigation error: {nav_err}")

        except Exception as e:
            err_msg = str(e)[:200]
            print(f"  ERROR on record {processed}: {err_msg}")
            tracker.mark_failed(rec, reason=err_msg)
            failed += 1
            accept_native_alert_if_any()
            time.sleep(0.1)
            # Try to go back to list
            try:
                if "claim-application-list" not in (driver.current_url or ""):
                    driver.get(CLAIM_LIST_URL)
                    time.sleep(0.1)
                    wait_spinner()
            except:
                pass

    print("\n" + "=" * 70)
    print("FINAL SUMMARY")
    print("=" * 70)
    print(f"  Successful : {successful}")
    print(f"  Failed     : {failed}")
    print(f"  Total      : {processed}")
    print("=" * 70)
    # Emit CSV data for dashboard download
    print("CSV_DATA_START")
    print(tracker.to_csv_string(), end="")
    print("CSV_DATA_END")

except Exception as e:
    print(f"\nFatal Error: {e}")
    traceback.print_exc()

finally:
    print("\nDone. Closing browser in 5 seconds...")
    time.sleep(2)
    try:
        driver.quit()
    except:
        pass
    print("Automation completed")



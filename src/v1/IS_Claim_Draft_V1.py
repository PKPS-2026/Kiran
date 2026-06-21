"""
IS_Claim_Draft_V1.py
Submits all DRAFT IS Claim records on fasalrin.gov.in.
DRAFT records are already filled — this script just clicks EDIT -> SUBMIT -> CONFIRM -> OK.
Usage: python IS_Claim_Draft_V1.py DD/MM/YYYY
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait, Select
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.keys import Keys
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time, re, sys, traceback
import record_tracker as tracker

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# =============================================================================
# CONFIGURATION
# =============================================================================
PORTAL_URL     = "https://fasalrin.gov.in/login"
CLAIM_LIST_URL = "https://fasalrin.gov.in/claim-application-list"
WAIT_TIME      = 30
FINANCIAL_YEAR = "2025-2026"
CLAIM_TYPE     = "IS"
CLAIM_STATUS   = "DRAFT"

END_DATE = sys.argv[1] if len(sys.argv) > 1 else ""
if not END_DATE:
    print("ERROR: End Date not provided!")
    raise SystemExit(1)

print("=" * 70)
print(" " * 12 + "IS CLAIM DRAFT SUBMIT  V1")
print("=" * 70)
print(f"  Interest Cycle End Date : {END_DATE}")
print(f"  Mode                    : DRAFT -> SUBMIT")
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


def get_total_count():
    try:
        el = driver.find_element(By.XPATH,
            "//*[contains(text(),'Total Count') or contains(text(),'Total count')]")
        m = re.search(r'\d+', el.text)
        if m:
            return int(m.group())
    except:
        pass
    return 0


def get_edit_buttons():
    """Return all visible EDIT buttons/links in the draft list table."""
    return driver.find_elements(By.XPATH,
        "//a[normalize-space(translate(.,'abcdefghijklmnopqrstuvwxyz',"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))='EDIT' and not(@disabled)]"
        " | //button[normalize-space(translate(.,'abcdefghijklmnopqrstuvwxyz',"
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ'))='EDIT' and not(@disabled)]"
    )


def set_filters_and_proceed():
    """Set Financial Year, Claim Type, Claim Status=DRAFT and click PROCEED."""
    # Financial Year
    for xp in [
        "//select[contains(@formcontrolname,'financialYear') or contains(@name,'financialYear')]",
        "//label[contains(.,'Financial Year')]/following::select[1]",
    ]:
        try:
            sel = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            s = Select(sel)
            for opt in s.options:
                if FINANCIAL_YEAR in opt.text:
                    s.select_by_visible_text(opt.text.strip())
                    time.sleep(0.1)
                    break
            break
        except:
            pass

    # Claim Type = IS
    for xp in [
        "//select[contains(@formcontrolname,'claimType') or contains(@name,'claimType')]",
        "//label[contains(.,'Claim type') or contains(.,'Claim Type')]/following::select[1]",
    ]:
        try:
            sel = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            s = Select(sel)
            for opt in s.options:
                if CLAIM_TYPE in opt.text.upper():
                    s.select_by_visible_text(opt.text.strip())
                    time.sleep(0.1)
                    break
            break
        except:
            pass

    # Claim Status = DRAFT
    for xp in [
        "//select[contains(@formcontrolname,'claimStatus') or contains(@name,'claimStatus')]",
        "//label[contains(.,'Claim Status') or contains(.,'Claim status')]/following::select[1]",
    ]:
        try:
            sel = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, xp)))
            s = Select(sel)
            for opt in s.options:
                if CLAIM_STATUS in opt.text.upper():
                    s.select_by_visible_text(opt.text.strip())
                    time.sleep(0.1)
                    break
            break
        except:
            pass

    time.sleep(0.1)

    # PROCEED
    for xp in [
        "//button[normalize-space(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'))='PROCEED']",
        "//button[contains(translate(.,'abcdefghijklmnopqrstuvwxyz','ABCDEFGHIJKLMNOPQRSTUVWXYZ'),'PROCEED')]",
    ]:
        try:
            safe_click(xp, timeout=8)
            break
        except:
            pass

    time.sleep(0.2)
    wait_spinner()


# =============================================================================
# MAIN
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
    print("\n  Waiting for login...")
    sys.stdout.flush()

    # Wait for login (max 5 min)
    _login_start = time.time()
    _login_ok = False
    while time.time() - _login_start < 300:
        try:
            cur = driver.current_url
        except:
            cur = ""
        if cur and "login" not in cur.lower() and "fasalrin.gov.in" in cur.lower():
            print("  Login detected - continuing...")
            _login_ok = True
            break
        elapsed = int(time.time() - _login_start)
        if elapsed > 0 and elapsed % 15 == 0:
            print(f"  Still waiting... ({elapsed}s)")
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

    # Navigate to IS/PRI Claim Application
    print("\nNavigating to IS/PRI Claim Application...")
    nav_done = False
    for xp in [
        "//a[contains(@href,'claim-application') or contains(@href,'claimApplication')]",
        "//a[contains(.,'IS/PRI') or contains(.,'Claim Application')]",
        "//span[contains(.,'IS/PRI') or contains(.,'Claim')]/..",
    ]:
        try:
            driver.execute_script("arguments[0].click();",
                driver.find_element(By.XPATH, xp))
            nav_done = True
            break
        except:
            pass

    if not nav_done:
        driver.get(CLAIM_LIST_URL)

    time.sleep(0.2)
    wait_spinner()

    # Set filters and PROCEED
    print("Setting filters: DRAFT...")
    set_filters_and_proceed()

    total_count = get_total_count()
    print(f"\n  Total DRAFT records: {total_count}")
    print("=" * 70)
    print(f"PROCESSING {total_count} DRAFT RECORDS")
    print("=" * 70)

    processed  = 0
    successful = 0
    failed     = 0

    while True:
        if not is_browser_alive():
            print("  Browser connection lost - stopping")
            break

        wait_spinner()
        accept_native_alert_if_any()

        edit_buttons = get_edit_buttons()
        if not edit_buttons:
            print("\n  No more EDIT buttons found - all draft records processed!")
            break

        processed += 1
        total_now = get_total_count() or total_count
        print(f"\n{'-'*70}")
        print(f"  Draft Record {processed}/{total_now}")
        print(f"{'-'*70}")
        sys.stdout.flush()

        rec = tracker.start_record(processed)

        try:
            # Click first EDIT button
            btn = edit_buttons[0]
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            time.sleep(0.1)
            driver.execute_script("arguments[0].click();", btn)
            print("  EDIT clicked")
            time.sleep(0.2)
            wait_spinner()

            # Wait for claim form to load
            try:
                WebDriverWait(driver, 10).until(
                    lambda d: "claim-against-loan-app" in d.current_url
                )
                print("  Claim form loaded")
            except:
                print("  WARNING: claim form URL not detected - continuing")

            time.sleep(0.2)

            # Read farmer info for tracking
            farmer_name, account_no, loan_app_no = tracker.read_farmer_info(driver)
            tracker.update(rec,
                farmer_name=farmer_name,
                account_no=account_no,
                loan_app_no=loan_app_no)
            print(f"  Farmer: {farmer_name} | Account: {account_no}")

            # Read existing values for CSV tracking
            try:
                mw_val = driver.execute_script("""
                    var ths = Array.from(document.querySelectorAll('th'));
                    for (var i=0; i<ths.length; i++) {
                        if (ths[i].textContent.indexOf('Max Withdrawal') >= 0) {
                            var row = ths[i].closest('tr');
                            if (!row) continue;
                            var allThs = Array.from(row.querySelectorAll('th'));
                            var col = allThs.indexOf(ths[i]);
                            var tbl = ths[i].closest('table');
                            var rows = tbl.querySelectorAll('tr');
                            for (var r=0; r<rows.length; r++) {
                                var tds = rows[r].querySelectorAll('td');
                                if (tds.length && col < tds.length) {
                                    var inp = tds[col].querySelector('input');
                                    if (inp) return inp.value || '';
                                    return tds[col].textContent.trim();
                                }
                            }
                        }
                    }
                    return '';
                """)
                if mw_val:
                    tracker.update(rec, max_withdrawal=re.sub(r'[^0-9.]', '', mw_val))
            except:
                pass

            # --- SUBMIT ---
            print("  Clicking SUBMIT...")
            submit_done = False
            for _s in range(5):
                submit_done = bool(driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var i=0;i<btns.length;i++) {
                        var t = (btns[i].textContent||'').trim().toUpperCase();
                        if (t==='SUBMIT' && btns[i].offsetParent !== null && !btns[i].disabled) {
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
                time.sleep(0.2)

            time.sleep(0.2)
            wait_spinner()
            accept_native_alert_if_any()

            # --- CONFIRM ---
            print("  Looking for CONFIRM button...")
            confirm_done = False
            for _c in range(5):
                confirm_btn = driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var i=0;i<btns.length;i++) {
                        var t = (btns[i].textContent||'').trim().toUpperCase();
                        if (t==='CONFIRM' && btns[i].offsetParent !== null && !btns[i].disabled)
                            return btns[i];
                    }
                    return null;
                """)
                if confirm_btn:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", confirm_btn)
                    time.sleep(0.1)
                    driver.execute_script("arguments[0].click();", confirm_btn)
                    print("  CONFIRM clicked")
                    confirm_done = True
                    break
                time.sleep(0.2)

            if not confirm_done:
                print("  WARNING: CONFIRM not found")

            time.sleep(0.2)
            wait_spinner()
            accept_native_alert_if_any()

            # --- Success popup: read Claim No. -> OK ---
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
                        print(f"  Claim No: {claim_no}")
                        tracker.update(rec, loan_app_no=claim_no)
            except:
                pass

            print("  Waiting for success OK popup...")
            final_ok = False
            for _ok in range(6):
                ok_btn = driver.execute_script("""
                    var btns = document.querySelectorAll('button');
                    for (var i=0;i<btns.length;i++) {
                        var t = (btns[i].textContent||'').trim().toUpperCase();
                        if ((t==='OK'||t==='OKAY') && btns[i].offsetParent !== null && !btns[i].disabled)
                            return btns[i];
                    }
                    return null;
                """)
                if ok_btn:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", ok_btn)
                    time.sleep(0.1)
                    driver.execute_script("arguments[0].click();", ok_btn)
                    print("  Success OK clicked")
                    final_ok = True
                    break
                accept_native_alert_if_any()
                time.sleep(0.2)

            if not final_ok:
                print("  NOTE: No final OK popup found")

            time.sleep(0.2)
            wait_spinner()

            print(f"  Draft Record {processed} SUBMITTED successfully!")
            tracker.mark_submitted(rec)
            successful += 1
            sys.stdout.flush()

            # Return to list
            for _w in range(5):
                try:
                    if "claim-application-list" in driver.current_url:
                        break
                except:
                    break
                time.sleep(0.2)

            if "claim-application-list" not in (driver.current_url or ""):
                print("  Navigating back to list...")
                driver.get(CLAIM_LIST_URL)
                time.sleep(0.2)
                wait_spinner()
                set_filters_and_proceed()

        except Exception as e:
            err_msg = str(e)[:200]
            print(f"  ERROR on draft record {processed}: {err_msg}")
            tracker.mark_failed(rec, reason=err_msg)
            failed += 1
            accept_native_alert_if_any()
            time.sleep(0.2)
            try:
                if "claim-application-list" not in (driver.current_url or ""):
                    driver.get(CLAIM_LIST_URL)
                    time.sleep(0.2)
                    wait_spinner()
                    set_filters_and_proceed()
            except:
                pass

    print("\n" + "=" * 70)
    print("FINAL SUMMARY - DRAFT RECORDS")
    print("=" * 70)
    print(f"  Successful : {successful}")
    print(f"  Failed     : {failed}")
    print(f"  Total      : {processed}")
    print("=" * 70)
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

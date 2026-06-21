"""
record_tracker.py — IS Claim Automation
Tracks per-record results during automation run.
Prints structured RECORD_DATA log lines (parsed by dashboard_is_claim.py).
Provides CSV export.
"""

import csv
import io
import sys
from datetime import datetime

# ── In-memory store ───────────────────────────────────────────────────────────
_records = []

# Fields per record
FIELDS = [
    "record_no",
    "farmer_name",
    "account_no",
    "loan_app_no",
    "sanction_date",
    "loan_sanctioned_amt",
    "max_withdrawal",
    "max_allowed_claim",
    "applicable_is",
    "interest_days",
    "status",          # SUBMITTED / FAILED / SKIPPED
    "failure_reason",
]

LOG_PREFIX = "RECORD_DATA"


def start_record(record_no, farmer_name="", account_no="", loan_app_no=""):
    """Call when ADD is clicked for a new record. Returns a record dict."""
    rec = {f: "" for f in FIELDS}
    rec["record_no"]    = str(record_no)
    rec["farmer_name"]  = farmer_name.strip()
    rec["account_no"]   = account_no.strip()
    rec["loan_app_no"]  = loan_app_no.strip()
    rec["status"]       = "IN_PROGRESS"
    _records.append(rec)
    return rec


def update(rec, **kwargs):
    """Update fields on a record dict."""
    for k, v in kwargs.items():
        if k in FIELDS:
            rec[k] = str(v).strip()


def mark_submitted(rec):
    rec["status"] = "SUBMITTED"
    rec["failure_reason"] = ""
    _emit(rec)


def mark_failed(rec, reason=""):
    rec["status"] = "FAILED"
    rec["failure_reason"] = reason.replace("|", "/").strip()
    _emit(rec)


def mark_skipped(rec, reason=""):
    rec["status"] = "SKIPPED"
    rec["failure_reason"] = reason.replace("|", "/").strip()
    _emit(rec)


def _emit(rec):
    """Print a pipe-delimited RECORD_DATA line that dashboard_is_claim.py parses."""
    values = [rec.get(f, "") for f in FIELDS]
    line = LOG_PREFIX + "|" + "|".join(values)
    print(line, flush=True)


def get_summary():
    submitted = sum(1 for r in _records if r["status"] == "SUBMITTED")
    failed    = sum(1 for r in _records if r["status"] == "FAILED")
    skipped   = sum(1 for r in _records if r["status"] == "SKIPPED")
    return {
        "total":     len(_records),
        "submitted": submitted,
        "failed":    failed,
        "skipped":   skipped,
    }


def to_csv_string():
    """Return all records as a CSV string for download."""
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=FIELDS, extrasaction="ignore")
    writer.writeheader()
    for rec in _records:
        writer.writerow(rec)
    return output.getvalue()


def read_farmer_info(driver):
    """
    Read Name, Account No, Loan Application No from the claim form header.
    Returns (farmer_name, account_no, loan_app_no) strings.
    """
    from selenium.webdriver.common.by import By
    farmer_name = account_no = loan_app_no = ""
    try:
        # Portal shows: "Name (As per Aadhaar)  NILAVVA VASANT HALAROTTI"
        # "Account No.  30021010100006562"
        # "Loan Application No.  2529192457025464542"
        page_text = driver.find_element(By.TAG_NAME, "body").text
        import re
        m = re.search(r'Name \(As per Aadhaar\)\s*\n([^\n]+)', page_text)
        if m: farmer_name = m.group(1).strip()
        m = re.search(r'Account No\.?\s*\n([^\n]+)', page_text)
        if m: account_no = m.group(1).strip()
        m = re.search(r'Loan Application No\.?\s*\n([^\n]+)', page_text)
        if m: loan_app_no = m.group(1).strip()
    except:
        pass
    return farmer_name, account_no, loan_app_no

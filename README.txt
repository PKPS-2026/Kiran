======================================================================
  KCC LOAN AUTOMATION — FINAL WORKING VERSION
  Date: 22-May-2026
======================================================================

FILES IN THIS FOLDER:
─────────────────────
  PR_V3.py          ← Main automation script (FINAL WORKING)
  dashboard.py      ← Web dashboard to run automation & view live logs
  config.example.py ← Template for config (copy → config.py, add credentials)

HOW TO RUN:
─────────────────────
  Option 1 — Dashboard (recommended):
      python dashboard.py
      Open browser → http://localhost:5000
      Upload Excel → Click Run

  Option 2 — Direct:
      python PR_V3.py loans.xlsx

EXCEL FORMAT (required columns):
─────────────────────────────────
  | Aadhar Number | Loan Disbursal Date | Max Withdrawal Amount (INR) |
  Column names must match exactly.

WHAT THE AUTOMATION DOES:
─────────────────────────
  1. Waits for manual login (mobile, password, captcha)
  2. Applicant Details → State / District / Block / Village
  3. UPDATE & CONTINUE (Applicant Details)
  4. UPDATE & CONTINUE (Account Details)
  5. Financial Details:
       - KCC loan sanctioned date  ← via RMDP calendar picker
       - KCC SOF Eligibility amount
       - KCC Drawing Limit amount
  6. SAVE & CONTINUE → Activity tab → Loan Sanctioned fill → SAVE

KEY TECHNICAL NOTE:
─────────────────────
  Portal calendar = RMDP (React Multi-Date Picker)
  Selectors used:
    Open  : inp.closest('.rmdp-container') → svg.parentElement
    Arrows: .rmdp-arrow-container.rmdp-left / rmdp-right
    Header: .rmdp-header-values span
    Day   : .rmdp-day:not(.rmdp-deactive) span

KNOWN ISSUES (portal-side, not automation):
─────────────────────────────────────────────
  - "A loan application already submitted" → submit IS/PRI claim first
  - State/District auto-select may fail (GetHandleVerifier crash in ChromeDriver)
    → portal pre-fills these if beneficiary is already registered, safe to ignore

======================================================================

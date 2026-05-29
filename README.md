# KCC Loan Automation

Selenium-based automation for batch submission of Kisan Credit Card (KCC) loan applications on [fasalrin.gov.in](https://fasalrin.gov.in).

## Files

| File | Description |
|---|---|
| `PR_V3.py` | Core automation — fills form up to Activity tab |
| `PR_V4.py` | V4 — adds PREVIEW → CONFIRM → final submission |
| `dashboard.py` | Flask web dashboard for V3 |
| `dashboard_v4.py` | Flask web dashboard for V4 (recommended) |
| `config.example.py` | Template for ngrok/tunnel credentials |
| `requirements.txt` | Python dependencies |

## Setup

```bash
pip install -r requirements.txt
```

Copy `config.example.py` → `config.py` and fill in your ngrok credentials (optional, for remote access).

## Excel Format

Required columns (exact names):

| Aadhar Number | Loan Disbursal Date | Max Withdrawal Amount (INR) |
|---|---|---|

Optional columns: `Account Number`, `Loan Repayment Date`, `Beneficiary Name`

## Running

**Option 1 — Dashboard (recommended)**
```bash
python dashboard_v4.py
```
Open browser → `http://localhost:5000` → Upload Excel → Click Run Automation

**Option 2 — Direct**
```bash
python PR_V4.py loans.xlsx
```

## Automation Flow (V4)

1. Manual login (mobile, password, captcha)
2. Auto-detects login and starts processing each row
3. Applicant Details → State / District / Block / Village
4. UPDATE & CONTINUE (Applicant Details)
5. UPDATE & CONTINUE (Account Details)
6. Financial Details → KCC sanctioned date, SOF eligibility, drawing limit
7. SAVE & CONTINUE → Activity tab → Loan Sanctioned → SAVE
8. Term Loan Details → PREVIEW
9. **CONFIRM** submission dialog
10. Success popup → OK

## Configuration

Hardcoded for: **Ainapur village, Kagwad block, Belagavi district, Karnataka**

To change location, edit these lines in `PR_V4.py`:
```python
STATE_TYPE    = "karn";  STATE_SELECT    = "KARNATAKA"
DISTRICT_TYPE = "bel";   DISTRICT_SELECT = "Belagavi"
BLOCK_SELECT_TEXT   = "Kagwad"
VILLAGE_SELECT_TEXT = "AINAPUR"
```

## Known Issues (portal-side)

- State/District auto-select may show a ChromeDriver warning — portal pre-fills these if the beneficiary is already registered, safe to ignore
- "A loan application already submitted" → submit IS/PRI claim first
- Dates must fall within the current financial year set in the portal

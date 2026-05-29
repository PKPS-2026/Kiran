# Setup & Run Guide — KCC Loan Automation

## Requirements

- Windows 10 / 11
- Python 3.10 or above → https://www.python.org/downloads/
- Google Chrome (latest)

---

## Step 1 — Install Python packages

Open PowerShell and run:

```powershell
cd "C:\Users\PKPS AINAPUR\Downloads\KCC_Final\KCC-Loan-Automation-29-05-2026"
python -m pip install -r requirements.txt
```

---

## Step 2 — Prepare your Excel file

Place your Excel file anywhere. Required columns (exact names):

| Aadhar Number | Loan Disbursal Date | Max Withdrawal Amount (INR) |
|---|---|---|

Optional columns: `Account Number`, `Loan Repayment Date`, `Beneficiary Name`

---

## Step 3 — Run the Dashboard (V4 — Recommended)

```powershell
cd "C:\Users\PKPS AINAPUR\Downloads\KCC_Final\KCC-Loan-Automation-29-05-2026\v4"
python dashboard_v4.py
```

Browser opens automatically → **http://localhost:5000**

---

## Step 4 — In the Dashboard

1. Upload your Excel file (drag & drop or click)
2. Click **Run Automation**
3. Chrome opens → **manually login** (mobile, password, captcha, LOGIN)
4. Script takes over automatically

---

## Full Automation Flow (V4)

```
Login detected
  → Aadhaar entered → Fetch
  → Account selected
  → State / District / Block / Village filled
  → UPDATE & CONTINUE  (Applicant Details)
  → UPDATE & CONTINUE  (Account Details)
  → KCC Sanctioned Date filled
  → SOF Eligibility + Drawing Limit filled
  → SAVE & CONTINUE
  → Loan Sanctioned filled (Activity tab)
  → Activity SAVE & CONTINUE
  → PREVIEW clicked
  → CONFIRM clicked
  → "Loan application submitted successfully" → OK
  → Next record...
```

---

## Run V3 (without final submit)

```powershell
cd "C:\Users\PKPS AINAPUR\Downloads\KCC_Final\KCC-Loan-Automation-29-05-2026\v3"
python dashboard.py
```

---

## Run directly without Dashboard

```powershell
cd "C:\Users\PKPS AINAPUR\Downloads\KCC_Final\KCC-Loan-Automation-29-05-2026\v4"
python PR_V4.py loans.xlsx
```

---

## Every Time You Run

```powershell
cd "C:\Users\PKPS AINAPUR\Downloads\KCC_Final\KCC-Loan-Automation-29-05-2026\v4"
python dashboard_v4.py
```

Open → http://localhost:5000

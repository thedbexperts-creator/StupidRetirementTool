# 🏠 Retirement Planner

**Version 1.0.7**

A free, offline retirement planning tool that runs locally on your computer.
No accounts, no subscriptions, no data ever leaves your machine.

> ⚠️ **DISCLAIMER:** This is a planning model, not financial advice. It is
> useful for comparing strategies against each other — claim early vs. late,
> convert to Roth vs. don't, spend more vs. leave a legacy. It is not a
> substitute for a CPA or a fee-only fiduciary planner, and it should not be the
> only input to an irreversible decision.
>
> **Please read [ASSUMPTIONS.md](ASSUMPTIONS.md)** before trusting a number. It
> documents exactly what is modelled and — more importantly — what is not.

---

## Features

- **Cash Flow Plan** — every dollar that moves in a given year, named and
  grouped: *"Convert $211,228 from 401k (Person 1) → Roth IRA (Person 1)"*,
  *"Sell $43,163 from Brokerage to pay the conversion tax"*. Money in minus
  money out reconciles to that year's surplus or shortfall. Exports to CSV.
- **Income Projection** — year-by-year income and portfolio balance, with an
  **after-tax value** alongside the raw balance, because a dollar in a
  traditional 401(k) is not a dollar.
- **Social Security Optimizer** — every combination of claiming ages for one or
  two people, scored on after-tax ending value.
- **Roth Conversion Optimizer** — bracket-fill strategies that actually fund the
  conversion tax and respect the ACA subsidy cliff, plus a **lifetime optimizer**
  that searches how hard to convert *and when to stop*, ranked on after-tax value.
- **Tax Analysis** — 2026 federal brackets, long-term capital gains, the 3.8%
  Net Investment Income Tax, IRMAA surcharges, and income tax for **all 50
  states**.
- **ACA Premium Tax Credits** — post-2025 rules including the restored 400% FPL
  subsidy cliff, and a guard that stops a Roth conversion from silently
  destroying your subsidy.
- **Monte Carlo Stress Test** — lognormal returns, optional dynamic-spending
  guardrails, and optional inflation volatility.
- **Scenario Comparison** — save and compare multiple plans side by side.
- **Spending Goals** — binary-search engine that finds what you can safely spend
  to hit a target end balance.
- **Flexible Accounts** — traditional, Roth, taxable, savings, and **HSA**
  (spent tax-free against medical costs, blocked after Medicare age).
- **Part-Time Income** — phased-retirement earnings with an age window, taxed as
  real earned income including FICA and ACA MAGI effects.
- **Survivor Scenario** — models the death of a spouse, including the switch to
  single-filer brackets.
- **NYS Tools** — ERS Tier 3/4/5/6 pension calculator using the official NYSLRS
  formulas and reduction tables, plus a sick-leave / NYSHIP credit calculator.

---

## Quick Start

### Option A — Python (recommended, works on Windows & Mac)

**Windows:**

1. Install Python from [python.org](https://www.python.org/downloads/) — check "Add Python to PATH"
2. Double-click `Start RetirementPlanner.bat`

**Mac:**

1. Python 3 is usually pre-installed. If not: `brew install python`
2. Double-click `Start RetirementPlanner.command` *(First time: right-click → Open to bypass Gatekeeper)*

Your browser opens automatically at `http://localhost:5000`

### Option B — Standalone App (no Python needed)

**Windows:** Run `build_exe.bat` once → share the resulting `RetirementPlanner.exe`

**Mac:** Run `bash build_mac_app.sh` once → share the resulting `RetirementPlanner.app`

---

## Your Data

- All data is stored locally in `profile.json` next to the app
- Nothing is sent to any server or external service
- The local server only accepts requests from `localhost` and refuses
  cross-site writes, so other websites in your browser cannot read or overwrite
  your profile
- Use **Export** to back up your profile or move it between computers

---

## Development

Run the test suite (no dependencies, ~0.5 seconds):

```bash
python3 test_app.py
```

73 tests pin published figures (SSA reduction percentages, NYSLRS reduction
tables and benefit formulas, IRS 2026 brackets, ACA applicable percentages) and
engine invariants (cash-flow reconciliation, conversion funding, optimizer
scoring). They run automatically on push via GitHub Actions, which also boots
the server, checks every endpoint, and asserts that cross-site writes are still
refused.

---

## Files

| File | Purpose |
| --- | --- |
| `app.py` | Backend — projection engine, tax calculations, Monte Carlo |
| `index.html` | Web UI — all tabs and charts |
| `test_app.py` | Regression test suite |
| `ASSUMPTIONS.md` | What is and is not modelled — **read this** |
| `CHANGELOG.md` | Version history |
| `.github/workflows/tests.yml` | CI — runs the suite on every push |
| `Start RetirementPlanner.bat` | Windows launcher |
| `Start RetirementPlanner.command` | Mac launcher |
| `build_exe.bat` | Build a standalone Windows .exe |
| `build_mac_app.sh` | Build a standalone Mac .app |
| `RetirementPlanner.spec` | PyInstaller config (Windows) |
| `RetirementPlanner_mac.spec` | PyInstaller config (Mac) |

---

## Requirements

- Python 3.8 or higher (no third-party packages required — uses only the standard library)

---

## License

Do whatever you want with it. Just don't blame me when it's wrong.

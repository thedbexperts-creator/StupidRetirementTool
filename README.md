# 🏠 Retirement Planner

**Version 1.0.0**

A free, offline retirement planning tool that runs locally on your computer. No accounts, no subscriptions, no data ever leaves your machine.

> ⚠️ **DISCLAIMER:** This software was written by a moron with no financial training who just watched a bunch of YouTube videos. It has been made available for testing purposes only. Anyone who would make real world decisions based on this tool is a bigger moron than the idiot who vibed it up. Use this tool at your own risk. No warranties. No promises. **This is not financial advice.**

---

## Features

- **Income Projection** — Year-by-year retirement income and portfolio balance
- **Withdrawal Plan** — Where your money comes from each year (which accounts get tapped and when)
- **Social Security Optimizer** — Find the optimal claiming ages for one or two people
- **Roth Conversion Optimizer** — Model conversion strategies to minimize lifetime taxes
- **Tax Analysis** — Annual federal + state tax burden; supports all 50 states (no-tax, flat-rate, and progressive brackets) plus a custom rate option
- **Monte Carlo Stress Test** — Run thousands of simulations to find your plan's success rate
- **Scenario Comparison** — Save and compare multiple retirement plans side by side
- **Spending Goals** — Binary-search engine that finds what you can safely spend to hit a target end balance
- **NYS Sick Leave Calculator** — Models NYSHIP health insurance credit and §41-j pension service credit for NYS employees
- **Flexible Accounts & Pensions** — Add or remove any number of investment accounts and pensions; each can be assigned to either person with individual tax-exempt flags and COLA settings

---

## Quick Start

### Option A — Python (recommended, works on Windows & Mac)

**Windows:**
1. Install Python from [python.org](https://www.python.org/downloads/) — check "Add Python to PATH"
2. Double-click `Start RetirementPlanner.bat`

**Mac:**
1. Python 3 is usually pre-installed. If not: `brew install python`
2. Double-click `Start RetirementPlanner.command`
   *(First time: right-click → Open to bypass Gatekeeper)*

Your browser opens automatically at `http://localhost:5000`

### Option B — Standalone App (no Python needed)

**Windows:** Run `build_exe.bat` once → share the resulting `RetirementPlanner.exe`

**Mac:** Run `bash build_mac_app.sh` once → share the resulting `RetirementPlanner.app`

---

## Your Data

- All data is stored locally in `profile.json` next to the app
- Nothing is sent to any server or external service
- Use **Export** to back up your profile or move it between computers
- Use **Import** to restore a saved profile

---

## Files

| File | Purpose |
|------|---------|
| `app.py` | Python backend — projection engine, tax calculations, Monte Carlo |
| `index.html` | Web UI — all tabs and charts |
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

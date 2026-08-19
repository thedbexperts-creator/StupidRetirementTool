# Changelog

All notable changes to Retirement Planner will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [1.0.7] - 2026-08-19

### Added — the after-tax value is now visible
- 1.0.6 computed `after_tax_balance` and scored the Social Security optimizer on it, but **never displayed it** — the number that changes the Roth conclusion was hidden. It now appears as a headline metric on the results dashboard, as a row in the scenario comparison, in the printed report, and as an insight explaining how much of the final balance is deferred tax rather than money.

### Added — lifetime Roth conversion optimizer
- The existing strategy is greedy: it fills a bracket each year with no view of the future. The real question is *when to stop* — convert hard in the low-income years between retiring and RMDs, then quit.
- New `/api/optimize_roth` endpoint and a **Lifetime Conversion Optimizer** panel on the Roth tab. It grid-searches strategy × conversion stop-age and ranks on **after-tax** ending value, reporting total converted, conversion tax, ACA subsidy lost, and shortfall years for each combination. Runs in well under a second.
- New profile options `roth_start_age` / `roth_end_age` bound the conversion window.
- Behaviour matches financial theory: converting becomes more valuable as the assumed heir tax rate rises (a $65k gain at a 22% heir rate versus $391k at 37%), and the recommended stop age lands just before RMDs begin.
- When converting genuinely does not pay, the panel says so plainly rather than recommending a conversion anyway.

### Added — CI, documentation, and an HSA option
- **GitHub Actions workflow** runs the suite on every push and pull request against Python 3.8 and 3.12, boots the server to check every endpoint responds, and asserts that a cross-site write is still refused with a 403 — so the CSRF protection added in 1.0.2 cannot silently regress. Verified locally before committing.
- **`ASSUMPTIONS.md`** — a plain-language account of what the tool does and does not model: no relocation, no QCDs, no windfalls or home sale, simplified PFRS, conservative state pension exclusions, IRMAA applied on current-year rather than two-years-prior income, no historical sequence backtesting, and more. The tool is now accurate enough that the *unmodelled* parts are the real risk.
- **README** refreshed from 1.0.2 to current, with the feature list, a development section, and a pointer to the assumptions doc. `FIXES.md` now redirects to the changelog.
- New `hsa_preserve` option to keep an HSA compounding as a late-life tax-free reserve instead of spending it against medical costs as they arise.

### Changed
- Test suite expanded from 68 to **73 tests**, covering the conversion window, optimizer ranking and baseline, the heir-rate sensitivity, and HSA preservation.

---

## [1.0.6] - 2026-08-19

### Added — after-tax ending balance
- Both optimizers previously scored plans on the **pre-tax** ending balance, treating $1 in a traditional 401(k) as equal to $1 in a Roth even though the traditional dollar still owes ordinary income tax — to the retiree or to heirs under the SECURE Act 10-year rule. This systematically understated the case for Roth conversions, the mirror image of the double-counting bug fixed in 1.0.4.
- Every projected year now reports `after_tax_balance`: traditional balances discounted by an assumed heir rate, Roth and HSA at full value, and unrealized gains in taxable accounts taxed only if heirs do **not** receive a stepped-up basis (they do by default under current law). Configure via `estate.heir_tax_rate`, `estate.heir_ltcg_rate` and `estate.step_up_basis`.
- The Social Security optimizer now scores on after-tax value. In a test profile this narrowed the apparent gap between "never convert" and "fill the 22% bracket" from **$722k to $212k** — the comparison is now honest rather than flattering the do-nothing strategy.

### Added — HSA accounts
- New `hsa` account type, the only triple-tax-advantaged vehicle: contributions are pre-tax, growth is untaxed, and withdrawals for qualified medical costs are tax-free.
- The engine spends the HSA against each year's medical bill **first**, keeping those dollars out of taxable income entirely. Anything left is treated as a true last resort after Roth, where a post-65 non-medical withdrawal is simply ordinary income.
- HSA contributions reduce MAGI, which matters directly for the ACA cliff added in 1.0.5 — an HSA contribution can be exactly what keeps a pre-Medicare household under 400% FPL.
- Contributions are correctly barred once the owner reaches Medicare age, and HSAs are never subject to RMDs.

### Added — part-time / phased retirement income
- Each person can now earn part-time income after their official retirement date, with a configurable age window (`part_time_income`, `part_time_start_age`, `part_time_end_age`).
- It is modelled as genuine **earned** income: it pays FICA, lands in AGI, and counts toward ACA MAGI. In testing, $40,000 of consulting income cut the first-year portfolio withdrawal from $90,800 to $52,002 — but also pushed the household from 1.16x to 3.22x FPL, roughly halving the premium tax credit. Both effects are now visible instead of only the first.

### Changed
- Test suite expanded from 54 to **68 tests**, covering after-tax valuation, HSA ordering and tax treatment, the Medicare contribution cut-off, and the part-time income window and its ACA interaction.
- Profile tab gains part-time income fields for each person; the account editor offers HSA as a type.

---

## [1.0.5] - 2026-08-19

### Fixed — 18 states were silently taxed as New York
- `get_state_tax_config` fell back to New York for any state code it did not recognise. Alabama, Arkansas, Delaware, Hawaii, Idaho, Kansas, Louisiana, Mississippi, Montana, Nebraska, New Mexico, North Dakota, Ohio, Oklahoma, Rhode Island, South Carolina, Virginia and West Virginia all received New York's progressive brackets **and** New York's $20,000 pension exclusion, with no warning — despite the README claiming all 50 states were supported. All 18 now have real 2026 brackets, standard deductions and Social Security treatment (source: Tax Foundation, *State Individual Income Tax Rates and Brackets, 2026*), and an unrecognised code now falls back to a neutral no-tax configuration instead of impersonating a high-tax state.

### Added — ACA premium tax credit (and the subsidy cliff)
- The enhanced ARPA/IRA subsidies expired 1 January 2026, so the **400% FPL cliff is back**. The engine previously charged the full benchmark premium with no credit at all, badly overstating pre-Medicare healthcare costs for most early retirees.
- Premium tax credits are now modelled on the 2026 applicable-percentage table (IRS Rev. Proc. 2025-25) against 2025 HHS poverty guidelines, resolved inside the withdrawal loop so the credit and the spending need converge together.
- **Roth conversions now respect the cliff.** A conversion is MAGI: cross 400% FPL and the entire credit disappears, which routinely costs far more than a bracket-fill saves. Conversions are capped at the cliff by default (`roth_respect_aca_cliff`, set it to `false` to opt out), and any subsidy still lost to a conversion is reported as `aca_subsidy_lost_to_conversion` rather than ignored. In a test profile the guard preserved **$155,000** of lifetime subsidy and about **$1.08M** of ending balance.
- New per-year fields: `aca_gross_premium`, `aca_subsidy`, `aca_fpl_ratio`, `aca_over_cliff`. The Cash Flow Plan shows the full premium and the credit as separate lines.

### Added — regression test suite
- `test_app.py`: 54 tests, standard library only, runs in under a second (`python3 test_app.py`). Every assertion pins either an officially published figure (SSA reduction percentages, NYSLRS reduction tables and benefit formulas, IRS 2026 brackets and NIIT thresholds, ACA applicable percentages) or an invariant that a past bug violated — cash-flow reconciliation, conversion funding, the SS optimizer score, and the New York fallback. There were previously no tests of any kind.

### Added — other
- **Net Investment Income Tax**: 3.8% on the lesser of investment income or MAGI above $250,000 (MFJ) / $200,000 (single), thresholds unindexed as in statute.
- **Inflation is now a modelled risk in Monte Carlo.** Set `inflation_vol` to draw each year's inflation around the planning assumption; the nominal spending need scales along each path. Defaults to 0, which reproduces prior behaviour.

### Changed
- Federal tables updated from 2024 to **2026** actuals (Rev. Proc. 2025-32): MFJ standard deduction $32,200, single $16,100, and the 2026 ordinary and long-term capital gains brackets. The inflation anchor moved from 2024 to 2026, so brackets are no longer projected forward from two-year-old figures.
- `validate_profile` now rejects `NaN` and `Infinity` anywhere in the payload. These previously passed validation and were written to `profile.json`, which is invalid strict JSON and silently corrupted every later calculation.

### Note
- The Monte Carlo variance-drag concern raised in review had already been fixed in 1.0.2 (returns are lognormal, so the drag is applied exactly once). A test now pins that behaviour so it cannot regress.

---

## [1.0.4] - 2026-08-19

### Added — Cash Flow Plan (every dollar that moves)
- **"Withdrawal Plan" is now the "Cash Flow Plan."** The tab previously showed only money coming *out* of the portfolio. It now accounts for every dollar that moves in a given year, grouped into three sections:
  - **Money In** — each pension listed by its own name and owner (e.g. *"NYS ERS (Dave)"*), Social Security per person, wages per person, required minimum distributions, and discretionary portfolio withdrawals.
  - **Internal Moves** — payroll contributions, Roth conversions (source account → destination account), how the conversion tax was funded, and surplus reinvestment. These shift money between accounts rather than in or out of the household.
  - **Money Out** — living expenses, medical costs, ACA premiums, long-term care, the IRMAA surcharge, one-time expense shocks, and federal / state / FICA taxes itemised separately.
- **Reconciliation line.** Each year shows `Money in − Money out = surplus or shortfall`, so the numbers visibly tie out. Verified exact (to the dollar) across every projected year in four scenarios: active Roth conversions, still-working years with wages and FICA, portfolio shortfall, and RMD-heavy years with long-term care and one-time shocks.
- **CSV export extended** with `Flow`, plus per-year `Money In`, `Money Out`, `Net` and `Shortfall` columns; downloads as `cash-flow-plan-<date>.csv`.

### Changed
- New per-year API fields: `flow_total_in`, `flow_total_out`, `flow_net`. Each entry in `cash_flow_plan` now carries a `flow` field (`in` / `internal` / `out`).
- The Roth conversion tax is intentionally **not** listed under Money Out — the Internal Moves section already itemises exactly how it was paid (sold from a named account and/or withheld from the conversion). Listing it in both places double-counted it and broke the reconciliation.

---

## [1.0.3] - 2026-08-18

### Added — Itemised withdrawal plan
- **Step-by-step action plan per year.** The Withdrawal Plan tab now names the exact accounts for every money movement instead of reporting lump sums — e.g. *"Convert $211,228 from 401k (Person 1) → deposit into Roth IRA (Person 1)"*, *"Sell $43,163 from Brokerage to pay the conversion tax"*, *"Withdraw $90,836 from Brokerage to fund spending"*. Expand any year to see it.
- **RMDs split from discretionary withdrawals.** When one account supplies both a required distribution and additional spending money, they are now separate line items. Previously a single combined figure hid which part was forced: a test year showed one `$175,769` draw that is now itemised as a `$63,291` RMD plus a `$112,478` discretionary withdrawal.
- **Roth conversion source → destination tracking.** The engine records which traditional account each converted dollar leaves and which Roth account receives it, rather than a single `roth_conversion` total.
- **Conversion tax funding is shown.** Each year states whether the conversion tax was paid by selling from a named cash/brokerage account or withheld from the conversion itself (in which case only the remainder reaches the Roth).
- **Surplus reinvestment destination is named** instead of reported as an unattributed total.
- **Two views + CSV export.** A toggle switches the year detail between a plain-English numbered action list and a structured table (Action / From / To / Amount / Why). A CSV button exports the full year-by-year itemisation for spreadsheets.

### Changed
- New per-year API fields on retirement rows: `cash_flow_plan` (ordered action list), `rmd_by_account`, `spend_by_account`, `roth_conv_from`, `roth_conv_to`, `roth_conv_tax_cash`, `roth_conv_withheld`, and `reinvest_account`. Existing fields are unchanged, and the itemised amounts reconcile exactly to `withdrawal_total`, `rmd_total`, and `roth_conversion` (verified across every projected year).
- Accumulation-phase rows carry an empty `cash_flow_plan` so the UI can rely on the key being present.

---

## [1.0.2] - 2026-08-18

### Fixed — Roth conversions
- **Conversion tax was never paid.** The engine calculated the tax on a Roth conversion, reported it, and then never debited it from any account — so converting was free money and the optimizer always recommended converting as hard as possible. On a $2.2M test portfolio this overstated the ending balance by ~$2.0M. The tax is now funded from taxable/savings accounts where available, and withheld from the conversion itself otherwise; a conversion the household cannot pay for is scaled back.
- **Conversions with no Roth account destroyed the portfolio.** The traditional balance was debited and, with no Roth account to receive it, the money simply vanished. In a test profile with the Roth rows deleted this drove the ending balance from $9.48M to $0. Conversions are now skipped when there is no destination account, and the Roth tab says why.
- **Conversions never ran for single-person profiles.** A disabled person 2 was modeled as retiring in year 9999, so the "both retired" gate never opened and the Roth tab silently produced nothing.

### Fixed — projection engine
- **A working spouse's salary was counted twice.** Gross wages were fully available to fund expenses *and* fully contributed to accounts. Contributions are now funded out of salary, capped at earned income, and pre-tax (traditional) contributions correctly reduce taxable income.
- **A disabled person 2 contributed forever.** Contributions to their accounts continued for the whole projection — $628k of phantom money by age 80 in a test case.
- **Person 2's life expectancy was ignored.** It only sized the loop; the shorter-lived spouse kept collecting Social Security and incurring couple-level expenses to the end of the run. Each person now actually dies at their life expectancy, which switches the projection to survivor rules and single filing status.
- **Taxable contributions during the retirement phase did not add to cost basis**, so every such dollar was later taxed as if it were pure capital gain.
- **Capital gains were omitted from Social Security provisional income** (they are included per IRS) and from the bracket headroom used to size Roth conversions.
- **Savings/HYSA interest was only taxed when withdrawn**, letting cash compound tax-deferred. Interest is now taxed in the year it is earned and credited to basis so it is not taxed twice.
- **IRMAA was wrong in both directions.** Thresholds and premiums were frozen at 2024 nominal values while income inflated, so every projection drifted into the top tier; and the MAGI proxy counted only pensions and Social Security, missing the withdrawals, RMDs and conversions that actually trigger the surcharge. It now uses the real MAGI from two years prior — the SSA lookback — with indexed thresholds.
- **The Social Security optimizer double-counted.** Its score added lifetime SS to the ending balance, but benefits already flow into that balance. The score is now the projected ending portfolio value, and any scenario that runs out of money ranks last.
- **The NYS pension formulas were wrong.** NYSLRS credits 1.66% per year below 20 years of service (not 1.75%); Tiers 3/4/5 credit 1.5% for years past 30 (previously a flat 2%); Tier 6 has no reduced tier past 30 (previously 1.5%). The early-retirement reduction tables were already correct.
- **RMDs stopped shrinking at age 95.** The Uniform Lifetime Table now runs to 120, so long life expectancies get the right divisor.
- **Shortfalls were overstated** when the portfolio ran dry — the gross-up loop kept inflating its target against empty accounts. Shortfall is now the true unfunded after-tax spending gap.
- **The asset-allocation glide path overrode every account**, including cash savings. It now applies only to invested accounts.
- **The FICA wage base was two years stale**, indexed from the profile's current year rather than from its 2024 base.
- **FICA silently vanished from `total_tax`** in any year with a Roth conversion.
- **The state pension/IRA exclusion was applied against wages, interest and capital gains** instead of only pension and tax-deferred income. NY's exclusion also starts at 59½, not 60.
- **Monte Carlo mixed log-space and simple returns** — the σ²/2 correction was subtracted from an arithmetic return and then applied as one, systematically understating growth. Returns are now properly log-normal. Guardrail triggers are also no longer counted in years where spending was already pinned at the floor or ceiling, and the initial withdrawal rate is anchored to the first year money is actually drawn.

### Security
- **Cross-site writes to `/api/save` (CSRF) are now blocked.** Removing the wildcard CORS header in 1.0.1 stopped other sites *reading* the profile, but an HTML form POST is a "simple request" that needs no preflight, so a malicious page could still overwrite or destroy `profile.json` while the app was running. POSTs now require a same-origin `Origin`/`Sec-Fetch-Site` and a JSON content type, which forms cannot send.
- A missing `Host` header no longer bypasses the DNS-rebinding check.
- `/api/save` validates the profile — including that it survives a projection — before replacing a good `profile.json` with a broken one.
- Errors are logged with a full traceback to the server's stderr while the client still gets only a short message. Previously the traceback was discarded at both ends, making failures invisible.

### Added
- `APP_VERSION` in `app.py` is the single source of truth for the version, served at `/api/version` and shown in the topbar. (The 1.0.0 changelog claimed this; it had never actually been implemented.)
- Malformed profile fields (strings like `"1,234"`, `null`, wrong types) are coerced or dropped instead of throwing.

---

## [1.0.1] - 2026-08-14

### Security
- Removed the wildcard `Access-Control-Allow-Origin: *` header. While the app was running, any website open in the browser could read the full profile from `GET /api/profile` or overwrite `profile.json` via `POST /api/save`. The local server no longer grants any cross-origin access.
- Added `Host` header validation so the server only answers requests addressed to `localhost` / `127.0.0.1` (DNS-rebinding protection).
- Stopped returning Python stack traces (`traceback.format_exc()`) in API error responses; errors now return only a short message.
- Capped POST request bodies at 5 MB (returns `413`) to prevent memory-exhaustion.
- `profile.json` writes are now serialized with a lock and written atomically (temp file + `os.replace`) to avoid corruption under the threaded server.

### Fixed
- **Spousal Social Security reduction** — corrected to the SSA rule (25/36 of 1% per month for the first 36 months, then 5/12 of 1% beyond). The previous factor understated the early-claiming reduction roughly threefold (~9% instead of 25% at 36 months early).
- **Social Security taxation for single filers** — after a spouse dies, provisional-income thresholds now use the single amounts ($25,000 / $34,000) instead of the married amounts ($32,000 / $44,000), and the second-tier add-on uses the correct `min(50% of benefits, cap)`.
- **NYS pension early-retirement reductions** — replaced the flat 6⅔%/yr approximation with the official NYS Comptroller reduction tables for ERS Tier 3/4, Tier 5, and Tier 6, interpolated by month (reproduces OSC's published half-year examples exactly). The 30-years-of-service exemption now correctly applies only to Tier 2/3/4, not Tier 5 or Tier 6.
- **Social Security indexing** — benefits are now indexed by COLA from the current year, keeping them nominal-consistent with inflated expenses (previously the FRA benefit only grew after the claiming age, understating SS for anyone years away from claiming).
- **RMD required-beginning age** — now follows SECURE 2.0: 73 for those born 1951–1959, 75 for those born 1960 or later (previously hardcoded to 73).
- **Monte Carlo** — corrected an off-by-one in percentile indexing (nearest-rank), and the dynamic-spending guardrails no longer disable themselves when the first retirement year has no portfolio withdrawal.

---

## [1.0.0] - 2026-06-27

### Added
- **Variable pensions** — add or remove any number of pensions per profile; each can be assigned to either person with its own name, monthly benefit, survivor benefit, start age, COLA, and state-tax-exempt flag. Automatically migrates existing profiles from the old two-pension format.
- **Variable investment accounts** — add or remove account rows directly from the Profile tab; each row has a Remove button and a new account can be added with one click.
- **Multi-state tax support** — state income tax now covers all 50 states: no-tax states (FL, TX, NV, etc.), flat-rate states (AZ, CO, PA, etc.), and progressive-bracket states (NY, CA, NJ, etc.). A "Custom" option accepts any flat rate. State is selected from a dropdown on the Profile tab.
- **Version number** — `APP_VERSION` constant in `app.py` is the single source of truth; served via `/api/version` and displayed live in the topbar.
- **Warning disclaimer** — startup modal requiring acknowledgement before use, plus a persistent red banner on all screens.
- **NYS Pension Calculator tab** — moved from the Profile tab into its own dedicated sidebar tab under NYS Tools.
- **Cross-platform distribution** — Windows `.bat` launcher, Mac `.command` launcher, PyInstaller build scripts for standalone `.exe` and `.app`, and a `RetirementPlanner.zip` for easy sharing.
- **README.md** and **CHANGELOG.md** added for GitHub.
- **`.gitignore`** excluding `profile.json`, build artifacts, and OS junk.

### Changed
- Default profile values zeroed out so new users start with a blank slate (no personal data in the defaults).
- `nys_tax` / `nys_taxable` renamed to `state_tax` / `st_taxable` throughout the projection engine and UI.
- `pension1` / `pension2` profile keys consolidated into a `pensions: []` array.
- Income chart pension labels now reflect actual pension names from the profile.
- "NYS Tax" label in Tax Analysis renamed to "State Tax".

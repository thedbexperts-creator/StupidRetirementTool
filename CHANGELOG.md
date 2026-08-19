# Changelog

All notable changes to Retirement Planner will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

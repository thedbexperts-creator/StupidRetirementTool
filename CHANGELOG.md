# Changelog

All notable changes to Retirement Planner will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

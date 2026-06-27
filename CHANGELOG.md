# Changelog

All notable changes to Retirement Planner will be documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

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

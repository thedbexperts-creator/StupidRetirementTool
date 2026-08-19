# Fixes applied to Retirement Planner (backend `app.py`)

This is a corrected build of the original StupidRetirementTool. Every change is
in `app.py`; `index.html` is unchanged. All fixes were verified against official
sources (SSA rules, IRS Pub. 915 thresholds, NYS Comptroller reduction tables)
and with an end-to-end run of every API endpoint.

## Security

1. **Cross-origin data exposure (the serious one).** The server sent
   `Access-Control-Allow-Origin: *` on every response while serving your full
   financial profile at `GET /api/profile` and accepting overwrites at
   `POST /api/save`. Any website open in your browser could read or overwrite
   `profile.json`. **Fix:** removed the wildcard CORS header entirely (the app
   is same-origin, so it never needed it) and stripped CORS from `OPTIONS`.

2. **DNS-rebinding guard.** Added a `Host:` header check (`_host_ok`) so the
   server only answers requests addressed to `localhost`/`127.0.0.1`.

3. **Information disclosure.** Error responses returned full Python stack traces
   (`traceback.format_exc()`) to the client. **Fix:** removed from all five
   handlers; errors now return only a short message.

4. **Unbounded request body.** `do_POST` read `Content-Length` bytes with no
   limit (memory-exhaustion DoS). **Fix:** 5 MB cap (`413` if exceeded) plus
   validation of the `Content-Length` value.

5. **Profile-file corruption.** `ThreadingHTTPServer` read/wrote `profile.json`
   with no lock. **Fix:** a `threading.Lock` serializes access and saves are now
   atomic (write temp file, then `os.replace`).

## Math / modeling

6. **Spousal Social Security reduction was ~3x too small.** Used `25/10000` per
   month (≈9% at 36 months) instead of the SSA rule of 25/36 of 1% per month.
   **Fix:** correct rule — 25% reduction at 36 months early, then 5/12 of 1% per
   month beyond. Verified: 25% @ age 64, 35% @ age 62 (FRA 67).

7. **SS taxation used MFJ thresholds for single filers.** After a spouse dies
   (single filer) the $32k/$44k thresholds understated taxable SS. **Fix:**
   `taxable_ss_portion` now takes filing status — Single uses $25k/$34k and a
   $4,500 second-tier cap; the add-on is `min(0.5·SS, cap)` rather than a flat
   $6,000.

8. **NYS pension early-retirement reduction didn't match NYSLRS.** A flat
   `(NRA-age)/15` overstated the penalty (e.g. 46.7% at age 55 vs. the official
   27% for Tier 4). **Fix:** replaced with the official NYS Comptroller reduction
   tables (Tier 3/4, Tier 5, Tier 6), interpolated by month. Reproduces OSC's
   published half-year examples exactly (16.5% / 20.83% / 29.25% at age 58½).
   Also corrected: the 30-years-of-service exemption applies only to Tier 2/3/4,
   **not** Tier 5 or Tier 6 (the original code wrongly exempted all tiers).

9. **Social Security wasn't indexed before claiming.** The FRA benefit was only
   grown by COLA *after* claiming, understating SS for anyone years from
   claiming. **Fix:** SS is now indexed from the current year so it's
   nominal-consistent with inflated expenses.

10. **RMD age hardcoded to 73.** SECURE 2.0 sets the required-beginning age to 75
    for anyone born 1960 or later. **Fix:** `rmd_start_age(birth_year)` returns
    73 or 75 and is applied per account owner.

11. **Monte Carlo percentile off-by-one.** `round(n·pct/100)` could over-index by
    one. **Fix:** proper nearest-rank `ceil(n·pct/100)-1`.

12. **Guardrails silently disabled when year-one withdrawal was $0.** **Fix:**
    the initial withdrawal rate is based on the first *positive* withdrawal.

## Not changed (documented simplifications)

PFRS is still modeled as a simplified 2%/yr (max 60%) plan without the special
20/25-year early-retirement rules. Default taxable cost basis is still assumed at
80% of balance. Tax-bracket inflation (2.5%) and SS COLA (2.4%) remain fixed
assumptions decoupled from the user's inflation input. These are reasonable for a
planning estimate but are approximations.

Still not modeled: brokerage dividends and capital-gain distributions (taxable
accounts defer all tax until sale); survivor Social Security when the deceased
had not yet claimed; RMDs on inherited accounts; the Tier 6 FAS 10%-per-year
growth cap; and the spousal-benefit rule that a partner must have filed before
a spousal benefit can begin.

---

# Round 2 — fixes applied 2026-08-18 (v1.0.2)

A second review found further defects, all in `app.py` unless noted. Every fix
below was verified by running the engine before and after. See `CHANGELOG.md`
for the full list; the load-bearing ones:

## Roth conversions (all three were severe)

13. **The conversion tax was computed, reported, and never actually paid.**
    No account was ever debited for it, so converting was free money and the
    optimizer maximized it. Measured on a $2.2M portfolio: `fill_24` reported
    an ending balance $2.0M *higher* than `none`. The tax is now paid from
    taxable/savings first (the optimal real-world approach) and withheld from
    the conversion when there is no outside cash; an unaffordable conversion is
    scaled back by bisection.

14. **A conversion with no Roth account deleted the money.** The traditional
    balance was debited unconditionally but only credited `if roth_keys:`.
    With the Roth rows removed from a test profile the ending balance went from
    $9.48M to **$0**. Conversions are now skipped with a note surfaced in the UI.

15. **Conversions never fired for single-person profiles.** A disabled person 2
    was given a retirement year of 9999, so `both_ret` was never true.

## Engine

16. **Working salary was spent twice** — fully available for expenses *and*
    fully contributed. Contributions now come out of salary, are capped at
    earned income, and pre-tax ones reduce taxable income.
17. **A disabled person 2 kept contributing forever** (same 9999 sentinel).
18. **Person 2's life expectancy was ignored** — it bounded the loop but never
    killed them, so they collected SS and incurred expenses to the end.
19. **Retirement-phase contributions to taxable accounts skipped basis**,
    unlike the accumulation phase.
20. **Capital gains were left out of SS provisional income** and out of the
    bracket headroom used to size conversions.
21. **HYSA interest was only taxed on withdrawal.** Now taxed as earned and
    credited to basis (savings basis defaults to the full balance, not 80%).
22. **IRMAA** used un-indexed 2024 thresholds against inflated income (everyone
    reached the top tier eventually) and a MAGI proxy that excluded the
    withdrawals and conversions that actually cause the surcharge. Now uses the
    real MAGI from two years prior with indexed thresholds and premiums.
23. **The SS optimizer's score double-counted benefits** (`lifetime SS + final
    balance − tax`, but SS already flows into the balance). Score is now the
    ending balance; scenarios that deplete rank last.
24. **NYS benefit formulas were wrong** — 1.66%/yr below 20 years of service,
    not 1.75%; 1.5% past 30 years for Tiers 3/4/5; and no 1.5% tier for Tier 6.
    Verified: Tier 4 @35 yrs = 67.5% of FAS, Tier 6 @25 yrs = 45%.
    (The reduction tables from round 1 were correct and are unchanged.)
25. **The RMD table stopped at 95**, defaulting to an 8.9 divisor forever after.
    Extended to 120.
26. **Shortfalls were inflated** by the gross-up loop iterating against empty
    accounts; now the true unfunded after-tax gap.
27. **The glide path overrode the cash/HYSA rate**; it now applies only to
    invested accounts.
28. **The FICA wage base was indexed off the profile year, not 2024** (two
    years stale), and **FICA disappeared from `total_tax`** in Roth years.
29. **The state pension exclusion sheltered wages, interest and capital gains**
    rather than only pension/IRA income; NY's exclusion begins at 59½.
30. **Monte Carlo mixed log and simple returns** — `drift = growth − σ²/2` is a
    log-space quantity but was applied as `bal × (1 + drift + shock)`. Now
    `bal × exp(drift + shock)` with `drift = ln(1+growth) − σ²/2`. Guardrail
    trigger counting and the initial-withdrawal-rate anchor were also corrected.

## Security

31. **CSRF write to `/api/save` was still possible.** Round 1 removed the
    wildcard CORS header, which blocks cross-origin *reads* — but an HTML form
    POST is a "simple request" with no preflight, and the handler ignored
    `Content-Type` and just parsed the body as JSON. Any page open in the
    browser could overwrite or wipe `profile.json`. POSTs now require a
    same-origin `Origin`/`Sec-Fetch-Site` and `application/json`.
32. **A missing `Host` header bypassed the rebinding check** (`''` was allowed).
33. **`/api/save` accepted any JSON**, so a malformed payload could replace a
    good profile and break every later calculation. It is now validated,
    including a trial projection.
34. **Errors were invisible on both ends** — round 1 removed the traceback from
    the response but never logged it. Tracebacks now go to the server's stderr.

## Robustness / housekeeping

35. Profile fields are coerced through a shared `_num()` / `normalize_accounts()`
    path, so `"1,234"`, `null`, missing `type` keys and wrong-typed lists no
    longer raise a bare `KeyError` mid-projection.
36. `APP_VERSION` + `/api/version` now exist and are displayed in the topbar —
    the 1.0.0 changelog had claimed this feature, but it was never implemented.
37. Removed the four leftover no-op `import traceback` statements.

> The original author's disclaimer still applies: this is a planning estimate,
> not financial advice.

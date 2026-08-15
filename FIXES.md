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

> The original author's disclaimer still applies: this is a planning estimate,
> not financial advice.

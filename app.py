#!/usr/bin/env python3
"""
Retirement Planner - Local Web Application
Run: python3 app.py  (or double-click the .exe)
Open: http://localhost:5000
"""

from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
import json, math, os, copy, random, sys, threading, webbrowser

PORT = 5000

# When bundled with PyInstaller, data files live in sys._MEIPASS.
# When running from source, they live next to this script.
if getattr(sys, 'frozen', False):
    _BASE_DIR = sys._MEIPASS          # PyInstaller temp-extract folder
    # Save profile next to the .exe, not inside the bundle
    _DATA_DIR = os.path.dirname(sys.executable)
else:
    _BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    _DATA_DIR = _BASE_DIR

CURRENT_DIR = _BASE_DIR
DATA_FILE   = os.path.join(_DATA_DIR, 'profile.json')

# ─── TAX TABLES 2024 (MFJ) ────────────────────────────────────────────────────

FED_BRACKETS_MFJ = [
    (23200, 0.10), (94300, 0.12), (201050, 0.22),
    (383900, 0.24), (487450, 0.32), (731200, 0.35), (float('inf'), 0.37)
]
FED_STD_DED = 29200

NYS_BRACKETS_MFJ = [
    (17150, 0.040), (23600, 0.045), (27900, 0.0525),
    (161550, 0.0585), (323200, 0.0625), (2155350, 0.0685), (float('inf'), 0.0965)
]
NYS_STD_DED = 16050
NYS_PENSION_EXCL_PER_PERSON = 20000   # per person, age 59½+

# ─── TAX TABLES 2024 (Single filer — used after one spouse dies) ──────────────

FED_BRACKETS_SINGLE = [
    (11600, 0.10), (47150, 0.12), (100525, 0.22),
    (191950, 0.24), (243725, 0.32), (609350, 0.35), (float('inf'), 0.37)
]
FED_STD_DED_SINGLE = 14600

NYS_BRACKETS_SINGLE = [
    (8500,  0.040), (11700, 0.045), (13900, 0.0525),
    (80650, 0.0585), (215400, 0.0625), (1077550, 0.0685), (float('inf'), 0.0965)
]
NYS_STD_DED_SINGLE = 8000
NYS_PENSION_EXCL_SINGLE = 20000   # per surviving person, age 59½+

# Federal Long-Term Capital Gains brackets 2024 (MFJ)
LTCG_BRACKETS_MFJ = [
    (94050,  0.00),
    (583750, 0.15),
    (float('inf'), 0.20),
]
# Federal Long-Term Capital Gains brackets 2024 (Single)
LTCG_BRACKETS_SINGLE = [
    (47025,  0.00),
    (518900, 0.15),
    (float('inf'), 0.20),
]
# NYS taxes capital gains as ordinary income (no special rate)

# IRS Uniform Lifetime Table (RMDs, SECURE 2.0: start age 73)
RMD_TABLE = {
    73:26.5, 74:25.5, 75:24.6, 76:23.7, 77:22.9,
    78:22.0, 79:21.1, 80:20.2, 81:19.4, 82:18.5, 83:17.7,
    84:16.8, 85:16.0, 86:15.2, 87:14.4, 88:13.7, 89:12.9,
    90:12.2, 91:11.5, 92:10.8, 93:10.1, 94:9.5,  95:8.9
}

# ─── FINANCIAL HELPERS ────────────────────────────────────────────────────────

def adj_brackets(brackets, ded, inflation, years):
    """Adjust tax brackets for inflation."""
    f = (1 + inflation) ** years
    return [(lim * f if lim != float('inf') else float('inf'), r) for lim, r in brackets], ded * f

def calc_tax(income, brackets, ded):
    """Calculate total tax for a given income level."""
    taxable = max(0.0, income - ded)
    tax, prev = 0.0, 0.0
    for lim, rate in brackets:
        if taxable <= prev:
            break
        tax += (min(taxable, lim) - prev) * rate
        prev = lim
    return tax

def marginal_rate_at(income, brackets, ded):
    """Return marginal tax rate for the given income."""
    taxable = max(0.0, income - ded)
    for lim, rate in brackets:
        if taxable <= lim:
            return rate
    return brackets[-1][1]

def bracket_room(income, target_rate, brackets, ded):
    """How much more income before hitting target_rate bracket."""
    taxable = max(0.0, income - ded)
    for lim, rate in brackets:
        if rate >= target_rate:
            return max(0.0, lim - taxable)
    return 0.0

def calc_ltcg_tax(gains, ordinary_income, brackets, ded, tax_inf, yrs):
    """
    Federal long-term capital gains tax.
    LTCG brackets are stacked ON TOP of ordinary income (after std deduction).
    The 0% bracket threshold means: ordinary taxable + gains ≤ threshold → 0%.
    """
    if gains <= 0:
        return 0.0
    ord_taxable = max(0.0, ordinary_income - ded)
    gains_top   = ord_taxable + gains        # total "stack" height
    f = (1 + tax_inf) ** yrs
    tax = 0.0
    prev_lim = 0.0
    for lim, rate in brackets:
        adj_lim = lim * f if lim != float('inf') else float('inf')
        # The gains sit in the slice [ord_taxable, gains_top]
        # Overlap with this bracket [prev_lim, adj_lim]:
        lo = max(ord_taxable, prev_lim)
        hi = min(gains_top,   adj_lim)
        if hi > lo:
            tax += (hi - lo) * rate
        prev_lim = adj_lim
        if gains_top <= adj_lim:
            break
    return tax


# ─── IRMAA SURCHARGE TABLE (2024, per-person/year) ────────────────────────────
# Based on MAGI from 2 years prior; thresholds for MFJ / Single filers.
# Surcharge is on top of standard Part B premium ($174.70/mo ≈ $2,096/yr).
# We store the *total* annual premium per person (standard + surcharge).
# (Part D surcharge ~$12-81/mo is approximated as 15% of the B surcharge.)
IRMAA_MFJ = [
    (206000,  2096),   # standard — no surcharge
    (258000,  3734),   # tier 1
    (322000,  5934),   # tier 2
    (386000,  8130),   # tier 3
    (750000,  9508),   # tier 4
    (float('inf'), 10096),  # tier 5
]
IRMAA_SINGLE = [
    (103000,  2096),
    (129000,  3734),
    (161000,  5934),
    (193000,  8130),
    (500000,  9508),
    (float('inf'), 10096),
]

def irmaa_annual_per_person(magi, use_single=False):
    """Annual Medicare Part B+D premium (standard + IRMAA surcharge) per person."""
    table = IRMAA_SINGLE if use_single else IRMAA_MFJ
    for threshold, annual in table:
        if magi <= threshold:
            return annual
    return table[-1][1]

def ss_monthly_at_age(fra_monthly, take_age, fra_age=67):
    """SS monthly benefit adjusted for early/late claiming."""
    months = (take_age - fra_age) * 12
    if months >= 0:
        return fra_monthly * (1 + min(months, (70 - fra_age) * 12) * 8 / 1200)
    early = abs(months)
    reduction = (36 * 5 / 900 + max(0, early - 36) * 5 / 1200) if early > 36 else early * 5 / 900
    return fra_monthly * (1 - reduction)

def spousal_ss_monthly(own_fra_monthly, partner_fra_monthly, take_age, fra_age=67):
    """
    SS benefit considering spousal benefit.
    Spousal = 50% of partner's PIA, reduced for early claiming (floor at 62).
    Returns the higher of own benefit vs spousal benefit.
    """
    own = ss_monthly_at_age(own_fra_monthly, take_age, fra_age)
    if partner_fra_monthly <= 0:
        return own
    # Spousal benefit: 50% of partner's PIA, reduced if taken before own FRA
    months_early = max(0, (fra_age - take_age) * 12)
    if months_early == 0:
        spousal = 0.5 * partner_fra_monthly
    elif months_early <= 36:
        spousal = 0.5 * partner_fra_monthly * (1 - months_early * 25/10000)
    else:
        spousal = 0.5 * partner_fra_monthly * (1 - (36*25 + (months_early-36)*25/12) / 10000)
    return max(own, spousal)

def taxable_ss_portion(ss_annual, other_income):
    """Federal taxable portion of SS benefits."""
    combined = other_income + 0.5 * ss_annual
    if combined < 32000:
        return 0.0
    elif combined < 44000:
        return min(0.5 * ss_annual, 0.5 * (combined - 32000))
    else:
        return min(0.85 * ss_annual, 0.85 * (combined - 44000) + 6000)

def rmd_required(balance, age):
    """RMD amount for a traditional account. SECURE 2.0: starts at 73."""
    if age < 73 or balance <= 0:
        return 0.0
    return balance / RMD_TABLE.get(min(age, 95), 8.9)

def pension_income_for_year(pension_def, person_age):
    """Annual pension income for a given age."""
    if not pension_def or person_age < pension_def.get('start_age', 65):
        return 0.0
    active_yrs = person_age - pension_def.get('start_age', 65)
    return pension_def.get('monthly_benefit', 0) * 12 * (1 + pension_def.get('cola', 0.0)) ** active_yrs

# ─── PROJECTION ENGINE ────────────────────────────────────────────────────────

def project(profile, ss1_age_override=None, ss2_age_override=None, do_roth=True):
    """
    Year-by-year retirement projection.
    Returns list of annual snapshots from current_year to p1 age 95.
    """
    p1 = profile['person1']
    p2 = profile['person2']
    p2_enabled = bool(p2.get('enabled', True))   # False → single-person / single-filer mode
    p1b = int(p1['birth_year'])
    p2b = int(p2['birth_year'])
    curr_yr = int(profile.get('current_year', 2026))
    inflation = float(profile.get('inflation', 0.03))
    tax_inf = 0.025   # tax brackets inflate slightly slower
    acct_defs = profile['accounts']
    contribs   = profile.get('contributions', {})
    catch_ups  = profile.get('catch_up_contributions', {})   # age 50+
    super_cups = profile.get('super_catch_up_contributions', {})  # ages 60-63 (SECURE 2.0)
    # Pensions — support new generic keys (pension1/pension2) with fallback to old keys
    pen1 = profile.get('pension1') or profile.get('nys_pension', {})
    pen2 = profile.get('pension2') or {}
    annual_exp = float(profile.get('annual_expenses', 0))

    # Pension owner: whose age drives start/income ('p1' or 'p2')
    pen1_owner = pen1.get('owner', 'p1')
    pen2_owner = pen2.get('owner', 'p1')

    # NYS income-tax exempt flag (NYS pension is exempt; most others are not)
    pen1_nys_exempt = bool(pen1.get('nys_exempt', True))
    pen2_nys_exempt = bool(pen2.get('nys_exempt', False))

    # Pension survivor monthly benefits (what the surviving spouse receives)
    pen1_survivor_mo = float(pen1.get('survivor_monthly', 0))
    pen2_survivor_mo = float(pen2.get('survivor_monthly', 0))

    # One-time expense shocks: [{label, p1_age, amount}]
    shocks = profile.get('shocks', [])
    # Build lookup: p1_age -> total shock amount that year
    shock_by_age = {}
    for sh in shocks:
        try:
            age = int(sh.get('p1_age', 0))
            amt = float(str(sh.get('amount', 0)).replace(',',''))
            if age > 0 and amt > 0:
                shock_by_age[age] = shock_by_age.get(age, 0.0) + amt
        except (ValueError, TypeError):
            pass

    # Survivor scenario: one spouse dies at a given age
    surv_cfg   = profile.get('survivor', {})
    surv_on    = bool(surv_cfg.get('enabled', False))
    surv_who   = surv_cfg.get('person', 'p2')   # 'p1' or 'p2'
    surv_age   = int(surv_cfg.get('death_age', 80))    # p1 age when death occurs
    surv_exp   = float(surv_cfg.get('expense_pct', 0.70))  # expenses drop to this %

    # Spending phases — age-based multiplier on base expenses
    spend_phases = profile.get('spending_phases', [])
    # Sort by through_age so lookup is in order
    spend_phases = sorted(spend_phases, key=lambda p: p.get('through_age', 999))

    def spending_multiplier(age):
        for ph in spend_phases:
            if age <= ph.get('through_age', 999):
                return float(ph.get('multiplier', 1.0))
        return spend_phases[-1].get('multiplier', 1.0) if spend_phases else 1.0

    # Medical costs — pre-Medicare vs post-Medicare
    medical = profile.get('medical', {})
    med_pre   = float(medical.get('pre_medicare_annual', 0))
    med_post  = float(medical.get('post_medicare_annual', 0))
    med_age   = int(medical.get('medicare_age', 65))
    med_inf   = float(medical.get('inflation_rate', 0.05))
    use_irmaa = bool(medical.get('use_irmaa', True))

    # ── ACA premiums (pre-Medicare gap) ───────────────────────────────────────
    aca_cfg   = profile.get('aca', {})
    aca_on    = bool(aca_cfg.get('enabled', False))
    aca_mo    = float(aca_cfg.get('monthly_premium', 0))   # estimated full benchmark premium
    aca_inf   = float(aca_cfg.get('inflation', 0.05))

    # ── Long-term care ────────────────────────────────────────────────────────
    ltc_cfg   = profile.get('ltc', {})
    ltc_on    = bool(ltc_cfg.get('enabled', False))
    # Per-person LTC config: [{person:'p1', start_age:82, duration:3, monthly_cost:0, insurance_monthly:0}]
    ltc_events = ltc_cfg.get('events', [])

    # ── Asset allocation glide path ───────────────────────────────────────────
    glide_cfg      = profile.get('glide_path', {})
    glide_on       = bool(glide_cfg.get('enabled', False))
    glide_eq_start = float(glide_cfg.get('equity_pct_start', 60)) / 100.0
    glide_eq_end   = float(glide_cfg.get('equity_pct_end',   40)) / 100.0
    glide_age_start = int(glide_cfg.get('age_start', 65))
    glide_age_end   = int(glide_cfg.get('age_end',   80))
    glide_stock_ret = float(glide_cfg.get('stock_return', 8.0)) / 100.0
    glide_bond_ret  = float(glide_cfg.get('bond_return',  3.5)) / 100.0

    strat = profile.get('strategy', {})
    ss1_age = ss1_age_override if ss1_age_override is not None else int(strat.get('ss1_age', p1.get('fra_age', 67)))
    ss2_age = ss2_age_override if ss2_age_override is not None else int(strat.get('ss2_age', p2.get('fra_age', 67)))

    # Spousal SS: each person gets max(own benefit, 50% of partner's PIA)
    p1_fra_mo = float(p1.get('ss_fra_monthly', 0))
    p2_fra_mo = float(p2.get('ss_fra_monthly', 0)) if p2_enabled else 0.0
    ss1_mo = spousal_ss_monthly(p1_fra_mo, p2_fra_mo, ss1_age, int(p1.get('fra_age', 67)))
    ss2_mo = 0.0 if not p2_enabled else spousal_ss_monthly(p2_fra_mo, p1_fra_mo, ss2_age, int(p2.get('fra_age', 67)))

    # Current gross annual income for each person while working
    p1_gross_income = float(p1.get('annual_income', 0))
    p2_gross_income = float(p2.get('annual_income', 0)) if p2_enabled else 0.0

    # FICA tax helper — employee share (SS 6.2% up to wage base + Medicare 1.45%)
    # SS wage base grows ~4% / yr from the 2024 base of $168,600
    SS_WAGE_BASE_2024 = 168_600.0
    def fica_tax(gross, yrs_elapsed):
        wage_base = SS_WAGE_BASE_2024 * (1.04 ** yrs_elapsed)
        ss_tax  = min(gross, wage_base) * 0.062
        med_tax = gross * 0.0145
        return ss_tax + med_tax

    p1_retire_yr = p1b + int(p1.get('retirement_age', 65))
    # When P2 is disabled treat them as never retiring (far future year)
    p2_retire_yr = p2b + int(p2.get('retirement_age', 65)) if p2_enabled else 9999
    first_retire_yr = min(p1_retire_yr, p2_retire_yr)

    # Deep-copy starting balances
    bal = {k: float(v['balance']) for k, v in acct_defs.items()}

    # Cost basis for taxable/savings accounts (contributions in, not growth)
    # Default: assume current balance is 80% basis / 20% unrealized gain
    basis = {}
    for k, v in acct_defs.items():
        if v['type'] in ('taxable', 'savings'):
            basis[k] = float(v.get('cost_basis', float(v['balance']) * 0.80))
        else:
            basis[k] = 0.0

    results = []
    p1_end = p1b + int(p1.get('life_expectancy', 95))
    p2_end = p2b + int(p2.get('life_expectancy', 90)) if p2_enabled else 0
    end_year = max(p1_end, p2_end)

    for yr in range(curr_yr, end_year + 1):
        p1a = yr - p1b
        p2a = yr - p2b
        yrs_since_2024 = yr - 2024

        p1_ret = yr >= p1_retire_yr
        p2_ret = yr >= p2_retire_yr
        any_ret = p1_ret or p2_ret
        both_ret = p1_ret and p2_ret

        # ── ACCUMULATION PHASE (no one retired yet) ──────────────────────────
        if not any_ret:
            for k, v in acct_defs.items():
                owner_age = p1a if v.get('owner', 'p1') == 'p1' else p2a
                c = float(contribs.get(k, 0))
                # Catch-up contributions (age 50+)
                if owner_age >= 50:
                    if owner_age >= 60 and owner_age <= 63:
                        # SECURE 2.0 super catch-up replaces standard catch-up
                        c += float(super_cups.get(k, catch_ups.get(k, 0)))
                    else:
                        c += float(catch_ups.get(k, 0))
                bal[k] = max(0.0, bal[k] + c)
                if v['type'] in ('taxable', 'savings'):
                    basis[k] += c        # contributions add to basis
                bal[k] *= (1 + float(v.get('growth_rate', 0.07)))
                # growth does NOT increase basis

            total_bal = sum(bal.values())
            results.append({
                'year': yr, 'p1_age': p1a, 'p2_age': p2a, 'phase': 'accumulation',
                'expenses': 0, 'guaranteed_income': 0, 'withdrawal_total': 0,
                'pension1': 0, 'pension2': 0, 'ss_p1': 0, 'ss_p2': 0,
                'total_ss': 0, 'federal_tax': 0, 'nys_tax': 0, 'total_tax': 0,
                'net_income': 0, 'shortfall': 0, 'roth_conversion': 0, 'rmd_total': 0,
                'total_balance': round(total_bal),
                'trad_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'traditional')),
                'roth_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'roth')),
                'taxable_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] in ['taxable', 'savings'])),
                'account_balances': {k: round(v) for k, v in bal.items()},
                'withdrawals': {k: 0 for k in bal},
            })
            continue

        # ── RETIREMENT PHASE ─────────────────────────────────────────────────

        # ── Survivor scenario — has one spouse died this year? ────────────────
        # surv_age is stored as p1_age at time of death.
        p1_alive = True
        p2_alive = True
        survivor_active = False
        if surv_on and p1a >= surv_age:
            survivor_active = True
            if surv_who == 'p1':
                p1_alive = False
            else:
                p2_alive = False

        # ── Tax filing status (single vs MFJ) ────────────────────────────────
        use_single = survivor_active or not p2_enabled

        # ── Expenses ─────────────────────────────────────────────────────────
        base_exp   = annual_exp * (1 + inflation) ** (yr - curr_yr)
        phase_mult = spending_multiplier(p1a)
        living_exp = base_exp * phase_mult

        # Survivor: expenses drop to configured percentage of couple amount
        if survivor_active:
            living_exp *= surv_exp

        # Medical costs — per-couple values split per-person
        med_yrs    = yr - curr_yr
        med_factor = (1 + med_inf) ** med_yrs
        per_pre    = med_pre  / 2.0
        per_post   = med_post / 2.0
        # Only living retirees incur medical costs
        p1_med = (per_post if p1a >= med_age else per_pre) * med_factor if (p1_ret and p1_alive) else 0
        p2_med = (per_post if p2a >= med_age else per_pre) * med_factor if (p2_enabled and p2_ret and p2_alive) else 0

        # ACA premiums: cover the gap between early retirement and Medicare age
        aca_exp = 0.0
        if aca_on and aca_mo > 0:
            aca_factor = (1 + aca_inf) ** med_yrs
            if p1_ret and p1_alive and p1a < med_age:
                aca_exp += aca_mo * 12 * aca_factor
            if p2_enabled and p2_ret and p2_alive and p2a < med_age:
                aca_exp += aca_mo * 12 * aca_factor

        # Long-term care expenses
        ltc_exp = 0.0
        if ltc_on:
            for ev in ltc_events:
                who       = ev.get('person', 'p1')
                ev_age    = int(ev.get('start_age', 82))
                duration  = int(ev.get('duration', 3))
                mo_cost   = float(ev.get('monthly_cost', 8000))
                mo_insure = float(ev.get('insurance_monthly', 0))
                net_mo    = max(0.0, mo_cost - mo_insure)
                ev_age_check = p1a if who == 'p1' else p2a
                ev_alive     = p1_alive if who == 'p1' else p2_alive
                if ev_alive and ev_age <= ev_age_check < ev_age + duration:
                    ltc_exp += net_mo * 12 * (1 + med_inf) ** med_yrs

        # IRMAA pre-estimate (using annual pension + SS benefit as MAGI proxy)
        # Pension income proxy: monthly_benefit * 12 * COLA^active_yrs for each pension at owner's age
        irmaa_cost = 0.0
        if use_irmaa:
            pen1_proxy_ann = pension_income_for_year(pen1, p1a if pen1_owner=='p1' else p2a)
            pen2_proxy_ann = pension_income_for_year(pen2, p1a if pen2_owner=='p1' else p2a)
            ss1_proxy = ss1_mo * 12 if p1a >= ss1_age else 0.0
            ss2_proxy = ss2_mo * 12 if (p2_enabled and p2a >= ss2_age) else 0.0
            magi_proxy = pen1_proxy_ann + pen2_proxy_ann + ss1_proxy + ss2_proxy
            p1_irmaa_est = irmaa_annual_per_person(magi_proxy, use_single) if (p1_alive and p1a >= med_age and p1_ret) else 0
            p2_irmaa_est = irmaa_annual_per_person(magi_proxy, use_single) if (p2_enabled and p2_alive and p2a >= med_age and p2_ret) else 0
            base_post_est = per_post * med_factor * ((1 if p1_alive and p1a >= med_age and p1_ret else 0) +
                                                      (1 if p2_enabled and p2_alive and p2a >= med_age and p2_ret else 0))
            irmaa_cost = max(0.0, (p1_irmaa_est + p2_irmaa_est) - base_post_est)

        medical_exp = p1_med + p2_med + aca_exp + ltc_exp

        # One-time expense shocks (indexed by p1 age)
        shock_amt = shock_by_age.get(p1a, 0.0)

        exp = living_exp + medical_exp + shock_amt + irmaa_cost

        # ── Pension income ────────────────────────────────────────────────────
        # Each pension uses its assigned owner's age.
        # If the owner dies (survivor scenario), switch to survivor monthly benefit.
        def _pen_inc(pen, pen_owner, pen_survivor_mo, p1_alive, p2_alive):
            owner_age  = p1a if pen_owner == 'p1' else p2a
            owner_alive = p1_alive if pen_owner == 'p1' else p2_alive
            if survivor_active and not owner_alive and pen_survivor_mo > 0:
                # Owner died — pay survivor benefit (COLA-adjusted from start_age)
                yrs_collecting = max(0, owner_age - int(pen.get('start_age', 65)))
                return pen_survivor_mo * 12 * (1 + float(pen.get('cola', 0))) ** yrs_collecting
            elif survivor_active and not owner_alive:
                return 0.0   # owner died, no survivor benefit elected
            else:
                return pension_income_for_year(pen, owner_age)

        pen1_inc = _pen_inc(pen1, pen1_owner, pen1_survivor_mo, p1_alive, p2_alive)
        pen2_inc = _pen_inc(pen2, pen2_owner, pen2_survivor_mo, p1_alive, p2_alive)

        # ── Social Security ───────────────────────────────────────────────────
        ss1_ann = ss1_mo * 12 * (1.024 ** max(0, p1a - ss1_age)) if p1a >= ss1_age else 0.0
        ss2_ann = ss2_mo * 12 * (1.024 ** max(0, p2a - ss2_age)) if p2a >= ss2_age else 0.0

        # Survivor SS: survivor keeps the HIGHER of the two benefits
        if survivor_active:
            if not p1_alive:
                # P1 is deceased — P2 gets max(ss2, ss1 survivor = ss1)
                ss2_ann = max(ss1_ann, ss2_ann)
                ss1_ann = 0.0
            else:
                # P2 is deceased — P1 gets max(ss1, ss2)
                ss1_ann = max(ss1_ann, ss2_ann)
                ss2_ann = 0.0
        total_ss = ss1_ann + ss2_ann

        # ── Working income ────────────────────────────────────────────────────
        yrs_elapsed = yr - curr_yr
        p1_work = p1_gross_income * (1 + inflation) ** yrs_elapsed if (not p1_ret and p1_alive) else 0.0
        p2_work = p2_gross_income * (1 + inflation) ** yrs_elapsed if (not p2_ret and p2_alive) else 0.0
        working_income = p1_work + p2_work
        total_fica = fica_tax(p1_work, yrs_elapsed) + fica_tax(p2_work, yrs_elapsed)

        guaranteed = pen1_inc + pen2_inc + total_ss + working_income

        # Contributions for still-working spouse
        if not both_ret:
            for k, v in acct_defs.items():
                owner = v.get('owner', 'p1')
                if (owner == 'p1' and not p1_ret) or (owner == 'p2' and not p2_ret):
                    owner_age = p1a if owner == 'p1' else p2a
                    c = float(contribs.get(k, 0))
                    if owner_age >= 50:
                        if owner_age >= 60 and owner_age <= 63:
                            c += float(super_cups.get(k, catch_ups.get(k, 0)))
                        else:
                            c += float(catch_ups.get(k, 0))
                    bal[k] = max(0.0, bal[k] + c)

        # ── RMDs ─────────────────────────────────────────────────────────────
        rmds = {}
        rmd_tot = 0.0
        for k, v in acct_defs.items():
            if v['type'] == 'traditional':
                owner_age = p1a if v.get('owner', 'p1') == 'p1' else p2a
                r = min(rmd_required(bal[k], owner_age), bal[k])
                rmds[k] = r
                rmd_tot += r
            else:
                rmds[k] = 0.0

        # ── TAX-AWARE WITHDRAWAL STRATEGY ────────────────────────────────────
        # Annual expenses are the AFTER-TAX target.  We need to withdraw
        # enough to cover expenses + the taxes generated by the withdrawals
        # themselves.  This is solved iteratively: withdraw, compute tax,
        # gross up the next pass by the tax deficit, repeat (converges in
        # 2-3 rounds).
        #
        # Order: RMDs → Taxable (savings/brokerage) → Traditional → Roth

        # Select tax brackets based on filing status (computed earlier in loop)
        if use_single:
            fb, fd = adj_brackets(FED_BRACKETS_SINGLE, FED_STD_DED_SINGLE, tax_inf, yrs_since_2024)
            nb, nd = adj_brackets(NYS_BRACKETS_SINGLE, NYS_STD_DED_SINGLE, tax_inf, yrs_since_2024)
            living_age = p1a if (not survivor_active or p1_alive) else p2a
            nys_excl = NYS_PENSION_EXCL_SINGLE * (1 if living_age >= 60 else 0) * (1.025 ** yrs_since_2024)
            ltcg_brackets = LTCG_BRACKETS_SINGLE
        else:
            fb, fd = adj_brackets(FED_BRACKETS_MFJ, FED_STD_DED, tax_inf, yrs_since_2024)
            nb, nd = adj_brackets(NYS_BRACKETS_MFJ, NYS_STD_DED, tax_inf, yrs_since_2024)
            nys_excl = NYS_PENSION_EXCL_PER_PERSON * (
                (1 if p1a >= 60 else 0) + (1 if p2a >= 60 else 0)
            ) * (1.025 ** yrs_since_2024)
            ltcg_brackets = LTCG_BRACKETS_MFJ

        # Snapshot balances and basis before any withdrawal, so we can
        # re-run with a grossed-up target on each iteration.
        bal_snap   = dict(bal)
        basis_snap = dict(basis)

        extra_for_tax = 0.0     # additional amount to cover tax
        total_tax     = 0.0
        fed_tax       = 0.0
        nys_tax       = 0.0
        fed_ltcg_tax  = 0.0
        fed_income    = 0.0     # set by the loop; used for Roth later

        for _tax_iter in range(6):
            # Restore from snapshot each iteration
            for k in bal:
                bal[k]   = bal_snap[k]
                basis[k] = basis_snap[k]

            w = {k: 0.0 for k in bal}
            need = max(0.0, exp - guaranteed + extra_for_tax)

            # 1. RMDs (mandatory — always taken regardless of need)
            for k, r in rmds.items():
                if r > 0:
                    take = min(r, bal[k])
                    w[k] += take; bal[k] = max(0, bal[k] - take)
                    need = max(0.0, need - take)

            # 2. Taxable accounts — track capital gains
            taxable_gains    = 0.0
            savings_interest = 0.0
            for k, v in acct_defs.items():
                if v['type'] in ('savings', 'taxable') and need > 0 and bal[k] > 0:
                    take = min(bal[k], need)
                    if bal[k] > 0:
                        gain_pct = max(0.0, (bal[k] - basis[k]) / bal[k])
                    else:
                        gain_pct = 0.0
                    gain       = take * gain_pct
                    basis_used = take - gain
                    basis[k]   = max(0.0, basis[k] - basis_used)

                    if v['type'] == 'taxable':
                        taxable_gains += gain
                    else:
                        savings_interest += gain

                    w[k] += take; bal[k] -= take; need -= take

            # 3. Traditional (tax-deferred, fully taxable as ordinary income)
            for k, v in acct_defs.items():
                if v['type'] == 'traditional' and need > 0 and bal[k] > 0:
                    take = min(bal[k], need)
                    w[k] += take; bal[k] -= take; need -= take

            # 4. Roth (last resort, tax-free)
            for k, v in acct_defs.items():
                if v['type'] == 'roth' and need > 0 and bal[k] > 0:
                    take = min(bal[k], need)
                    w[k] += take; bal[k] -= take; need -= take

            # ── Tax on this iteration's withdrawals ─────────────────────────
            trad_w       = sum(w[k] for k, v in acct_defs.items() if v['type'] == 'traditional')
            # Federal: all pension income is ordinary income regardless of NYS exemption
            # Working income is earned income — taxed at regular rates
            fed_ordinary = pen1_inc + pen2_inc + trad_w + savings_interest + working_income
            tx_ss        = taxable_ss_portion(total_ss, fed_ordinary)
            fed_ordinary += tx_ss

            fed_ltcg_tax = calc_ltcg_tax(taxable_gains, fed_ordinary,
                                         ltcg_brackets, fd, tax_inf, yrs_since_2024)
            fed_income   = fed_ordinary
            # NYS: only include pensions that are NOT NYS-exempt.
            # Working income is fully NYS-taxable (no pension exclusion on wages).
            nys_pen_taxable = (0.0 if pen1_nys_exempt else pen1_inc) + \
                              (0.0 if pen2_nys_exempt else pen2_inc)
            nys_taxable  = max(0.0, nys_pen_taxable + trad_w + savings_interest
                               + taxable_gains + working_income - nys_excl)

            fed_tax   = calc_tax(fed_income, fb, fd) + fed_ltcg_tax
            nys_tax   = calc_tax(nys_taxable, nb, nd)
            total_tax = fed_tax + nys_tax + total_fica

            # Check: did we withdraw enough to cover expenses + tax?
            gross_income = guaranteed + sum(w.values())
            net_after_tax = gross_income - total_tax
            deficit = exp - net_after_tax

            if deficit <= 50:    # close enough (within $50)
                break
            # Gross up by deficit / (1 - combined_marginal) so the extra
            # withdrawal covers its own federal + NYS tax in one shot.
            fed_marginal = marginal_rate_at(fed_income, fb, fd)
            nys_marginal = marginal_rate_at(nys_taxable, nb, nd)
            combined     = fed_marginal + nys_marginal
            gross_up = deficit / max(0.30, 1.0 - combined) if combined < 0.95 else deficit
            extra_for_tax = max(0.0, extra_for_tax + gross_up)

        shortfall = max(0.0, need)  # > 0 means ran out of money this year

        # ── ROTH CONVERSIONS ─────────────────────────────────────────────────
        roth_conv = 0.0
        roth_conv_tax = 0.0

        roth_strategy = str(profile.get('roth_strategy', 'fill_22'))  # fixed, fill_12, fill_22, fill_24, fill_32, none
        roth_fixed_amt = float(profile.get('roth_fixed_amount', 20000))
        ROTH_BRACKET_MAP = {'fill_12': 0.12, 'fill_22': 0.22, 'fill_24': 0.24, 'fill_32': 0.32}

        if do_roth and both_ret and roth_strategy != 'none':
            trad_bal_total = sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'traditional')
            if trad_bal_total > 5000:
                if roth_strategy == 'fixed':
                    room = roth_fixed_amt
                else:
                    target_rate = ROTH_BRACKET_MAP.get(roth_strategy, 0.22)
                    room = bracket_room(fed_income, target_rate, fb, fd)
                if room > 0:
                    roth_conv = min(room, trad_bal_total, 250000)
                    roth_conv_tax = calc_tax(fed_income + roth_conv, fb, fd) - calc_tax(fed_income, fb, fd)
                    # Move from traditional → Roth
                    rem_conv = roth_conv
                    roth_keys = [k for k, v in acct_defs.items() if v['type'] == 'roth']
                    for k, v in acct_defs.items():
                        if v['type'] == 'traditional' and rem_conv > 0:
                            take = min(bal[k], rem_conv)
                            bal[k] -= take
                            if roth_keys:
                                bal[roth_keys[0]] += take
                            rem_conv -= take
                    fed_income += roth_conv
                    nys_taxable = max(0.0, nys_taxable + roth_conv)

        # Pre-Roth tax = the amount the gross-up loop was designed to cover.
        # Roth conversion tax is a strategic cost, not a spending cost, so
        # net_income (which measures "can I cover expenses?") uses pre-Roth tax.
        tax_pre_roth = total_tax

        # Recalculate final tax including Roth conversion (for total reporting)
        if roth_conv > 0:
            fed_tax   = calc_tax(fed_income, fb, fd) + fed_ltcg_tax
            nys_tax   = calc_tax(nys_taxable, nb, nd)
            total_tax = fed_tax + nys_tax

        # ── REINVEST SURPLUS (RMD excess beyond spending needs) ──────────────
        # When forced distributions (RMDs) + guaranteed income exceed
        # after-tax spending needs, the after-tax surplus is reinvested
        # into a taxable brokerage account.
        spending_income = guaranteed + sum(w.values()) - tax_pre_roth
        surplus = max(0.0, spending_income - exp)
        if surplus > 0:
            # Find the first taxable/brokerage account to reinvest into
            reinvest_key = None
            for k, v in acct_defs.items():
                if v['type'] == 'taxable':
                    reinvest_key = k
                    break
            if reinvest_key is None:
                for k, v in acct_defs.items():
                    if v['type'] == 'savings':
                        reinvest_key = k
                        break
            if reinvest_key:
                bal[reinvest_key] += surplus
                basis[reinvest_key] += surplus   # already taxed — all basis

        # ── GROW ACCOUNTS ────────────────────────────────────────────────────
        eq_pct = None
        for k, v in acct_defs.items():
            base_gr = float(v.get('ret_growth', float(v.get('growth_rate', 0.07)) * 0.85))
            if glide_on and any_ret:
                # Blend between equity and bond returns based on p1 age
                if p1a <= glide_age_start:
                    eq_pct = glide_eq_start
                elif p1a >= glide_age_end:
                    eq_pct = glide_eq_end
                else:
                    t = (p1a - glide_age_start) / max(1, glide_age_end - glide_age_start)
                    eq_pct = glide_eq_start + t * (glide_eq_end - glide_eq_start)
                gr = eq_pct * glide_stock_ret + (1 - eq_pct) * glide_bond_ret
            else:
                gr = base_gr
            bal[k] = max(0.0, bal[k] * (1 + gr))

        total_bal = sum(bal.values())

        results.append({
            'year': yr, 'p1_age': p1a, 'p2_age': p2a, 'phase': 'retirement',
            'expenses': round(exp),
            'living_expenses': round(living_exp),
            'medical_expenses': round(medical_exp),
            'irmaa_cost': round(irmaa_cost),
            'aca_expense': round(aca_exp),
            'ltc_expense': round(ltc_exp),
            'spending_multiplier': round(phase_mult, 2),
            'pension1': round(pen1_inc),
            'pension2': round(pen2_inc),
            'ss_p1': round(ss1_ann),
            'ss_p2': round(ss2_ann),
            'total_ss': round(total_ss),
            'working_income': round(working_income),
            'fica_tax': round(total_fica),
            'shock_expense': round(shock_amt),
            'survivor_active': survivor_active,
            'guaranteed_income': round(guaranteed),
            'withdrawal_total': round(sum(w.values())),
            'withdrawals': {k: round(v) for k, v in w.items()},
            'roth_conversion': round(roth_conv),
            'roth_conversion_tax': round(roth_conv_tax),
            'federal_tax': round(fed_tax),
            'federal_ltcg_tax': round(fed_ltcg_tax),
            'capital_gains': round(taxable_gains),
            'nys_tax': round(nys_tax),
            'total_tax': round(total_tax),
            'net_income': round(guaranteed + sum(w.values()) - tax_pre_roth),
            'shortfall': round(shortfall),
            'total_balance': round(total_bal),
            'trad_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'traditional')),
            'roth_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'roth')),
            'taxable_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] in ['taxable', 'savings'])),
            'rmd_total': round(rmd_tot),
            'surplus_reinvested': round(surplus),
            'glide_equity_pct': round(eq_pct * 100, 1) if (glide_on and any_ret) else None,
            'account_balances': {k: round(v) for k, v in bal.items()},
        })

    return results


def _run_ss_scenario(profile, a1, a2):
    """Run one SS scenario and extract summary metrics."""
    proj = project(profile, ss1_age_override=a1, ss2_age_override=a2, do_roth=False)
    ret_rows = [r for r in proj if r['phase'] == 'retirement']
    if not ret_rows:
        return None
    total_ss   = sum(r['total_ss']  for r in ret_rows)
    ss_p1      = sum(r['ss_p1']     for r in ret_rows)
    ss_p2      = sum(r['ss_p2']     for r in ret_rows)
    total_tax  = sum(r['total_tax'] for r in ret_rows)
    final_bal  = proj[-1]['total_balance']
    shortfall_yrs = sum(1 for r in ret_rows if r['shortfall'] > 0)
    return {
        'ss1_age': a1, 'ss2_age': a2,
        'total_lifetime_ss': round(total_ss),
        'lifetime_ss_p1':    round(ss_p1),
        'lifetime_ss_p2':    round(ss_p2),
        'total_lifetime_tax': round(total_tax),
        'final_balance':     round(final_bal),
        'shortfall_years':   shortfall_yrs,
        'score':             total_ss + final_bal - total_tax,
    }


def optimize_ss(profile):
    """Compare SS claiming ages for both people and find optimal timing.

    Returns:
      - comparisons: full matrix of all (p1_age, p2_age) combos
      - recommended: best combo overall
      - individual_p1: vary p1 age while holding p2 at optimal
      - individual_p2: vary p2 age while holding p1 at optimal
    """
    p1 = profile['person1']
    p2 = profile['person2']
    curr_yr = int(profile.get('current_year', 2026))
    p1_curr_age = curr_yr - int(p1['birth_year'])
    p2_curr_age = curr_yr - int(p2['birth_year'])

    p2_enabled = bool(p2.get('enabled', True))
    candidate_ages = [62, 63, 64, 65, 66, 67, 68, 69, 70]
    ages1 = [a for a in candidate_ages if a >= p1_curr_age]
    # When P2 is disabled, fix their SS age at FRA so the optimizer only varies P1
    ages2 = [int(p2.get('fra_age', 67))] if not p2_enabled else [a for a in candidate_ages if a >= p2_curr_age]

    # ── Full matrix ─────────────────────────────────────────────────────
    comparisons = []
    for a1 in ages1:
        for a2 in ages2:
            row = _run_ss_scenario(profile, a1, a2)
            if row:
                comparisons.append(row)

    if not comparisons:
        return {'comparisons': [], 'recommended': None,
                'individual_p1': [], 'individual_p2': []}

    best = max(comparisons, key=lambda x: x['score'])
    best_a1 = best['ss1_age']
    best_a2 = best['ss2_age']

    # ── Individual analysis: vary one person, hold other at optimal ──────
    individual_p1 = []
    for a1 in ages1:
        row = next((c for c in comparisons if c['ss1_age']==a1 and c['ss2_age']==best_a2), None)
        if row:
            individual_p1.append({
                'age': a1,
                'lifetime_ss':  row['lifetime_ss_p1'],
                'total_ss':     row['total_lifetime_ss'],
                'total_tax':    row['total_lifetime_tax'],
                'final_balance': row['final_balance'],
                'shortfall_years': row['shortfall_years'],
                'score':        row['score'],
            })

    individual_p2 = []
    for a2 in ages2:
        row = next((c for c in comparisons if c['ss1_age']==best_a1 and c['ss2_age']==a2), None)
        if row:
            individual_p2.append({
                'age': a2,
                'lifetime_ss':  row['lifetime_ss_p2'],
                'total_ss':     row['total_lifetime_ss'],
                'total_tax':    row['total_lifetime_tax'],
                'final_balance': row['final_balance'],
                'shortfall_years': row['shortfall_years'],
                'score':        row['score'],
            })

    return {
        'comparisons': comparisons,
        'recommended': {'ss1_age': best_a1, 'ss2_age': best_a2},
        'individual_p1': individual_p1,
        'individual_p2': individual_p2,
    }


# ─── SPENDING RECOMMENDATION ENGINE ─────────────────────────────────────────

def _final_balance_at_age(profile, annual_expenses, target_age):
    """Run a projection with the given annual_expenses and return the
    total_balance at the first row where p1_age >= target_age (or last row)."""
    p = copy.deepcopy(profile)
    p['annual_expenses'] = annual_expenses
    rows = project(p)
    if not rows:
        return 0.0
    # find the row at target_age; fall back to last row
    for r in rows:
        if r['p1_age'] >= target_age:
            return float(r['total_balance'])
    return float(rows[-1]['total_balance'])


def recommend_spending(profile, target_wealth=0, target_age=None, n_scenarios=5):
    """
    Binary-search annual_expenses to find the spending level that leaves
    `target_wealth` at `target_age`.

    Also returns a scenario table spanning from die-broke to a generous legacy.

    Returns:
      recommended_spending : annual spending that hits target_wealth at target_age
      current_spending     : annual_expenses in the profile
      current_end_balance  : projected balance at target_age with current spending
      target_age           : the age used
      target_wealth        : the requested end balance
      scenarios            : list of {label, annual_spending, end_balance, monthly_spending}
      shortfall_spending   : spending level that risks depletion (end_bal <= 0)
    """
    curr_yr  = int(profile.get('current_year', 2026))
    p1_by    = int(profile['person1']['birth_year'])
    p1_age   = curr_yr - p1_by

    # Default target age: last year of projection (typically age 95)
    if target_age is None:
        rows = project(copy.deepcopy(profile))
        target_age = rows[-1]['p1_age'] if rows else 95

    # Current-profile end balance
    current_spending = float(profile.get('annual_expenses', 100000))
    current_end_bal  = _final_balance_at_age(profile, current_spending, target_age)

    # ── Binary search: find spending that hits exactly target_wealth ──────────
    lo = 10_000.0
    hi = max(current_spending * 5, 500_000.0)

    # Ensure feasibility: at lo spending, end_bal must be >= target_wealth
    bal_at_lo = _final_balance_at_age(profile, lo, target_age)
    if bal_at_lo < target_wealth:
        # Even minimal spending doesn't reach the target — can't do it
        recommended = lo
    else:
        for _ in range(40):          # 40 iterations → ~$1 precision
            mid = (lo + hi) / 2.0
            bal = _final_balance_at_age(profile, mid, target_age)
            if bal > target_wealth:
                lo = mid             # can spend more
            else:
                hi = mid             # spending too much, back off
        recommended = (lo + hi) / 2.0

    # ── Scenario table ────────────────────────────────────────────────────────
    # Find the "spend everything" (die-broke) level first
    lo2, hi2 = 10_000.0, max(current_spending * 8, 1_000_000.0)
    bal_lo2 = _final_balance_at_age(profile, lo2, target_age)
    if bal_lo2 <= 0:
        die_broke = lo2
    else:
        for _ in range(40):
            mid2 = (lo2 + hi2) / 2.0
            if _final_balance_at_age(profile, mid2, target_age) > 0:
                lo2 = mid2
            else:
                hi2 = mid2
        die_broke = (lo2 + hi2) / 2.0

    # Build scenario anchors:
    #   Anchor 0 = die-broke, then evenly spaced up to recommended*1.5 legacy
    #   We'll create fixed legacy-wealth levels and compute spending for each
    legacy_targets = [0, 250_000, 500_000, 1_000_000, 2_000_000]

    def spending_for_target(tw):
        lo_s, hi_s = 10_000.0, max(current_spending * 8, 1_000_000.0)
        if _final_balance_at_age(profile, lo_s, target_age) < tw:
            return lo_s   # can't reach this legacy even at min spending
        for _ in range(40):
            mid_s = (lo_s + hi_s) / 2.0
            if _final_balance_at_age(profile, mid_s, target_age) > tw:
                lo_s = mid_s
            else:
                hi_s = mid_s
        return (lo_s + hi_s) / 2.0

    scenarios = []
    labels = ['Die Broke', '$250k Legacy', '$500k Legacy', '$1M Legacy', '$2M Legacy']
    for lbl, tw in zip(labels, legacy_targets):
        sp = spending_for_target(tw)
        eb = _final_balance_at_age(profile, sp, target_age)
        scenarios.append({
            'label':            lbl,
            'target_wealth':    tw,
            'annual_spending':  round(sp),
            'monthly_spending': round(sp / 12),
            'end_balance':      round(max(0, eb)),
            'vs_current_pct':   round((sp / current_spending - 1) * 100, 1) if current_spending else 0,
        })

    return {
        'recommended_spending': round(recommended),
        'recommended_monthly':  round(recommended / 12),
        'current_spending':     round(current_spending),
        'current_monthly':      round(current_spending / 12),
        'current_end_balance':  round(current_end_bal),
        'target_age':           target_age,
        'target_wealth':        target_wealth,
        'scenarios':            scenarios,
        'vs_current_pct':       round((recommended / current_spending - 1) * 100, 1) if current_spending else 0,
    }


# ─── NYS PENSION CALCULATOR ──────────────────────────────────────────────────

def calc_nys_pension(params):
    """
    Calculate NYS ERS or PFRS pension benefit from service record.

    ERS Tier formulas (NYSERS):
      Tier 3/4  (1976–2009): FAS = avg 3 highest consec. yrs
                              <20 yrs → 1.75% × FAS × service
                              ≥20 yrs → 2.00% × FAS × service (all years)
                              NRA 62; early reduction 6⅔%/yr before 62 unless 30+ yrs
      Tier 5    (2010–2012): FAS = avg 3 highest consec. yrs
                              2.00% × FAS × service (all years)
                              NRA 62; same early reduction rules
      Tier 6    (2012–now):  FAS = avg 5 highest consec. yrs
                              ≤20 yrs: 1.75% × FAS × service
                              21–30 yrs: +2.00% per yr over 20
                              31+ yrs:  +1.50% per yr over 30
                              NRA 63; early reduction 6⅔%/yr before 63 unless 30+ yrs

    PFRS (Police & Fire):     2.00% × FAS × service, max 60% (30 yrs)
                              NRA = 20 years of service at any age
    """
    system      = params.get('system', 'ERS')
    tier        = str(params.get('tier', '6'))
    cur_salary  = float(params.get('current_salary', 0))
    cur_age     = float(params.get('current_age', 55))
    cur_service = float(params.get('current_service_years', 0))
    raise_rate  = float(params.get('annual_raise_pct', 2.0)) / 100.0
    fas_yrs     = 5 if tier == '6' else 3   # Tier 6 uses 5-year FAS

    # ── Two ages that can differ ──────────────────────────────────────────────
    # leave_age:   when employment ends → service years and FAS are FROZEN here
    # benefit_age: when payments begin  → determines early-retirement reduction
    #   (you can leave at 57, defer benefits to 62, and avoid the 33% penalty)
    leave_age   = float(params.get('leave_employment_age', params.get('planned_retire_age', 65)))
    benefit_age = float(params.get('benefit_start_age',   params.get('planned_retire_age', leave_age)))
    benefit_age = max(benefit_age, leave_age)   # can't collect before leaving

    def project_fas_and_service(leave_at_age):
        """FAS and service are locked at the age employment ends — not when benefits start."""
        yrs_remaining = max(0.0, leave_at_age - cur_age)
        service = cur_service + yrs_remaining
        sal_at_leave = cur_salary * (1 + raise_rate) ** yrs_remaining
        if raise_rate == 0:
            fas = sal_at_leave
        else:
            fas = sum(sal_at_leave / (1 + raise_rate) ** i for i in range(fas_yrs)) / fas_yrs
        return fas, service

    def compute_benefit(fas, service, benefit_start_age):
        """
        Compute pension. Service/FAS are already locked at leave_age.
        benefit_start_age drives only the early-retirement reduction.
        """
        if fas <= 0 or service <= 0:
            return 0.0, 0.0, 0.0, 0.0, system

        if system == 'PFRS':
            gross = fas * min(service * 0.02, 0.60)
            return gross, gross / 12, 0.0, gross, 'PFRS'

        if tier in ('3', '4'):
            factor = 0.02 if service >= 20 else 0.0175
            gross  = fas * factor * service
            nra    = 62
            if benefit_start_age < nra and service < 30:
                reduction = min((nra - benefit_start_age) / 15.0, 0.50)
            else:
                reduction = 0.0
            annual = gross * (1.0 - reduction)
            return annual, annual / 12, reduction, gross, f'Tier {tier} ERS'

        elif tier == '5':
            gross = fas * 0.02 * service
            nra   = 62
            if benefit_start_age < nra and service < 30:
                reduction = min((nra - benefit_start_age) / 15.0, 0.50)
            else:
                reduction = 0.0
            annual = gross * (1.0 - reduction)
            return annual, annual / 12, reduction, gross, 'Tier 5 ERS'

        elif tier == '6':
            if service <= 20:
                gross = fas * 0.0175 * service
            elif service <= 30:
                gross = fas * 0.0175 * 20 + fas * 0.02 * (service - 20)
            else:
                gross = fas * 0.0175 * 20 + fas * 0.02 * 10 + fas * 0.015 * (service - 30)
            nra = 63
            if benefit_start_age < nra and service < 30:
                reduction = min((nra - benefit_start_age) / 15.0, 0.50)
            else:
                reduction = 0.0
            annual = gross * (1.0 - reduction)
            return annual, annual / 12, reduction, gross, 'Tier 6 ERS'

        else:
            gross = fas * 0.02 * service
            return gross, gross / 12, 0.0, gross, f'Tier {tier}'

    # ── Primary result: FAS/service frozen at leave_age, reduction at benefit_age ──
    fas, service = project_fas_and_service(leave_age)
    annual, monthly, reduction, gross, tier_label = compute_benefit(fas, service, benefit_age)

    # ── Comparison: hold leave_age fixed, vary benefit_start_age ─────────────
    # This reveals the value of deferring collection to reduce or eliminate penalty.
    comparison = []
    test_benefit_ages = sorted({55, 57, 60, 62, 63, 65, 67, int(leave_age), int(benefit_age)})
    for tba in test_benefit_ages:
        if tba < leave_age:      # can't collect before leaving
            continue
        if tba < cur_age:
            continue
        a, m, red, gr, _ = compute_benefit(fas, service, tba)
        comparison.append({
            'leave_age':       int(leave_age),
            'benefit_age':     tba,
            'service_years':   round(service, 1),
            'fas':             round(fas),
            'gross_annual':    round(gr),
            'reduction_pct':   round(red * 100, 1),
            'annual_benefit':  round(a),
            'monthly_benefit': round(m),
            'pct_of_fas':      round(a / fas * 100, 1) if fas > 0 else 0,
        })

    return {
        'ok': True,
        'tier_label':  tier_label,
        'fas_years':   fas_yrs,
        'leave_age':   leave_age,
        'benefit_age': benefit_age,
        'planned': {
            'leave_age':       leave_age,
            'benefit_age':     benefit_age,
            'service_years':   round(service, 1),
            'fas':             round(fas),
            'gross_annual':    round(gross),
            'annual_benefit':  round(annual),
            'monthly_benefit': round(monthly),
            'reduction_pct':   round(reduction * 100, 1),
            'pct_of_fas':      round(annual / fas * 100, 1) if fas > 0 else 0,
        },
        'comparison': comparison,
    }


# ─── DEFAULT PROFILE ─────────────────────────────────────────────────────────

DEFAULT_PROFILE = {
    "current_year": 2026,
    "inflation": 0.03,
    "annual_expenses": 0,
    "spending_phases": [
        {"label": "Active (Go-Go)",   "through_age": 72, "multiplier": 1.00},
        {"label": "Slower (Slow-Go)", "through_age": 82, "multiplier": 0.85},
        {"label": "Later (No-Go)",    "through_age": 95, "multiplier": 0.70}
    ],
    "medical": {
        "pre_medicare_annual": 0,
        "post_medicare_annual": 0,
        "medicare_age": 65,
        "inflation_rate": 0.05
    },
    "person1": {
        "name": "Person 1",
        "birth_year": 1970,
        "retirement_age": 65,
        "fra_age": 67,
        "ss_fra_monthly": 0,
        "life_expectancy": 90
    },
    "person2": {
        "name": "Person 2",
        "birth_year": 1972,
        "retirement_age": 65,
        "fra_age": 67,
        "ss_fra_monthly": 0,
        "life_expectancy": 90
    },
    "accounts": {
        "account1": {"label": "401k (Person 1)",    "type": "traditional", "owner": "p1", "balance": 0, "growth_rate": 0.07, "ret_growth": 0.06},
        "account2": {"label": "401k (Person 2)",    "type": "traditional", "owner": "p2", "balance": 0, "growth_rate": 0.07, "ret_growth": 0.06},
        "account3": {"label": "Roth IRA (Person 1)","type": "roth",        "owner": "p1", "balance": 0, "growth_rate": 0.07, "ret_growth": 0.06},
        "account4": {"label": "Roth IRA (Person 2)","type": "roth",        "owner": "p2", "balance": 0, "growth_rate": 0.07, "ret_growth": 0.06},
        "account5": {"label": "Brokerage",          "type": "taxable",     "owner": "p1", "balance": 0, "growth_rate": 0.07, "ret_growth": 0.06},
        "account6": {"label": "Savings / HYSA",     "type": "savings",     "owner": "p1", "balance": 0, "growth_rate": 0.045,"ret_growth": 0.04}
    },
    "contributions": {
        "account1": 0,
        "account2": 0,
        "account3": 0,
        "account4": 0,
        "account5": 0,
        "account6": 0
    },
    "catch_up_contributions": {
        "account1": 0,
        "account2": 0,
        "account3": 0,
        "account4": 0
    },
    "super_catch_up_contributions": {
        "account1": 0,
        "account2": 0,
        "account3": 0,
        "account4": 0
    },
    "pension1": {
        "name": "Pension 1",
        "owner": "p1",
        "monthly_benefit": 0,
        "survivor_monthly": 0,
        "start_age": 65,
        "cola": 0.0,
        "nys_exempt": False
    },
    "pension2": {
        "name": "Pension 2",
        "owner": "p2",
        "monthly_benefit": 0,
        "survivor_monthly": 0,
        "start_age": 65,
        "cola": 0.0,
        "nys_exempt": False
    },
    "strategy": {
        "ss1_age": 67,
        "ss2_age": 67
    }
}


# ─── HTTP SERVER ─────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # Quiet server log

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype):
        try:
            with open(path, 'rb') as f:
                body = f.read()
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except FileNotFoundError:
            self.send_response(404); self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if self.path in ('/', '/index.html'):
            self.send_file(os.path.join(CURRENT_DIR, 'index.html'), 'text/html; charset=utf-8')
        elif self.path == '/api/profile':
            if os.path.exists(DATA_FILE):
                with open(DATA_FILE) as f:
                    self.send_json(json.load(f))
            else:
                self.send_json(DEFAULT_PROFILE)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            self.send_json({'error': 'Invalid JSON'}, 400); return

        if self.path == '/api/save':
            try:
                with open(DATA_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                self.send_json({'ok': True})
            except Exception as e:
                self.send_json({'error': str(e)}, 500)

        elif self.path == '/api/calculate':
            try:
                results = project(data)
                self.send_json({'ok': True, 'results': results})
            except Exception as e:
                import traceback
                self.send_json({'error': str(e), 'trace': traceback.format_exc()}, 500)

        elif self.path == '/api/calculate_no_roth':
            try:
                results = project(data, do_roth=False)
                self.send_json({'ok': True, 'results': results})
            except Exception as e:
                self.send_json({'error': str(e)}, 500)

        elif self.path == '/api/optimize_ss':
            try:
                result = optimize_ss(data)
                self.send_json({'ok': True, **result})
            except Exception as e:
                import traceback
                self.send_json({'error': str(e), 'trace': traceback.format_exc()}, 500)

        elif self.path == '/api/calc_nys_pension':
            try:
                result = calc_nys_pension(data)
                self.send_json(result)
            except Exception as e:
                import traceback
                self.send_json({'error': str(e), 'trace': traceback.format_exc()}, 500)

        elif self.path == '/api/recommend':
            try:
                target_wealth = float(data.get('target_wealth', 0))
                target_age    = data.get('target_age', None)
                if target_age is not None:
                    target_age = int(target_age)
                profile_data  = data.get('profile', data)
                result = recommend_spending(profile_data, target_wealth=target_wealth, target_age=target_age)
                self.send_json({'ok': True, **result})
            except Exception as e:
                import traceback
                self.send_json({'error': str(e), 'trace': traceback.format_exc()}, 500)

        elif self.path == '/api/monte_carlo':
            try:
                n_sims     = max(100, min(2000, int(data.get('n_sims', 500))))
                vol        = max(0.0, min(0.40, float(data.get('volatility', 0.12))))
                gr_cut     = max(0.0, min(0.30, float(data.get('gr_cut',   0.10))))
                gr_boost   = max(0.0, min(0.30, float(data.get('gr_boost', 0.10))))
                gr_floor   = max(0.50, min(1.00, float(data.get('gr_floor', 0.85))))
                gr_ceil    = max(1.00, min(2.00, float(data.get('gr_ceil',  1.25))))
                result     = monte_carlo(data, n_sims=n_sims, volatility=vol,
                                         guardrails=True, gr_cut=gr_cut,
                                         gr_boost=gr_boost, gr_floor=gr_floor,
                                         gr_ceil=gr_ceil)
                self.send_json(result)
            except Exception as e:
                import traceback
                self.send_json({'error': str(e), 'trace': traceback.format_exc()}, 500)

        else:
            self.send_response(404); self.end_headers()


def _run_sim_set(all_shocks, start_bal, withdrawals, drift, ages,
                 guardrails=False, gr_upper=1.20, gr_lower=0.80,
                 gr_cut=0.10, gr_boost=0.10, gr_floor=0.85, gr_ceil=1.25):
    """
    Replay a pre-generated shock matrix against the withdrawal schedule.
    Returns percentiles, success stats, and guardrail trigger info.
    Using the same shock matrix for base and guardrail runs gives a
    true apples-to-apples comparison of what the circuit breakers buy.
    """
    n_sims   = len(all_shocks)
    n_years  = len(withdrawals)
    initial_wr = withdrawals[0] / start_bal if start_bal > 0 else 0

    all_balances   = []
    depletion_ages = []
    trigger_years  = 0       # total sim-years a guardrail fired
    total_adj      = 0.0     # cumulative adjustment factor (for avg)

    for shocks in all_shocks:
        bal         = float(start_bal)
        sim_bals    = []
        depleted_at = None
        adj_mult    = 1.0    # running guardrail multiplier

        for i in range(n_years):
            base_w = withdrawals[i]

            if guardrails and bal > 0 and initial_wr > 0:
                # Current withdrawal rate vs initial rate
                current_wr  = (base_w * adj_mult) / bal
                rate_ratio  = current_wr / initial_wr

                if rate_ratio > gr_upper:
                    # Portfolio stressed — cut spending
                    new_mult = adj_mult * (1.0 - gr_cut)
                    adj_mult = max(new_mult, gr_floor)
                    trigger_years += 1
                elif rate_ratio < gr_lower:
                    # Portfolio thriving — allow more spending
                    new_mult = adj_mult * (1.0 + gr_boost)
                    adj_mult = min(new_mult, gr_ceil)
                    trigger_years += 1

            actual_w = base_w * adj_mult if guardrails else base_w
            total_adj += adj_mult

            annual_return = drift + shocks[i]
            bal = max(0.0, (bal - actual_w) * (1.0 + annual_return))
            sim_bals.append(round(bal))
            if bal == 0 and depleted_at is None:
                depleted_at = ages[i]

        all_balances.append(sim_bals)
        depletion_ages.append(depleted_at)

    # ── Percentiles ────────────────────────────────────────────────────────
    percentiles = {}
    for pct in [10, 25, 50, 75, 90]:
        idx = max(0, min(n_sims - 1, int(round(n_sims * pct / 100))))
        percentiles[str(pct)] = [
            sorted(s[y] for s in all_balances)[idx]
            for y in range(n_years)
        ]

    n_success      = sum(1 for d in depletion_ages if d is None)
    failed_ages    = sorted(d for d in depletion_ages if d is not None)
    total_sim_yrs  = n_sims * n_years

    return {
        'percentiles':         percentiles,
        'success_rate':        round(n_success / n_sims * 100, 1),
        'n_depleted':          n_sims - n_success,
        'median_final':        percentiles['50'][-1] if percentiles['50'] else 0,
        'worst_10_final':      percentiles['10'][-1] if percentiles['10'] else 0,
        'best_90_final':       percentiles['90'][-1] if percentiles['90'] else 0,
        'median_depletion_age': failed_ages[len(failed_ages) // 2] if failed_ages else None,
        'trigger_pct':         round(trigger_years / total_sim_yrs * 100, 1) if guardrails else 0,
        'avg_spend_adj_pct':   round((total_adj / total_sim_yrs - 1.0) * 100, 1) if guardrails else 0,
    }


def monte_carlo(profile, n_sims=500, volatility=0.12,
                guardrails=False, gr_cut=0.10, gr_boost=0.10,
                gr_floor=0.85, gr_ceil=1.25,
                gr_upper=1.20, gr_lower=0.80):
    """
    Monte Carlo simulation with optional dynamic-spending guardrails.

    The same random shock matrix is used for both the base run and the
    guardrail run, so the two results are directly comparable — the only
    difference is whether the circuit breakers are active.

    Guardrail logic (Guyton-Klinger style):
      - Track current withdrawal rate vs. initial withdrawal rate.
      - If current rate rises above gr_upper × initial (portfolio shrinking
        faster than expected) → cut spending by gr_cut, floor at gr_floor.
      - If current rate falls below gr_lower × initial (portfolio doing well)
        → boost spending by gr_boost, ceiling at gr_ceil.
    """
    base     = project(profile)
    ret_rows = [r for r in base if r['phase'] == 'retirement']
    pre_rows = [r for r in base if r['phase'] == 'accumulation']

    if not ret_rows:
        return {'error': 'No retirement years to simulate'}

    # Starting balance at retirement
    if pre_rows:
        start_bal = float(pre_rows[-1]['total_balance'])
    else:
        start_bal = float(ret_rows[0]['total_balance']) + float(ret_rows[0]['withdrawal_total'])

    n_years     = len(ret_rows)
    ages        = [r['p1_age'] for r in ret_rows]
    withdrawals = [float(r['withdrawal_total']) for r in ret_rows]

    # Weighted average base growth rate
    accts     = profile.get('accounts', {})
    total_val = sum(float(v.get('balance', 0)) for v in accts.values())
    if total_val > 0:
        base_growth = sum(
            float(v.get('ret_growth', float(v.get('growth_rate', 0.065)) * 0.85))
            * float(v.get('balance', 0))
            for v in accts.values()
        ) / total_val
    else:
        base_growth = 0.065

    drift = base_growth - (volatility ** 2) / 2.0  # geometric mean correction

    # ── Generate shocks ONCE; reuse for both runs ─────────────────────────
    all_shocks = [
        [random.gauss(0, volatility) for _ in range(n_years)]
        for _ in range(n_sims)
    ]

    base_res = _run_sim_set(all_shocks, start_bal, withdrawals, drift, ages)

    result = {
        'ok':              True,
        'ages':            ages,
        'n_sims':          n_sims,
        'volatility':      round(volatility * 100, 1),
        'base_growth_pct': round(base_growth * 100, 2),
        'guardrails_enabled': guardrails,
        **{k: base_res[k] for k in [
            'percentiles', 'success_rate', 'n_depleted',
            'median_final', 'worst_10_final', 'best_90_final',
            'median_depletion_age',
        ]},
    }

    if guardrails:
        gr_res = _run_sim_set(
            all_shocks, start_bal, withdrawals, drift, ages,
            guardrails=True,
            gr_upper=gr_upper, gr_lower=gr_lower,
            gr_cut=gr_cut,    gr_boost=gr_boost,
            gr_floor=gr_floor, gr_ceil=gr_ceil,
        )
        result.update({
            'percentiles_gr':        gr_res['percentiles'],
            'success_rate_gr':       gr_res['success_rate'],
            'n_depleted_gr':         gr_res['n_depleted'],
            'median_final_gr':       gr_res['median_final'],
            'worst_10_final_gr':     gr_res['worst_10_final'],
            'best_90_final_gr':      gr_res['best_90_final'],
            'median_depletion_age_gr': gr_res['median_depletion_age'],
            'trigger_pct':           gr_res['trigger_pct'],
            'avg_spend_adj_pct':     gr_res['avg_spend_adj_pct'],
            'gr_cut_pct':            round(gr_cut   * 100),
            'gr_boost_pct':          round(gr_boost * 100),
            'gr_floor_pct':          round(gr_floor * 100),
            'gr_ceil_pct':           round(gr_ceil  * 100),
        })

    return result


if __name__ == '__main__':
    import socket
    class ReusableHTTPServer(ThreadingHTTPServer):
        allow_reuse_address = True
        def server_bind(self):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            super().server_bind()
    server = ReusableHTTPServer(('localhost', PORT), Handler)
    url = f"http://localhost:{PORT}"
    print(f"\n{'='*52}")
    print(f"  Retirement Planner is running!")
    print(f"  Open: {url}")
    print(f"  Press Ctrl+C to stop")
    print(f"{'='*52}\n")
    # Auto-open browser after a short delay (gives server time to start)
    threading.Timer(1.2, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nServer stopped.")

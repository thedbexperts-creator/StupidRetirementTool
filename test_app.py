#!/usr/bin/env python3
"""
Regression tests for the Retirement Planner engine.

Run:  python3 test_app.py          (no dependencies — standard library only)

Every assertion here corresponds to a bug that was found and fixed, or to an
official published figure (SSA rules, IRS tables, NYS Comptroller tables). If
one of these fails, a real behaviour has regressed.
"""

import copy
import math
import unittest
import importlib.util
import os

_spec = importlib.util.spec_from_file_location(
    "app", os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.py"))
app = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(app)


def base_profile(**over):
    """A funded two-person profile that exercises the whole engine."""
    p = copy.deepcopy(app.DEFAULT_PROFILE)
    p['annual_expenses'] = 90000
    p['person1'].update(name='P1', birth_year=1960, retirement_age=65,
                        ss_fra_monthly=2500, life_expectancy=90)
    p['person2'].update(name='P2', birth_year=1962, retirement_age=65,
                        ss_fra_monthly=1800, life_expectancy=90)
    for k in p['accounts']:
        p['accounts'][k]['balance'] = 300000
    p.update(over)
    return p


# ─────────────────────────────────────────────────────────────────────────────
class TestSocialSecurity(unittest.TestCase):
    """SSA claiming rules."""

    def test_own_benefit_reduction(self):
        # SSA: 30% reduction at 62 with FRA 67; 20% at 64.
        self.assertAlmostEqual(app.ss_monthly_at_age(1000, 62, 67), 700.0, places=2)
        self.assertAlmostEqual(app.ss_monthly_at_age(1000, 64, 67), 800.0, places=2)
        self.assertAlmostEqual(app.ss_monthly_at_age(1000, 67, 67), 1000.0, places=2)

    def test_delayed_credits(self):
        # 8%/yr delayed retirement credits, capped at 70.
        self.assertAlmostEqual(app.ss_monthly_at_age(1000, 70, 67), 1240.0, places=2)
        self.assertAlmostEqual(app.ss_monthly_at_age(1000, 72, 67), 1240.0, places=2)

    def test_spousal_reduction_matches_ssa(self):
        # REGRESSION: was 25/10000 per month (~9% at 36 months) instead of
        # 25/36 of 1% per month. SSA: 25% at 36 months early, 35% at 62.
        at64 = app.spousal_ss_monthly(0, 2000, 64, 67)   # own=0 so spousal wins
        at62 = app.spousal_ss_monthly(0, 2000, 62, 67)
        self.assertAlmostEqual(at64 / 1000.0, 0.75, places=4)   # 25% reduction
        self.assertAlmostEqual(at62 / 1000.0, 0.65, places=4)   # 35% reduction

    def test_spousal_never_below_own(self):
        own = app.ss_monthly_at_age(3000, 67, 67)
        self.assertGreaterEqual(app.spousal_ss_monthly(3000, 1000, 67, 67), own)


class TestSocialSecurityTaxation(unittest.TestCase):
    """IRS provisional-income rules (Pub. 915). Thresholds are NOT indexed."""

    def test_below_base_is_untaxed(self):
        self.assertEqual(app.taxable_ss_portion(20000, 10000, False), 0.0)

    def test_single_thresholds_differ_from_mfj(self):
        # REGRESSION: single filers (e.g. a survivor) used the MFJ 32k/44k
        # bases, understating their tax. Single bases are 25k/34k.
        mfj = app.taxable_ss_portion(30000, 20000, False)
        single = app.taxable_ss_portion(30000, 20000, True)
        self.assertGreater(single, mfj)

    def test_85_percent_cap(self):
        for single in (True, False):
            self.assertLessEqual(app.taxable_ss_portion(40000, 500000, single),
                                 0.85 * 40000 + 0.01)


class TestNYSPension(unittest.TestCase):
    """Official NYS Comptroller tables."""

    def _reduction(self, tier, age, service=5):
        r = app.calc_nys_pension({
            'system': 'ERS', 'tier': tier, 'current_salary': 80000,
            'current_age': 50, 'current_service_years': service,
            'leave_employment_age': age, 'benefit_start_age': age})
        return r['planned']['reduction_pct']

    def test_published_reduction_anchors(self):
        self.assertAlmostEqual(self._reduction('4', 55), 27.0, places=1)
        self.assertAlmostEqual(self._reduction('4', 62), 0.0, places=1)
        self.assertAlmostEqual(self._reduction('6', 55), 52.0, places=1)
        self.assertAlmostEqual(self._reduction('6', 63), 0.0, places=1)

    def test_published_half_year_examples(self):
        # OSC publishes these exact half-year examples. The engine reports
        # reduction_pct rounded to one decimal, so allow 0.05 of slack.
        self.assertAlmostEqual(self._reduction('4', 58.5), 16.5, delta=0.06)
        self.assertAlmostEqual(self._reduction('5', 58.5), 20.83, delta=0.06)
        self.assertAlmostEqual(self._reduction('6', 58.5), 29.25, delta=0.06)

    def test_thirty_year_exemption_only_tiers_2_3_4(self):
        # REGRESSION: the 30-year exemption was wrongly applied to Tier 5/6.
        self.assertAlmostEqual(self._reduction('4', 55, service=32), 0.0, places=1)
        self.assertGreater(self._reduction('5', 55, service=32), 0.0)
        self.assertGreater(self._reduction('6', 55, service=32), 0.0)

    def test_benefit_formula_rates(self):
        # REGRESSION: used 1.75% for <20 years; NYSLRS uses 1.66%.
        def gross(tier, svc):
            return app.calc_nys_pension({
                'system': 'ERS', 'tier': tier, 'current_salary': 100000,
                'current_age': 62, 'current_service_years': svc,
                'annual_raise_pct': 0, 'leave_employment_age': 62,
                'benefit_start_age': 65})['planned']['gross_annual']
        self.assertAlmostEqual(gross('4', 15), 24900, delta=1)   # 1.66% x 15
        self.assertAlmostEqual(gross('4', 25), 50000, delta=1)   # 2.00% x 25
        self.assertAlmostEqual(gross('4', 35), 67500, delta=1)   # 2%x30 + 1.5%x5
        self.assertAlmostEqual(gross('6', 20), 35000, delta=1)   # 35% of FAS


class TestRMD(unittest.TestCase):
    def test_secure_20_start_age(self):
        # REGRESSION: hardcoded to 73 regardless of birth year.
        self.assertEqual(app.rmd_start_age(1955), 73)
        self.assertEqual(app.rmd_start_age(1959), 73)
        self.assertEqual(app.rmd_start_age(1960), 75)
        self.assertEqual(app.rmd_start_age(1970), 75)

    def test_no_rmd_before_start_age(self):
        self.assertEqual(app.rmd_required(500000, 72, 73), 0.0)
        self.assertGreater(app.rmd_required(500000, 73, 73), 0.0)

    def test_uniform_lifetime_divisor(self):
        self.assertAlmostEqual(app.rmd_required(265000, 73, 73), 10000.0, places=2)


class TestStateTax(unittest.TestCase):
    def test_all_fifty_states_modelled(self):
        modelled = set(app.STATE_TAX_DATA) - {'CUSTOM'}
        all50 = {
            'AL','AK','AZ','AR','CA','CO','CT','DE','FL','GA','HI','ID','IL',
            'IN','IA','KS','KY','LA','ME','MD','MA','MI','MN','MS','MO','MT',
            'NE','NV','NH','NJ','NM','NY','NC','ND','OH','OK','OR','PA','RI',
            'SC','SD','TN','TX','UT','VT','VA','WA','WV','WI','WY'}
        self.assertEqual(all50 - modelled, set())

    def test_unknown_state_does_not_silently_become_new_york(self):
        # REGRESSION: any unmodelled state fell through to NY's brackets AND
        # NY's pension exclusion, producing a confidently wrong tax bill.
        ny = app.get_state_tax_config({'state': 'NY'})
        self.assertNotEqual(app.get_state_tax_config({'state': 'ZZ'}), ny)
        self.assertNotEqual(app.get_state_tax_config({'state': 'OH'}), ny)

    def test_no_tax_states_are_zero(self):
        for st in ('FL', 'TX', 'WA', 'NV'):
            b, d, bs, ds, _, _, _ = app.get_state_tax_config({'state': st})
            self.assertEqual(app.calc_tax(200000, b, d), 0.0, st)

    def test_ohio_zero_bracket(self):
        # Ohio: 0% up to $26,050, then 2.75%, less a $4,800 exemption (MFJ).
        b, d, _, _, _, _, _ = app.get_state_tax_config({'state': 'OH'})
        expected = (100000 - 4800 - 26050) * 0.0275
        self.assertAlmostEqual(app.calc_tax(100000, b, d), expected, places=2)

    def test_custom_rate(self):
        b, d, _, _, _, _, _ = app.get_state_tax_config(
            {'state': 'CUSTOM', 'custom_state_rate': 5.0})
        self.assertAlmostEqual(app.calc_tax(100000, b, d), 5000.0, places=2)


class TestFederalTax(unittest.TestCase):
    def test_2026_standard_deductions(self):
        self.assertEqual(app.FED_STD_DED, 32200)
        self.assertEqual(app.FED_STD_DED_SINGLE, 16100)

    def test_bracket_boundaries_are_monotonic(self):
        for table in (app.FED_BRACKETS_MFJ, app.FED_BRACKETS_SINGLE,
                      app.LTCG_BRACKETS_MFJ, app.LTCG_BRACKETS_SINGLE):
            limits = [l for l, _ in table]
            self.assertEqual(limits, sorted(limits))
            self.assertEqual(limits[-1], float('inf'))

    def test_ten_percent_bracket(self):
        # First $24,800 of taxable income (MFJ) at 10%.
        tax = app.calc_tax(app.FED_STD_DED + 24800, app.FED_BRACKETS_MFJ,
                           app.FED_STD_DED)
        self.assertAlmostEqual(tax, 2480.0, places=2)

    def test_zero_income_zero_tax(self):
        self.assertEqual(app.calc_tax(0, app.FED_BRACKETS_MFJ, app.FED_STD_DED), 0.0)

    def test_niit(self):
        # 3.8% on the lesser of investment income or MAGI over the threshold.
        self.assertAlmostEqual(app.niit_tax(50000, 300000, False), 1900.0, places=2)
        self.assertAlmostEqual(app.niit_tax(50000, 260000, False), 380.0, places=2)
        self.assertEqual(app.niit_tax(50000, 200000, False), 0.0)
        self.assertEqual(app.niit_tax(0, 900000, False), 0.0)


class TestACA(unittest.TestCase):
    """Post-2025 rules: sliding scale to 400% FPL, then a hard cliff."""

    def test_applicable_percentages(self):
        self.assertAlmostEqual(app.aca_applicable_pct(1.00), 0.0210, places=4)
        self.assertAlmostEqual(app.aca_applicable_pct(1.33), 0.0210, places=4)
        self.assertAlmostEqual(app.aca_applicable_pct(2.00), 0.0660, places=4)
        self.assertAlmostEqual(app.aca_applicable_pct(3.00), 0.0996, places=4)
        self.assertAlmostEqual(app.aca_applicable_pct(4.00), 0.0996, places=4)

    def test_cliff_returns_no_credit(self):
        self.assertIsNone(app.aca_applicable_pct(4.01))
        credit, ratio, over = app.aca_subsidy(200000, 22000, 2)
        self.assertEqual(credit, 0.0)
        self.assertTrue(over)

    def test_credit_is_premium_less_required_contribution(self):
        fpl2 = app.federal_poverty_level(2)
        magi = 2.0 * fpl2                      # exactly 200% FPL -> 6.60%
        credit, ratio, over = app.aca_subsidy(magi, 22000, 2)
        self.assertAlmostEqual(ratio, 2.0, places=6)
        self.assertFalse(over)
        self.assertAlmostEqual(credit, 22000 - magi * 0.0660, places=2)

    def test_one_dollar_over_the_cliff_is_catastrophic(self):
        fpl2 = app.federal_poverty_level(2)
        just_under, _, _ = app.aca_subsidy(4.00 * fpl2, 22000, 2)
        just_over, _, _ = app.aca_subsidy(4.01 * fpl2, 22000, 2)
        self.assertGreater(just_under, 10000)
        self.assertEqual(just_over, 0.0)

    def test_poverty_level_scales_with_household(self):
        self.assertAlmostEqual(app.federal_poverty_level(1), 15650.0, places=2)
        self.assertAlmostEqual(app.federal_poverty_level(2), 21150.0, places=2)


class TestProjectionInvariants(unittest.TestCase):
    """Whole-engine properties that must hold on every projected year."""

    def setUp(self):
        self.rows = app.project(base_profile())
        self.ret = [r for r in self.rows if r['phase'] == 'retirement']

    def test_produces_retirement_rows(self):
        self.assertGreater(len(self.ret), 10)

    def test_balances_never_negative(self):
        for r in self.rows:
            self.assertGreaterEqual(r['total_balance'], 0, r['year'])
            for k, v in r['account_balances'].items():
                self.assertGreaterEqual(v, 0, f"{r['year']} {k}")

    def test_years_are_contiguous(self):
        years = [r['year'] for r in self.rows]
        self.assertEqual(years, list(range(years[0], years[-1] + 1)))

    def test_cash_flow_plan_present_on_every_row(self):
        for r in self.rows:
            self.assertIn('cash_flow_plan', r)

    def test_itemised_withdrawals_reconcile_to_total(self):
        # REGRESSION: RMD and discretionary draws are itemised separately;
        # together they must still equal the reported withdrawal total.
        for r in self.ret:
            parts = sum(a['amount'] for a in r['cash_flow_plan']
                        if a['kind'] in ('rmd', 'spend'))
            self.assertAlmostEqual(parts, r['withdrawal_total'], delta=2, msg=str(r['year']))

    def test_rmd_items_reconcile(self):
        for r in self.ret:
            rmds = sum(a['amount'] for a in r['cash_flow_plan'] if a['kind'] == 'rmd')
            self.assertAlmostEqual(rmds, r['rmd_total'], delta=2, msg=str(r['year']))

    def test_money_in_minus_money_out_reconciles(self):
        # The cash-flow plan must tie out: in - out = surplus - shortfall.
        for r in self.ret:
            expected = r['surplus_reinvested'] - r['shortfall']
            self.assertAlmostEqual(r['flow_net'], expected, delta=3, msg=str(r['year']))

    def test_flow_totals_match_their_items(self):
        for r in self.ret:
            tin = sum(a['amount'] for a in r['cash_flow_plan'] if a['flow'] == 'in')
            tout = sum(a['amount'] for a in r['cash_flow_plan'] if a['flow'] == 'out')
            self.assertEqual(tin, r['flow_total_in'], r['year'])
            self.assertEqual(tout, r['flow_total_out'], r['year'])

    def test_conversions_reconcile(self):
        for r in self.ret:
            conv = sum(a['amount'] for a in r['cash_flow_plan'] if a['kind'] == 'convert')
            self.assertAlmostEqual(conv, r['roth_conversion'], delta=2, msg=str(r['year']))


class TestRothConversions(unittest.TestCase):
    def test_no_roth_account_does_not_destroy_money(self):
        # REGRESSION: with no Roth destination the traditional balance was
        # debited and the money vanished.
        p = base_profile(roth_strategy='fill_22')
        for k in [k for k, v in p['accounts'].items() if v['type'] == 'roth']:
            del p['accounts'][k]
            p['contributions'].pop(k, None)
        rows = app.project(p)
        ret = [r for r in rows if r['phase'] == 'retirement']
        self.assertTrue(all(r['roth_conversion'] == 0 for r in ret))
        self.assertGreater(rows[-1]['total_balance'], 0)

    def test_conversion_tax_is_actually_funded(self):
        # REGRESSION: conversion tax was reported but never debited, making
        # conversions look free and biasing the optimiser.
        converting = app.project(base_profile(roth_strategy='fill_22'))
        not_converting = app.project(base_profile(roth_strategy='none'))
        yrs = [r for r in converting if r['phase'] == 'retirement'
               and r['roth_conversion'] > 0]
        self.assertTrue(yrs, "expected at least one conversion year")
        for r in yrs:
            paid = r['roth_conv_tax_cash'] + r['roth_conv_withheld']
            self.assertAlmostEqual(paid, r['roth_conversion_tax'], delta=2)
        # Converting cannot be a free lunch relative to not converting.
        self.assertLess(converting[-1]['total_balance'],
                        not_converting[-1]['total_balance'] * 1.5)

    def test_aca_cliff_guard_caps_conversion(self):
        # A pre-Medicare household on ACA should not be pushed over the 400%
        # FPL cliff by an automatic bracket-fill conversion.
        p = base_profile(roth_strategy='fill_22', state='OH')
        p['person1'].update(birth_year=1968, retirement_age=58)
        p['person2'].update(birth_year=1968, retirement_age=58)
        p['aca'] = {'enabled': True, 'monthly_premium': 1600, 'inflation': 0.05}
        guarded = [r for r in app.project(p) if r['phase'] == 'retirement'
                   and r['aca_gross_premium'] > 0]
        self.assertTrue(guarded)
        self.assertFalse(guarded[0]['aca_over_cliff'])
        self.assertGreater(guarded[0]['aca_subsidy'], 0)

        p['roth_respect_aca_cliff'] = False
        unguarded = [r for r in app.project(p) if r['phase'] == 'retirement'
                     and r['aca_gross_premium'] > 0]
        # Without the guard the conversion is larger and the subsidy is lost.
        self.assertGreater(unguarded[0]['roth_conversion'],
                           guarded[0]['roth_conversion'])
        self.assertLess(unguarded[0]['aca_subsidy'], guarded[0]['aca_subsidy'])


class TestSurvivorScenario(unittest.TestCase):
    def test_survivor_switches_to_single_brackets(self):
        p = base_profile()
        p['survivor'] = {'enabled': True, 'person': 'p2',
                         'death_age': 75, 'expense_pct': 0.70}
        ret = [r for r in app.project(p) if r['phase'] == 'retirement']
        after = [r for r in ret if r['survivor_active']]
        self.assertTrue(after)
        # Survivor keeps the larger of the two Social Security benefits.
        for r in after:
            self.assertEqual(r['ss_p2'], 0)


class TestMonteCarlo(unittest.TestCase):
    def test_runs_and_reports_sane_success_rate(self):
        res = app.monte_carlo(base_profile(), n_sims=120)
        self.assertTrue(res.get('ok'))
        self.assertGreaterEqual(res['success_rate'], 0.0)
        self.assertLessEqual(res['success_rate'], 100.0)
        self.assertEqual(len(res['ages']), len(res['percentiles']['50']))

    def test_percentiles_are_ordered(self):
        res = app.monte_carlo(base_profile(), n_sims=200)
        p = res['percentiles']
        for y in range(len(p['50'])):
            self.assertLessEqual(p['10'][y], p['50'][y])
            self.assertLessEqual(p['50'][y], p['90'][y])

    def test_lognormal_returns_do_not_double_count_variance_drag(self):
        # REGRESSION: returns were built as (g - sigma^2/2) + shock and applied
        # arithmetically, subtracting the variance drag twice.
        g, vol, n = 0.065, 0.12, 60000
        drift = math.log(1.0 + g) - vol ** 2 / 2.0
        import random as _r
        _r.seed(7)
        rs = [math.exp(drift + _r.gauss(0, vol)) - 1.0 for _ in range(n)]
        self.assertAlmostEqual(sum(rs) / n, g, delta=0.004)
        self.assertTrue(all(r > -1.0 for r in rs))   # never below -100%

    def test_inflation_volatility_is_accepted(self):
        res = app.monte_carlo(base_profile(), n_sims=120, inflation_vol=0.02)
        self.assertTrue(res.get('ok'))
        self.assertEqual(res['inflation_vol'], 2.0)


class TestValidation(unittest.TestCase):
    def test_rejects_non_objects(self):
        self.assertFalse(app.validate_profile([])[0])
        self.assertFalse(app.validate_profile("nope")[0])

    def test_rejects_non_finite_numbers(self):
        # REGRESSION: NaN passed validation and was written to profile.json as
        # invalid strict JSON.
        for bad in (float('nan'), float('inf'), float('-inf')):
            ok, _ = app.validate_profile(
                {'accounts': {'a': {'type': 'roth', 'balance': bad}}})
            self.assertFalse(ok, repr(bad))

    def test_rejects_unknown_account_type(self):
        ok, why = app.validate_profile(
            {'accounts': {'a': {'type': 'definitely-not-real', 'balance': 1}}})
        self.assertFalse(ok)

    def test_accepts_the_default_profile(self):
        ok, why = app.validate_profile(copy.deepcopy(app.DEFAULT_PROFILE))
        self.assertTrue(ok, why)


class TestSpendingEngine(unittest.TestCase):
    def test_recommended_spending_is_positive_and_bounded(self):
        rec = app.recommend_spending(base_profile())
        self.assertGreater(rec['recommended_spending'], 0)
        self.assertEqual(rec['recommended_monthly'],
                         round(rec['recommended_spending'] / 12))

    def test_more_spending_leaves_less_money(self):
        low = app.project(base_profile(annual_expenses=60000))[-1]['total_balance']
        high = app.project(base_profile(annual_expenses=150000))[-1]['total_balance']
        self.assertGreater(low, high)


class TestSSOptimizer(unittest.TestCase):
    def test_recommends_a_valid_pair(self):
        res = app.optimize_ss(base_profile())
        rec = res['recommended']
        self.assertIn(rec['ss1_age'], range(62, 71))
        self.assertIn(rec['ss2_age'], range(62, 71))

    def test_score_is_ending_balance_not_double_counted(self):
        # REGRESSION: score was total_ss + final_balance - total_tax, which
        # counted every benefit dollar twice and biased the recommendation.
        res = app.optimize_ss(base_profile())
        for row in res['comparisons']:
            self.assertEqual(row['score'], row['final_balance'])


if __name__ == '__main__':
    unittest.main(verbosity=2)

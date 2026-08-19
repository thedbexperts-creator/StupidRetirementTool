# Assumptions and Limitations

**Read this before trusting a number.** The tool is reasonably careful about the
things it models, which makes it important to be clear about the things it does
not. Everything below is a deliberate simplification, not a bug.

---

## What the numbers are

- All figures are **nominal dollars** (actual future dollars, not today's
  purchasing power) unless a screen explicitly says otherwise.
- The projection runs to the **later of the two life expectancies**. It is a
  single deterministic path; the Monte Carlo tab is where uncertainty lives.
- Everything is a **household-level annual model**. There is no monthly cash
  flow, no mid-year timing, and no modelling of *when* in the year money moves.

---

## Taxes

**Federal.** 2026 brackets, standard deduction, and long-term capital gains
brackets (IRS Rev. Proc. 2025-32). Brackets are inflated forward at a fixed
2.5%/yr from 2026 — a simplification, since real adjustments use chained CPI.

**What is modelled:** ordinary income, long-term capital gains stacked on top of
ordinary income, the 3.8% Net Investment Income Tax, Social Security
provisional-income taxation (with correct single vs. married thresholds), FICA
on earned income, IRMAA surcharges, and the ACA premium tax credit.

**What is NOT modelled:**

- Alternative Minimum Tax
- The extra standard deduction for age 65+, and the OBBBA senior deduction
- Itemised deductions of any kind (charitable, medical, SALT, mortgage interest)
- Qualified Business Income (§199A), self-employment tax on part-time income
  (part-time work is taxed as W-2 wages)
- Qualified Charitable Distributions — a significant omission for charitably
  inclined retirees with large IRAs
- Tax-loss or tax-gain harvesting
- State estate or inheritance taxes; federal estate tax
- City or local income taxes (NYC, Yonkers, Ohio municipalities, etc.)

**State income tax.** All 50 states have 2026 rates, brackets and standard
deductions (source: Tax Foundation, *State Individual Income Tax Rates and
Brackets, 2026*). Important caveats:

- **Your state is fixed for the whole projection.** Retiring in one state and
  moving to another is not supported — a common plan the tool cannot express.
- **Pension and retirement-income exclusions are simplified.** Many states have
  income-tested exclusions, or rules that apply only to specific pension types
  (government vs. private, defined benefit vs. IRA). Where a state's rule is
  complicated, the exclusion is set conservatively or to zero. **Use the
  per-pension "state tax exempt" checkbox** on the Profile tab to model your
  actual situation.
- Social Security is treated as untaxed by the state except where a state
  clearly taxes it; partial and income-tested state SS rules are approximated.
- Personal exemptions granted as a *credit* rather than a deduction are ignored.

---

## Social Security

- Claiming adjustments follow SSA rules exactly: reductions before FRA
  (30% at 62 with FRA 67), 8%/yr delayed credits capped at 70, and spousal
  benefits at 50% of the partner's PIA reduced 25/36 of 1% per month.
- **COLA is a fixed 2.4%/yr** and is not linked to your inflation input.
- Benefits are entered in today's dollars at FRA and indexed forward from the
  current year.
- **Not modelled:** the earnings test (benefits withheld if you claim early
  while still working), child or disability benefits, divorced-spouse benefits,
  or Social Security trust-fund shortfall scenarios.
- WEP and GPO are not modelled — they were repealed in January 2025.

---

## Healthcare

- **ACA:** post-2025 rules with the 400% FPL subsidy cliff restored. The 2026
  applicable percentage table (Rev. Proc. 2025-25) is applied against 2025 HHS
  poverty guidelines for the **48 contiguous states** — Alaska and Hawaii have
  higher guidelines and are not handled separately.
- You supply the **benchmark (second-lowest silver) premium**. The tool does not
  know plan prices in your area; get the number from healthcare.gov.
- Cost-sharing reductions (lower deductibles below 250% FPL) are not modelled.
- **IRMAA:** surcharges are applied on the *current* year's income. In reality
  IRMAA uses MAGI from **two years prior**, so a one-off income spike shows up
  in this tool a year or two earlier than it would in life.
- Medical costs are entered per couple and split evenly per person.
- Long-term care is a simple monthly cost over a fixed duration, net of any
  insurance benefit you enter.

---

## Accounts and withdrawals

- Withdrawal order is fixed: **RMDs → HSA (against medical) → taxable/savings →
  traditional → Roth → leftover HSA.** It is not optimised per year.
- **Cost basis** for taxable accounts defaults to **80% of the balance** if you
  do not set it. This directly drives capital gains tax — set it if you can.
- RMDs use the IRS Uniform Lifetime Table and the SECURE 2.0 start age (73, or
  75 if born 1960 or later). The **Joint Life table for a much-younger spouse is
  not used**, so RMDs may be overstated in that case.
- Inherited IRAs and the SECURE Act 10-year rule are not modelled.
- Contribution limits are **not enforced** — the tool will let you contribute
  more than the IRS allows.
- HSA funds are spent automatically against each year's medical costs, which is
  optimal but is not what everyone does; there is no "preserve the HSA" option.

---

## Investment returns

- Each account has a flat growth rate, with an optional glide path that blends
  stock and bond returns by age.
- **Monte Carlo** draws lognormal annual returns around your growth rate, so the
  variance drag is applied exactly once and returns can never fall below -100%.
  It uses a **single blended portfolio**, not per-account returns, and assumes
  returns are independent year to year — there is no mean reversion, no
  correlation between asset classes, and no fat tails. Real market crashes are
  more extreme and more clustered than a normal distribution implies.
- Historical sequence backtesting (e.g. "what if I retired in 1966?") is not
  available; all randomness is parametric.
- Inflation can optionally be randomised (`inflation_vol`), but it is
  uncorrelated with investment returns, which is unrealistic.

---

## After-tax value

The "after-tax value" figure discounts pre-tax balances by an assumed heir
income-tax rate (default 24%) and assumes heirs receive a **stepped-up basis**
on taxable accounts, which is current law. It is a planning approximation, not
an estate calculation: it ignores the actual bracket your heirs will be in, the
timing of distributions under the 10-year rule, and estate taxes entirely.

---

## The NYS tools

- The pension calculator implements **ERS Tiers 3/4, 5 and 6** with the official
  NYSLRS benefit formulas and early-retirement reduction tables.
- **PFRS is simplified** to 2%/yr capped at 60% and does **not** implement the
  special 20- and 25-year plans that most police and fire members are actually
  in. Do not rely on the PFRS numbers.
- Tier 1 and 2, disability retirement, and Correction Officer/SHTA titles are
  not modelled.
- Final Average Salary is projected from your current salary and a flat raise
  assumption, and does not apply the Tier 6 overtime cap or the Tier 3/4
  10%-per-year FAS limitation.

---

## Bottom line

This is a **planning model**. It is good for comparing strategies against each
other — claim early vs. late, convert vs. don't, spend more vs. leave a legacy.
It is not a substitute for a CPA or a fee-only fiduciary planner, and it should
not be the only input to an irreversible decision.

**This is not financial advice.**

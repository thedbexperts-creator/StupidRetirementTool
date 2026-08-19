#!/usr/bin/env python3
"""
Retirement Planner - Local Web Application
Run: python3 app.py  (or double-click the .exe)
Open: http://localhost:5000
"""

from http.server import HTTPServer, ThreadingHTTPServer, BaseHTTPRequestHandler
import json, math, os, copy, random, sys, threading, traceback, webbrowser

APP_VERSION = '1.0.5'
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
DATA_LOCK   = threading.Lock()   # serialize profile.json reads/writes

# ─── TAX TABLES 2026 (MFJ) — IRS Rev. Proc. 2025-32 ────────────────────────────────────────────────────

FED_BRACKETS_MFJ = [
    (24800, 0.10), (100800, 0.12), (211400, 0.22),
    (403550, 0.24), (512450, 0.32), (768700, 0.35), (float('inf'), 0.37)
]
FED_STD_DED = 32200

# ─── STATE INCOME TAX DATA 2024 ───────────────────────────────────────────────
# brackets: list of (upper_limit, marginal_rate) tuples, same format as federal.
# pension_excl_per_person: annual exclusion per qualifying person (age >= pension_excl_age).
# ss_taxable_pct: fraction of SS subject to state tax (0 = state doesn't tax SS).
# pension_exempt_flag_honored: if True, pensions marked state_exempt in profile are 100% excluded.

_INF = float('inf')

STATE_TAX_DATA = {
    # ── No income tax ──────────────────────────────────────────────────────
    'AK': {'name':'Alaska',        'type':'none'},
    'FL': {'name':'Florida',       'type':'none'},
    'NV': {'name':'Nevada',        'type':'none'},
    'NH': {'name':'New Hampshire', 'type':'none'},
    'SD': {'name':'South Dakota',  'type':'none'},
    'TN': {'name':'Tennessee',     'type':'none'},
    'TX': {'name':'Texas',         'type':'none'},
    'WA': {'name':'Washington',    'type':'none'},
    'WY': {'name':'Wyoming',       'type':'none'},

    # ── Flat rate ──────────────────────────────────────────────────────────
    'AZ': {'name':'Arizona',       'type':'flat','rate':0.025,
           'std_ded_mfj':29200,'std_ded_single':14600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'CO': {'name':'Colorado',      'type':'flat','rate':0.044,
           'std_ded_mfj':29200,'std_ded_single':14600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':24000,'pension_excl_age':65},
    'GA': {'name':'Georgia',       'type':'flat','rate':0.0549,
           'std_ded_mfj':18500,'std_ded_single':12000,
           'ss_taxable_pct':0.0,'pension_excl_per_person':35000,'pension_excl_age':62},
    'IA': {'name':'Iowa',          'type':'flat','rate':0.038,
           'std_ded_mfj':29200,'std_ded_single':14600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'IL': {'name':'Illinois',      'type':'flat','rate':0.0495,
           'std_ded_mfj':0,'std_ded_single':0,
           'ss_taxable_pct':0.0,'pension_excl_per_person':999999,'pension_excl_age':0},
    'IN': {'name':'Indiana',       'type':'flat','rate':0.0305,
           'std_ded_mfj':0,'std_ded_single':0,
           'ss_taxable_pct':0.0,'pension_excl_per_person':16000,'pension_excl_age':60},
    'KY': {'name':'Kentucky',      'type':'flat','rate':0.040,
           'std_ded_mfj':5980,'std_ded_single':2980,
           'ss_taxable_pct':0.0,'pension_excl_per_person':31110,'pension_excl_age':0},
    'MA': {'name':'Massachusetts', 'type':'flat','rate':0.050,
           'std_ded_mfj':8800,'std_ded_single':4400,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'MI': {'name':'Michigan',      'type':'flat','rate':0.0425,
           'std_ded_mfj':0,'std_ded_single':0,
           'ss_taxable_pct':0.0,'pension_excl_per_person':54404,'pension_excl_age':67},
    'NC': {'name':'North Carolina','type':'flat','rate':0.045,
           'std_ded_mfj':21500,'std_ded_single':10750,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'PA': {'name':'Pennsylvania',  'type':'flat','rate':0.0307,
           'std_ded_mfj':0,'std_ded_single':0,
           'ss_taxable_pct':0.0,'pension_excl_per_person':999999,'pension_excl_age':0},
    'UT': {'name':'Utah',          'type':'flat','rate':0.0465,
           'std_ded_mfj':29200,'std_ded_single':14600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},

    # ── Progressive ────────────────────────────────────────────────────────
    'NY': {'name':'New York', 'type':'progressive',
           'brackets_mfj':   [(17150,0.040),(23600,0.045),(27900,0.0525),
                               (161550,0.0585),(323200,0.0625),(2155350,0.0685),(_INF,0.0965)],
           'brackets_single':[(8500,0.040),(11700,0.045),(13900,0.0525),
                               (80650,0.0585),(215400,0.0625),(1077550,0.0685),(_INF,0.0965)],
           'std_ded_mfj':16050,'std_ded_single':8000,
           # NY's $20k pension/annuity exclusion starts at age 59½.
           'ss_taxable_pct':0.0,'pension_excl_per_person':20000,'pension_excl_age':59.5},
    'CA': {'name':'California','type':'progressive',
           'brackets_mfj':   [(20824,0.01),(49368,0.02),(77918,0.04),(108162,0.06),
                               (136700,0.08),(698274,0.093),(837922,0.103),(1000000,0.113),(_INF,0.133)],
           'brackets_single':[(10412,0.01),(24684,0.02),(38959,0.04),(54081,0.06),
                               (68350,0.08),(349137,0.093),(418961,0.103),(698274,0.113),(_INF,0.133)],
           'std_ded_mfj':10726,'std_ded_single':5202,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'NJ': {'name':'New Jersey','type':'progressive',
           'brackets_mfj':   [(20000,0.014),(50000,0.0175),(70000,0.0245),(80000,0.035),
                               (150000,0.05525),(500000,0.0637),(_INF,0.1075)],
           'brackets_single':[(20000,0.014),(50000,0.0175),(70000,0.0245),(80000,0.035),
                               (150000,0.05525),(500000,0.0637),(_INF,0.1075)],
           'std_ded_mfj':2000,'std_ded_single':1000,
           'ss_taxable_pct':0.0,'pension_excl_per_person':100000,'pension_excl_age':62},
    'MN': {'name':'Minnesota','type':'progressive',
           'brackets_mfj':   [(43950,0.0535),(174400,0.068),(304970,0.0785),(_INF,0.0985)],
           'brackets_single':[(30070,0.0535),(98760,0.068),(183340,0.0785),(_INF,0.0985)],
           'std_ded_mfj':27650,'std_ded_single':13825,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'OR': {'name':'Oregon',   'type':'progressive',
           'brackets_mfj':   [(18400,0.0475),(46200,0.0675),(250000,0.0875),(_INF,0.099)],
           'brackets_single':[(4050,0.0475),(10200,0.0675),(125000,0.0875),(_INF,0.099)],
           'std_ded_mfj':4960,'std_ded_single':2420,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'WI': {'name':'Wisconsin','type':'progressive',
           'brackets_mfj':   [(13810,0.035),(27630,0.044),(304600,0.053),(_INF,0.0765)],
           'brackets_single':[(13810,0.035),(27630,0.044),(304600,0.053),(_INF,0.0765)],
           'std_ded_mfj':23620,'std_ded_single':11790,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'MD': {'name':'Maryland', 'type':'progressive',
           'brackets_mfj':   [(1000,0.02),(2000,0.03),(3000,0.04),(150000,0.0475),
                               (175000,0.05),(225000,0.0525),(300000,0.055),(_INF,0.0575)],
           'brackets_single':[(1000,0.02),(2000,0.03),(3000,0.04),(150000,0.0475),
                               (175000,0.05),(225000,0.0525),(300000,0.055),(_INF,0.0575)],
           'std_ded_mfj':4700,'std_ded_single':2350,
           'ss_taxable_pct':0.0,'pension_excl_per_person':36200,'pension_excl_age':65},
    'CT': {'name':'Connecticut','type':'progressive',
           'brackets_mfj':   [(20000,0.02),(100000,0.045),(200000,0.055),(400000,0.06),
                               (500000,0.065),(1000000,0.069),(_INF,0.0699)],
           'brackets_single':[(10000,0.02),(50000,0.045),(100000,0.055),(200000,0.06),
                               (250000,0.065),(500000,0.069),(_INF,0.0699)],
           'std_ded_mfj':24000,'std_ded_single':15000,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'VT': {'name':'Vermont',  'type':'progressive',
           'brackets_mfj':   [(75900,0.0335),(183400,0.066),(311400,0.076),(_INF,0.0875)],
           'brackets_single':[(47150,0.0335),(113450,0.066),(193500,0.076),(_INF,0.0875)],
           'std_ded_mfj':27700,'std_ded_single':14600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'MO': {'name':'Missouri', 'type':'progressive',
           'brackets_mfj':   [(1207,0.005),(2414,0.015),(3621,0.02),(4828,0.025),
                               (6035,0.03),(7242,0.035),(8449,0.04),(9656,0.045),(_INF,0.048)],
           'brackets_single':[(1207,0.005),(2414,0.015),(3621,0.02),(4828,0.025),
                               (6035,0.03),(7242,0.035),(8449,0.04),(9656,0.045),(_INF,0.048)],
           'std_ded_mfj':27700,'std_ded_single':14600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':6000,'pension_excl_age':0},
    'ME': {'name':'Maine',    'type':'progressive',
           'brackets_mfj':   [(47950,0.058),(113250,0.0675),(_INF,0.0715)],
           'brackets_single':[(23000,0.058),(54450,0.0675),(_INF,0.0715)],
           'std_ded_mfj':27700,'std_ded_single':14600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':10000,'pension_excl_age':65},

    # ── Added 2026: states previously missing (they silently fell back to NY) ──
    # Rates/brackets/standard deductions: Tax Foundation "State Individual Income
    # Tax Rates and Brackets, 2026" (IRS-conforming deductions noted where used).
    # Where a state grants a personal *exemption* as a deduction it is folded
    # into std_ded; credit-style exemptions are ignored.
    # SS: ss_taxable_pct 0 means the state does not tax Social Security.
    # Pension exclusions vary a lot by income and pension type; where a state's
    # rule is income-tested or applies only to specific pension types, use the
    # per-pension "state tax exempt" checkbox on the Profile tab instead.
    'AL': {'name':'Alabama', 'type':'progressive',
           'brackets_single':[(500,0.02),(3000,0.04),(_INF,0.05)],
           'brackets_mfj':   [(1000,0.02),(6000,0.04),(_INF,0.05)],
           'std_ded_single':4500,'std_ded_mfj':11500,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'AR': {'name':'Arkansas', 'type':'progressive',
           'brackets_single':[(4600,0.02),(_INF,0.039)],
           'brackets_mfj':   [(4600,0.02),(_INF,0.039)],
           'std_ded_single':2470,'std_ded_mfj':4940,
           'ss_taxable_pct':0.0,'pension_excl_per_person':6000,'pension_excl_age':0},
    'DE': {'name':'Delaware', 'type':'progressive',
           'brackets_single':[(2000,0.0),(5000,0.022),(10000,0.039),(20000,0.048),
                              (25000,0.052),(60000,0.0555),(_INF,0.066)],
           'brackets_mfj':   [(2000,0.0),(5000,0.022),(10000,0.039),(20000,0.048),
                              (25000,0.052),(60000,0.0555),(_INF,0.066)],
           'std_ded_single':3250,'std_ded_mfj':6500,
           'ss_taxable_pct':0.0,'pension_excl_per_person':12500,'pension_excl_age':60},
    'HI': {'name':'Hawaii', 'type':'progressive',
           'brackets_single':[(9600,0.014),(14400,0.032),(19200,0.055),(24000,0.064),
                              (36000,0.068),(48000,0.072),(125000,0.076),(175000,0.079),
                              (225000,0.0825),(275000,0.09),(325000,0.10),(_INF,0.11)],
           'brackets_mfj':   [(19200,0.014),(28800,0.032),(38400,0.055),(48000,0.064),
                              (72000,0.068),(96000,0.072),(250000,0.076),(350000,0.079),
                              (450000,0.0825),(550000,0.09),(650000,0.10),(_INF,0.11)],
           'std_ded_single':4400,'std_ded_mfj':8800,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'ID': {'name':'Idaho', 'type':'progressive',
           'brackets_single':[(4811,0.0),(_INF,0.053)],
           'brackets_mfj':   [(9622,0.0),(_INF,0.053)],
           'std_ded_single':16100,'std_ded_mfj':32200,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'KS': {'name':'Kansas', 'type':'progressive',
           'brackets_single':[(23000,0.052),(_INF,0.0558)],
           'brackets_mfj':   [(46000,0.052),(_INF,0.0558)],
           'std_ded_single':12765,'std_ded_mfj':26560,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'LA': {'name':'Louisiana', 'type':'flat','rate':0.03,
           'std_ded_single':12875,'std_ded_mfj':25750,
           'ss_taxable_pct':0.0,'pension_excl_per_person':6000,'pension_excl_age':65},
    'MS': {'name':'Mississippi', 'type':'progressive',
           'brackets_single':[(10000,0.0),(_INF,0.04)],
           'brackets_mfj':   [(10000,0.0),(_INF,0.04)],
           'std_ded_single':8300,'std_ded_mfj':16600,
           'ss_taxable_pct':0.0,'pension_excl_per_person':999999,'pension_excl_age':0},
    'MT': {'name':'Montana', 'type':'progressive',
           'brackets_single':[(47500,0.047),(_INF,0.0565)],
           'brackets_mfj':   [(95000,0.047),(_INF,0.0565)],
           'std_ded_single':16100,'std_ded_mfj':32200,
           'ss_taxable_pct':0.85,'pension_excl_per_person':4640,'pension_excl_age':0},
    'ND': {'name':'North Dakota', 'type':'progressive',
           'brackets_single':[(48475,0.0),(244825,0.0195),(_INF,0.025)],
           'brackets_mfj':   [(80975,0.0),(298075,0.0195),(_INF,0.025)],
           'std_ded_single':16100,'std_ded_mfj':32200,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'NE': {'name':'Nebraska', 'type':'progressive',
           'brackets_single':[(4130,0.0246),(24760,0.0351),(_INF,0.0455)],
           'brackets_mfj':   [(8250,0.0246),(49530,0.0351),(_INF,0.0455)],
           'std_ded_single':8850,'std_ded_mfj':17700,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'NM': {'name':'New Mexico', 'type':'progressive',
           'brackets_single':[(5500,0.015),(16500,0.032),(33500,0.043),
                              (66500,0.047),(210000,0.049),(_INF,0.059)],
           'brackets_mfj':   [(8000,0.015),(25000,0.032),(50000,0.043),
                              (100000,0.047),(315000,0.049),(_INF,0.059)],
           'std_ded_single':16100,'std_ded_mfj':32200,
           'ss_taxable_pct':0.0,'pension_excl_per_person':8000,'pension_excl_age':65},
    'OH': {'name':'Ohio', 'type':'progressive',
           'brackets_single':[(26050,0.0),(_INF,0.0275)],
           'brackets_mfj':   [(26050,0.0),(_INF,0.0275)],
           'std_ded_single':2400,'std_ded_mfj':4800,
           'ss_taxable_pct':0.0,'pension_excl_per_person':0,'pension_excl_age':0},
    'OK': {'name':'Oklahoma', 'type':'progressive',
           'brackets_single':[(3750,0.0),(4900,0.025),(7200,0.035),(_INF,0.045)],
           'brackets_mfj':   [(7500,0.0),(9800,0.025),(14400,0.035),(_INF,0.045)],
           'std_ded_single':7350,'std_ded_mfj':14700,
           'ss_taxable_pct':0.0,'pension_excl_per_person':10000,'pension_excl_age':0},
    'RI': {'name':'Rhode Island', 'type':'progressive',
           'brackets_single':[(82050,0.0375),(186450,0.0475),(_INF,0.0599)],
           'brackets_mfj':   [(82050,0.0375),(186450,0.0475),(_INF,0.0599)],
           'std_ded_single':11200,'std_ded_mfj':22400,
           'ss_taxable_pct':0.0,'pension_excl_per_person':20000,'pension_excl_age':67},
    'SC': {'name':'South Carolina', 'type':'progressive',
           'brackets_single':[(3640,0.0),(18230,0.03),(_INF,0.06)],
           'brackets_mfj':   [(3640,0.0),(18230,0.03),(_INF,0.06)],
           'std_ded_single':8350,'std_ded_mfj':16700,
           'ss_taxable_pct':0.0,'pension_excl_per_person':10000,'pension_excl_age':65},
    'VA': {'name':'Virginia', 'type':'progressive',
           'brackets_single':[(3000,0.02),(5000,0.03),(17000,0.05),(_INF,0.0575)],
           'brackets_mfj':   [(3000,0.02),(5000,0.03),(17000,0.05),(_INF,0.0575)],
           'std_ded_single':8750,'std_ded_mfj':17500,
           'ss_taxable_pct':0.0,'pension_excl_per_person':12000,'pension_excl_age':65},
    'WV': {'name':'West Virginia', 'type':'progressive',
           'brackets_single':[(10000,0.0222),(25000,0.0296),(40000,0.0333),
                              (60000,0.0444),(_INF,0.0482)],
           'brackets_mfj':   [(10000,0.0222),(25000,0.0296),(40000,0.0333),
                              (60000,0.0444),(_INF,0.0482)],
           'std_ded_single':2000,'std_ded_mfj':4000,
           'ss_taxable_pct':0.0,'pension_excl_per_person':8000,'pension_excl_age':0},

    # ── Custom / Other ─────────────────────────────────────────────────────
    'CUSTOM': {'name':'Custom / Other', 'type':'custom'},
}

def get_state_tax_config(profile):
    """Return (brackets_mfj, std_ded_mfj, brackets_single, std_ded_single,
               ss_taxable_pct, pension_excl_per_person, pension_excl_age)
    for the state in the profile."""
    state  = profile.get('state', 'NY')
    s      = STATE_TAX_DATA.get(state)
    if s is None:
        # An unrecognised state code used to fall through to New York — one of
        # the highest-tax states, complete with NY's pension exclusion. That
        # silently produced a wrong (and wrongly-shaped) tax bill with no
        # warning. Fail to a neutral no-tax config instead; the UI restricts the
        # dropdown to modelled states plus "Custom".
        zero = [(float('inf'), 0.0)]
        return zero, 0, zero, 0, 0.0, 0, 0
    stype  = s['type']

    if stype == 'none':
        zero = [(float('inf'), 0.0)]
        return zero, 0, zero, 0, 0.0, 0, 0

    if stype == 'custom':
        rate = _num(profile.get('custom_state_rate'), 0.0) / 100.0
        b = [(float('inf'), rate)]
        return b, 0, b, 0, 0.0, 0, 0

    if stype == 'flat':
        rate = s['rate']
        b_mfj = [(float('inf'), rate)]
        b_sng = [(float('inf'), rate)]
        return (b_mfj, s.get('std_ded_mfj', 0),
                b_sng, s.get('std_ded_single', 0),
                s.get('ss_taxable_pct', 0.0),
                s.get('pension_excl_per_person', 0),
                s.get('pension_excl_age', 0))

    # progressive
    return (s['brackets_mfj'], s.get('std_ded_mfj', 0),
            s['brackets_single'], s.get('std_ded_single', 0),
            s.get('ss_taxable_pct', 0.0),
            s.get('pension_excl_per_person', 0),
            s.get('pension_excl_age', 0))

# ─── TAX TABLES 2026 (Single filer — used after one spouse dies) ──────────────

FED_BRACKETS_SINGLE = [
    (12400, 0.10), (50400, 0.12), (105700, 0.22),
    (201775, 0.24), (256225, 0.32), (640600, 0.35), (float('inf'), 0.37)
]
FED_STD_DED_SINGLE = 16100

# Federal Long-Term Capital Gains brackets 2024 (MFJ)
LTCG_BRACKETS_MFJ = [
    (98900,  0.00),
    (613700, 0.15),
    (float('inf'), 0.20),
]
# Federal Long-Term Capital Gains brackets 2024 (Single)
LTCG_BRACKETS_SINGLE = [
    (49450,  0.00),
    (545500, 0.15),
    (float('inf'), 0.20),
]
# NYS taxes capital gains as ordinary income (no special rate)

# IRS Uniform Lifetime Table (RMDs, SECURE 2.0: start age 73 or 75).
# Runs to 120+ so long life expectancies keep getting the correct divisor
# (a truncated table understates forced distributions and their tax).
RMD_TABLE = {
    72:27.4, 73:26.5, 74:25.5, 75:24.6, 76:23.7, 77:22.9,
    78:22.0, 79:21.1, 80:20.2, 81:19.4, 82:18.5, 83:17.7,
    84:16.8, 85:16.0, 86:15.2, 87:14.4, 88:13.7, 89:12.9,
    90:12.2, 91:11.5, 92:10.8, 93:10.1, 94:9.5,  95:8.9,
    96:8.4,  97:7.8,  98:7.3,  99:6.8,  100:6.4, 101:6.0,
    102:5.6, 103:5.2, 104:4.9, 105:4.6, 106:4.3, 107:4.1,
    108:3.9, 109:3.7, 110:3.5, 111:3.4, 112:3.3, 113:3.1,
    114:3.0, 115:2.9, 116:2.8, 117:2.7, 118:2.5, 119:2.3,
    120:2.0
}

# ─── FINANCIAL HELPERS ────────────────────────────────────────────────────────

def _num(value, default=0.0):
    """Coerce a profile field to float. Tolerates None, '', and '1,234.56'.

    Profiles are hand-editable JSON and the UI sends some fields as strings,
    so a missing or malformed number must not take down a whole projection.
    """
    if value is None:
        return float(default)
    if isinstance(value, bool):
        return float(default)
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).replace(',', '').replace('$', '').strip() or default)
    except (TypeError, ValueError):
        return float(default)


def _dict_list(value):
    """Coerce a profile field to a list of dicts, dropping anything else."""
    if not isinstance(value, list):
        return []
    return [v for v in value if isinstance(v, dict)]


ACCOUNT_TYPES = ('traditional', 'roth', 'taxable', 'savings')


def normalize_accounts(raw_accounts):
    """Return a sanitized copy of the accounts dict.

    Guarantees every account has a valid 'type', a numeric 'balance', and
    numeric growth rates, so the engine can index them directly without a
    KeyError taking out the request.
    """
    out = {}
    for k, v in (raw_accounts or {}).items():
        if not isinstance(v, dict):
            continue
        a = dict(v)
        t = str(a.get('type', 'taxable')).strip().lower()
        a['type'] = t if t in ACCOUNT_TYPES else 'taxable'
        a['balance'] = max(0.0, _num(a.get('balance', 0)))
        a['owner'] = 'p2' if str(a.get('owner', 'p1')).lower() == 'p2' else 'p1'
        a['growth_rate'] = _num(a.get('growth_rate', 0.07), 0.07)
        if a.get('ret_growth') is None:
            a['ret_growth'] = a['growth_rate'] * 0.85
        else:
            a['ret_growth'] = _num(a.get('ret_growth'), a['growth_rate'] * 0.85)
        out[k] = a
    return out


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

def irmaa_annual_per_person(magi, use_single=False, threshold_factor=1.0, premium_factor=1.0):
    """Annual Medicare Part B+D premium (standard + IRMAA surcharge) per person.

    IRMAA thresholds are CPI-indexed each year and premiums rise with medical
    costs, so both are scaled forward rather than held at their 2024 nominal
    values — otherwise inflated income drifts into the top tier over a 30-year
    projection and everyone looks like a high earner.
    """
    table = IRMAA_SINGLE if use_single else IRMAA_MFJ
    for threshold, annual in table:
        if magi <= threshold * threshold_factor:
            return annual * premium_factor
    return table[-1][1] * premium_factor

# ─── ACA PREMIUM TAX CREDIT ──────────────────────────────────────────────────
# The enhanced (ARPA/IRA) subsidies expired 1 Jan 2026, so the pre-2021 rules
# are back: a sliding scale from 100%–400% FPL and a HARD CLIFF above 400% —
# one dollar over and the entire credit disappears.
#
# This matters enormously for Roth conversions before Medicare age: a conversion
# raises MAGI, which raises the required contribution and can push a household
# over the cliff. Without this, the Roth optimiser recommends conversions whose
# true cost it cannot see.
#
# 2025 HHS poverty guidelines (used for 2026 coverage), 48 contiguous states.
FPL_BASE_2025 = 15650.0
FPL_ADD_2025  = 5500.0     # per additional household member

# IRS Rev. Proc. 2025-25 applicable percentage table for 2026.
# (fpl_ratio_upper, pct_at_lower_bound, pct_at_upper_bound) — linear in between.
ACA_APPLICABLE_PCT_2026 = [
    (1.33, 0.0210, 0.0210),
    (1.50, 0.0314, 0.0419),
    (2.00, 0.0419, 0.0660),
    (2.50, 0.0660, 0.0844),
    (3.00, 0.0844, 0.0996),
    (4.00, 0.0996, 0.0996),
]
ACA_CLIFF_FPL = 4.00

def federal_poverty_level(household_size, inflation=0.0, years=0):
    """FPL for a household, optionally indexed forward."""
    n = max(1, int(household_size))
    base = FPL_BASE_2025 + FPL_ADD_2025 * (n - 1)
    return base * ((1 + inflation) ** years)

def aca_applicable_pct(fpl_ratio):
    """Share of MAGI the household is expected to contribute toward the
    benchmark plan. Returns None above the 400% FPL cliff (no credit)."""
    if fpl_ratio > ACA_CLIFF_FPL:
        return None
    prev_upper = 1.0
    for upper, pct_lo, pct_hi in ACA_APPLICABLE_PCT_2026:
        if fpl_ratio <= upper:
            if upper == prev_upper or pct_hi == pct_lo:
                return pct_lo
            frac = (fpl_ratio - prev_upper) / (upper - prev_upper)
            return pct_lo + frac * (pct_hi - pct_lo)
        prev_upper = upper
    return ACA_APPLICABLE_PCT_2026[-1][2]

def aca_subsidy(magi, benchmark_premium, household_size,
                inflation=0.0, years=0):
    """Annual premium tax credit.

    Returns (credit, fpl_ratio, over_cliff). The credit is the benchmark
    premium less the household's required contribution, floored at zero.
    """
    if benchmark_premium <= 0:
        return 0.0, 0.0, False
    fpl = federal_poverty_level(household_size, inflation, years)
    if fpl <= 0:
        return 0.0, 0.0, False
    ratio = max(0.0, magi) / fpl
    pct = aca_applicable_pct(ratio)
    if pct is None:
        return 0.0, ratio, True          # over the cliff — no credit at all
    required = max(0.0, magi) * pct
    return max(0.0, benchmark_premium - required), ratio, False

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
    base_spousal = 0.5 * partner_fra_monthly
    if months_early == 0:
        spousal = base_spousal
    elif months_early <= 36:
        # SSA: spousal benefit reduced 25/36 of 1% per month, first 36 months
        reduction = months_early * (25.0 / 36.0) / 100.0
        spousal = base_spousal * (1 - reduction)
    else:
        # ...then 5/12 of 1% per month beyond 36 (25% reduction at 36 months)
        reduction = 0.25 + (months_early - 36) * (5.0 / 12.0) / 100.0
        spousal = base_spousal * (1 - reduction)
    return max(own, spousal)

def taxable_ss_portion(ss_annual, other_income, use_single=False):
    """Federal taxable portion of SS benefits.

    IRS base amounts depend on filing status and are NOT inflation-indexed
    (by design). MFJ: 32k/44k; Single: 25k/34k. Second-tier add-on is the
    smaller of 50% of benefits or 6,000 (MFJ) / 4,500 (Single)."""
    combined = other_income + 0.5 * ss_annual
    if use_single:
        t1, t2, addon_cap = 25000.0, 34000.0, 4500.0
    else:
        t1, t2, addon_cap = 32000.0, 44000.0, 6000.0
    if combined < t1:
        return 0.0
    elif combined < t2:
        return min(0.5 * ss_annual, 0.5 * (combined - t1))
    else:
        return min(0.85 * ss_annual,
                   0.85 * (combined - t2) + min(0.5 * ss_annual, addon_cap))

# ─── NET INVESTMENT INCOME TAX (NIIT) ────────────────────────────────────────
# 3.8% on the LESSER of net investment income or MAGI above the threshold.
# These thresholds are set in statute and are NOT inflation-indexed.
NIIT_RATE = 0.038
NIIT_THRESHOLD_MFJ = 250000.0
NIIT_THRESHOLD_SINGLE = 200000.0

def niit_tax(net_investment_income, magi, use_single=False):
    """Additional 3.8% Medicare surtax on investment income."""
    if net_investment_income <= 0:
        return 0.0
    threshold = NIIT_THRESHOLD_SINGLE if use_single else NIIT_THRESHOLD_MFJ
    excess = max(0.0, magi - threshold)
    return NIIT_RATE * min(net_investment_income, excess)


def rmd_start_age(birth_year):
    """SECURE 2.0 required-beginning age: 73 for those born 1951-1959,
    75 for those born 1960 or later."""
    return 75 if int(birth_year) >= 1960 else 73

def rmd_required(balance, age, start_age=73):
    """RMD amount for a traditional account. SECURE 2.0 start age varies."""
    if age < start_age or balance <= 0:
        return 0.0
    return balance / RMD_TABLE.get(min(int(age), 120), 2.0)

def pension_income_for_year(pension_def, person_age):
    """Annual pension income for a given age."""
    if not pension_def:
        return 0.0
    start_age = _num(pension_def.get('start_age'), 65)
    if person_age < start_age:
        return 0.0
    active_yrs = person_age - start_age
    monthly = _num(pension_def.get('monthly_benefit'), 0)
    cola    = _num(pension_def.get('cola'), 0.0)
    return monthly * 12 * (1 + cola) ** active_yrs

# ─── PROJECTION ENGINE ────────────────────────────────────────────────────────

def project(profile, ss1_age_override=None, ss2_age_override=None, do_roth=True):
    """
    Year-by-year retirement projection.

    Returns a list of annual snapshots from `current_year` until the last
    person alive reaches their life expectancy.
    """
    p1 = profile.get('person1') or {}
    p2 = profile.get('person2') or {}
    p2_enabled = bool(p2.get('enabled', True))   # False → single-person / single-filer mode
    p1b = int(_num(p1.get('birth_year'), 1970))
    p2b = int(_num(p2.get('birth_year'), 1970))
    curr_yr = int(_num(profile.get('current_year'), 2026))
    inflation = _num(profile.get('inflation'), 0.03)
    tax_inf = 0.025   # tax brackets inflate slightly slower
    acct_defs = normalize_accounts(profile.get('accounts'))
    contribs   = profile.get('contributions', {}) or {}
    catch_ups  = profile.get('catch_up_contributions', {}) or {}   # age 50+
    super_cups = profile.get('super_catch_up_contributions', {}) or {}  # ages 60-63 (SECURE 2.0)
    # Pensions — dynamic array; backward compat with old pension1/pension2 keys
    pensions_list = profile.get('pensions', None)
    if pensions_list is None:
        pen1_old = profile.get('pension1') or profile.get('nys_pension', {})
        pen2_old = profile.get('pension2') or {}
        pensions_list = [p for p in [pen1_old, pen2_old] if p]
    pensions_list = _dict_list(pensions_list)
    annual_exp = _num(profile.get('annual_expenses'), 0)

    # State tax configuration
    (st_brackets_mfj, st_std_ded_mfj,
     st_brackets_single, st_std_ded_single,
     st_ss_taxable_pct,
     st_pension_excl_pp, st_pension_excl_age) = get_state_tax_config(profile)

    # One-time expense shocks: [{label, p1_age, amount}]
    shocks = _dict_list(profile.get('shocks'))
    # Build lookup: p1_age -> total shock amount that year
    shock_by_age = {}
    for sh in shocks:
        age = int(_num(sh.get('p1_age'), 0))
        amt = _num(sh.get('amount'), 0)
        if age > 0 and amt > 0:
            shock_by_age[age] = shock_by_age.get(age, 0.0) + amt

    # Survivor scenario: one spouse dies at a given age
    surv_cfg   = profile.get('survivor') or {}
    surv_on    = bool(surv_cfg.get('enabled', False))
    surv_who   = surv_cfg.get('person', 'p2')   # 'p1' or 'p2'
    surv_age   = int(_num(surv_cfg.get('death_age'), 80))  # p1 age when death occurs
    surv_exp   = _num(surv_cfg.get('expense_pct'), 0.70)   # expenses drop to this %

    # Spending phases — age-based multiplier on base expenses
    # Sort by through_age so lookup is in order
    spend_phases = sorted(_dict_list(profile.get('spending_phases')),
                          key=lambda p: _num(p.get('through_age'), 999))

    def spending_multiplier(age):
        for ph in spend_phases:
            if age <= _num(ph.get('through_age'), 999):
                return _num(ph.get('multiplier'), 1.0)
        return _num(spend_phases[-1].get('multiplier'), 1.0) if spend_phases else 1.0

    # Medical costs — pre-Medicare vs post-Medicare
    medical = profile.get('medical') or {}
    med_pre   = _num(medical.get('pre_medicare_annual'), 0)
    med_post  = _num(medical.get('post_medicare_annual'), 0)
    med_age   = int(_num(medical.get('medicare_age'), 65))
    med_inf   = _num(medical.get('inflation_rate'), 0.05)
    use_irmaa = bool(medical.get('use_irmaa', True))

    # ── ACA premiums (pre-Medicare gap) ───────────────────────────────────────
    aca_cfg   = profile.get('aca') or {}
    aca_on    = bool(aca_cfg.get('enabled', False))
    aca_mo    = _num(aca_cfg.get('monthly_premium'), 0)   # estimated full benchmark premium
    aca_inf   = _num(aca_cfg.get('inflation'), 0.05)

    # ── Long-term care ────────────────────────────────────────────────────────
    ltc_cfg   = profile.get('ltc') or {}
    ltc_on    = bool(ltc_cfg.get('enabled', False))
    # Per-person LTC config: [{person:'p1', start_age:82, duration:3, monthly_cost:0, insurance_monthly:0}]
    ltc_events = _dict_list(ltc_cfg.get('events'))

    # ── Asset allocation glide path ───────────────────────────────────────────
    glide_cfg      = profile.get('glide_path') or {}
    glide_on       = bool(glide_cfg.get('enabled', False))
    glide_eq_start = _num(glide_cfg.get('equity_pct_start'), 60) / 100.0
    glide_eq_end   = _num(glide_cfg.get('equity_pct_end'),   40) / 100.0
    glide_age_start = int(_num(glide_cfg.get('age_start'), 65))
    glide_age_end   = int(_num(glide_cfg.get('age_end'),   80))
    glide_stock_ret = _num(glide_cfg.get('stock_return'), 8.0) / 100.0
    glide_bond_ret  = _num(glide_cfg.get('bond_return'),  3.5) / 100.0

    strat = profile.get('strategy') or {}
    p1_fra_age = int(_num(p1.get('fra_age'), 67))
    p2_fra_age = int(_num(p2.get('fra_age'), 67))
    ss1_age = int(_num(ss1_age_override if ss1_age_override is not None
                       else strat.get('ss1_age'), p1_fra_age))
    ss2_age = int(_num(ss2_age_override if ss2_age_override is not None
                       else strat.get('ss2_age'), p2_fra_age))

    # Spousal SS: each person gets max(own benefit, 50% of partner's PIA)
    p1_fra_mo = _num(p1.get('ss_fra_monthly'), 0)
    p2_fra_mo = _num(p2.get('ss_fra_monthly'), 0) if p2_enabled else 0.0
    ss1_mo = spousal_ss_monthly(p1_fra_mo, p2_fra_mo, ss1_age, p1_fra_age)
    ss2_mo = 0.0 if not p2_enabled else spousal_ss_monthly(p2_fra_mo, p1_fra_mo, ss2_age, p2_fra_age)

    # Current gross annual income for each person while working
    p1_gross_income = _num(p1.get('annual_income'), 0)
    p2_gross_income = _num(p2.get('annual_income'), 0) if p2_enabled else 0.0

    # FICA tax helper — employee share (SS 6.2% up to wage base + Medicare 1.45%)
    # SS wage base grows ~4% / yr from the 2024 base of $168,600.
    # Indexed off 2024 (like the tax brackets), not off the profile's current
    # year, so the base is correct in the projection's first year.
    SS_WAGE_BASE_2024 = 168_600.0
    def fica_tax(gross, yrs_from_2024):
        wage_base = SS_WAGE_BASE_2024 * (1.04 ** max(0, yrs_from_2024))
        ss_tax  = min(gross, wage_base) * 0.062
        med_tax = gross * 0.0145
        return ss_tax + med_tax

    p1_retire_yr = p1b + int(_num(p1.get('retirement_age'), 65))
    p2_retire_yr = p2b + int(_num(p2.get('retirement_age'), 65))

    # Deep-copy starting balances
    bal = {k: float(v['balance']) for k, v in acct_defs.items()}

    # Cost basis for taxable/savings accounts (contributions in, not growth).
    # Brokerage default: current balance is 80% basis / 20% unrealized gain.
    # Savings/HYSA has no unrealized gain — its interest is taxed as it is
    # earned (below), so basis tracks the balance and withdrawals realize
    # nothing further.
    basis = {}
    for k, v in acct_defs.items():
        if v['type'] == 'taxable':
            default_basis = v['balance'] * 0.80
        elif v['type'] == 'savings':
            default_basis = v['balance']
        else:
            basis[k] = 0.0
            continue
        cb = v.get('cost_basis')
        basis[k] = _num(cb, default_basis) if cb is not None else default_basis

    results = []
    # Life expectancy bounds the projection AND governs when each person dies.
    p1_end = p1b + int(_num(p1.get('life_expectancy'), 95))
    p2_end = p2b + int(_num(p2.get('life_expectancy'), 90)) if p2_enabled else 0
    end_year = max(p1_end, p2_end)

    # MAGI by year, for the Medicare IRMAA 2-year lookback.
    magi_by_year = {}

    for yr in range(curr_yr, end_year + 1):
        p1a = yr - p1b
        p2a = yr - p2b
        yrs_since_2024 = yr - 2026   # anchor year for the 2026 tax tables

        p1_ret = yr >= p1_retire_yr
        # P2 only "retires" if they exist. `both_ret` means "nobody in the
        # household is still working", which for a single-person profile is
        # simply p1 being retired — otherwise Roth conversions (gated on
        # both_ret) could never fire for a single filer.
        p2_ret = (yr >= p2_retire_yr) if p2_enabled else False
        any_ret = p1_ret or p2_ret
        both_ret = p1_ret and (p2_ret or not p2_enabled)
        p1_working = not p1_ret
        p2_working = p2_enabled and not p2_ret

        # ── ACCUMULATION PHASE (no one retired yet) ──────────────────────────
        if not any_ret:
            for k, v in acct_defs.items():
                owner = v['owner']
                # A disabled person 2 has no accounts to fund.
                if owner == 'p2' and not p2_enabled:
                    bal[k] *= (1 + v['growth_rate'])
                    continue
                owner_age = p1a if owner == 'p1' else p2a
                c = _num(contribs.get(k, 0))
                # Catch-up contributions (age 50+)
                if owner_age >= 50:
                    if owner_age >= 60 and owner_age <= 63:
                        # SECURE 2.0 super catch-up replaces standard catch-up
                        c += _num(super_cups.get(k, catch_ups.get(k, 0)))
                    else:
                        c += _num(catch_ups.get(k, 0))
                bal[k] = max(0.0, bal[k] + c)
                if v['type'] in ('taxable', 'savings'):
                    basis[k] += c        # contributions add to basis
                if v['type'] == 'savings':
                    # HYSA interest is taxed as it is earned, so it is basis too.
                    basis[k] += bal[k] * v['growth_rate']
                bal[k] *= (1 + v['growth_rate'])
                # growth does NOT increase basis (except savings interest, above)

            # MAGI for the IRMAA 2-year lookback: wages while still working.
            magi_by_year[yr] = (
                (p1_gross_income * (1 + inflation) ** (yr - curr_yr)) +
                (p2_gross_income * (1 + inflation) ** (yr - curr_yr))
            )

            total_bal = sum(bal.values())
            results.append({
                'year': yr, 'p1_age': p1a, 'p2_age': p2a, 'phase': 'accumulation',
                'expenses': 0, 'guaranteed_income': 0, 'withdrawal_total': 0,
                'pension1': 0, 'pension2': 0, 'ss_p1': 0, 'ss_p2': 0,
                'total_ss': 0, 'federal_tax': 0, 'state_tax': 0, 'total_tax': 0,
                'net_income': 0, 'shortfall': 0, 'roth_conversion': 0, 'rmd_total': 0,
                'total_balance': round(total_bal),
                'trad_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'traditional')),
                'roth_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'roth')),
                'taxable_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] in ['taxable', 'savings'])),
                'account_balances': {k: round(v) for k, v in bal.items()},
                'withdrawals': {k: 0 for k in bal},
                'cash_flow_plan': [],
            })
            continue

        # ── RETIREMENT PHASE ─────────────────────────────────────────────────

        # ── Who is still alive? ──────────────────────────────────────────────
        # Each person's life expectancy governs their death, not just the
        # length of the projection — otherwise the shorter-lived spouse keeps
        # drawing Social Security and incurring expenses to the end of the run.
        # The optional survivor scenario can kill someone off earlier still.
        p1_alive = yr <= p1_end
        p2_alive = p2_enabled and yr <= p2_end
        if surv_on and p1a >= surv_age:
            if surv_who == 'p1':
                p1_alive = False
            else:
                p2_alive = False
        # Everyone has died — the projection is over.
        if not p1_alive and not p2_alive:
            break

        # Exactly one member of a couple remaining → survivor rules apply.
        survivor_active = p2_enabled and (p1_alive != p2_alive)

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

        # ACA premiums: cover the gap between early retirement and Medicare age.
        # aca_gross is the full benchmark premium; any premium tax credit is
        # applied inside the withdrawal loop below, because the credit depends
        # on MAGI, which depends on how much is withdrawn/converted.
        aca_gross = 0.0
        aca_members = 0
        if aca_on and aca_mo > 0:
            aca_factor = (1 + aca_inf) ** med_yrs
            if p1_ret and p1_alive and p1a < med_age:
                aca_gross += aca_mo * 12 * aca_factor
                aca_members += 1
            if p2_enabled and p2_ret and p2_alive and p2a < med_age:
                aca_gross += aca_mo * 12 * aca_factor
                aca_members += 1
        # Household size for FPL: living people in the tax household
        aca_household = (1 if p1_alive else 0) + (1 if (p2_enabled and p2_alive) else 0)
        aca_household = max(1, aca_household)
        aca_exp = aca_gross          # refined below once MAGI is known

        # Long-term care expenses
        ltc_exp = 0.0
        if ltc_on:
            for ev in ltc_events:
                who       = ev.get('person', 'p1')
                ev_age    = int(_num(ev.get('start_age'), 82))
                duration  = int(_num(ev.get('duration'), 3))
                mo_cost   = _num(ev.get('monthly_cost'), 8000)
                mo_insure = _num(ev.get('insurance_monthly'), 0)
                net_mo    = max(0.0, mo_cost - mo_insure)
                ev_age_check = p1a if who == 'p1' else p2a
                ev_alive     = p1_alive if who == 'p1' else p2_alive
                if ev_alive and ev_age <= ev_age_check < ev_age + duration:
                    ltc_exp += net_mo * 12 * (1 + med_inf) ** med_yrs

        # ── IRMAA (Medicare high-income surcharge) ───────────────────────────
        # Uses the MAGI actually computed two years earlier — the SSA lookback
        # period — so traditional withdrawals, RMDs and Roth conversions all
        # count, not just pensions and Social Security. Thresholds are CPI
        # indexed and the premiums track medical inflation.
        irmaa_cost = 0.0
        if use_irmaa:
            if (yr - 2) in magi_by_year:
                magi_lookback = magi_by_year[yr - 2]
            else:
                # First two years of the projection have no prior-year MAGI —
                # fall back to the guaranteed-income proxy.
                pen_proxy_ann = sum(
                    pension_income_for_year(pen, p1a if pen.get('owner','p1')=='p1' else p2a)
                    for pen in pensions_list
                )
                ss1_proxy = ss1_mo * 12 if p1a >= ss1_age else 0.0
                ss2_proxy = ss2_mo * 12 if (p2_enabled and p2a >= ss2_age) else 0.0
                magi_lookback = pen_proxy_ann + ss1_proxy + ss2_proxy
            irmaa_thr_factor = (1 + tax_inf) ** max(0, yrs_since_2024)
            irmaa_prem_factor = (1 + med_inf) ** med_yrs
            p1_on_medicare = p1_alive and p1a >= med_age and p1_ret
            p2_on_medicare = p2_enabled and p2_alive and p2a >= med_age and p2_ret
            per_person_prem = irmaa_annual_per_person(
                magi_lookback, use_single, irmaa_thr_factor, irmaa_prem_factor)
            n_on_medicare = (1 if p1_on_medicare else 0) + (1 if p2_on_medicare else 0)
            # The profile's post-Medicare medical budget is assumed to already
            # include the standard Part B/D premium, so only charge the excess.
            base_post_est = per_post * med_factor * n_on_medicare
            irmaa_cost = max(0.0, per_person_prem * n_on_medicare - base_post_est)

        medical_exp = p1_med + p2_med + aca_exp + ltc_exp

        # One-time expense shocks (indexed by p1 age)
        shock_amt = shock_by_age.get(p1a, 0.0)

        exp = living_exp + medical_exp + shock_amt + irmaa_cost

        # ── Pension income ────────────────────────────────────────────────────
        # Iterate over all pensions; each uses its assigned owner's age.
        # If the owner dies (survivor scenario), switch to survivor monthly benefit.
        def _pen_inc(pen, p1_alive, p2_alive):
            pen_owner      = pen.get('owner', 'p1')
            pen_survivor_mo = _num(pen.get('survivor_monthly'), 0)
            owner_age      = p1a if pen_owner == 'p1' else p2a
            owner_alive    = p1_alive if pen_owner == 'p1' else p2_alive
            if survivor_active and not owner_alive and pen_survivor_mo > 0:
                yrs_collecting = max(0, owner_age - int(_num(pen.get('start_age'), 65)))
                return pen_survivor_mo * 12 * (1 + _num(pen.get('cola'), 0)) ** yrs_collecting
            elif survivor_active and not owner_alive:
                return 0.0
            else:
                return pension_income_for_year(pen, owner_age)

        pen_details = [(pen, _pen_inc(pen, p1_alive, p2_alive)) for pen in pensions_list]
        pen1_inc = sum(inc for pen, inc in pen_details if pen.get('owner', 'p1') == 'p1')
        pen2_inc = sum(inc for pen, inc in pen_details if pen.get('owner', 'p1') == 'p2')

        # ── Social Security ───────────────────────────────────────────────────
        # SS entered in today's dollars at FRA; index by COLA from the current
        # year so it stays nominal-consistent with inflated expenses.
        ss1_ann = ss1_mo * 12 * (1.024 ** (yr - curr_yr)) if p1a >= ss1_age else 0.0
        ss2_ann = ss2_mo * 12 * (1.024 ** (yr - curr_yr)) if p2a >= ss2_age else 0.0

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
        p1_work = p1_gross_income * (1 + inflation) ** yrs_elapsed if (p1_working and p1_alive) else 0.0
        p2_work = p2_gross_income * (1 + inflation) ** yrs_elapsed if (p2_working and p2_alive) else 0.0
        working_income = p1_work + p2_work
        total_fica = fica_tax(p1_work, yrs_since_2024) + fica_tax(p2_work, yrs_since_2024)

        # ── Contributions for a still-working spouse ─────────────────────────
        # Contributions are funded OUT OF salary, so they are computed first,
        # capped at earned income (you cannot contribute what you did not
        # earn), and then subtracted from the cash available to spend.
        # Contributions to traditional accounts are pre-tax and also reduce
        # taxable income. Previously the salary was both fully spendable and
        # fully contributed, which created money out of nothing.
        contrib_total   = 0.0
        contrib_pretax  = 0.0
        planned = []
        if not both_ret:
            for k, v in acct_defs.items():
                owner = v['owner']
                if (owner == 'p1' and p1_working) or (owner == 'p2' and p2_working):
                    owner_age = p1a if owner == 'p1' else p2a
                    c = _num(contribs.get(k, 0))
                    if owner_age >= 50:
                        if owner_age >= 60 and owner_age <= 63:
                            c += _num(super_cups.get(k, catch_ups.get(k, 0)))
                        else:
                            c += _num(catch_ups.get(k, 0))
                    if c > 0:
                        planned.append((k, v, c))
                        contrib_total += c

        if contrib_total > 0:
            # Cannot contribute more than the household earned this year.
            scale = min(1.0, working_income / contrib_total) if working_income > 0 else 0.0
            contrib_total = 0.0
            for k, v, c in planned:
                c *= scale
                if c <= 0:
                    continue
                bal[k] = max(0.0, bal[k] + c)
                if v['type'] in ('taxable', 'savings'):
                    basis[k] += c      # already-taxed money — adds to basis
                if v['type'] == 'traditional':
                    contrib_pretax += c
                contrib_total += c

        # Salary left over after funding the contributions is what can be spent.
        guaranteed = pen1_inc + pen2_inc + total_ss + max(0.0, working_income - contrib_total)
        taxable_wages = max(0.0, working_income - contrib_pretax)

        # ── RMDs ─────────────────────────────────────────────────────────────
        rmds = {}
        rmd_tot = 0.0
        for k, v in acct_defs.items():
            if v['type'] == 'traditional':
                _own = v.get('owner', 'p1')
                owner_age = p1a if _own == 'p1' else p2a
                _own_by = p1b if _own == 'p1' else p2b
                r = min(rmd_required(bal[k], owner_age, rmd_start_age(_own_by)), bal[k])
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
        inf_adj = 1.025 ** yrs_since_2024
        if use_single:
            fb, fd = adj_brackets(FED_BRACKETS_SINGLE, FED_STD_DED_SINGLE, tax_inf, yrs_since_2024)
            nb, nd = adj_brackets(st_brackets_single, st_std_ded_single, tax_inf, yrs_since_2024)
            living_age = p1a if (not survivor_active or p1_alive) else p2a
            qualifies  = 1 if (st_pension_excl_age == 0 or living_age >= st_pension_excl_age) else 0
            state_excl = st_pension_excl_pp * qualifies * inf_adj
            ltcg_brackets = LTCG_BRACKETS_SINGLE
        else:
            fb, fd = adj_brackets(FED_BRACKETS_MFJ, FED_STD_DED, tax_inf, yrs_since_2024)
            nb, nd = adj_brackets(st_brackets_mfj, st_std_ded_mfj, tax_inf, yrs_since_2024)
            q1 = 1 if (st_pension_excl_age == 0 or p1a >= st_pension_excl_age) else 0
            q2 = 1 if (st_pension_excl_age == 0 or p2a >= st_pension_excl_age) else 0
            state_excl = st_pension_excl_pp * (q1 + q2) * inf_adj
            ltcg_brackets = LTCG_BRACKETS_MFJ

        # Snapshot balances and basis before any withdrawal, so we can
        # re-run with a grossed-up target on each iteration.
        bal_snap   = dict(bal)
        basis_snap = dict(basis)

        # ACA credit state — resolved inside the loop once MAGI is known.
        exp_base       = exp     # expenses assuming the FULL benchmark premium
        aca_credit     = 0.0
        aca_fpl_ratio  = 0.0
        aca_over_cliff = False

        extra_for_tax = 0.0     # additional amount to cover tax
        total_tax     = 0.0
        fed_tax       = 0.0
        state_tax     = 0.0
        fed_ltcg_tax  = 0.0
        fed_income    = 0.0     # set by the loop; used for Roth later

        for _tax_iter in range(6):
            # Restore from snapshot each iteration
            for k in bal:
                bal[k]   = bal_snap[k]
                basis[k] = basis_snap[k]

            w = {k: 0.0 for k in bal}
            w_rmd = {k: 0.0 for k in bal}   # forced portion, for the action plan
            need = max(0.0, exp - guaranteed + extra_for_tax)

            # 1. RMDs (mandatory — always taken regardless of need)
            for k, r in rmds.items():
                if r > 0:
                    take = min(r, bal[k])
                    w[k] += take; w_rmd[k] += take; bal[k] = max(0, bal[k] - take)
                    need = max(0.0, need - take)

            # 2. Taxable accounts — track capital gains.
            #    Savings/HYSA basis tracks its balance (interest is taxed as
            #    earned, below), so only brokerage realizes a gain here.
            taxable_gains = 0.0
            for k, v in acct_defs.items():
                if v['type'] in ('savings', 'taxable') and need > 0 and bal[k] > 0:
                    take = min(bal[k], need)
                    gain_pct   = max(0.0, (bal[k] - basis[k]) / bal[k])
                    gain       = take * gain_pct
                    basis_used = take - gain
                    basis[k]   = max(0.0, basis[k] - basis_used)

                    if v['type'] == 'taxable':
                        taxable_gains += gain

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

            # Savings/HYSA interest is taxable in the year it is earned, even if
            # never withdrawn. Computed on the post-withdrawal balance; the
            # matching basis credit happens in the growth step below.
            savings_interest = sum(
                bal[k] * acct_defs[k]['ret_growth']
                for k in bal if acct_defs[k]['type'] == 'savings'
            )

            # ── Tax on this iteration's withdrawals ─────────────────────────
            trad_w       = sum(w[k] for k, v in acct_defs.items() if v['type'] == 'traditional')
            # Federal: all pension income is ordinary income regardless of the
            # state exemption. Wages are net of pre-tax 401(k) contributions.
            fed_ordinary = pen1_inc + pen2_inc + trad_w + savings_interest + taxable_wages
            # Provisional income for the SS calculation includes capital gains.
            tx_ss        = taxable_ss_portion(total_ss, fed_ordinary + taxable_gains, use_single)
            fed_ordinary += tx_ss

            fed_ltcg_tax = calc_ltcg_tax(taxable_gains, fed_ordinary,
                                         ltcg_brackets, fd, tax_inf, yrs_since_2024)
            fed_income   = fed_ordinary
            # Capital gains stack on top of ordinary income for bracket
            # purposes (used later for Roth conversion headroom).
            fed_stack    = fed_ordinary + taxable_gains
            # State tax: exclude pensions marked state-exempt; the pension/IRA
            # exclusion applies only to pension and tax-deferred withdrawals —
            # not to wages, interest or capital gains.
            st_ss        = total_ss * st_ss_taxable_pct  # most states don't tax SS
            st_pen_inc   = sum(inc for pen, inc in pen_details if not pen.get('nys_exempt', False))
            st_excl_used = min(state_excl, st_pen_inc + trad_w)
            st_taxable   = max(0.0, st_pen_inc + trad_w + savings_interest
                               + taxable_gains + taxable_wages + st_ss - st_excl_used)

            fed_niit  = niit_tax(taxable_gains + savings_interest,
                                 fed_income + taxable_gains, use_single)
            fed_tax   = calc_tax(fed_income, fb, fd) + fed_ltcg_tax + fed_niit
            state_tax = calc_tax(st_taxable, nb, nd)
            total_tax = fed_tax + state_tax + total_fica

            # ── ACA premium tax credit ───────────────────────────────────────
            # MAGI for ACA = AGI + non-taxable Social Security. Recomputed each
            # pass so the credit reflects this iteration's withdrawals; the loop
            # then converges on a consistent (spending, MAGI, credit) triple.
            if aca_gross > 0:
                aca_magi = max(0.0, fed_income + taxable_gains + (total_ss - tx_ss))
                _credit, _ratio, _over = aca_subsidy(
                    aca_magi, aca_gross, aca_household, inflation, med_yrs)
                aca_credit    = _credit
                aca_fpl_ratio = _ratio
                aca_over_cliff = _over
                aca_exp = max(0.0, aca_gross - aca_credit)
            exp = exp_base - (aca_gross - aca_exp)

            # Check: did we withdraw enough to cover expenses + tax?
            gross_income = guaranteed + sum(w.values())
            net_after_tax = gross_income - total_tax
            deficit = exp - net_after_tax

            if deficit <= 50:    # close enough (within $50)
                break
            if sum(bal.values()) <= 0.01:
                # Portfolio is exhausted — grossing up further cannot raise
                # another dollar, and would inflate the reported shortfall.
                break
            # Gross up by deficit / (1 - combined_marginal) so the extra
            # withdrawal covers its own federal + state tax in one shot.
            fed_marginal   = marginal_rate_at(fed_income, fb, fd)
            state_marginal = marginal_rate_at(st_taxable, nb, nd)
            combined       = fed_marginal + state_marginal
            gross_up = deficit / max(0.30, 1.0 - combined) if combined < 0.95 else deficit
            extra_for_tax = max(0.0, extra_for_tax + gross_up)

        # Unfunded after-tax spending. Measured against what was actually
        # raised, so an exhausted portfolio reports the true gap rather than
        # the gross-up loop's inflated target.
        shortfall = max(0.0, exp - (guaranteed + sum(w.values()) - total_tax))

        # ── ROTH CONVERSIONS ─────────────────────────────────────────────────
        roth_conv = 0.0
        roth_conv_tax = 0.0
        roth_conv_note = None
        # Action-plan detail: which account each conversion dollar came from,
        # where it landed, and how the resulting tax bill was paid.
        conv_from     = {}     # {traditional_key: amount}
        conv_to       = None   # destination roth key
        conv_tax_from = {}     # {cash_key: amount sold to pay the tax}
        conv_tax_cash = 0.0    # total paid from cash
        conv_withheld = 0.0    # total withheld out of the conversion itself

        roth_strategy = str(profile.get('roth_strategy', 'fill_22'))  # fixed, fill_12, fill_22, fill_24, fill_32, none
        roth_fixed_amt = _num(profile.get('roth_fixed_amount'), 20000)
        ROTH_BRACKET_MAP = {'fill_12': 0.12, 'fill_22': 0.22, 'fill_24': 0.24, 'fill_32': 0.32}

        if do_roth and both_ret and roth_strategy != 'none':
            trad_keys = [k for k, v in acct_defs.items() if v['type'] == 'traditional']
            roth_keys = [k for k, v in acct_defs.items() if v['type'] == 'roth']
            trad_bal_total = sum(bal[k] for k in trad_keys)
            if not roth_keys:
                # Without a destination account the conversion has nowhere to
                # land. Previously the traditional balance was debited anyway
                # and the money simply vanished.
                if trad_bal_total > 5000:
                    roth_conv_note = 'no_roth_account'
            elif trad_bal_total > 5000:
                if roth_strategy == 'fixed':
                    room = roth_fixed_amt
                else:
                    target_rate = ROTH_BRACKET_MAP.get(roth_strategy, 0.22)
                    # Gains stack on top of ordinary income, so headroom is
                    # measured against the full stack.
                    room = bracket_room(fed_stack, target_rate, fb, fd)

                # ── ACA subsidy cliff guard ──────────────────────────────────
                # Before Medicare, a conversion raises MAGI. Cross 400% FPL and
                # the ENTIRE premium tax credit vanishes — frequently a far
                # bigger hit than the bracket-fill saves. Cap the conversion at
                # the cliff unless the household is already above it (nothing
                # left to lose) or the user opts out.
                if (aca_gross > 0 and room > 0
                        and bool(profile.get('roth_respect_aca_cliff', True))):
                    _magi_now = max(0.0, fed_income + taxable_gains + (total_ss - tx_ss))
                    _fpl = federal_poverty_level(aca_household, inflation, med_yrs)
                    _cliff_magi = ACA_CLIFF_FPL * _fpl
                    if _magi_now <= _cliff_magi:
                        headroom = max(0.0, _cliff_magi - _magi_now)
                        if headroom < room:
                            room = headroom
                            roth_conv_note = 'aca_cliff_capped'

                if room > 0:
                    roth_conv = min(room, trad_bal_total, 250000)

                    def _conv_tax(amount):
                        """Federal + state tax generated by converting `amount`."""
                        f = calc_tax(fed_income + amount, fb, fd) - calc_tax(fed_income, fb, fd)
                        s = calc_tax(st_taxable + amount, nb, nd) - calc_tax(st_taxable, nb, nd)
                        return f + s

                    # The conversion tax has to be paid with real money. Cash
                    # from taxable/savings accounts is used first (the optimal
                    # approach, since it leaves the whole conversion compounding
                    # tax-free); any remainder is withheld from the conversion
                    # itself. Previously the tax was reported but never funded,
                    # which made every conversion look free.
                    cash_keys = [k for k, v in acct_defs.items()
                                 if v['type'] in ('taxable', 'savings')]
                    cash_avail = sum(bal[k] for k in cash_keys)

                    roth_conv_tax = _conv_tax(roth_conv)
                    paid_from_cash = min(roth_conv_tax, cash_avail)
                    withheld = roth_conv_tax - paid_from_cash
                    if withheld > roth_conv:
                        # Cannot even withhold enough — scale the conversion
                        # back to what the household can actually pay for.
                        lo_c, hi_c = 0.0, roth_conv
                        for _ in range(30):
                            mid_c = (lo_c + hi_c) / 2.0
                            if _conv_tax(mid_c) <= cash_avail + mid_c:
                                lo_c = mid_c
                            else:
                                hi_c = mid_c
                        roth_conv = lo_c
                        roth_conv_tax = _conv_tax(roth_conv)
                        paid_from_cash = min(roth_conv_tax, cash_avail)
                        withheld = max(0.0, roth_conv_tax - paid_from_cash)

                    if roth_conv > 0:
                        # Debit the gross conversion from traditional accounts.
                        rem_conv = roth_conv
                        for k in trad_keys:
                            if rem_conv <= 0:
                                break
                            take = min(bal[k], rem_conv)
                            bal[k] -= take
                            conv_from[k] = conv_from.get(k, 0.0) + take
                            rem_conv -= take
                        conv_to = roth_keys[0]
                        conv_withheld = withheld
                        conv_tax_cash = paid_from_cash
                        # Only the net (after any withholding) reaches the Roth.
                        bal[roth_keys[0]] += max(0.0, roth_conv - withheld)

                        # Sell taxable/savings assets to cover the cash portion.
                        rem_cash = paid_from_cash
                        for k in cash_keys:
                            if rem_cash <= 0:
                                break
                            take = min(bal[k], rem_cash)
                            if take <= 0:
                                continue
                            conv_tax_from[k] = conv_tax_from.get(k, 0.0) + take
                            if bal[k] > 0:
                                gain_pct = max(0.0, (bal[k] - basis[k]) / bal[k])
                                basis[k] = max(0.0, basis[k] - take * (1 - gain_pct))
                            bal[k] -= take
                            rem_cash -= take

                        fed_income += roth_conv
                        fed_stack  += roth_conv
                        st_taxable  = max(0.0, st_taxable + roth_conv)
                    else:
                        roth_conv_tax = 0.0
                        roth_conv_note = 'unaffordable'

        # Pre-Roth tax = the amount the gross-up loop was designed to cover.
        # Roth conversion tax is a strategic cost, not a spending cost, so
        # net_income (which measures "can I cover expenses?") uses pre-Roth tax.
        # ── Re-price the ACA credit now that the conversion is known ─────────
        # A conversion is MAGI. Even after the cliff guard, filling a bracket
        # raises the required contribution and shrinks the credit; that lost
        # subsidy is a real cost of converting and is reported alongside the
        # conversion tax rather than being quietly ignored.
        aca_subsidy_lost = 0.0
        if aca_gross > 0 and roth_conv > 0:
            _magi_post = max(0.0, fed_income + taxable_gains + (total_ss - tx_ss))
            _c2, _r2, _o2 = aca_subsidy(_magi_post, aca_gross, aca_household,
                                        inflation, med_yrs)
            aca_subsidy_lost = max(0.0, aca_credit - _c2)
            aca_credit     = _c2
            aca_fpl_ratio  = _r2
            aca_over_cliff = _o2
            aca_exp        = max(0.0, aca_gross - aca_credit)
            exp            = exp_base - (aca_gross - aca_exp)

        tax_pre_roth = total_tax
        # Component split of the spending tax bill, for the cash-flow plan.
        # (The incremental Roth conversion tax is reported separately, since it
        # is a strategic cost rather than part of funding this year's living.)
        fed_tax_spend   = fed_tax
        state_tax_spend = state_tax

        # Recalculate final tax including Roth conversion (for total reporting)
        if roth_conv > 0:
            fed_tax   = calc_tax(fed_income, fb, fd) + fed_ltcg_tax
            state_tax = calc_tax(st_taxable, nb, nd)
            total_tax = fed_tax + state_tax + total_fica

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
        reinvest_dest = reinvest_key if surplus > 0 else None

        # ── GROW ACCOUNTS ────────────────────────────────────────────────────
        # The glide path describes the invested portfolio's stock/bond mix, so
        # it deliberately does NOT override a cash savings/HYSA rate.
        eq_pct = None
        if glide_on and any_ret:
            if p1a <= glide_age_start:
                eq_pct = glide_eq_start
            elif p1a >= glide_age_end:
                eq_pct = glide_eq_end
            else:
                t = (p1a - glide_age_start) / max(1, glide_age_end - glide_age_start)
                eq_pct = glide_eq_start + t * (glide_eq_end - glide_eq_start)
            glide_gr = eq_pct * glide_stock_ret + (1 - eq_pct) * glide_bond_ret

        for k, v in acct_defs.items():
            if eq_pct is not None and v['type'] != 'savings':
                gr = glide_gr
            else:
                gr = v['ret_growth']
            growth = bal[k] * gr
            bal[k] = max(0.0, bal[k] + growth)
            if v['type'] == 'savings':
                # Interest was taxed as ordinary income this year, so it is
                # basis — a later withdrawal must not tax it again.
                basis[k] = min(bal[k], basis[k] + max(0.0, growth))

        total_bal = sum(bal.values())

        # ── ITEMISED CASH FLOW PLAN ──────────────────────────────────────────
        # Every dollar that moves this year, named and grouped:
        #   flow 'in'       — money arriving (pensions, SS, wages, portfolio draws)
        #   flow 'internal' — portfolio-to-portfolio moves (conversions, reinvest)
        #   flow 'out'      — money leaving (living costs, healthcare, taxes)
        # Amounts are nominal dollars. Money-in minus money-out reconciles to the
        # year's surplus or shortfall.
        def _lbl(key):
            d = acct_defs.get(key) or {}
            return d.get('label') or str(key)

        p1_name = str(p1.get('name') or 'Person 1')
        p2_name = str(p2.get('name') or 'Person 2')

        plan = []

        def _add(kind, amount, src_key=None, dest_key=None, note='',
                 flow='in', label=None, dest_label=None):
            if amount is None or round(amount) <= 0:
                return
            plan.append({
                'kind':       kind,
                'flow':       flow,
                'from':       src_key,
                'from_label': label if label else (_lbl(src_key) if src_key else None),
                'to':         dest_key,
                'to_label':   dest_label if dest_label else (_lbl(dest_key) if dest_key else None),
                'amount':     round(amount),
                'note':       note,
            })

        # ── MONEY IN ─────────────────────────────────────────────────────────
        # 1. Pensions — one line per pension, by its own name
        for _pen, _inc in pen_details:
            _who = p1_name if _pen.get('owner', 'p1') == 'p1' else p2_name
            _pname = str(_pen.get('name') or 'Pension')
            _add('pension', _inc, flow='in',
                 label=f'{_pname} ({_who})',
                 note='Pension income')

        # 2. Social Security — per person
        _add('social_security', ss1_ann, flow='in',
             label=f'Social Security — {p1_name}', note='Social Security benefit')
        if p2_enabled:
            _add('social_security', ss2_ann, flow='in',
                 label=f'Social Security — {p2_name}', note='Social Security benefit')

        # 3. Wages, for anyone still working
        _add('wages', p1_work, flow='in', label=f'Wages — {p1_name}',
             note='Employment income')
        if p2_enabled:
            _add('wages', p2_work, flow='in', label=f'Wages — {p2_name}',
                 note='Employment income')

        # 4. Required minimum distributions (forced portfolio draw)
        for k in acct_defs:
            _add('rmd', w_rmd.get(k, 0.0), src_key=k, flow='in',
                 note='Required minimum distribution')

        # 5. Discretionary withdrawals to fund spending (net of the RMD part)
        for k in acct_defs:
            _add('spend', w.get(k, 0.0) - w_rmd.get(k, 0.0), src_key=k, flow='in',
                 note='To fund living expenses')

        # ── INTERNAL MOVES ───────────────────────────────────────────────────
        # 6. Payroll contributions while still working
        _add('contribute', contrib_total, flow='internal',
             label='Wages', dest_label='Retirement accounts',
             note='Contributed from wages')

        # 7. Roth conversions — source account → destination account
        for k, amt in conv_from.items():
            _add('convert', amt, src_key=k, dest_key=conv_to, flow='internal',
                 note='Roth conversion')

        # 8. How the conversion tax was funded
        for k, amt in conv_tax_from.items():
            _add('convert_tax', amt, src_key=k, flow='internal',
                 note='Sold to pay Roth conversion tax')
        _add('convert_tax_withheld', conv_withheld, src_key=conv_to, flow='internal',
             note='Tax withheld from the conversion (never reaches the Roth)')

        # 9. Surplus reinvestment
        _add('reinvest', surplus, dest_key=reinvest_dest, flow='internal',
             note='After-tax surplus reinvested')

        # ── MONEY OUT ────────────────────────────────────────────────────────
        _add('living', living_exp, flow='out', label='Living expenses',
             note=(f'{round(phase_mult*100)}% of base spending'
                   if phase_mult != 1 else 'Base spending'))
        _add('medical', p1_med + p2_med, flow='out', label='Medical costs',
             note='Out-of-pocket healthcare')
        if aca_credit > 0:
            _add('aca', aca_gross, flow='out', label='ACA premiums (full price)',
                 note='Pre-Medicare health insurance, before subsidy')
            _add('aca_subsidy', aca_credit, flow='in', label='ACA premium tax credit',
                 note=f'Subsidy at {aca_fpl_ratio:.0%} of the federal poverty level')
        else:
            _add('aca', aca_exp, flow='out', label='ACA premiums',
                 note=('No subsidy — income is over the 400% FPL cliff'
                       if aca_over_cliff else 'Pre-Medicare health insurance'))
        _add('ltc', ltc_exp, flow='out', label='Long-term care',
             note='Net of any LTC insurance')
        _add('irmaa', irmaa_cost, flow='out', label='IRMAA surcharge',
             note='Income-related Medicare surcharge')
        _add('shock', shock_amt, flow='out', label='One-time expense',
             note='Planned one-off cost this year')
        _add('federal_tax', fed_tax_spend, flow='out', label='Federal income tax',
             note='On pensions, SS, wages and withdrawals')
        _add('state_tax', state_tax_spend, flow='out', label='State income tax',
             note='State tax on taxable income')
        _add('fica', total_fica, flow='out', label='FICA (payroll tax)',
             note='Social Security + Medicare on wages')
        # NOTE: the Roth conversion tax is deliberately NOT listed here. It is a
        # strategic cost funded from the portfolio, and the internal-moves
        # section already itemises exactly how it was paid (sold from a named
        # account and/or withheld). Listing it again would double-count it and
        # break the in/out reconciliation.

        # Reconciliation totals for the UI
        _flow_in  = sum(x['amount'] for x in plan if x['flow'] == 'in')
        _flow_out = sum(x['amount'] for x in plan if x['flow'] == 'out')

        results.append({
            'cash_flow_plan': plan,
            'flow_total_in':  _flow_in,
            'flow_total_out': _flow_out,
            'flow_net':       _flow_in - _flow_out,
            'rmd_by_account':   {k: round(v) for k, v in w_rmd.items() if round(v) > 0},
            'spend_by_account': {k: round(w[k] - w_rmd.get(k, 0.0))
                                 for k in w if round(w[k] - w_rmd.get(k, 0.0)) > 0},
            'roth_conv_from':      {k: round(v) for k, v in conv_from.items() if round(v) > 0},
            'roth_conv_to':        conv_to,
            'roth_conv_tax_cash':  round(conv_tax_cash),
            'roth_conv_withheld':  round(conv_withheld),
            'reinvest_account':    reinvest_dest,
            'year': yr, 'p1_age': p1a, 'p2_age': p2a, 'phase': 'retirement',
            'expenses': round(exp),
            'living_expenses': round(living_exp),
            'medical_expenses': round(medical_exp),
            'irmaa_cost': round(irmaa_cost),
            'aca_expense': round(aca_exp),
            'aca_gross_premium': round(aca_gross),
            'aca_subsidy': round(aca_credit),
            'aca_fpl_ratio': round(aca_fpl_ratio, 2),
            'aca_over_cliff': bool(aca_over_cliff and aca_gross > 0),
            'aca_subsidy_lost_to_conversion': round(aca_subsidy_lost),
            'ltc_expense': round(ltc_exp),
            'spending_multiplier': round(phase_mult, 2),
            'pension1': round(pen1_inc),
            'pension2': round(pen2_inc),
            'ss_p1': round(ss1_ann),
            'ss_p2': round(ss2_ann),
            'total_ss': round(total_ss),
            'working_income': round(working_income),
            'contributions_total': round(contrib_total),
            'fica_tax': round(total_fica),
            'shock_expense': round(shock_amt),
            'survivor_active': survivor_active,
            'p1_alive': p1_alive,
            'p2_alive': p2_alive,
            'guaranteed_income': round(guaranteed),
            'withdrawal_total': round(sum(w.values())),
            'withdrawals': {k: round(v) for k, v in w.items()},
            'roth_conversion': round(roth_conv),
            'roth_conversion_tax': round(roth_conv_tax),
            'roth_conversion_note': roth_conv_note,
            'federal_tax': round(fed_tax),
            'federal_ltcg_tax': round(fed_ltcg_tax),
            'capital_gains': round(taxable_gains),
            'state_tax': round(state_tax),
            'total_tax': round(total_tax),
            'net_income': round(guaranteed + sum(w.values()) - tax_pre_roth),
            'shortfall': round(shortfall),
            'total_balance': round(total_bal),
            'trad_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'traditional')),
            'roth_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] == 'roth')),
            'taxable_balance': round(sum(bal[k] for k, v in acct_defs.items() if v['type'] in ['taxable', 'savings'])),
            'rmd_total': round(rmd_tot),
            'surplus_reinvested': round(surplus),
            'glide_equity_pct': round(eq_pct * 100, 1) if eq_pct is not None else None,
            'account_balances': {k: round(v) for k, v in bal.items()},
        })

        # Record this year's MAGI for the IRMAA 2-year lookback.
        magi_by_year[yr] = fed_stack

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
        # Score = ending portfolio value. Expenses are identical across
        # scenarios, so the terminal balance already captures the whole effect
        # of the claiming decision: more Social Security means smaller
        # withdrawals, and taxes are paid out of the portfolio along the way.
        # (The old score added lifetime SS to the ending balance and so
        # counted every benefit dollar twice, biasing the recommendation.)
        'score':             round(final_bal),
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

    # Avoiding a year where the money runs out beats any ending balance.
    best = max(comparisons, key=lambda x: (-x['shortfall_years'], x['score']))
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

NYSLRS_REDUCTION = {
    # Official NYS Comptroller early-retirement reduction tables (% by age).
    # Interpolated by month, these reproduce OSC's published half-year examples.
    'tier34': {62: 0.0, 61: 6.0, 60: 12.0, 59: 15.0, 58: 18.0, 57: 21.0, 56: 24.0, 55: 27.0},
    'tier5':  {62: 0.0, 61: 6.67, 60: 13.33, 59: 18.33, 58: 23.33, 57: 28.33, 56: 33.33, 55: 38.33},
    'tier6':  {63: 0.0, 62: 6.5, 61: 13.0, 60: 19.5, 59: 26.0, 58: 32.5, 57: 39.0, 56: 45.5, 55: 52.0},
}

def nyslrs_reduction(age, table_key, nra):
    """Early-retirement reduction (fraction) for the given benefit age,
    interpolated by month between NYSLRS annual anchors."""
    table = NYSLRS_REDUCTION[table_key]
    if age >= nra:
        return 0.0
    if age <= 55:
        return table[55] / 100.0
    lo = int(math.floor(age))
    hi = lo + 1
    lo = max(55, min(lo, nra))
    hi = max(55, min(hi, nra))
    r_lo = table.get(lo, table[55])
    r_hi = table.get(hi, 0.0)
    frac = age - math.floor(age)
    return (r_lo + (r_hi - r_lo) * frac) / 100.0


def calc_nys_pension(params):
    """
    Calculate NYS ERS or PFRS pension benefit from service record.

    ERS Tier formulas (NYSLRS):
      Tier 3/4  (1976–2009): FAS = avg 3 highest consec. yrs
                              <20 yrs  → 1.66% × FAS × service
                              20–30 yrs → 2.00% × FAS × service (all years)
                              >30 yrs  → 2.00% × FAS × 30 + 1.50% × FAS × (service-30)
                              NRA 62; early reduction per the NYSLRS table
                              unless 30+ yrs of service
      Tier 5    (2010–2012): FAS = avg 3 highest consec. yrs
                              same graded percentages as Tier 3/4
                              NRA 62; no 30-year exemption from the reduction
      Tier 6    (2012–now):  FAS = avg 5 highest consec. yrs
                              <20 yrs → 1.66% × FAS × service
                              20 yrs  → 1.75% × FAS × 20  (= 35% of FAS)
                              >20 yrs → 35% of FAS + 2.00% per yr beyond 20
                              NRA 63; no 30-year exemption from the reduction

    PFRS (Police & Fire):     2.00% × FAS × service, max 60% (30 yrs)
                              NRA = 20 years of service at any age
    """
    system      = params.get('system', 'ERS')
    tier        = str(params.get('tier', '6'))
    cur_salary  = _num(params.get('current_salary'), 0)
    cur_age     = _num(params.get('current_age'), 55)
    cur_service = _num(params.get('current_service_years'), 0)
    raise_rate  = _num(params.get('annual_raise_pct'), 2.0) / 100.0
    fas_yrs     = 5 if tier == '6' else 3   # Tier 6 uses 5-year FAS

    # ── Two ages that can differ ──────────────────────────────────────────────
    # leave_age:   when employment ends → service years and FAS are FROZEN here
    # benefit_age: when payments begin  → determines early-retirement reduction
    #   (you can leave at 57, defer benefits to 62, and avoid the 33% penalty)
    leave_age   = _num(params.get('leave_employment_age') or params.get('planned_retire_age'), 65)
    benefit_age = _num(params.get('benefit_start_age') or params.get('planned_retire_age'), leave_age)
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

        def ers_graded(fas_, service_):
            """Tier 3/4/5 service-fraction: 1.66% under 20 years, 2% for
            20-30 years (applied to all years), 1.5% for years beyond 30."""
            if service_ < 20:
                return fas_ * 0.0166 * service_
            if service_ <= 30:
                return fas_ * 0.02 * service_
            return fas_ * 0.02 * 30 + fas_ * 0.015 * (service_ - 30)

        if tier in ('3', '4'):
            gross = ers_graded(fas, service)
            nra   = 62
            # Tier 2/3/4: 30+ years of service => no early-retirement reduction
            if benefit_start_age < nra and service < 30:
                reduction = nyslrs_reduction(benefit_start_age, 'tier34', nra)
            else:
                reduction = 0.0
            annual = gross * (1.0 - reduction)
            return annual, annual / 12, reduction, gross, f'Tier {tier} ERS'

        elif tier == '5':
            gross = ers_graded(fas, service)
            nra   = 62
            # Tier 5 ERS: the 30-year exemption does NOT apply (NYSLRS)
            reduction = nyslrs_reduction(benefit_start_age, 'tier5', nra)
            annual = gross * (1.0 - reduction)
            return annual, annual / 12, reduction, gross, 'Tier 5 ERS'

        elif tier == '6':
            # 1.66% under 20 years; exactly 20 years earns 35% of FAS; every
            # year beyond 20 adds 2%. Tier 6 has no reduced rate past 30.
            if service < 20:
                gross = fas * 0.0166 * service
            else:
                gross = fas * 0.35 + fas * 0.02 * (service - 20)
            nra = 63
            # Tier 6 ERS: the 30-year exemption does NOT apply (NYSLRS)
            reduction = nyslrs_reduction(benefit_start_age, 'tier6', nra)
            annual = gross * (1.0 - reduction)
            return annual, annual / 12, reduction, gross, 'Tier 6 ERS'

        else:
            gross = ers_graded(fas, service)
            return gross, gross / 12, 0.0, gross, f'Tier {tier}'

    # ── Primary result: FAS/service frozen at leave_age, reduction at benefit_age ──
    fas, service = project_fas_and_service(leave_age)
    annual, monthly, reduction, gross, tier_label = compute_benefit(fas, service, benefit_age)

    # ── Comparison: hold leave_age fixed, vary benefit_start_age ─────────────
    # This reveals the value of deferring collection to reduce or eliminate penalty.
    comparison = []
    # Keep the exact leave/benefit ages (they may be fractional) so the
    # planned scenario always appears in the comparison table.
    test_benefit_ages = sorted({55, 57, 60, 62, 63, 65, 67} | {leave_age, benefit_age})
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
    "state": "NY",
    "custom_state_rate": 0.0,
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
    "pensions": [
        {
            "name": "Pension 1",
            "owner": "p1",
            "monthly_benefit": 0,
            "survivor_monthly": 0,
            "start_age": 65,
            "cola": 0.0,
            "nys_exempt": False
        },
        {
            "name": "Pension 2",
            "owner": "p2",
            "monthly_benefit": 0,
            "survivor_monthly": 0,
            "start_age": 65,
            "cola": 0.0,
            "nys_exempt": False
        }
    ],
    "strategy": {
        "ss1_age": 67,
        "ss2_age": 67
    }
}


# ─── PROFILE VALIDATION ──────────────────────────────────────────────────────

def validate_profile(data):
    """Sanity-check a profile before it is written to disk.

    Not a full schema — just enough that a malformed payload cannot replace a
    good profile.json and then break every subsequent calculation.
    Returns (ok, reason).
    """
    if not isinstance(data, dict):
        return False, 'not an object'

    # Reject non-finite numbers anywhere in the payload. json.dumps happily
    # writes NaN/Infinity, but those are not valid strict JSON and every later
    # read of profile.json would produce silently wrong arithmetic.
    def _finite(node, path='profile'):
        if isinstance(node, float):
            if math.isnan(node) or math.isinf(node):
                return False, f'{path} is not a finite number'
        elif isinstance(node, dict):
            for k, v in node.items():
                ok, why = _finite(v, f'{path}.{k}')
                if not ok:
                    return False, why
        elif isinstance(node, list):
            for i, v in enumerate(node):
                ok, why = _finite(v, f'{path}[{i}]')
                if not ok:
                    return False, why
        return True, ''
    ok, why = _finite(data)
    if not ok:
        return False, why
    for key in ('person1', 'person2'):
        if key in data and not isinstance(data[key], dict):
            return False, f'{key} must be an object'
    accounts = data.get('accounts')
    if accounts is not None:
        if not isinstance(accounts, dict):
            return False, 'accounts must be an object'
        for k, v in accounts.items():
            if not isinstance(v, dict):
                return False, f'account {k} must be an object'
            t = str(v.get('type', 'taxable')).lower()
            if t not in ACCOUNT_TYPES:
                return False, f'account {k} has unknown type {t!r}'
    if 'pensions' in data and not isinstance(data['pensions'], list):
        return False, 'pensions must be a list'
    # Must survive an actual projection, or it is not a usable profile.
    try:
        project(copy.deepcopy(data))
    except Exception as e:
        return False, f'projection failed ({type(e).__name__})'
    return True, ''


# ─── HTTP SERVER ─────────────────────────────────────────────────────────────

ALLOWED_HOSTS = ('localhost', '127.0.0.1', '::1')


class Handler(BaseHTTPRequestHandler):
    MAX_BODY = 5 * 1024 * 1024  # 5 MB request cap (DoS guard)

    def log_message(self, format, *args):
        pass  # Quiet server log

    def _host_ok(self):
        # Anti DNS-rebinding: only honor requests addressed to localhost.
        # A missing Host is rejected too — HTTP/1.1 requires it, and allowing
        # it left an easy bypass for the check.
        host = self.headers.get('Host')
        if not host:
            return False
        return host.rsplit(':', 1)[0].strip('[]') in ALLOWED_HOSTS

    def _origin_ok(self):
        """Reject cross-site writes (CSRF).

        Dropping the wildcard CORS header stops another site *reading* the
        profile, but an HTML form POST is a 'simple request' that needs no
        preflight — so a malicious page could still overwrite profile.json.
        Requiring a same-origin Origin/Sec-Fetch-Site and a JSON content type
        (which forms cannot send) closes that hole.
        """
        site = self.headers.get('Sec-Fetch-Site')
        if site is not None and site not in ('same-origin', 'none'):
            return False

        origin = self.headers.get('Origin')
        if origin:
            allowed = set()
            for h in ALLOWED_HOSTS:
                hh = f'[{h}]' if ':' in h else h
                allowed.add(f'http://{hh}:{PORT}')
            if origin not in allowed:
                return False

        ctype = (self.headers.get('Content-Type') or '').split(';')[0].strip().lower()
        return ctype == 'application/json'

    def _fail(self, message, status=500):
        """Log the real traceback locally; tell the client only what it needs."""
        traceback.print_exc(file=sys.stderr)
        self.send_json({'error': message}, status)

    def send_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
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
        # Same-origin local app; no cross-origin access is granted.
        self.send_response(200)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def do_GET(self):
        if not self._host_ok():
            self.send_response(403); self.end_headers(); return
        if self.path in ('/', '/index.html'):
            self.send_file(os.path.join(CURRENT_DIR, 'index.html'), 'text/html; charset=utf-8')
        elif self.path == '/api/version':
            self.send_json({'version': APP_VERSION})
        elif self.path == '/api/profile':
            try:
                with DATA_LOCK:
                    if os.path.exists(DATA_FILE):
                        with open(DATA_FILE) as f:
                            profile = json.load(f)
                    else:
                        profile = DEFAULT_PROFILE
            except Exception:
                self._fail('Could not read profile.json'); return
            self.send_json(profile)
        else:
            self.send_response(404); self.end_headers()

    def do_POST(self):
        if not self._host_ok():
            self.send_response(403); self.end_headers(); return
        if not self._origin_ok():
            self.send_json({'error': 'Cross-site request refused'}, 403); return
        try:
            length = int(self.headers.get('Content-Length', 0))
        except (TypeError, ValueError):
            self.send_json({'error': 'Invalid Content-Length'}, 400); return
        if length < 0 or length > self.MAX_BODY:
            self.send_json({'error': 'Request too large'}, 413); return
        body = self.rfile.read(length)
        try:
            data = json.loads(body)
        except Exception:
            self.send_json({'error': 'Invalid JSON'}, 400); return
        if not isinstance(data, dict):
            self.send_json({'error': 'Expected a JSON object'}, 400); return

        if self.path == '/api/save':
            ok, why = validate_profile(data)
            if not ok:
                self.send_json({'error': f'Invalid profile: {why}'}, 400); return
            try:
                with DATA_LOCK:
                    tmp = DATA_FILE + '.tmp'
                    with open(tmp, 'w') as f:
                        json.dump(data, f, indent=2)
                    os.replace(tmp, DATA_FILE)
                self.send_json({'ok': True})
            except Exception:
                self._fail('Could not save profile')

        elif self.path == '/api/calculate':
            try:
                results = project(data)
                self.send_json({'ok': True, 'results': results})
            except Exception:
                self._fail('Projection failed')

        elif self.path == '/api/calculate_no_roth':
            try:
                results = project(data, do_roth=False)
                self.send_json({'ok': True, 'results': results})
            except Exception:
                self._fail('Projection failed')

        elif self.path == '/api/optimize_ss':
            try:
                result = optimize_ss(data)
                self.send_json({'ok': True, **result})
            except Exception:
                self._fail('Social Security optimization failed')

        elif self.path == '/api/calc_nys_pension':
            try:
                result = calc_nys_pension(data)
                self.send_json(result)
            except Exception:
                self._fail('Pension calculation failed')

        elif self.path == '/api/recommend':
            try:
                target_wealth = _num(data.get('target_wealth'), 0)
                target_age    = data.get('target_age', None)
                if target_age is not None:
                    target_age = int(_num(target_age, 95))
                profile_data  = data.get('profile', data)
                result = recommend_spending(profile_data, target_wealth=target_wealth, target_age=target_age)
                self.send_json({'ok': True, **result})
            except Exception:
                self._fail('Spending recommendation failed')

        elif self.path == '/api/monte_carlo':
            try:
                n_sims     = max(100, min(2000, int(_num(data.get('n_sims'), 500))))
                vol        = max(0.0, min(0.40, _num(data.get('volatility'), 0.12)))
                gr_cut     = max(0.0, min(0.30, _num(data.get('gr_cut'),   0.10)))
                gr_boost   = max(0.0, min(0.30, _num(data.get('gr_boost'), 0.10)))
                gr_floor   = max(0.50, min(1.00, _num(data.get('gr_floor'), 0.85)))
                gr_ceil    = max(1.00, min(2.00, _num(data.get('gr_ceil'),  1.25)))
                infl_vol   = max(0.0, min(0.10, _num(data.get('inflation_vol'), 0.0)))
                result     = monte_carlo(data, n_sims=n_sims, volatility=vol,
                                         guardrails=True, gr_cut=gr_cut,
                                         gr_boost=gr_boost, gr_floor=gr_floor,
                                         gr_ceil=gr_ceil, inflation_vol=infl_vol)
                self.send_json(result)
            except Exception:
                self._fail('Monte Carlo simulation failed')

        else:
            self.send_response(404); self.end_headers()


def _run_sim_set(all_shocks, start_bal, withdrawals, drift, ages,
                 guardrails=False, gr_upper=1.20, gr_lower=0.80,
                 gr_cut=0.10, gr_boost=0.10, gr_floor=0.85, gr_ceil=1.25,
                 all_infl=None):
    """
    Replay a pre-generated shock matrix against the withdrawal schedule.
    Returns percentiles, success stats, and guardrail trigger info.
    Using the same shock matrix for base and guardrail runs gives a
    true apples-to-apples comparison of what the circuit breakers buy.
    """
    n_sims   = len(all_shocks)
    n_years  = len(withdrawals)

    all_balances   = []
    depletion_ages = []
    trigger_years  = 0       # total sim-years a guardrail actually moved spending
    total_adj      = 0.0     # cumulative adjustment factor (for avg)

    for _sim_idx, shocks in enumerate(all_shocks):
        infl_path   = all_infl[_sim_idx] if all_infl is not None else None
        bal         = float(start_bal)
        sim_bals    = []
        depleted_at = None
        adj_mult    = 1.0    # running guardrail multiplier
        # Anchor the initial withdrawal rate on the balance in the first year
        # money is actually drawn, which may be years into retirement.
        initial_wr  = None

        for i in range(n_years):
            base_w = withdrawals[i]
            # Inflation risk: the deterministic schedule assumes one fixed
            # inflation rate forever. When inflation runs hot, the same real
            # lifestyle costs more nominal dollars, so the required withdrawal
            # scales up on that path.
            if all_infl is not None:
                base_w *= infl_path[i]

            if initial_wr is None and base_w > 0 and bal > 0:
                initial_wr = base_w / bal

            if guardrails and bal > 0 and initial_wr:
                # Current withdrawal rate vs initial rate
                current_wr  = (base_w * adj_mult) / bal
                rate_ratio  = current_wr / initial_wr
                prev_mult   = adj_mult

                if rate_ratio > gr_upper:
                    # Portfolio stressed — cut spending
                    adj_mult = max(adj_mult * (1.0 - gr_cut), gr_floor)
                elif rate_ratio < gr_lower:
                    # Portfolio thriving — allow more spending
                    adj_mult = min(adj_mult * (1.0 + gr_boost), gr_ceil)
                # Only count a trigger when it changed spending; already being
                # pinned at the floor or ceiling is not a fresh adjustment.
                if adj_mult != prev_mult:
                    trigger_years += 1

            actual_w = base_w * adj_mult if guardrails else base_w
            total_adj += adj_mult

            # Log-normal returns: `drift` is already a log-space mean, so it
            # must be exponentiated rather than used as a simple return.
            bal = max(0.0, (bal - actual_w) * math.exp(drift + shocks[i]))
            sim_bals.append(round(bal))
            if bal == 0 and depleted_at is None:
                depleted_at = ages[i]

        all_balances.append(sim_bals)
        depletion_ages.append(depleted_at)

    # ── Percentiles ────────────────────────────────────────────────────────
    percentiles = {}
    for pct in [10, 25, 50, 75, 90]:
        idx = max(0, min(n_sims - 1, int(math.ceil(n_sims * pct / 100.0)) - 1))
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
                gr_upper=1.20, gr_lower=0.80, inflation_vol=0.0):
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
    base_inflation = float(profile.get('inflation', 0.03) or 0.0)
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
    accts     = normalize_accounts(profile.get('accounts'))
    total_val = sum(v['balance'] for v in accts.values())
    if total_val > 0:
        base_growth = sum(
            v['ret_growth'] * v['balance'] for v in accts.values()
        ) / total_val
    else:
        base_growth = 0.065

    # Log-space mean: exp(drift + shock) has an arithmetic mean of
    # (1 + base_growth), so the simulated median compounds correctly.
    drift = math.log(1.0 + max(-0.99, base_growth)) - (volatility ** 2) / 2.0

    # ── Generate shocks ONCE; reuse for both runs ─────────────────────────
    all_shocks = [
        [random.gauss(0, volatility) for _ in range(n_years)]
        for _ in range(n_sims)
    ]

    # ── Inflation paths ───────────────────────────────────────────────────
    # Each year's inflation is drawn around the planning assumption; the
    # cumulative deviation from that assumption scales the nominal spending
    # need. inflation_vol = 0 reproduces the old fixed-inflation behaviour.
    all_infl = None
    if inflation_vol > 0:
        all_infl = []
        for _ in range(n_sims):
            cum, path = 1.0, []
            for _y in range(n_years):
                shock = random.gauss(0.0, inflation_vol)
                cum *= (1.0 + shock / (1.0 + base_inflation))
                path.append(max(0.25, min(4.0, cum)))
            all_infl.append(path)

    base_res = _run_sim_set(all_shocks, start_bal, withdrawals, drift, ages,
                            all_infl=all_infl)

    result = {
        'ok':              True,
        'ages':            ages,
        'n_sims':          n_sims,
        'volatility':      round(volatility * 100, 1),
        'inflation_vol':   round(inflation_vol * 100, 1),
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
            all_infl=all_infl,
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

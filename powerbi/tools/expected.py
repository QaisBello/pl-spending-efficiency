"""What the Power BI report should show, recomputed in pandas and checked against the Python analysis
(data/clean/club_summary.csv and summary.json). Run from powerbi/:  python tools/expected.py"""
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(os.path.dirname(ROOT), "data", "clean")
S = json.load(open(os.path.join(CLEAN, "summary.json")))
cl = pd.read_csv(os.path.join(CLEAN, "club_seasons.csv"))
cs = pd.read_csv(os.path.join(CLEAN, "club_summary.csv")).set_index("club")
e = pd.read_csv(os.path.join(CLEAN, "efficiency.csv"))
t = pd.read_csv(os.path.join(CLEAN, "transfers.csv"))
problems = []


def check(label, got, want, tol):
    ok = abs(got - want) <= tol
    if not ok:
        problems.append(f"{label}: {got} vs {want}")


g = e.groupby("club")
rows = []
for club, x in g:
    r = dict(club=club, titles=int(x.champions.sum()), avg_pts=x.pts.mean(), over=x.over_pts.mean(), over_adj=x.over_pts_adj.mean(),
             cpp=x.squad_cost_gbp_m.sum() / x.pts.sum())
    rows.append(r)
    check(f"{club} titles", r["titles"], cs.titles[club], 0)
    check(f"{club} points a season", round(r["avg_pts"], 1), cs.avg_pts[club], 0.051)
    check(f"{club} above expected", round(r["over"], 2), cs.avg_over_pts[club], 0.0051)
    check(f"{club} above expected (adjusted)", round(r["over_adj"], 2), cs.avg_over_pts_adj[club], 0.0051)
    check(f"{club} cost per point", round(r["cpp"], 3), cs.cost_per_point_gbp_m[club], 0.0005)
c = cl[(cl.club == "Manchester City") & cl.season.between("2009-10", "2017-18")]
cwr = c.wages_gbp_m.sum() / c.revenue_gbp_m.sum()
cwra = c.wages_gbp_m.sum() / (c.revenue_gbp_m - c.owner_funded_sponsorship_gbp_m).sum()
check("City wages to revenue 2009-18", round(100 * cwr, 1), S["city_wage_revenue_2009_18"], 0.051)
check("City wages to revenue 2009-18 without owner money", round(100 * cwra, 1), S["city_wage_revenue_2009_18_adj"], 0.051)
check("Hidden costs total", round(cl.hidden_cost_gbp_m.sum(), 2), S["hidden_cost_total_gbp_m"], 0.006)
wr = cl.groupby("club").apply(lambda x: pd.Series(dict(wr=x.wages_gbp_m.sum() / x.revenue_gbp_m.sum(),
                                                       wra=x.wages_gbp_m.sum() / (x.revenue_gbp_m - x.owner_funded_sponsorship_gbp_m).sum())))
r = pd.DataFrame(rows).sort_values("over", ascending=False)
paid, recv = t[t.direction == "in"].fee_gbp_m.sum(), t[t.direction == "out"].fee_gbp_m.sum()
lines = ["# Expected values", "", "From `tools/expected.py`, checked against the Python analysis (`club_summary.csv`, `summary.json`): "
         f"**{'all agree' if not problems else 'DISAGREEMENTS: ' + '; '.join(problems)}**.", "",
         "## Page 1: clubs", "", "| Club | Titles | Points a season | Above expected | Adjusted | Cost per point |", "|---|---:|---:|---:|---:|---:|"]
lines += [f"| {x.club} | {x.titles} | {x.avg_pts:.1f} | {x.over:+.1f} | {x.over_adj:+.1f} | £{x.cpp:.2f}m |" for x in r.itertuples()]
lines += ["", "## Page 2 cards", "", "| Card | Expected |", "|---|---:|",
          f"| City wages to revenue, 2009-10 to 2017-18 | {cwr:.1%} |", f"| Without owner-funded sponsorship | {cwra:.1%} |",
          f"| Hidden costs found by the verdict | £{cl.hidden_cost_gbp_m.sum():.1f}m |",
          "", "Wages to revenue, all seasons (bottom chart):", "", "| Club | Reported revenue | Without owner money |", "|---|---:|---:|",
          *[f"| {k} | {v.wr:.1%} | {v.wra:.1%} |" for k, v in wr.iterrows()],
          "", "## Page 3 cards (all clubs)", "", "| Card | Expected |", "|---|---:|",
          f"| Fees paid | £{paid:,.1f}m |", f"| Fees received | £{recv:,.1f}m |", f"| Players signed | {(t.direction == 'in').sum():,} |"]
os.makedirs(os.path.join(ROOT, "docs"), exist_ok=True)
open(os.path.join(ROOT, "docs", "expected_values.md"), "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
sys.exit(1 if problems else 0)

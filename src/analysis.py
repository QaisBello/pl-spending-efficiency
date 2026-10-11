"""Did City just outspend everyone, or spend better? Efficiency of the top six, 2008-09 onwards.

Spending rose every year for everyone, so raw pounds are not comparable across seasons. Each club's wage bill is
expressed relative to the top-six average that season (wage index: 1.0 = average, 1.3 = 30% above). Then:

  expected points   a line fitted through every top-six club-season: points against log(wage index).
                    It says how many points a club "should" get for its relative wage bill.
  over-performance  actual points minus expected. Positive = more points than the spending buys on average.
  cost per point    (wages + net transfer spend) / points, in GBP m.

Only seasons with all six wage bills are used (an index against a partial set would be biased).
Wage bills explain most of the gap between clubs in the long run, which is why they are the main measure
of spending here. Transfer spend is shown alongside.

Verdict-adjusted scenario: City's wages are increased by the costs the Independent Commission found were kept off
its accounts (GBP 66.18m over 2009-10 to 2017-18, spread evenly), and the model is refitted. The break-even
figure asks how much more City would have needed to hide, every season, to lose its lead on efficiency.

Writes data/clean/efficiency.csv, data/clean/club_summary.csv and data/clean/summary.json.
"""
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")
RNG = np.random.default_rng(2026)


def fit(df, wage_col):
    """Points against log(wage index) across all club-seasons with a wage figure. Returns the frame with expected points."""
    complete = df.groupby("season")[wage_col].count().eq(df.club.nunique())
    d = df[df.season.isin(complete[complete].index)].copy()        # only seasons with all six wage bills
    d["wage_index"] = d[wage_col] / d.groupby("season")[wage_col].transform("mean")
    x, y = np.log(d.wage_index), d.pts
    slope, intercept = np.polyfit(x, y, 1)
    d["expected_pts"] = intercept + slope * x
    d["over_pts"] = d.pts - d.expected_pts
    r2 = 1 - ((y - d.expected_pts) ** 2).sum() / ((y - y.mean()) ** 2).sum()
    return d, dict(slope=round(slope, 2), intercept=round(intercept, 2), r2=round(r2, 3), n=int(len(d)))


def bootstrap_mean(v, n=5000):
    v = np.asarray(v, float)
    m = RNG.choice(v, size=(n, len(v)), replace=True).mean(axis=1)
    return round(float(np.percentile(m, 2.5)), 2), round(float(np.percentile(m, 97.5)), 2)


def club_summary(d):
    rows = []
    for club, g in d.groupby("club"):
        lo, hi = bootstrap_mean(g.over_pts)
        rows.append(dict(club=club, seasons=len(g), pts=int(g.pts.sum()), titles=int(g.champions.sum()),
                         avg_pts=round(g.pts.mean(), 1), avg_wage_index=round(g.wage_index.mean(), 3),
                         avg_over_pts=round(g.over_pts.mean(), 2), over_pts_ci_low=lo, over_pts_ci_high=hi,
                         total_over_pts=round(g.over_pts.sum(), 1)))
    return pd.DataFrame(rows).sort_values("avg_over_pts", ascending=False)


def main():
    cs = pd.read_csv(os.path.join(CLEAN, "club_seasons.csv"))
    cs["wages_adj_gbp_m"] = cs.wages_12m_gbp_m + cs.hidden_cost_gbp_m

    base, m_base = fit(cs, "wages_12m_gbp_m")
    adj, m_adj = fit(cs, "wages_adj_gbp_m")
    base = base.merge(adj[["club", "season", "wage_index", "expected_pts", "over_pts"]].rename(
        columns={"wage_index": "wage_index_adj", "expected_pts": "expected_pts_adj", "over_pts": "over_pts_adj"}), on=["club", "season"])

    # cost per point, where both wages and transfers are known
    base["squad_cost_gbp_m"] = base.wages_12m_gbp_m + base.net_spend_gbp_m
    base["cost_per_point_gbp_m"] = (base.squad_cost_gbp_m / base.pts).round(3)
    base["wages_per_point_gbp_m"] = (base.wages_12m_gbp_m / base.pts).round(3)
    # wages as a share of revenue, with and without the owner-funded sponsorship
    base["wage_revenue_pct"] = (100 * base.wages_gbp_m / base.revenue_gbp_m).round(1)
    base["wage_revenue_pct_adj"] = (100 * base.wages_gbp_m / (base.revenue_gbp_m - base.owner_funded_sponsorship_gbp_m)).round(1)
    base.round(3).to_csv(os.path.join(CLEAN, "efficiency.csv"), index=False)

    s_base, s_adj = club_summary(base), club_summary(adj)
    s = s_base.merge(s_adj[["club", "avg_over_pts", "over_pts_ci_low", "over_pts_ci_high"]].add_suffix("_adj").rename(columns={"club_adj": "club"}), on="club")
    tr = base[base.squad_cost_gbp_m.notna()].groupby("club").agg(cost=("squad_cost_gbp_m", "sum"), pts=("pts", "sum"),
                                                                   net=("net_spend_gbp_m", "sum"), seasons_cost=("season", "count"))
    s = s.merge((tr.cost / tr.pts).round(3).rename("cost_per_point_gbp_m").reset_index(), on="club") \
         .merge(tr.net.round(0).rename("net_spend_gbp_m").reset_index(), on="club")
    s.to_csv(os.path.join(CLEAN, "club_summary.csv"), index=False)

    # break-even: extra GBP m per season of hidden City wages (over its title-era seasons) that would erase City's lead
    city = "Manchester City"
    runner = s_base[s_base.club != city].avg_over_pts.max()
    def city_lead(extra):
        x = cs.copy()
        x.loc[x.club.eq(city) & x.wages_adj_gbp_m.notna(), "wages_adj_gbp_m"] += extra
        d, _ = fit(x, "wages_adj_gbp_m")
        g = d.groupby("club").over_pts.mean()
        return g[city] - g.drop(city).max()
    lo, hi = 0.0, 1000.0
    if city_lead(0) > 0:
        for _ in range(50):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if city_lead(mid) > 0 else (lo, mid)
    breakeven = round(hi, 1)

    # robustness: refit leaving out one season at a time; does City stay top, and how far does its edge move?
    loso = []
    for season in sorted(base.season.unique()):
        d, _ = fit(cs[cs.season != season], "wages_12m_gbp_m")
        g = d.groupby("club").over_pts.mean().sort_values(ascending=False)
        loso.append(dict(left_out=season, city=round(g[city], 2), city_rank=int(list(g.index).index(city) + 1)))
    loso = pd.DataFrame(loso)
    loso.to_csv(os.path.join(CLEAN, "robustness_leave_one_season_out.csv"), index=False)
    c = cs[cs.club == city]                                   # all seasons, including any left out of the model
    out = dict(
        seasons=[cs.season.min(), cs.season.max()], wage_seasons=sorted(base.season.unique().tolist()),
        model=m_base, model_adj=m_adj,
        clubs=s.to_dict(orient="records"),
        city_rank=int((s.sort_values("avg_over_pts", ascending=False).club.tolist()).index(city) + 1),
        city_rank_adj=int((s.sort_values("avg_over_pts_adj", ascending=False).club.tolist()).index(city) + 1),
        hidden_cost_total_gbp_m=round(float(cs.hidden_cost_gbp_m.sum()), 2),
        hidden_cost_per_season_gbp_m=round(float(cs.hidden_cost_gbp_m.max()), 2),
        breakeven_extra_per_season_gbp_m=breakeven,
        breakeven_vs_hidden=round(breakeven / cs.hidden_cost_gbp_m.max(), 1),
        owner_funded_total_gbp_m=round(float(cs.owner_funded_sponsorship_gbp_m.sum()), 2),
        city_wage_revenue_2009_18=round(100 * c[c.season.between("2009-10", "2017-18")].wages_gbp_m.sum() / c[c.season.between("2009-10", "2017-18")].revenue_gbp_m.sum(), 1),
        city_wage_revenue_2009_18_adj=round(100 * c[c.season.between("2009-10", "2017-18")].wages_gbp_m.sum() / (c[c.season.between("2009-10", "2017-18")].revenue_gbp_m - c[c.season.between("2009-10", "2017-18")].owner_funded_sponsorship_gbp_m).sum(), 1),
        titles={k: int(v) for k, v in base.groupby("club").champions.sum().items()},
        runner_up_avg_over_pts=round(float(runner), 2),
        robustness=dict(city_top_in=int((loso.city_rank == 1).sum()), of=int(len(loso)),
                        city_over_pts_min=float(loso.city.min()), city_over_pts_max=float(loso.city.max())),
    )
    with open(os.path.join(CLEAN, "summary.json"), "w") as f:
        json.dump(out, f, indent=2, default=float)
    print(json.dumps(out, indent=2, default=float))


if __name__ == "__main__":
    main()

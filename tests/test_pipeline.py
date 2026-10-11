"""Checks on the cleaned data and the analysis."""
import json
import os

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLEAN = os.path.join(ROOT, "data", "clean")
read = lambda f: pd.read_csv(os.path.join(CLEAN, f), dtype={"season": str})


def test_every_season_is_a_complete_league():
    t = read("league_tables.csv")
    assert t.groupby("season").size().eq(20).all() and t.played.eq(38).all()
    assert t.season.nunique() == 18


def test_champions_match_the_record():
    t = read("league_tables.csv")
    champs = t[t.position == 1].set_index("season").team.to_dict()
    known = {"2008-09": "Manchester United", "2011-12": "Manchester City", "2015-16": "Leicester City", "2016-17": "Chelsea",
             "2017-18": "Manchester City", "2019-20": "Liverpool", "2024-25": "Liverpool", "2025-26": "Arsenal"}
    for s, c in known.items():
        assert champs[s] == c, s
    assert t[(t.season == "2017-18") & (t.team == "Manchester City")].pts.item() == 100


def test_one_row_per_club_season_with_points():
    cs = read("club_seasons.csv")
    assert len(cs) == 108 and not cs.duplicated(["club", "season"]).any() and cs.pts.notna().all()


def test_wage_figures_all_have_sources_and_no_estimates():
    raw = pd.read_csv(os.path.join(ROOT, "data", "raw", "club_accounts_wages_revenue.csv"))
    assert raw[raw.wages_gbp_m.notna()].source_url.notna().all()
    cs = read("club_seasons.csv")
    assert cs.wages_gbp_m.isna().sum() == raw.wages_gbp_m.isna().sum()      # blanks stay blank


def test_transfer_fees_are_converted_once_and_only_paid_fees_count():
    t = read("transfers.csv")
    assert (t.loc[t.fee_type.isin(["end_of_loan", "loan_no_fee", "free", "unknown"]), "fee_gbp_m"] == 0).all()
    fx = read("fx_gbp_per_eur.csv").set_index("season").gbp_per_eur
    paid = t[t.fee_eur_m > 0]
    assert ((paid.fee_gbp_m - paid.fee_eur_m * paid.season.map(fx)).abs() < 0.01).all()


def test_hidden_costs_only_touch_city_2009_to_2018():
    cs = read("club_seasons.csv")
    hit = cs[cs.hidden_cost_gbp_m > 0]
    assert set(hit.club) == {"Manchester City"} and hit.season.min() == "2009-10" and hit.season.max() == "2017-18"
    assert abs(hit.hidden_cost_gbp_m.sum() - 66.18) < 0.01
    assert abs(cs.owner_funded_sponsorship_gbp_m.sum() - 830.69) < 0.01


def test_model_uses_only_seasons_with_all_six_wage_bills():
    e = read("efficiency.csv")
    assert e.groupby("season").size().eq(6).all()
    assert abs(e.over_pts.sum()) < 1e-6                     # residuals of a least-squares fit sum to zero


def test_city_result_is_robust_to_dropping_any_season():
    s = json.load(open(os.path.join(CLEAN, "summary.json")))
    assert s["robustness"]["city_top_in"] == s["robustness"]["of"]
    assert s["breakeven_extra_per_season_gbp_m"] > s["hidden_cost_per_season_gbp_m"]

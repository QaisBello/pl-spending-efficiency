"""Clean the raw sources (data/raw) into one table per top-six club per season (data/clean).

Sources in data/raw, kept exactly as collected:
  results/*.txt                          every Premier League match 2008-09 to 2025-26 (openfootball, public domain)
  transfermarkt_ewenme_premier-league.csv  every Premier League transfer to 2022-23 (Transfermarkt via github.com/ewenme/transfers), EUR
  transfermarkt_transfers.csv.gz         Transfermarkt player transfers to July 2026 (github.com/dcaribou/transfermarkt-datasets), EUR
  club_accounts_wages_revenue.csv        wage bill and revenue from each club's annual accounts, one source URL per figure, GBP
  fx_daily_usd.csv                       daily USD exchange rates (Federal Reserve H.10, via github.com/datasets/exchange-rates)
  verdict_figures.csv                    amounts from the Independent Commission's decision on Manchester City (Sept 2026)

Every check and fix is written to data/clean/data_quality_log.csv.
"""
import os
import re
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from parse_results import matches  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW, OUT = os.path.join(ROOT, "data", "raw"), os.path.join(ROOT, "data", "clean")
SEASONS = [f"{y}-{(y + 1) % 100:02d}" for y in range(2008, 2026)]
TOP6 = ["Manchester City", "Manchester United", "Liverpool", "Chelsea", "Arsenal", "Tottenham"]
LOG = []


def log(source, check, rows, finding, action):
    LOG.append(dict(source=source, check=check, rows_affected=int(rows), finding=finding, action=action))


def club(name):
    """One name per club: 'Liverpool FC', 'Tottenham Hotspur FC', 'Arsenal' -> 'Liverpool', 'Tottenham', 'Arsenal'."""
    n = re.sub(r"\s+(FC|AFC)$", "", str(name).strip())
    n = re.sub(r"^AFC\s+", "", n)
    return {"Tottenham Hotspur": "Tottenham", "Brighton & Hove Albion": "Brighton", "Wolverhampton Wanderers": "Wolves"}.get(n, n)


# ------------------------------------------------------------------ results -> league tables
def league_tables():
    m = matches(os.path.join(RAW, "results"))
    log("results", "Matches parsed", len(m), f"{len(m)} matches in {m.season.nunique()} seasons (380 each)", "-")
    assert m.groupby("season").size().eq(380).all()
    before = pd.concat([m.home, m.away]).nunique()
    m["home"], m["away"] = m.home.map(club), m.away.map(club)
    log("results", "Club names", before - pd.concat([m.home, m.away]).nunique(),
        "Same club spelt differently across seasons (e.g. 'Liverpool' and 'Liverpool FC')", "Standardised to one name per club")
    side = pd.concat([m.assign(team=m.home, gf=m.hg, ga=m.ag), m.assign(team=m.away, gf=m.ag, ga=m.hg)])
    side["pts"] = 3 * (side.gf > side.ga) + (side.gf == side.ga)
    side["w"], side["d"], side["l"] = side.gf > side.ga, side.gf == side.ga, side.gf < side.ga
    t = side.groupby(["season", "team"]).agg(played=("pts", "size"), won=("w", "sum"), drawn=("d", "sum"), lost=("l", "sum"),
                                             gf=("gf", "sum"), ga=("ga", "sum"), pts=("pts", "sum")).reset_index()
    t["gd"] = t.gf - t.ga
    t = t.sort_values(["season", "pts", "gd", "gf"], ascending=[True, False, False, False])
    t["position"] = t.groupby("season").cumcount() + 1
    assert t.played.eq(38).all() and t.groupby("season").size().eq(20).all()
    m.to_csv(os.path.join(OUT, "matches.csv"), index=False)
    t.to_csv(os.path.join(OUT, "league_tables.csv"), index=False)
    return t


# ------------------------------------------------------------------ exchange rates
def fx_by_season():
    fx = pd.read_csv(os.path.join(RAW, "fx_daily_usd.csv"))
    fx = fx[fx.Country.isin(["Euro", "United Kingdom"])].pivot(index="Date", columns="Country", values="Exchange rate").dropna()
    fx.index = pd.to_datetime(fx.index)
    fx["gbp_per_eur"] = fx["United Kingdom"] / fx["Euro"]          # both quoted per US dollar
    y = fx.index.year - (fx.index.month < 7)                         # a season runs July to June
    fx["season"] = [f"{a}-{(a + 1) % 100:02d}" for a in y]
    s = fx[fx.season.isin(SEASONS)].groupby("season").gbp_per_eur.mean().round(4)
    assert s.between(0.7, 1.0).all() and len(s) == len(SEASONS)
    log("fx", "Exchange rates", len(s), f"GBP per EUR, July-June average of daily rates: {s.min():.3f} to {s.max():.3f}",
        "Transfer fees (EUR) converted to GBP at the rate for their season")
    s.to_frame().reset_index().to_csv(os.path.join(OUT, "fx_gbp_per_eur.csv"), index=False)
    return s


# ------------------------------------------------------------------ transfers
FEE_TYPES = [("end_of_loan", r"^End of loan"), ("loan_no_fee", r"^loan transfer$"), ("free", r"^free transfer$"),
             ("unknown", r"^[-?]$"), ("loan_fee", r"^Loan fee:"), ("fee", r"^€")]


def transfers_ewenme():
    d = pd.read_csv(os.path.join(RAW, "transfermarkt_ewenme_premier-league.csv"))
    d["season"] = d.season.str.replace(r"^(\d{4})/\d{2}(\d{2})$", r"\1-\2", regex=True)
    d = d[d.season.isin(SEASONS)].copy()
    d["club"] = d.club_name.map(club)
    d = d[d.club.isin(TOP6)].copy()
    log("transfers", "Rows read (2008-09 to 2022-23)", len(d), "Top-six transfer rows from the Transfermarkt league history", "-")
    d["fee_type"] = "other"
    for t, pat in reversed(FEE_TYPES):
        d.loc[d.fee.fillna("").str.contains(pat, regex=True), "fee_type"] = t
    assert (d.fee_type != "other").all(), d[d.fee_type == "other"].fee.unique()[:10]
    for t in ("end_of_loan", "loan_no_fee", "free", "unknown"):
        log("transfers", f"Fee type: {t}", (d.fee_type == t).sum(),
            {"end_of_loan": "Player returning from loan, no fee", "loan_no_fee": "Loan with no fee", "free": "Free transfer",
             "unknown": "Fee shown as '-' or '?' (not disclosed)"}[t], "No fee counted")
    log("transfers", "Loan fees", (d.fee_type == "loan_fee").sum(), "Fee paid to borrow a player", "Counted, as Transfermarkt does")
    n = d.duplicated(["club", "player_name", "transfer_movement", "season", "transfer_period", "fee"]).sum()
    d = d.drop_duplicates(["club", "player_name", "transfer_movement", "season", "transfer_period", "fee"])
    log("transfers", "Duplicate transfers", n, "Same player, club, window and fee listed twice", "Kept one")
    d["fee_eur_m"] = d.fee_cleaned.where(d.fee_type.isin(["fee", "loan_fee"])).fillna(0.0)
    d["direction"] = d.transfer_movement.map({"in": "in", "out": "out"})
    return d[["club", "season", "transfer_period", "direction", "player_name", "club_involved_name", "fee", "fee_type", "fee_eur_m"]] \
        .rename(columns={"transfer_period": "window", "player_name": "player", "club_involved_name": "other_club", "fee": "fee_text"})


# Transfermarkt club ids for the top six first teams (youth and reserve sides have their own ids and are excluded)
TM_IDS = {281: "Manchester City", 985: "Manchester United", 31: "Liverpool", 631: "Chelsea", 11: "Arsenal", 148: "Tottenham"}


def transfers_dcaribou():
    path = os.path.join(RAW, "transfermarkt_transfers.csv.gz")
    if not os.path.exists(path):
        log("transfers", "2023-24 to 2025-26 transfers", 0, "transfermarkt_transfers.csv.gz not in data/raw", "Seasons left without transfer data")
        return None
    d = pd.read_csv(path)
    d["season"] = d.transfer_season.str.replace(r"^(\d{2})/(\d{2})$", r"20\1-\2", regex=True)
    rows = []
    for direction, col, other in (("in", "to_club_id", "from_club_id"), ("out", "from_club_id", "to_club_id")):
        x = d.assign(club=d[col].map(TM_IDS), direction=direction,
                     other_club=d["from_club_name" if direction == "in" else "to_club_name"]).dropna(subset=["club"])
        x = x[x[other].map(TM_IDS) != x.club]           # moves between a club's own first team and academy are not transfers
        rows.append(x)
    d = pd.concat(rows)
    d = d[d.season.isin(SEASONS)]
    d["fee_eur_m"] = (d.transfer_fee.fillna(0) / 1e6)
    d["fee_type"] = d.transfer_fee.map(lambda v: "unknown" if pd.isna(v) else ("fee" if v > 0 else "free_or_loan"))
    d["window"] = pd.to_datetime(d.transfer_date).dt.month.map(lambda m: "Winter" if m in (1, 2) else "Summer")
    log("transfers", "Rows read (dcaribou)", len(d), "Top-six transfers from Transfermarkt player histories", "-")
    n = d.duplicated(["club", "player_id", "transfer_date", "direction"]).sum()
    d = d.drop_duplicates(["club", "player_id", "transfer_date", "direction"])
    log("transfers", "Duplicate transfers (dcaribou)", n, "Same player and date listed twice", "Kept one")
    return d.rename(columns={"player_name": "player"})[
        ["club", "season", "window", "direction", "player", "other_club", "fee_type", "fee_eur_m"]].assign(fee_text="")


def transfers(fx):
    a = transfers_ewenme()
    b = transfers_dcaribou()
    if b is not None:
        # 2022-23 is in both: compare, then use the league history up to 2022-23 and player histories after
        sa = a[a.season == "2022-23"].groupby(["club", "direction"]).fee_eur_m.sum()
        sb = b[b.season == "2022-23"].groupby(["club", "direction"]).fee_eur_m.sum()
        gap = (sa - sb).abs()
        log("transfers", "Cross-check 2022-23", int((gap / sa.clip(lower=1) > 0.05).sum()),
            f"The two Transfermarkt extracts agree within 5% on {int((gap / sa.clip(lower=1) <= 0.05).sum())} of {len(gap)} club-direction totals (max gap EUR {gap.max():.1f}m)",
            "League history used to 2022-23, player histories from 2023-24")
        b = b[b.season > "2022-23"]
        a = pd.concat([a.assign(source="ewenme"), b.assign(source="dcaribou")])
    else:
        a = a.assign(source="ewenme")
    a["fee_gbp_m"] = (a.fee_eur_m * a.season.map(fx)).round(3)
    a.to_csv(os.path.join(OUT, "transfers.csv"), index=False)
    s = a.pivot_table(index=["club", "season"], columns="direction", values="fee_gbp_m", aggfunc="sum", fill_value=0)
    s = s.rename(columns={"in": "transfer_spend_gbp_m", "out": "transfer_income_gbp_m"}).reset_index()
    return s


# ------------------------------------------------------------------ wages and revenue from annual accounts
def accounts():
    w = pd.read_csv(os.path.join(RAW, "club_accounts_wages_revenue.csv"))
    w["club"] = w.club.map(club)
    assert set(w.club) == set(TOP6) and set(w.season) == set(SEASONS)
    log("accounts", "Figures collected", w.wages_gbp_m.notna().sum(),
        f"Wage bills found for {w.wages_gbp_m.notna().sum()} of {len(w)} club-seasons; every figure has a source URL", "-")
    missing = w[w.wages_gbp_m.isna()]
    log("accounts", "Wage bill not found", len(missing), "; ".join(f"{c} {s}" for c, s in zip(missing.club, missing.season)),
        "Left blank: no estimates. Those seasons are left out of wage-based measures")
    assert w[w.wages_gbp_m.notna()].source_url.notna().all()
    notes = w.notes.fillna("")
    w["partial_year"] = notes.str.contains(r"13-month|10-month|13 month|10 month", case=False)
    w["low_confidence"] = notes.str.contains("low confidence", case=False)
    log("accounts", "Accounting periods not 12 months", w.partial_year.sum(),
        "City 2016-17 (13 months) and Liverpool 2011-12 (10 months), as published", "Flagged; wages scaled to 12 months for per-season measures")
    w["months"] = 12
    w.loc[notes.str.contains(r"13[- ]month", case=False), "months"] = 13
    w.loc[notes.str.contains(r"10[- ]month", case=False), "months"] = 10
    w["wages_12m_gbp_m"] = (w.wages_gbp_m * 12 / w.months).round(1)
    log("accounts", "Low-confidence figures", w.low_confidence.sum(), "Figure from a secondary source only (see notes)", "Kept and flagged")
    return w[["club", "season", "fy_end", "months", "wages_gbp_m", "wages_12m_gbp_m", "revenue_gbp_m", "partial_year", "low_confidence", "source_url"]]


# ------------------------------------------------------------------ verdict
def verdict():
    v = pd.read_csv(os.path.join(RAW, "verdict_figures.csv"))
    hidden = v[v.type == "hidden_cost"].amount_gbp_m.sum()
    tagged = v[(v.type == "overstated_revenue") & v.item.str.startswith("Abu Dhabi")].set_index("season").amount_gbp_m
    log("verdict", "Hidden costs", (v.type == "hidden_cost").sum(), f"Costs kept off City's accounts 2009-10 to 2017-18: GBP {hidden:.2f}m",
        "Added back to City's wages in the verdict-adjusted scenario")
    log("verdict", "Owner-funded sponsorship", len(tagged), f"Sponsorship income actually paid by the owner: GBP {tagged.sum():.2f}m",
        "Removed from City's revenue in the verdict-adjusted scenario")
    return hidden, tagged


def main():
    os.makedirs(OUT, exist_ok=True)
    t = league_tables()
    fx = fx_by_season()
    tr = transfers(fx)
    acc = accounts()
    hidden, tagged = verdict()

    cs = pd.DataFrame([(c, s) for c in TOP6 for s in SEASONS], columns=["club", "season"])
    cs = cs.merge(t.rename(columns={"team": "club"})[["club", "season", "position", "pts", "won", "drawn", "lost", "gf", "ga", "gd"]],
                  on=["club", "season"], how="left")
    assert cs.pts.notna().all(), "every top-six club played every Premier League season"
    cs["champions"] = cs.position.eq(1)
    cs = cs.merge(acc, on=["club", "season"], how="left").merge(tr, on=["club", "season"], how="left")
    cs["net_spend_gbp_m"] = (cs.transfer_spend_gbp_m - cs.transfer_income_gbp_m).round(2)

    # the verdict: hidden costs spread evenly over the nine seasons; owner-funded sponsorship removed from revenue
    yrs = [s for s in SEASONS if "2009-10" <= s <= "2017-18"]
    city = cs.club.eq("Manchester City")
    cs["hidden_cost_gbp_m"] = 0.0
    cs.loc[city & cs.season.isin(yrs), "hidden_cost_gbp_m"] = round(hidden / len(yrs), 3)
    cs["owner_funded_sponsorship_gbp_m"] = 0.0
    cs.loc[city, "owner_funded_sponsorship_gbp_m"] = cs.loc[city, "season"].map(tagged).fillna(0.0)
    cs.to_csv(os.path.join(OUT, "club_seasons.csv"), index=False)
    log("output", "Club-seasons", len(cs), f"{len(TOP6)} clubs x {len(SEASONS)} seasons", "Written to club_seasons.csv")
    pd.DataFrame(LOG).to_csv(os.path.join(OUT, "data_quality_log.csv"), index=False)
    print(pd.DataFrame(LOG).to_string())


if __name__ == "__main__":
    main()

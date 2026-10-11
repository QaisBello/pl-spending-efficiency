"""Power BI version of "Spent more, or spent better?" (Premier League top-six spending efficiency). Run from powerbi/:

    python tools/spec.py        # writes PL_Spending.pbip and its folders
    python tools/validate.py    # schema and reference checks
    python tools/expected.py    # what the visuals should show, checked against data/clean/summary.json and club_summary.csv

The regression (expected points from the wage index) and the bootstrap confidence intervals come from the Python analysis
and are loaded as columns; DAX aggregates them and builds the money measures (cost per point, wages to revenue with and
without owner-funded sponsorship).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pbikit import C, M, build, card, color, lit, series_colors, slicer, text_box, visual  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NAME = "PL_Spending"
CITY, GREY, INK, ORANGE = "#6CABDD", "#9AA3A0", "#13201B", "#C2410C"
GBPM = '£#,0.0"m"'

SEASON_ORDER = '''
            #"Season Order" = Table.AddColumn(#"Filtered Rows", "Season Order", each Number.FromText(Text.Start([season], 4)), Int64.Type)
        '''
TABLES = {
    "Efficiency": dict(
        file="efficiency.csv",
        description="One row per club per season where all six wage bills are known (15 seasons x 6 clubs = 90). Expected points come "
                    "from the Python regression of points on the wage index (wage bill / top-six average that season).",
        columns=[("club", "string", {}), ("season", "string", {}), ("position", "int64", {"summarizeBy": "none"}), ("pts", "int64", {}),
                 ("won", "int64", {"isHidden": True}), ("drawn", "int64", {"isHidden": True}), ("lost", "int64", {"isHidden": True}),
                 ("gf", "int64", {"isHidden": True}), ("ga", "int64", {"isHidden": True}), ("gd", "int64", {"isHidden": True}),
                 ("champions", "boolean", {}), ("fy_end", "string", {"isHidden": True}), ("months", "int64", {"isHidden": True}),
                 ("wages_gbp_m", "double", {"isHidden": True}), ("wages_12m_gbp_m", "double", {"isHidden": True}),
                 ("revenue_gbp_m", "double", {"isHidden": True}), ("partial_year", "boolean", {"isHidden": True}),
                 ("low_confidence", "boolean", {"isHidden": True}), ("source_url", "string", {"isHidden": True}),
                 ("transfer_spend_gbp_m", "double", {"isHidden": True}), ("transfer_income_gbp_m", "double", {"isHidden": True}),
                 ("net_spend_gbp_m", "double", {"isHidden": True}), ("hidden_cost_gbp_m", "double", {"isHidden": True}),
                 ("owner_funded_sponsorship_gbp_m", "double", {"isHidden": True}), ("wages_adj_gbp_m", "double", {"isHidden": True}),
                 ("wage_index", "double", {"formatString": "0.00"}), ("expected_pts", "double", {"isHidden": True}),
                 ("over_pts", "double", {"isHidden": True}), ("wage_index_adj", "double", {"isHidden": True}),
                 ("expected_pts_adj", "double", {"isHidden": True}), ("over_pts_adj", "double", {"isHidden": True}),
                 ("squad_cost_gbp_m", "double", {"isHidden": True}), ("cost_per_point_gbp_m", "double", {"isHidden": True}),
                 ("wages_per_point_gbp_m", "double", {"isHidden": True}), ("wage_revenue_pct", "double", {"isHidden": True}),
                 ("wage_revenue_pct_adj", "double", {"isHidden": True})],
        added=[("Club Season", "string", {})],
        m_extra='''
            #"Club Season" = Table.AddColumn(#"Filtered Rows", "Club Season", each [club] & " " & [season], type text)
        ''', m_last="Club Season"),
    "Clubs": dict(
        file="club_summary.csv",
        description="One row per club: totals, titles and points above expected with 95% bootstrap confidence intervals (reported and "
                    "verdict-adjusted).",
        columns=[("club", "string", {"isKey": True}), ("seasons", "int64", {"isHidden": True}), ("pts", "int64", {"isHidden": True}),
                 ("titles", "int64", {"isHidden": True}), ("avg_pts", "double", {"isHidden": True}),
                 ("avg_wage_index", "double", {"isHidden": True}), ("avg_over_pts", "double", {"isHidden": True}),
                 ("over_pts_ci_low", "double", {"formatString": "+0.0;-0.0;0.0"}), ("over_pts_ci_high", "double", {"formatString": "+0.0;-0.0;0.0"}),
                 ("total_over_pts", "double", {"isHidden": True}), ("avg_over_pts_adj", "double", {"isHidden": True}),
                 ("over_pts_ci_low_adj", "double", {"formatString": "+0.0;-0.0;0.0"}),
                 ("over_pts_ci_high_adj", "double", {"formatString": "+0.0;-0.0;0.0"}),
                 ("cost_per_point_gbp_m", "double", {"isHidden": True}), ("net_spend_gbp_m", "double", {"isHidden": True})]),
    "Seasons": dict(
        file="league_tables.csv",
        description="Premier League seasons 2008-09 to 2025-26 (distinct seasons from the league tables).",
        columns=[("season", "string", {"isKey": True, "sortByColumn": "Season Order"})],
        m='''
let
    Source = Csv.Document(Web.Contents(BaseUrl, [RelativePath = "league_tables.csv"]), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Seasons = Table.Distinct(Table.SelectColumns(Promoted, {"season"})),
    Typed = Table.TransformColumnTypes(Seasons, {{"season", type text}}),
    Result = Table.AddColumn(Typed, "Season Order", each Number.FromText(Text.Start([season], 4)), Int64.Type)
in
    Result'''),
    "Transfers": dict(
        file="transfers.csv",
        description="Every recorded transfer in and out for the six clubs, 2008-09 to 2025-26 (Transfermarkt via ewenme and dcaribou), "
                    "fees converted to pounds at the daily rate.",
        columns=[("club", "string", {}), ("season", "string", {}), ("window", "string", {}), ("direction", "string", {}),
                 ("player", "string", {}), ("other_club", "string", {}), ("fee_text", "string", {"isHidden": True}),
                 ("fee_type", "string", {}), ("fee_eur_m", "double", {"isHidden": True}), ("source", "string", {"isHidden": True}),
                 ("fee_gbp_m", "double", {"formatString": GBPM})]),
}
TABLES["Club Seasons"] = dict(
    file="club_seasons.csv",
    description="Every club and season, 2008-09 to 2025-26, with wages and revenue where the accounts were found (8 of 108 wage bills "
                "are missing and are not estimated). Used for the money measures, which do not need the regression.",
    columns=[(c, ty, {"isHidden": True}) for c, ty in [
        ("club", "string"), ("season", "string"), ("position", "int64"), ("pts", "int64"), ("won", "int64"), ("drawn", "int64"),
        ("lost", "int64"), ("gf", "int64"), ("ga", "int64"), ("gd", "int64"), ("champions", "boolean"), ("fy_end", "string"),
        ("months", "int64"), ("wages_gbp_m", "double"), ("wages_12m_gbp_m", "double"), ("revenue_gbp_m", "double"),
        ("partial_year", "boolean"), ("low_confidence", "boolean"), ("source_url", "string"), ("transfer_spend_gbp_m", "double"),
        ("transfer_income_gbp_m", "double"), ("net_spend_gbp_m", "double"), ("hidden_cost_gbp_m", "double"),
        ("owner_funded_sponsorship_gbp_m", "double")]])
TABLES["Seasons"]["columns"].append(("Season Order", "int64", {"isHidden": True}))

RELATIONSHIPS = [
    (("Efficiency", "club"), ("Clubs", "club"), {}),
    (("Transfers", "club"), ("Clubs", "club"), {}),
    (("Efficiency", "season"), ("Seasons", "season"), {}),
    (("Transfers", "season"), ("Seasons", "season"), {}),
    (("Club Seasons", "club"), ("Clubs", "club"), {}),
    (("Club Seasons", "season"), ("Seasons", "season"), {}),
]

E = "Efficiency"
MEASURES = [
    ("Points", E, "Results", "#,0", "SUM ( Efficiency[pts] )", "League points."),
    ("Titles", E, "Results", "#,0", "CALCULATE ( COUNTROWS ( Efficiency ), Efficiency[champions] == TRUE () )", "League titles."),
    ("Average Points", E, "Results", "0.0", "AVERAGE ( Efficiency[pts] )", "Points per season."),
    ("Expected Points", E, "Model", "#,0", "SUM ( Efficiency[expected_pts] )", "Points the wage index predicts (Python regression)."),
    ("Points Above Expected", E, "Model", "+#,0.0;-#,0.0;0", "SUM ( Efficiency[over_pts] )", "Actual minus expected points."),
    ("Points Above Expected per Season", E, "Model", "+0.0;-0.0;0.0", "AVERAGE ( Efficiency[over_pts] )",
     "Average points a season above (or below) what the wage bill predicts."),
    ("Points Above Expected per Season (Adjusted)", E, "Model", "+0.0;-0.0;0.0", "AVERAGE ( Efficiency[over_pts_adj] )",
     "The same, with the costs the 114-charge verdict found hidden added to City's wage bill."),
    ("Average Wage Index", E, "Model", "0.00", "AVERAGE ( Efficiency[wage_index] )", "Wage bill against the top-six average that season (1.00 = average)."),
    ("Wage Bill", "Club Seasons", "Money", GBPM, "SUM ( 'Club Seasons'[wages_gbp_m] )", "Wages as reported in the accounts."),
    ("Revenue", "Club Seasons", "Money", GBPM, "SUM ( 'Club Seasons'[revenue_gbp_m] )", "Revenue as reported."),
    ("Owner-Funded Sponsorship", "Club Seasons", "Money", GBPM, "SUM ( 'Club Seasons'[owner_funded_sponsorship_gbp_m] )",
     "Sponsorship the verdict found was funded by the owner (City only)."),
    ("Wages to Revenue", "Club Seasons", "Money", "0.0%", "DIVIDE ( [Wage Bill], [Revenue] )", "Wage bill as a share of reported revenue."),
    ("Wages to Revenue (Without Owner Money)", "Club Seasons", "Money", "0.0%", "DIVIDE ( [Wage Bill], [Revenue] - [Owner-Funded Sponsorship] )",
     "Wage bill as a share of revenue with owner-funded sponsorship taken out."),
    ("Net Transfer Spend", E, "Money", GBPM, "SUM ( Efficiency[net_spend_gbp_m] )", "Fees paid minus fees received."),
    ("Squad Cost", E, "Money", GBPM, "SUM ( Efficiency[squad_cost_gbp_m] )", "Wages (12-month basis) plus net transfer spend."),
    ("Cost per Point", E, "Money", '£#,0.00"m"', "DIVIDE ( [Squad Cost], [Points] )", "Squad cost per league point."),
    ("Hidden Costs", "Club Seasons", "Money", GBPM, "SUM ( 'Club Seasons'[hidden_cost_gbp_m] )", "Costs the verdict found kept off City's books."),
    ("City Wages to Revenue 2009-18", "Club Seasons", "Money", "0.0%",
     """CALCULATE ( [Wages to Revenue], REMOVEFILTERS ( 'Club Seasons' ), REMOVEFILTERS ( Seasons ), REMOVEFILTERS ( Clubs ), 'Club Seasons'[club] = "Manchester City", 'Club Seasons'[season] >= "2009-10", 'Club Seasons'[season] <= "2017-18" )""",
     "City's wages to reported revenue across the seasons the charges cover."),
    ("City Wages to Revenue 2009-18 (Without Owner Money)", "Club Seasons", "Money", "0.0%",
     """CALCULATE ( [Wages to Revenue (Without Owner Money)], REMOVEFILTERS ( 'Club Seasons' ), REMOVEFILTERS ( Seasons ), REMOVEFILTERS ( Clubs ), 'Club Seasons'[club] = "Manchester City", 'Club Seasons'[season] >= "2009-10", 'Club Seasons'[season] <= "2017-18" )""",
     "The same without the owner-funded sponsorship."),
    ("Transfer Fees Paid", "Transfers", "Transfers", GBPM, 'CALCULATE ( SUM ( Transfers[fee_gbp_m] ), Transfers[direction] = "in" )', "Fees paid for incoming players."),
    ("Transfer Fees Received", "Transfers", "Transfers", GBPM, 'CALCULATE ( SUM ( Transfers[fee_gbp_m] ), Transfers[direction] = "out" )', "Fees received."),
    ("Signings", "Transfers", "Transfers", "#,0", 'CALCULATE ( COUNTROWS ( Transfers ), Transfers[direction] = "in" )', "Players signed (including free and loan)."),
]

p1, p2, p3 = "value", "money", "transfers"
wr, wra = M("Club Seasons", "Wages to Revenue", "Reported revenue"), M("Club Seasons", "Wages to Revenue (Without Owner Money)", "Without owner money")
PAGES = [
    (p1, "Who got value", [
        text_box(p1, "title", 24, 12, 1232, 52, "Spent more, or spent better? Points against the wage bill, Premier League top six", 18),
        visual(p1, "scatter", "scatterChart", 24, 76, 700, 400,
               {"Category": [C(E, "Club Season", "Club and season")], "Series": [C(E, "club", "Club")],
                "X": [M(E, "Average Wage Index", "Wage index")], "Y": [M(E, "Points", "Points")]},
               "Each dot is one club in one season: wage index (1.00 = top-six average) against points", z=10),
        visual(p1, "bar", "clusteredBarChart", 740, 76, 516, 400,
               {"Category": [C(E, "club", "Club")], "Y": [M(E, "Points Above Expected per Season", "Points above expected a season")]},
               "Points above what the wage bill predicts, per season", objects={"dataPoint": [{"properties": {"fill": color(CITY)}}],
                                                                                 "labels": [{"properties": {"show": lit(True)}}]},
               sort=(M(E, "Points Above Expected per Season"), "Descending"), z=11),
        visual(p1, "table", "tableEx", 24, 488, 1232, 220,
               {"Values": [C("Clubs", "club", "Club"), M(E, "Titles"), M(E, "Average Points", "Points a season"),
                           M(E, "Points Above Expected per Season", "Above expected"), C("Clubs", "over_pts_ci_low", "95% CI low"),
                           C("Clubs", "over_pts_ci_high", "95% CI high"), M(E, "Points Above Expected per Season (Adjusted)", "Adjusted for hidden costs"),
                           M(E, "Cost per Point", "Cost per point")]},
               "Clubs: 15 complete seasons each (bootstrap 95% confidence intervals)", sort=(M(E, "Points Above Expected per Season"), "Descending"), z=12),
    ]),
    (p2, "Money", [
        text_box(p2, "title", 24, 12, 860, 52, "What it cost: squad cost per point, and who paid the wages", 18),
        slicer(p2, "club", 900, 8, 356, 64, C("Clubs", "club", "Club"), None),
        card(p2, "cwr", 24, 76, 400, 96, M("Club Seasons", "City Wages to Revenue 2009-18", "City wages to revenue, 2009-10 to 2017-18")),
        card(p2, "cwra", 436, 76, 400, 96, M("Club Seasons", "City Wages to Revenue 2009-18 (Without Owner Money)", "Without owner-funded sponsorship")),
        card(p2, "hidden", 848, 76, 408, 96, M("Club Seasons", "Hidden Costs", "Hidden costs found by the verdict")),
        visual(p2, "cost", "lineChart", 24, 184, 820, 300, {"Category": [C("Seasons", "season", "Season")], "Y": [M(E, "Squad Cost", "Squad cost")],
                                                            "Series": [C(E, "club", "Club")]},
               "Squad cost (wages + net transfer spend) by season", sort=(C("Seasons", "season"), "Ascending"), z=10),
        visual(p2, "cpp", "clusteredBarChart", 860, 184, 396, 300, {"Category": [C(E, "club", "Club")], "Y": [M(E, "Cost per Point", "Cost per point")]},
               "Cost per point", objects={"dataPoint": [{"properties": {"fill": color(INK)}}], "labels": [{"properties": {"show": lit(True)}}]},
               sort=(M(E, "Cost per Point"), "Ascending"), z=11),
        visual(p2, "wages", "clusteredColumnChart", 24, 496, 1232, 212, {"Category": [C("Clubs", "club", "Club")], "Y": [wr, wra]},
               "Wages as a share of revenue, all seasons with accounts, with and without owner-funded sponsorship",
               objects={"dataPoint": series_colors([wr, wra], [GREY, CITY]), "labels": [{"properties": {"show": lit(True)}}]}, z=12),
    ]),
    (p3, "Transfers", [
        text_box(p3, "title", 24, 12, 860, 52, "Every transfer, 2008-09 to 2025-26", 18),
        slicer(p3, "club", 900, 8, 356, 64, C("Clubs", "club", "Club"), None),
        card(p3, "paid", 24, 76, 400, 96, M("Transfers", "Transfer Fees Paid", "Fees paid")),
        card(p3, "recv", 436, 76, 400, 96, M("Transfers", "Transfer Fees Received", "Fees received")),
        card(p3, "n", 848, 76, 408, 96, M("Transfers", "Signings", "Players signed")),
        visual(p3, "season", "clusteredColumnChart", 24, 184, 620, 524,
               {"Category": [C("Seasons", "season", "Season")], "Y": [M("Transfers", "Transfer Fees Paid", "Fees paid")]},
               "Fees paid by season", objects={"dataPoint": [{"properties": {"fill": color(CITY)}}]}, sort=(C("Seasons", "season"), "Ascending"), z=10),
        visual(p3, "list", "tableEx", 660, 184, 596, 524,
               {"Values": [C("Transfers", "player", "Player"), C("Transfers", "club", "Club"), C("Transfers", "season", "Season"),
                           C("Transfers", "direction", "In/out"), C("Transfers", "other_club", "From/to"), C("Transfers", "fee_gbp_m", "Fee")]},
               "Transfers, largest fees first", sort=(C("Transfers", "fee_gbp_m"), "Descending"), z=11),
    ]),
]

SPEC = dict(name=NAME, root=ROOT, tables=TABLES, measures=MEASURES, relationships=RELATIONSHIPS, pages=PAGES,
            base_url="https://raw.githubusercontent.com/QaisBello/pl-spending-efficiency/main/data/clean/",
            base_desc="Folder of cleaned CSVs from this repo (data/clean). Point it at a local folder or another branch to test.")

if __name__ == "__main__":
    build(SPEC)

"""Tests for the four marketing extracts behind the Tableau attribution, ROI, CPA and budget dashboard
(sql/tableau/attribution_by_channel, channel_performance, campaign_performance, budget_recommendations).
The real extract SQL runs in DuckDB on small hand-built mart tables, so the joins, the labels and the budget rules are checked
on numbers worked out by hand."""

import re
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

duckdb = pytest.importorskip("duckdb")
sqlglot = pytest.importorskip("sqlglot")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import export_for_tableau as ex  # noqa: E402

MARTS = yaml.safe_load((ROOT / "dbt" / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))
COLUMNS = {m["name"]: {c["name"] for c in m["columns"]} for m in MARTS["models"]}
MODELS = ["first_touch", "last_touch", "linear", "time_decay", "ga4_session"]
FOUR = MODELS[:4]


def sql_of(name: str) -> str:
    return (ex.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")


def run(name: str, **tables: pd.DataFrame) -> pd.DataFrame:
    """Run an extract in DuckDB: `da02-customer360.marts.x` becomes the registered frame x."""
    text = re.sub(r"`da02-customer360\.marts\.(\w+)`", r"\1", sql_of(name))
    con = duckdb.connect()
    for table, df in tables.items():
        con.register(table, df)
    return con.execute(sqlglot.transpile(text, read="bigquery", write="duckdb")[0]).df()


# ----------------------------------------------------------------------------- hand-built marts
# campaign key -> (channel, spend, {model: (orders, revenue)})
CAMPAIGNS = {
    # every view pays back at least $1.50 per $1 and has enough orders: Increase
    "Display|a|x|up": ("Display", 100.0, {m: (10, 200.0) for m in MODELS}),
    # every view is below $1 per $1: Reduce
    "Paid Social|b|x|down": ("Paid Social", 100.0, {m: (8, 60.0) for m in MODELS}),
    # the views disagree (ga4_session low, models high): Hold
    "Paid Search|c|x|mixed": ("Paid Search", 100.0, {**{m: (9, 200.0) for m in FOUR}, "ga4_session": (9, 40.0)}),
    # high ROAS but only 2 orders: Not enough data
    "Affiliate|d|x|thin": ("Affiliate", 50.0, {m: (2, 400.0) for m in MODELS}),
    # huge ROAS from an assumed cost: forced to Hold
    "Email|e|x|mail": ("Email", 1.0, {m: (50, 900.0) for m in MODELS}),
}


def campaign_roi() -> pd.DataFrame:
    rows = []
    for key, (channel, spend, by_model) in CAMPAIGNS.items():
        for model in MODELS:
            orders, revenue = by_model[model]
            rows.append(dict(model=model, campaign_key=key, channel=channel, source=key.split("|")[1], medium="x",
                             campaign=key.split("|")[3], first_spend_date=pd.Timestamp("2020-11-01").date(),
                             last_spend_date=pd.Timestamp("2020-12-01").date(), days_with_spend=30, impressions=1000,
                             clicks=100, spend_usd=spend, cost_per_click=spend / 100, attributed_orders=float(orders),
                             attributed_revenue_usd=revenue, profit_usd=revenue - spend, roas=revenue / spend,
                             roi=(revenue - spend) / spend, cpa_usd=spend / orders, revenue_per_click=revenue / 100))
    return pd.DataFrame(rows)


def campaign_cpa(roi: pd.DataFrame) -> pd.DataFrame:
    c = roi[["model", "campaign_key", "channel", "source", "medium", "campaign", "spend_usd", "clicks",
             "attributed_orders", "attributed_revenue_usd", "cpa_usd"]].copy()
    c["new_customers"] = (c["attributed_orders"] / 2).where(c["model"] != "ga4_session")
    c["repeat_orders"] = c["attributed_orders"] - c["new_customers"]
    c["cac_usd"] = c["spend_usd"] / c["new_customers"]
    c["avg_order_value_usd"] = c["attributed_revenue_usd"] / c["attributed_orders"]
    c["cpa_to_aov"] = c["cpa_usd"] / c["avg_order_value_usd"]
    c["has_enough_orders"] = c["attributed_orders"] >= 5
    c["cpa_rank"] = 1
    c["cpa_vs_channel"] = 1.0
    return c


def channel_roi(roi: pd.DataFrame) -> pd.DataFrame:
    g = roi.groupby(["model", "channel"], as_index=False).agg(
        campaigns=("campaign_key", "count"), campaign_days=("days_with_spend", "sum"), impressions=("impressions", "sum"),
        clicks=("clicks", "sum"), spend_usd=("spend_usd", "sum"), attributed_orders=("attributed_orders", "sum"),
        attributed_revenue_usd=("attributed_revenue_usd", "sum"))
    g["cost_per_click"] = g["spend_usd"] / g["clicks"]
    g["profit_usd"] = g["attributed_revenue_usd"] - g["spend_usd"]
    g["roas"] = g["attributed_revenue_usd"] / g["spend_usd"]
    g["roi"] = g["profit_usd"] / g["spend_usd"]
    g["cpa_usd"] = g["spend_usd"] / g["attributed_orders"]
    g["revenue_per_click"] = g["attributed_revenue_usd"] / g["clicks"]
    return g


def channel_cpa(cpa: pd.DataFrame) -> pd.DataFrame:
    g = cpa.groupby(["model", "channel"], as_index=False).agg(
        campaigns=("campaign_key", "count"), spend_usd=("spend_usd", "sum"), clicks=("clicks", "sum"),
        attributed_orders=("attributed_orders", "sum"), new_customers=("new_customers", lambda x: x.sum(min_count=1)),
        attributed_revenue_usd=("attributed_revenue_usd", "sum"))
    g["repeat_orders"] = g["attributed_orders"] - g["new_customers"]
    g["cpa_usd"] = g["spend_usd"] / g["attributed_orders"]
    g["cac_usd"] = g["spend_usd"] / g["new_customers"]
    g["avg_order_value_usd"] = g["attributed_revenue_usd"] / g["attributed_orders"]
    g["cpa_to_aov"] = g["cpa_usd"] / g["avg_order_value_usd"]
    g["has_enough_orders"] = g["attributed_orders"] >= 5
    g["cpa_rank"] = 1
    return g


def by_channel() -> pd.DataFrame:
    rows = []
    for model, k in zip(FOUR, [100, 80, 90, 85]):
        for ch, share in [("Paid Search", 0.2), ("Organic Search", 0.5), ("Direct / Unknown", 0.3)]:
            rows.append(dict(model=model, credited_channel=ch, attributed_orders=share * 10, attributed_revenue_usd=share * k,
                             share_of_orders=share, share_of_revenue=share))
    return pd.DataFrame(rows)


def comparison() -> pd.DataFrame:
    return pd.DataFrame([
        dict(credited_channel="Paid Search", is_known_source=True, is_paid_channel=True, revenue_spread_usd=4.0,
             revenue_spread_pct=0.2, introducing_gap_usd=3.0, role="Introduces"),
        dict(credited_channel="Organic Search", is_known_source=True, is_paid_channel=False, revenue_spread_usd=10.0,
             revenue_spread_pct=0.2, introducing_gap_usd=-6.0, role="Closes"),
        dict(credited_channel="Direct / Unknown", is_known_source=False, is_paid_channel=False, revenue_spread_usd=6.0,
             revenue_spread_pct=0.2, introducing_gap_usd=0.0, role="No known source")])


@pytest.fixture(scope="module")
def marts():
    roi = campaign_roi()
    cpa = campaign_cpa(roi)
    return dict(fct_campaign_roi=roi, fct_campaign_cpa=cpa, fct_channel_roi=channel_roi(roi), fct_channel_cpa=channel_cpa(cpa),
                fct_attribution_by_channel=by_channel(), fct_attribution_model_comparison=comparison())


# ----------------------------------------------------------------------------- shape of the files
@pytest.mark.parametrize("name", ex.ROI_EXPORTS)
def test_every_file_exists_parses_and_has_unique_columns(name):
    tree = sqlglot.parse_one(sql_of(name), read="bigquery")
    cols = [e.alias_or_name for e in tree.expressions]
    assert cols and len(cols) == len(set(cols))
    assert "da02-customer360.marts." in sql_of(name)
    assert not {"email", "full_name", "email_sha256", "customer_id"} & set(cols), "no personal fields"


@pytest.mark.parametrize("name", ex.ROI_EXPORTS)
def test_every_table_read_is_a_documented_mart(name):
    tables = set(re.findall(r"`da02-customer360\.marts\.(\w+)`", sql_of(name)))
    assert tables and tables <= set(COLUMNS), f"not in _marts.yml: {sorted(tables - set(COLUMNS))}"


@pytest.mark.parametrize("name", ["attribution_by_channel", "channel_performance", "campaign_performance"])
def test_qualified_columns_exist_in_their_mart(name):
    tree = sqlglot.parse_one(sql_of(name), read="bigquery")
    alias = {t.alias_or_name: t.name for t in tree.find_all(sqlglot.exp.Table)}
    for col in tree.find_all(sqlglot.exp.Column):
        if col.table:
            assert col.name in COLUMNS[alias[col.table]], f"{alias[col.table]}.{col.name} does not exist"


def test_the_exporter_lists_every_file():
    assert ex.ALL_EXPORTS == ex.EXPORTS + ex.ROI_EXPORTS and len(ex.ALL_EXPORTS) == 7
    assert len(set(ex.ALL_EXPORTS)) == 7


# ----------------------------------------------------------------------------- attribution_by_channel
def test_attribution_extract_has_one_row_per_model_and_channel(marts):
    out = run("attribution_by_channel", **marts)
    assert len(out) == len(marts["fct_attribution_by_channel"]) == 12
    assert not out.duplicated(["model", "credited_channel"]).any()
    assert set(out["model_label"]) == {"First touch", "Last touch", "Linear", "Time decay"}
    assert out.groupby("model")["model_order"].nunique().eq(1).all() and sorted(out["model_order"].unique()) == [1, 2, 3, 4]


def test_attribution_extract_carries_the_channel_role(marts):
    out = run("attribution_by_channel", **marts)
    roles = out.drop_duplicates("credited_channel").set_index("credited_channel")["role"].to_dict()
    assert roles == {"Paid Search": "Introduces", "Organic Search": "Closes", "Direct / Unknown": "No known source"}
    ps = out[out["credited_channel"] == "Paid Search"].iloc[0]
    assert bool(ps["is_paid_channel"]) and ps["introducing_gap_usd"] == pytest.approx(3.0)


def test_attribution_extract_revenue_matches_the_mart(marts):
    out = run("attribution_by_channel", **marts)
    assert out["attributed_revenue_usd"].sum() == pytest.approx(marts["fct_attribution_by_channel"]["attributed_revenue_usd"].sum())


# ----------------------------------------------------------------------------- channel and campaign performance
def test_channel_performance_joins_roi_and_cpa_without_fan_out(marts):
    out = run("channel_performance", **marts)
    assert len(out) == len(marts["fct_channel_roi"]) == 25
    assert not out.duplicated(["model", "channel"]).any()
    assert set(out["model_label"]) == {"First touch", "Last touch", "Linear", "Time decay", "GA4 session"}
    d = out[(out["model"] == "linear") & (out["channel"] == "Display")].iloc[0]
    assert d["roas"] == pytest.approx(2.0) and d["cpa_usd"] == pytest.approx(10.0) and d["cac_usd"] == pytest.approx(20.0)
    assert d["new_customers"] == pytest.approx(5.0) and d["repeat_orders"] == pytest.approx(5.0)


def test_channel_performance_ga4_session_has_no_new_customers(marts):
    out = run("channel_performance", **marts)
    g = out[out["model"] == "ga4_session"]
    assert len(g) == 5 and g["cac_usd"].isna().all()


def test_campaign_performance_joins_roi_and_cpa_without_fan_out(marts):
    out = run("campaign_performance", **marts)
    assert len(out) == len(marts["fct_campaign_roi"]) == 25
    assert not out.duplicated(["model", "campaign_key"]).any()
    m = out[(out["model"] == "first_touch") & (out["campaign_key"] == "Paid Social|b|x|down")].iloc[0]
    assert m["roas"] == pytest.approx(0.6) and m["roi"] == pytest.approx(-0.4) and m["profit_usd"] == pytest.approx(-40.0)
    assert m["spend_usd"] == pytest.approx(100.0) and m["cpa_to_aov"] == pytest.approx((100 / 8) / (60 / 8))


def test_performance_extracts_agree_on_spend(marts):
    ch = run("channel_performance", **marts)
    ca = run("campaign_performance", **marts)
    for model in MODELS:
        assert ch[ch["model"] == model]["spend_usd"].sum() == pytest.approx(ca[ca["model"] == model]["spend_usd"].sum())
        assert ch[ch["model"] == model]["attributed_revenue_usd"].sum() == pytest.approx(
            ca[ca["model"] == model]["attributed_revenue_usd"].sum())


# ----------------------------------------------------------------------------- budget_recommendations
@pytest.fixture(scope="module")
def budget(marts):
    return run("budget_recommendations", **marts)


def pick(budget, level, item):
    return budget[(budget["level"] == level) & (budget["item"] == item)].iloc[0]


def test_budget_has_one_row_per_channel_and_campaign(budget):
    assert len(budget) == 5 + 5
    assert not budget.duplicated(["level", "item"]).any()
    assert sorted(budget["level"].unique()) == ["Campaign", "Channel"]


@pytest.mark.parametrize("campaign,want", [
    ("Display|a|x|up", "Increase"),
    ("Paid Social|b|x|down", "Reduce"),
    ("Paid Search|c|x|mixed", "Hold"),
    ("Affiliate|d|x|thin", "Not enough data"),
    ("Email|e|x|mail", "Hold"),
])
def test_budget_rules(budget, campaign, want):
    assert pick(budget, "Campaign", campaign)["recommendation"] == want


def test_channel_rows_follow_the_same_rules(budget):
    want = {"Display": "Increase", "Paid Social": "Reduce", "Paid Search": "Hold", "Affiliate": "Not enough data", "Email": "Hold"}
    for channel, rec in want.items():
        assert pick(budget, "Channel", channel)["recommendation"] == rec


def test_budget_suggested_change_and_proposed_spend(budget):
    up, down, hold = (pick(budget, "Campaign", k) for k in ["Display|a|x|up", "Paid Social|b|x|down", "Paid Search|c|x|mixed"])
    assert up["suggested_change_pct"] == pytest.approx(0.20) and up["proposed_spend_usd"] == pytest.approx(120.0)
    assert down["suggested_change_pct"] == pytest.approx(-0.30) and down["proposed_spend_usd"] == pytest.approx(70.0)
    assert hold["suggested_change_pct"] == 0 and hold["proposed_spend_usd"] == pytest.approx(100.0)
    thin = pick(budget, "Campaign", "Affiliate|d|x|thin")
    assert thin["suggested_change_pct"] == 0 and thin["proposed_spend_usd"] == pytest.approx(50.0)


def test_budget_roas_range_covers_all_five_views(budget):
    m = pick(budget, "Campaign", "Paid Search|c|x|mixed")
    assert m["roas_low"] == pytest.approx(0.4) and m["roas_high"] == pytest.approx(2.0)
    assert m["roas_models_avg"] == pytest.approx(2.0)                 # the four models only, without ga4_session
    assert m["orders_models_avg"] == pytest.approx(9.0) and m["revenue_models_avg"] == pytest.approx(200.0)


def test_budget_spend_ties_out_across_levels(budget, marts):
    by = budget.groupby("level")["spend_usd"].sum()
    assert by["Channel"] == pytest.approx(by["Campaign"]) == pytest.approx(marts["fct_campaign_roi"].query("model == 'linear'")["spend_usd"].sum())
    assert budget.groupby("level")["spend_share"].sum().round(9).eq(1.0).all()


def test_budget_every_row_has_a_reason_and_a_known_recommendation(budget):
    assert set(budget["recommendation"]) <= {"Increase", "Hold", "Reduce", "Not enough data"}
    assert budget["reason"].notna().all() and (budget["reason"].str.len() > 10).all()
    assert budget["recommendation_order"].between(1, 4).all()
    order = budget.drop_duplicates("recommendation").set_index("recommendation")["recommendation_order"].to_dict()
    assert order == {k: v for k, v in {"Increase": 1, "Hold": 2, "Reduce": 3, "Not enough data": 4}.items() if k in order}


def test_documented_thresholds_match_the_sql():
    sql = sql_of("budget_recommendations")
    doc = (ROOT / "docs" / "budget_recommendations.md").read_text(encoding="utf-8")
    m = re.search(r"select (\d+) as min_orders, ([\d.]+) as increase_roas, ([\d.]+) as reduce_roas, ([\d.]+) as increase_pct, (-[\d.]+) as reduce_pct", sql)
    assert m, "the rules CTE must keep its one-line form"
    orders, up, down, inc, red = m.groups()
    assert f"fewer than {orders} attributed orders" in doc
    assert f"at least {up}" in doc and f"below {int(float(down))}" in doc
    assert f"+{int(float(inc) * 100)}%" in doc and f"-{int(abs(float(red)) * 100)}%" in doc

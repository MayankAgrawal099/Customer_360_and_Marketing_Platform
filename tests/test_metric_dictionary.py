"""The metric dictionary must stay in step with the marts: every `table.column` it names exists and is documented,
and the headline metrics of each area are present."""

import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
DOC = (ROOT / "docs" / "metric_dictionary.md").read_text(encoding="utf-8")
MARTS = yaml.safe_load((ROOT / "dbt" / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))
COLUMNS = {m["name"]: {c["name"] for c in m.get("columns", [])} for m in MARTS["models"]}


def metric_rows():
    rows = []
    for line in DOC.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) == 4 and re.fullmatch(r"`[a-z0-9_]+\.[a-z0-9_]+`", cells[3]):
            rows.append(cells)
    return rows


ROWS = metric_rows()


def test_the_dictionary_has_rows():
    assert len(ROWS) >= 50


@pytest.mark.parametrize("metric,meaning,formula,where", ROWS, ids=[r[0] + ":" + r[3] for r in ROWS])
def test_every_named_column_exists(metric, meaning, formula, where):
    table, column = where.strip("`").split(".")
    assert table in COLUMNS, f"{table} is not a documented mart"
    assert column in COLUMNS[table], f"{table}.{column} does not exist"
    assert meaning and formula


def test_no_metric_is_defined_twice_for_the_same_column():
    wheres = [r[3] for r in ROWS]
    assert len(wheres) == len(set(wheres))


@pytest.mark.parametrize("heading", ["Customer value", "RFM", "Customer lifetime value", "Attribution", "Campaign ROI",
                                     "Cost per acquisition"])
def test_each_area_has_a_section(heading):
    assert re.search(rf"^## {re.escape(heading)}", DOC, re.M)


@pytest.mark.parametrize("table,columns", [
    ("fct_customer_rfm", ["recency_days", "frequency", "monetary_usd", "r_score", "f_score", "m_score"]),
    ("fct_customer_clv", ["clv_12m_usd", "predicted_revenue_90d_usd", "predicted_revenue_12m_usd"]),
    ("fct_attribution_by_channel", ["attributed_orders", "attributed_revenue_usd", "share_of_revenue"]),
    ("fct_campaign_roi", ["roas", "roi", "profit_usd", "spend_usd"]),
    ("fct_campaign_cpa", ["cpa_usd", "cac_usd", "cpa_to_aov"]),
])
def test_headline_metrics_are_covered(table, columns):
    for col in columns:
        assert f"`{table}.{col}`" in DOC


def test_formulas_match_the_model_parameters():
    clv = (ROOT / "dbt" / "models" / "marts" / "fct_customer_clv.sql").read_text(encoding="utf-8")
    att = (ROOT / "dbt" / "models" / "marts" / "fct_attribution_credits.sql").read_text(encoding="utf-8")
    assert "90 as prior_days" in clv and "3 as prior_orders" in clv and "365 as long_horizon_days" in clv
    assert "7.0 as half_life_days" in att
    assert "+ 90 x population rate" in DOC and "3 x population AOV" in DOC and "/ 7)" in DOC

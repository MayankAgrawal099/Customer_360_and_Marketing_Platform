"""Tests for the cost-per-acquisition tables (fct_campaign_cpa, fct_channel_cpa), their dbt tests and the reconciliation
test. The real SQL runs in DuckDB on the ROI test world; orders get an is_first_order flag."""

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

pytest.importorskip("duckdb")
sqlglot = pytest.importorskip("sqlglot")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests import test_dbt_attribution as ta  # noqa: E402
from tests import test_dbt_roi as tr  # noqa: E402
from tests.test_dbt_sessions import DBT, SINGULAR, run  # noqa: E402

CPA_SQL = (DBT / "models" / "marts" / "fct_campaign_cpa.sql").read_text(encoding="utf-8")
CHN_SQL = (DBT / "models" / "marts" / "fct_channel_cpa.sql").read_text(encoding="utf-8")
GOOGLE, BING = tr.GOOGLE, tr.BING


def orders() -> pd.DataFrame:
    o = ta.orders()
    o["is_first_order"] = o["order_id"] != "O2"          # O2 is C1's second order
    return o


@pytest.fixture(scope="module")
def cr():
    tp = run(ta.TP_SQL, fct_orders=ta.orders(), stg_identity__links=ta.links(), fct_sessions=ta.sessions())
    c = run(ta.CR_SQL, fct_orders=ta.orders(), int_conversion_touchpoints=tp)
    c["ad_campaign_key"] = c["ad_campaign_key"].where(c["ad_campaign_key"].isna(), GOOGLE)
    return c


@pytest.fixture(scope="module")
def roi(cr):
    return run(tr.ROI_SQL, stg_ad_spend=tr.ad_spend(), fct_attribution_credits=cr, fct_sessions=tr.sessions())


@pytest.fixture(scope="module")
def cpa(roi, cr):
    return run(CPA_SQL, fct_campaign_roi=roi, fct_attribution_credits=cr, fct_orders=orders())


@pytest.fixture(scope="module")
def chn(cpa):
    return run(CHN_SQL, fct_campaign_cpa=cpa)


def row(df, model, key):
    return df[(df["model"] == model) & (df["campaign_key"] == key)].iloc[0]


def test_same_rows_and_spend_as_the_roi_table(cpa, roi):
    assert len(cpa) == len(roi)
    assert cpa.groupby("model")["spend_usd"].sum().round(2).eq(60.0).all()


def test_cpa_is_spend_over_orders(cpa):
    g = row(cpa, "ga4_session", GOOGLE)
    assert g["attributed_orders"] == 2 and g["cpa_usd"] == pytest.approx(25.0)
    assert g["avg_order_value_usd"] == pytest.approx(75.0)
    assert g["cpa_to_aov"] == pytest.approx(25 / 75)


def test_new_customers_count_first_orders_only(cpa):
    g = row(cpa, "first_touch", GOOGLE)
    assert g["attributed_orders"] == 3                    # O1, O2, O5 all start with the d1.1 / d5.1 paid sessions
    assert g["new_customers"] == 2                        # O2 is a repeat order
    assert g["repeat_orders"] == 1
    assert g["cac_usd"] == pytest.approx(50.0 / 2)
    assert g["cpa_usd"] == pytest.approx(50.0 / 3)


def test_ga4_session_has_no_new_customers(cpa):
    g = cpa[cpa["model"] == "ga4_session"]
    assert g["new_customers"].isna().all() and g["cac_usd"].isna().all()


def test_campaign_without_orders_has_no_cpa_or_cac(cpa):
    for m in ["first_touch", "last_touch", "linear", "time_decay"]:
        b = row(cpa, m, BING)
        assert b["attributed_orders"] == 0 and b["new_customers"] == 0
        assert pd.isna(b["cpa_usd"]) and pd.isna(b["cac_usd"])


def test_ranking_only_for_campaigns_with_enough_orders(cpa):
    assert cpa["has_enough_orders"].eq(cpa["attributed_orders"] >= 5).all()
    assert cpa.loc[~cpa["has_enough_orders"], "cpa_rank"].isna().all()


def test_ranking_orders_by_cpa(roi, cr):
    r = roi.copy()
    r.loc[(r["model"] == "linear") & (r["campaign_key"] == GOOGLE), ["attributed_orders", "attributed_revenue_usd"]] = [10, 500.0]
    r.loc[(r["model"] == "linear") & (r["campaign_key"] == BING), ["attributed_orders", "attributed_revenue_usd"]] = [5, 100.0]
    r["cpa_usd"] = r["spend_usd"] / r["attributed_orders"].where(r["attributed_orders"] > 0)
    out = run(CPA_SQL, fct_campaign_roi=r, fct_attribution_credits=cr, fct_orders=orders())
    lin = out[out["model"] == "linear"].set_index("campaign_key")
    assert lin.loc[GOOGLE, "cpa_rank"] == 2 and lin.loc[BING, "cpa_rank"] == 1        # 5.0 vs 2.0 per order


def test_cpa_vs_channel_is_one_when_a_channel_has_one_campaign(roi, cr):
    r = roi[roi["campaign_key"] == GOOGLE]
    out = run(CPA_SQL, fct_campaign_roi=r, fct_attribution_credits=cr, fct_orders=orders())
    ok = out[out["cpa_usd"].notna()]
    assert ok["cpa_vs_channel"].eq(1.0).all()


def test_channel_table_rolls_up(cpa, chn):
    assert len(chn) == 5
    f = chn[chn["model"] == "first_touch"].iloc[0]
    assert (f["campaigns"], f["spend_usd"], f["attributed_orders"], f["new_customers"]) == (2, 60.0, 3, 2)
    assert f["cpa_usd"] == pytest.approx(20.0) and f["cac_usd"] == pytest.approx(30.0)


def test_reconciliation_passes_on_good_data(roi, cr, cpa, chn):
    t = dict(fct_campaign_roi=roi, fct_attribution_credits=cr, fct_orders=orders(), fct_campaign_cpa=cpa, fct_channel_cpa=chn)
    assert run(SINGULAR["assert_cpa_ties_out"], **t).empty


def test_reconciliation_catches_breaks(roi, cr, cpa, chn):
    t = dict(fct_campaign_roi=roi, fct_attribution_credits=cr, fct_orders=orders(), fct_campaign_cpa=cpa, fct_channel_cpa=chn)
    name = "assert_cpa_ties_out"
    assert not run(SINGULAR[name], **{**t, "fct_campaign_cpa": cpa[cpa["campaign_key"] != BING]}).empty
    bad = cpa.copy()
    bad.loc[(bad["model"] == "first_touch") & (bad["campaign_key"] == GOOGLE), "new_customers"] = 3
    assert not run(SINGULAR[name], **{**t, "fct_campaign_cpa": bad}).empty
    bad = cpa.copy()
    bad.loc[(bad["model"] == "linear") & (bad["campaign_key"] == GOOGLE), "cpa_usd"] += 1
    assert not run(SINGULAR[name], **{**t, "fct_campaign_cpa": bad}).empty
    bad = chn.copy()
    bad.loc[bad["model"] == "last_touch", "spend_usd"] += 1
    assert not run(SINGULAR[name], **{**t, "fct_channel_cpa": bad}).empty


def test_yaml_documents_every_output_column(cpa, chn):
    spec = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))
    by = {m["name"]: m for m in spec["models"]}
    for name, df in (("fct_campaign_cpa", cpa), ("fct_channel_cpa", chn)):
        assert [c["name"] for c in by[name]["columns"]] == list(df.columns)
        assert all(c["description"] for c in by[name]["columns"])

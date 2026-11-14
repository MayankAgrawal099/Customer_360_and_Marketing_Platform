"""Tests for the campaign ROI tables (fct_campaign_roi, fct_channel_roi), their dbt tests and the reconciliation test.
The real SQL runs in DuckDB on the attribution test world plus a small ad-spend table."""

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
from tests.test_dbt_sessions import DBT, SINGULAR, run  # noqa: E402
from tests.test_dbt_staging import output_columns  # noqa: E402

ROI_SQL = (DBT / "models" / "marts" / "fct_campaign_roi.sql").read_text(encoding="utf-8")
CHN_SQL = (DBT / "models" / "marts" / "fct_channel_roi.sql").read_text(encoding="utf-8")
GOOGLE = "Paid Search|google|cpc|c"
BING = "Paid Search|bing|cpc|c"
MODELS = ["first_touch", "last_touch", "linear", "time_decay", "ga4_session"]


def ad_spend() -> pd.DataFrame:
    def a(day, key, clicks, spend):
        ch, src, med, camp = key.split("|")
        return dict(ad_spend_id=f"{day}{key}", campaign_key=key, date=pd.Timestamp(day).date(), channel=ch, source=src,
                    medium=med, campaign=camp, impressions=clicks * 20, clicks=clicks, spend_usd=spend)
    return pd.DataFrame([a("2020-11-01", GOOGLE, 10, 20.0), a("2020-11-02", GOOGLE, 10, 30.0),
                         a("2020-11-03", BING, 5, 10.0)])


def sessions() -> pd.DataFrame:
    s = ta.sessions()
    s["ad_campaign_key"] = s["ad_campaign_key"].where(s["ad_campaign_key"].isna(), GOOGLE)
    s["valid_purchases"] = 0
    s["revenue_usd"] = 0.0
    s.loc[s["session_key"] == "d1.1", ["valid_purchases", "revenue_usd"]] = [1, 70.0]
    s.loc[s["session_key"] == "d5.1", ["valid_purchases", "revenue_usd"]] = [1, 80.0]
    return s


@pytest.fixture(scope="module")
def cr():
    tp = run(ta.TP_SQL, fct_orders=ta.orders(), stg_identity__links=ta.links(), fct_sessions=ta.sessions())
    c = run(ta.CR_SQL, fct_orders=ta.orders(), int_conversion_touchpoints=tp)
    c["ad_campaign_key"] = c["ad_campaign_key"].where(c["ad_campaign_key"].isna(), GOOGLE)
    return c


@pytest.fixture(scope="module")
def roi(cr):
    return run(ROI_SQL, stg_ad_spend=ad_spend(), fct_attribution_credits=cr, fct_sessions=sessions())


@pytest.fixture(scope="module")
def chn(roi):
    return run(CHN_SQL, fct_campaign_roi=roi)


def row(df, model, key):
    return df[(df["model"] == model) & (df["campaign_key"] == key)].iloc[0]


def test_one_row_per_model_and_campaign(roi):
    assert len(roi) == 2 * len(MODELS)
    assert sorted(roi["model"].unique()) == sorted(MODELS)
    assert not roi.duplicated(["model", "campaign_key"]).any()


def test_spend_is_the_same_under_every_model(roi):
    assert roi.groupby("model")["spend_usd"].sum().round(2).eq(60.0).all()
    g = row(roi, "linear", GOOGLE)
    assert (g["spend_usd"], g["clicks"], g["days_with_spend"]) == (50.0, 20, 2)
    assert g["cost_per_click"] == pytest.approx(2.5)


def test_ga4_session_basis_uses_the_sessions_own_purchases(roi):
    g = row(roi, "ga4_session", GOOGLE)
    assert (g["attributed_orders"], g["attributed_revenue_usd"]) == (2, 150.0)
    assert g["roas"] == pytest.approx(3.0)
    assert g["roi"] == pytest.approx(2.0)
    assert g["cpa_usd"] == pytest.approx(25.0)
    assert g["profit_usd"] == pytest.approx(100.0)


def test_campaign_without_revenue_is_kept_with_zeros_and_no_cpa(roi):
    for m in MODELS:
        b = row(roi, m, BING)
        assert b["attributed_revenue_usd"] == 0 and b["attributed_orders"] == 0
        assert b["roas"] == 0 and b["roi"] == pytest.approx(-1.0)
        assert pd.isna(b["cpa_usd"])


def test_credit_models_match_the_credits_table(roi, cr):
    for m in MODELS[:4]:
        c = cr[(cr["model"] == m) & cr["ad_campaign_key"].notna()]
        g = row(roi, m, GOOGLE)
        assert g["attributed_orders"] == pytest.approx(c["credit"].sum())
        assert g["attributed_revenue_usd"] == pytest.approx(c["credited_revenue_usd"].sum())
        assert g["roas"] == pytest.approx(g["attributed_revenue_usd"] / 50.0)


def test_channel_table_rolls_up_the_campaigns(roi, chn):
    assert len(chn) == len(MODELS)
    g = chn[chn["model"] == "ga4_session"].iloc[0]
    assert (g["campaigns"], g["spend_usd"], g["clicks"], g["attributed_revenue_usd"]) == (2, 60.0, 25, 150.0)
    assert g["roas"] == pytest.approx(2.5)
    assert g["cpa_usd"] == pytest.approx(30.0)


def test_reconciliation_passes_on_good_data(cr, roi, chn):
    t = dict(stg_ad_spend=ad_spend(), fct_attribution_credits=cr, fct_sessions=sessions(), fct_campaign_roi=roi,
             fct_channel_roi=chn)
    assert run(SINGULAR["assert_campaign_roi_ties_out"], **t).empty


def test_reconciliation_catches_lost_spend_and_revenue(cr, roi, chn):
    t = dict(stg_ad_spend=ad_spend(), fct_attribution_credits=cr, fct_sessions=sessions(), fct_campaign_roi=roi,
             fct_channel_roi=chn)
    lost = roi[roi["campaign_key"] != BING]
    assert not run(SINGULAR["assert_campaign_roi_ties_out"], **{**t, "fct_campaign_roi": lost}).empty
    bad = roi.copy()
    bad.loc[(bad["model"] == "linear") & (bad["campaign_key"] == GOOGLE), "attributed_revenue_usd"] += 5
    assert not run(SINGULAR["assert_campaign_roi_ties_out"], **{**t, "fct_campaign_roi": bad}).empty
    bad_ch = chn.copy()
    bad_ch.loc[bad_ch["model"] == "first_touch", "spend_usd"] += 1
    assert not run(SINGULAR["assert_campaign_roi_ties_out"], **{**t, "fct_channel_roi": bad_ch}).empty


def test_yaml_documents_every_output_column(roi, chn):
    spec = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))
    by = {m["name"]: m for m in spec["models"]}
    for name, df in (("fct_campaign_roi", roi), ("fct_channel_roi", chn)):
        assert [c["name"] for c in by[name]["columns"]] == list(df.columns)
        assert all(c["description"] for c in by[name]["columns"])

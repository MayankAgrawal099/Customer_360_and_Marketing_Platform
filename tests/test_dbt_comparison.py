"""Tests for the model-comparison tables (fct_attribution_model_comparison, fct_attribution_checks), their dbt tests and
the report script. The real SQL runs in DuckDB on the same small attribution world as test_dbt_attribution."""

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

pytest.importorskip("duckdb")
sqlglot = pytest.importorskip("sqlglot")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import attribution_report as rep  # noqa: E402
from tests import test_dbt_attribution as ta  # noqa: E402
from tests.test_dbt_sessions import DBT, SINGULAR, render, run  # noqa: E402
from tests.test_dbt_staging import output_columns  # noqa: E402

CMP_SQL = (DBT / "models" / "marts" / "fct_attribution_model_comparison.sql").read_text(encoding="utf-8")
CHK_SQL = (DBT / "models" / "marts" / "fct_attribution_checks.sql").read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def world():
    tp = run(ta.TP_SQL, fct_orders=ta.orders(), stg_identity__links=ta.links(), fct_sessions=ta.sessions())
    cr = run(ta.CR_SQL, fct_orders=ta.orders(), int_conversion_touchpoints=tp)
    by = run(ta.CH_SQL, fct_attribution_credits=cr)
    return tp, cr, by


def profile():
    o = ta.orders()
    return pd.DataFrame(dict(customer_id=o["customer_id"], net_revenue_usd=o["net_revenue_usd"]))


def checks_for(cr, by, prof=None):
    return run(CHK_SQL, fct_orders=ta.orders(), dim_customers=profile() if prof is None else prof,
               fct_attribution_credits=cr, fct_attribution_by_channel=by)


@pytest.fixture(scope="module")
def cmp_(world):
    return run(CMP_SQL, fct_attribution_by_channel=world[2]).set_index("credited_channel")


@pytest.fixture(scope="module")
def checks(world):
    return checks_for(world[1], world[2])


# ----------------------------------------------------------------------------- the comparison
def test_one_row_per_channel_and_flags(cmp_):
    assert sorted(cmp_.index) == sorted(["Paid Search", "Organic Search", "Referral", "Display", "Direct / Unknown",
                                         "No Touchpoint"])
    assert cmp_["is_known_source"].to_dict() == {"Paid Search": True, "Organic Search": True, "Referral": True,
                                                 "Display": True, "Direct / Unknown": False, "No Touchpoint": False}
    assert cmp_["is_paid_channel"].to_dict() == {"Paid Search": True, "Organic Search": False, "Referral": False,
                                                 "Display": True, "Direct / Unknown": False, "No Touchpoint": False}


def test_revenue_under_each_model(cmp_, world):
    r = cmp_.loc["Paid Search"]
    assert (r["revenue_first_touch"], r["revenue_last_touch"], r["revenue_linear"]) == (230.0, 80.0, pytest.approx(155.0))
    cr = world[1]
    td = cr[(cr["model"] == "time_decay") & (cr["credited_channel"] == "Paid Search")]["credited_revenue_usd"].sum()
    assert r["revenue_time_decay"] == pytest.approx(td) and 80.0 < td < 230.0
    assert r["orders_first_touch"] == 3 and r["orders_last_touch"] == 1 and r["orders_linear"] == pytest.approx(2.0)


def test_totals_and_shares_are_the_same_for_every_model(cmp_):
    for m in rep.MODELS:
        assert cmp_[f"revenue_{m}"].sum() == pytest.approx(325.0)
        assert cmp_[f"share_{m}"].sum() == pytest.approx(1.0)
        assert cmp_[f"orders_{m}"].sum() == pytest.approx(6.0)


def test_spread_and_gap(cmp_):
    r = cmp_.loc["Paid Search"]
    assert r["revenue_min"] == 80.0 and r["revenue_max"] == 230.0 and r["revenue_spread_usd"] == 150.0
    assert r["introducing_gap_usd"] == 150.0
    assert r["revenue_spread_pct"] == pytest.approx(150.0 / r["revenue_first_touch"] * (230.0 / (sum(r[f"revenue_{m}"] for m in rep.MODELS) / 4)))


def test_roles(cmp_):
    assert cmp_["role"].to_dict() == {"Paid Search": "Introduces", "Referral": "Introduces", "Organic Search": "Closes",
                                      "Display": "Closes", "Direct / Unknown": "No known source",
                                      "No Touchpoint": "No known source"}


def test_the_orders_without_a_known_source_are_identical_under_every_model(cmp_):
    for ch in ("Direct / Unknown", "No Touchpoint"):
        r = cmp_.loc[ch]
        assert r["revenue_spread_usd"] == 0 and r["revenue_first_touch"] == r["revenue_time_decay"]


# ----------------------------------------------------------------------------- the checks
def test_all_checks_pass_on_good_data_and_there_are_30(checks):
    assert checks["passed"].all() and len(checks) == 30
    assert checks.groupby("check_name").size().to_dict()["credited_revenue_equals_net_revenue"] == 4
    assert {"four_models_present", "orders_revenue_equals_customer_profile",
            "same_revenue_under_all_models: Direct / Unknown", "same_revenue_under_all_models: No Touchpoint"} <= set(checks["check_name"])


def test_checks_catch_credit_that_does_not_add_up(world):
    tp, cr, by = world
    broken = cr.copy()
    broken.loc[(broken["conversion_id"] == "O1") & (broken["model"] == "linear") & (broken["touchpoint_session_key"] == "d1.1"), "credit"] = 0.9
    broken["credited_revenue_usd"] = broken["credit"] * broken["revenue_usd"]
    bad = checks_for(broken, run(ta.CH_SQL, fct_attribution_credits=broken))
    failed = set(bad.loc[~bad["passed"], "check_name"])
    assert {"every_order_has_one_unit_of_credit", "credited_revenue_equals_net_revenue"} <= failed
    assert set(bad.loc[~bad["passed"], "model"]) == {"linear"}


def test_checks_catch_a_channel_table_that_drifted_and_a_profile_mismatch(world):
    tp, cr, by = world
    drift = by.copy()
    drift.loc[0, "attributed_revenue_usd"] += 5
    assert "channel_table_revenue_equals_net_revenue" in set(checks_for(cr, drift).query("not passed")["check_name"])
    prof = profile()
    prof.loc[0, "net_revenue_usd"] += 1
    assert "orders_revenue_equals_customer_profile" in set(checks_for(cr, by, prof).query("not passed")["check_name"])


def test_checks_catch_models_that_disagree_on_orders_without_a_source(world):
    tp, cr, by = world
    broken = cr.copy()
    m = (broken["conversion_id"] == "O4") & (broken["model"] == "last_touch")
    broken.loc[m, "credited_channel"] = "Direct / Unknown"
    bad = checks_for(broken, run(ta.CH_SQL, fct_attribution_credits=broken))
    assert any(n.startswith("same_revenue_under_all_models") for n in bad.loc[~bad["passed"], "check_name"])


# ----------------------------------------------------------------------------- singular tests and schema
def test_singular_check_test_passes_and_catches_failures(world, checks):
    t = "assert_attribution_checks_all_pass"
    assert run(SINGULAR[t], fct_attribution_checks=checks).empty
    broken = checks.copy()
    broken.loc[0, "passed"] = False
    assert not run(SINGULAR[t], fct_attribution_checks=broken).empty
    assert not run(SINGULAR[t], fct_attribution_checks=checks.head(5)).empty        # cannot pass by recording too little


def test_keys_test_covers_the_new_composite_key(world, checks, cmp_):
    tp, cr, by = world
    t = "assert_attribution_keys_are_unique"
    good = dict(int_conversion_touchpoints=tp, fct_attribution_credits=cr, fct_attribution_by_channel=by,
                fct_attribution_checks=checks,
                fct_campaign_roi=pd.DataFrame(dict(model=["linear"], campaign_key=["k"])),
                fct_channel_roi=pd.DataFrame(dict(model=["linear"], channel=["Paid Search"])))
    assert run(SINGULAR[t], **good).empty
    out = run(SINGULAR[t], **{**good, "fct_attribution_checks": pd.concat([checks, checks.iloc[[0]]])})
    assert list(out["model"]) == ["fct_attribution_checks"]


@pytest.mark.parametrize("model,sql", [("fct_attribution_model_comparison", CMP_SQL), ("fct_attribution_checks", CHK_SQL)])
def test_models_return_exactly_the_documented_columns(model, sql):
    doc = next(m for m in yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))["models"]
               if m["name"] == model)
    got = output_columns(sqlglot.parse_one(render(sql), read="bigquery"))
    want = [c["name"] for c in doc["columns"]]
    assert sorted(got) == sorted(want), set(got) ^ set(want)
    assert all(c.get("description") for c in doc["columns"])


# ----------------------------------------------------------------------------- the report
def test_report_states_the_numbers_it_computes(cmp_, checks):
    text, nums = rep.build_report(cmp_.reset_index(), checks, "2026-11-14")
    assert "ALL CHECKS PASSED" in text and "30 of 30 checks passed" in text
    assert nums["total_revenue_by_model"]["linear"] == pytest.approx(325.0)
    assert nums["revenue_without_known_source"] == pytest.approx(70.0) and nums["share_without_known_source"] == pytest.approx(70 / 325)
    assert nums["introduces"] == ["Paid Search", "Referral"] and nums["closes"] == ["Display", "Organic Search"]
    assert "## Net revenue by channel" in text and "**Total**" in text and "$325" in text
    assert "has no known source and is credited identically by all four models" in text


def test_report_flags_failed_checks(cmp_, checks):
    bad = checks.copy()
    bad.loc[bad["check_name"] == "four_models_present", "passed"] = False
    text, nums = rep.build_report(cmp_.reset_index(), bad, "2026-11-14")
    assert "CHECKS FAILED" in text and "`four_models_present`" in text and nums["checks_passed"] == 29


def test_cli_returns_1_without_credentials(monkeypatch, tmp_path, capsys):
    import types

    fake = types.SimpleNamespace(Client=lambda project: (_ for _ in ()).throw(RuntimeError("no credentials")),
                                 QueryJobConfig=lambda **k: None)
    monkeypatch.setitem(sys.modules, "google.cloud.bigquery", fake)
    import google.cloud
    monkeypatch.setattr(google.cloud, "bigquery", fake, raising=False)
    assert rep.main(["--report", str(tmp_path / "r.md"), "--json", str(tmp_path / "r.json")]) == 1
    assert "gcloud auth application-default login" in capsys.readouterr().out

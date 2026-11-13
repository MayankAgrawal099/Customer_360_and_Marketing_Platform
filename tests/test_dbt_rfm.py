"""Tests for the RFM mart (fct_customer_rfm) and its dbt tests, run in DuckDB on hand-built buyers."""

import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

pytest.importorskip("duckdb")
sqlglot = pytest.importorskip("sqlglot")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_dbt_sessions import DBT, SINGULAR, render, run  # noqa: E402
from tests.test_dbt_staging import output_columns  # noqa: E402

RFM_SQL = (DBT / "models" / "marts" / "fct_customer_rfm.sql").read_text(encoding="utf-8")
T = pd.Timestamp


def dim(rows=None) -> pd.DataFrame:
    """Ten buyers B01..B10 plus two sign-ups without orders. Last orders on 10 distinct days."""
    base = T("2020-12-01")
    out = []
    for i in range(1, 11):
        orders = 1 if i <= 6 else (2 if i == 7 else (3 if i == 8 else (5 if i == 9 else 8)))
        out.append(dict(customer_id=f"B{i:02d}", is_buyer=True, orders=orders, net_revenue_usd=10.0 * i,
                        first_order_date=(base - pd.Timedelta(days=40)).date(),
                        last_order_date=(base + pd.Timedelta(days=i)).date()))   # B10 is the most recent
    out += [dict(customer_id=c, is_buyer=False, orders=0, net_revenue_usd=0.0, first_order_date=None,
                 last_order_date=None) for c in ("N1", "N2")]
    return pd.DataFrame(rows if rows is not None else out)


def fct_orders() -> pd.DataFrame:
    return pd.DataFrame(dict(order_date=[T("2020-12-11").date(), T("2020-12-03").date()]))


@pytest.fixture(scope="module")
def rfm() -> pd.DataFrame:
    return run(RFM_SQL, dim_customers=dim(), fct_orders=fct_orders()).set_index("customer_id")


def test_only_buyers_are_scored(rfm):
    assert sorted(rfm.index) == [f"B{i:02d}" for i in range(1, 11)]


def test_as_of_date_is_the_day_after_the_latest_order_and_recency_counts_to_it(rfm):
    assert set(pd.to_datetime(rfm["as_of_date"])) == {T("2020-12-12")}
    assert rfm.loc["B10", "recency_days"] == 1 and rfm.loc["B01", "recency_days"] == 10


def test_recency_and_monetary_scores_are_quintiles_with_5_best(rfm):
    want = [1, 1, 2, 2, 3, 3, 4, 4, 5, 5]
    ids = [f"B{i:02d}" for i in range(1, 11)]
    assert rfm.loc[ids, "r_score"].tolist() == want      # B01 is the least recent
    assert rfm.loc[ids, "m_score"].tolist() == want      # B01 spent the least


def test_frequency_uses_fixed_bands(rfm):
    assert [rfm.loc[f"B{i:02d}", "f_score"] for i in (1, 6, 7, 8, 9, 10)] == [1, 1, 2, 3, 5, 5]


def test_code_total_and_money(rfm):
    r = rfm.loc["B09"]
    assert (r["rfm_code"], r["rfm_total"]) == ("555", 15)
    assert (r["frequency"], r["monetary_usd"]) == (5, 90.0)
    assert rfm.loc["B01", "rfm_code"] == "111" and rfm.loc["B01", "rfm_total"] == 3


def test_equal_values_always_share_a_score():
    d = dim()
    d.loc[d["is_buyer"], "net_revenue_usd"] = 25.0
    d.loc[d["is_buyer"], "last_order_date"] = T("2020-12-11").date()
    out = run(RFM_SQL, dim_customers=d, fct_orders=fct_orders())
    assert set(out["m_score"]) == {5} and set(out["r_score"]) == {5}


def test_scores_stay_between_1_and_5_for_odd_group_sizes():
    d = dim()
    d = d[d["customer_id"] != "B05"]
    out = run(RFM_SQL, dim_customers=d, fct_orders=fct_orders())
    assert out["r_score"].between(1, 5).all() and out["m_score"].between(1, 5).all()
    assert out["r_score"].max() == 5 and out["m_score"].min() == 1


def test_model_returns_exactly_the_documented_columns():
    models = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))["models"]
    doc = next(m for m in models if m["name"] == "fct_customer_rfm")
    got = output_columns(sqlglot.parse_one(render(RFM_SQL), read="bigquery"))
    want = [c["name"] for c in doc["columns"]]
    assert sorted(got) == sorted(want), set(got) ^ set(want)
    assert all(c.get("description") for c in doc["columns"])


def test_the_model_never_reads_the_ground_truth():
    code = "\n".join(l for l in RFM_SQL.splitlines() if not l.strip().startswith("--"))
    assert "ground_truth" not in code


# ----------------------------------------------------------------------------- singular dbt tests
NAMES = ["assert_rfm_covers_exactly_the_buyers", "assert_rfm_scores_follow_the_values"]


def singular(name: str, rfm: pd.DataFrame, **extra) -> pd.DataFrame:
    tables = dict(fct_customer_rfm=rfm.reset_index(), dim_customers=dim())
    tables.update(extra)
    return run(SINGULAR[name], **tables)


@pytest.mark.parametrize("name", NAMES)
def test_singular_tests_pass_on_good_data(name, rfm):
    assert singular(name, rfm).empty


def test_catches_a_missing_buyer_a_stranger_or_changed_money(rfm):
    assert not singular("assert_rfm_covers_exactly_the_buyers", rfm.drop("B03")).empty
    extra = rfm.copy()
    extra.loc["N1"] = extra.loc["B01"]
    assert not singular("assert_rfm_covers_exactly_the_buyers", extra).empty
    broken = rfm.copy()
    broken.loc["B02", "monetary_usd"] = 99.0
    assert not singular("assert_rfm_covers_exactly_the_buyers", broken).empty
    broken = rfm.copy()
    broken.loc["B02", "as_of_date"] = T("2021-01-01")
    assert not singular("assert_rfm_covers_exactly_the_buyers", broken).empty


def test_catches_scores_that_do_not_follow_the_values(rfm):
    for col, val in (("r_score", 5), ("m_score", 1), ("f_score", 4)):
        broken = rfm.copy()
        broken.loc["B05", col] = val
        assert not singular("assert_rfm_scores_follow_the_values", broken).empty, col
    broken = rfm.copy()
    broken.loc["B05", "r_score"] = 6
    assert not singular("assert_rfm_scores_follow_the_values", broken).empty


def test_catches_a_wrong_code_or_total(rfm):
    broken = rfm.copy()
    broken.loc["B05", "rfm_total"] = 15
    assert list(singular("assert_rfm_scores_follow_the_values", broken)["measure"]) == ["row"]
    broken = rfm.copy()
    broken.loc["B05", "rfm_code"] = "999"
    assert not singular("assert_rfm_scores_follow_the_values", broken).empty

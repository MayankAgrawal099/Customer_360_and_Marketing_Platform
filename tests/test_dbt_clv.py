"""Tests for the lifetime-value mart (fct_customer_clv) and its dbt tests, run in DuckDB on hand-built buyers."""

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

CLV_SQL = (DBT / "models" / "marts" / "fct_customer_clv.sql").read_text(encoding="utf-8")
AS_OF = pd.Timestamp("2020-12-31")

# customer, first order (days before as_of), orders, net revenue
BUYERS = [("B1", 60, 1, 50.0), ("B2", 60, 3, 210.0), ("B3", 30, 1, 70.0), ("B4", 30, 2, 120.0), ("B5", 10, 1, 40.0)]


def dim() -> pd.DataFrame:
    rows = [dict(customer_id=c, is_buyer=True, orders=n, net_revenue_usd=v, gross_revenue_usd=v + 5.0,
                 first_order_date=(AS_OF - pd.Timedelta(days=d)).date(), last_order_date=(AS_OF - pd.Timedelta(days=1)).date())
            for c, d, n, v in BUYERS]
    rows.append(dict(customer_id="N1", is_buyer=False, orders=0, net_revenue_usd=0.0, gross_revenue_usd=0.0,
                     first_order_date=None, last_order_date=None))
    return pd.DataFrame(rows)


def rfm() -> pd.DataFrame:
    return pd.DataFrame(dict(customer_id=[b[0] for b in BUYERS], as_of_date=[AS_OF] * len(BUYERS)))


@pytest.fixture(scope="module")
def clv() -> pd.DataFrame:
    return run(CLV_SQL, dim_customers=dim(), fct_customer_rfm=rfm()).set_index("customer_id")


# population: repeat orders 0+2+0+1+0 = 3 over 60+60+30+30+10 = 190 days; net 490 over 8 orders
POP_RATE, POP_AOV = 3 / 190, 490 / 8


def test_only_buyers_are_valued(clv):
    assert sorted(clv.index) == ["B1", "B2", "B3", "B4", "B5"]


def test_population_figures(clv):
    assert clv["population_repeat_rate_per_day"].iloc[0] == pytest.approx(POP_RATE)
    assert clv["population_aov_usd"].iloc[0] == pytest.approx(POP_AOV)


def test_expected_rate_and_value_are_blended_with_the_population(clv):
    r = clv.loc["B2"]
    assert r["days_observed"] == 60 and r["repeat_orders"] == 2
    assert r["expected_repeat_rate_per_day"] == pytest.approx((2 + 90 * POP_RATE) / (60 + 90))
    assert r["expected_aov_usd"] == pytest.approx((210 + 3 * POP_AOV) / (3 + 3))


def test_predictions_follow_the_recipe(clv):
    r = clv.loc["B4"]
    rate, aov = r["expected_repeat_rate_per_day"], r["expected_aov_usd"]
    assert r["predicted_orders_90d"] == pytest.approx(rate * 90)
    assert r["predicted_revenue_90d_usd"] == pytest.approx(rate * 90 * aov)
    assert r["predicted_orders_12m"] == pytest.approx(rate * 365)
    assert r["predicted_revenue_12m_usd"] == pytest.approx(rate * 365 * aov)
    assert r["clv_12m_usd"] == pytest.approx(120 + rate * 365 * aov)
    assert r["historical_net_revenue_usd"] == 120.0


def test_more_repeat_orders_in_the_same_time_mean_a_higher_rate_and_value(clv):
    assert clv.loc["B2", "expected_repeat_rate_per_day"] > clv.loc["B1", "expected_repeat_rate_per_day"]
    assert clv.loc["B4", "expected_repeat_rate_per_day"] > clv.loc["B3", "expected_repeat_rate_per_day"]
    assert clv.loc["B2", "clv_12m_usd"] > clv.loc["B1", "clv_12m_usd"]


def test_a_one_time_buyer_is_not_predicted_to_have_zero_future_value(clv):
    assert (clv["predicted_revenue_90d_usd"] > 0).all()      # the population prior keeps every rate above zero


def test_model_returns_exactly_the_documented_columns():
    models = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))["models"]
    doc = next(m for m in models if m["name"] == "fct_customer_clv")
    got = output_columns(sqlglot.parse_one(render(CLV_SQL), read="bigquery"))
    want = [c["name"] for c in doc["columns"]]
    assert sorted(got) == sorted(want), set(got) ^ set(want)
    assert all(c.get("description") for c in doc["columns"])


def test_the_model_never_reads_the_ground_truth():
    assert "ground_truth" not in "\n".join(l for l in CLV_SQL.splitlines() if not l.strip().startswith("--"))


# ----------------------------------------------------------------------------- singular dbt tests
NAMES = ["assert_clv_covers_the_buyers_and_ties_to_history", "assert_clv_prediction_is_consistent"]


def singular(name: str, clv: pd.DataFrame) -> pd.DataFrame:
    return run(SINGULAR[name], fct_customer_clv=clv.reset_index(), dim_customers=dim())


@pytest.mark.parametrize("name", NAMES)
def test_singular_tests_pass_on_good_data(name, clv):
    assert singular(name, clv).empty


def test_catches_a_missing_buyer_changed_history_or_negative_values(clv):
    t = "assert_clv_covers_the_buyers_and_ties_to_history"
    assert not singular(t, clv.drop("B3")).empty
    broken = clv.copy()
    broken.loc["B2", "historical_net_revenue_usd"] = 1.0
    assert not singular(t, broken).empty
    broken = clv.copy()
    broken.loc["B2", "predicted_revenue_90d_usd"] = -1.0
    assert not singular(t, broken).empty
    broken = clv.copy()
    broken.loc["B2", "clv_12m_usd"] = 1.0
    assert not singular(t, broken).empty


def test_catches_a_broken_recipe(clv):
    t = "assert_clv_prediction_is_consistent"
    for col, val in (("predicted_orders_12m", 99.0), ("clv_12m_usd", 5000.0), ("predicted_revenue_12m_usd", 1.0),
                     ("days_observed", 0), ("repeat_orders", 9)):
        broken = clv.copy()
        broken.loc["B2", col] = val
        assert not singular(t, broken).empty, col


def test_catches_a_rate_that_falls_when_repeat_orders_rise(clv):
    broken = clv.copy()
    broken.loc["B2", "expected_repeat_rate_per_day"] = 0.0     # B2 has more repeat orders than B1 in the same 60 days
    assert list(singular("assert_clv_prediction_is_consistent", broken)["customer_id"]) == ["B2"]

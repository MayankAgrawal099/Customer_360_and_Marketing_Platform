"""Tests for the customer profile mart (dim_customers) and its dbt tests.

The real model SQL runs in DuckDB on small hand-built tables: every customer appears exactly once
(buyers or not), order totals tie to the orders mart, linked devices and their sessions are summed
without doubling anything, and the singular dbt tests pass on good data and catch damaged data.
"""

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

CUSTOMERS_SQL = (DBT / "models" / "marts" / "dim_customers.sql").read_text(encoding="utf-8")
D = pd.Timestamp  # DuckDB hands dates back as timestamps


def stg_customers() -> pd.DataFrame:
    def row(cid, country, created, opt):
        ts = pd.Timestamp(created)
        return dict(customer_id=cid, full_name=f"Name {cid}", email=f"{cid.lower()}@x.com", email_sha256=f"h{cid}",
                    country=country, created_at=ts, created_date=ts.date(), marketing_opt_in=opt)
    return pd.DataFrame([row("C1", "US", "2020-10-15 10:00:00", True), row("C2", "IN", "2020-11-02 09:00:00", False),
                         row("C3", "GB", "2020-11-20 09:00:00", True), row("C4", "US", "2020-12-01 09:00:00", False)])


def fct_orders() -> pd.DataFrame:
    def row(oid, cust, ts, ch, value, refund, num, match, channel_group):
        ts = pd.Timestamp(ts)
        return dict(order_id=oid, customer_id=cust, order_ts=ts, order_date=ts.date(), order_channel=ch, item_count=2,
                    is_refunded=refund > 0, order_value_usd=value, refund_usd=refund, net_revenue_usd=value - refund,
                    is_first_order=num == 1, ga4_match_status=match, purchase_channel_group=channel_group)
    return pd.DataFrame([
        row("O2", "C1", "2020-11-15 12:00:00", "app", 30.0, 0.0, 2, "app_order", None),      # out of order on purpose
        row("O1", "C1", "2020-11-05 10:00:00", "web", 50.0, 0.0, 1, "matched", "Paid Search"),
        row("O3", "C1", "2020-12-01 09:00:00", "web", 20.0, 20.0, 3, "web_no_transaction_id", None),
        row("O4", "C2", "2020-11-10 08:00:00", "web", 40.0, 0.0, 1, "matched", "Organic Search"),
    ])


def links() -> pd.DataFrame:
    return pd.DataFrame([dict(user_pseudo_id="d1", customer_id="C1", confidence="high"),
                         dict(user_pseudo_id="d1b", customer_id="C1", confidence="medium"),
                         dict(user_pseudo_id="d3", customer_id="C3", confidence="medium")])


def fct_sessions() -> pd.DataFrame:
    def row(key, cust, ts, ch, src, med, conv):
        ts = pd.Timestamp(ts)
        return dict(session_key=key, customer_id=cust, session_start_ts=ts, session_date=ts.date(), channel_group=ch,
                    source=src, medium=med, is_converted=conv)
    return pd.DataFrame([
        row("d1.2", "C1", "2020-11-05 09:00:00", "Paid Search", "google", "cpc", True),
        row("d1.1", "C1", "2020-11-01 09:00:00", "Organic Search", "google", "organic", False),
        row("d1b.1", "C1", "2020-11-03 09:00:00", "Direct", "(direct)", "(none)", False),
        row("d3.1", "C3", "2020-11-21 09:00:00", "Referral", "blog.com", "referral", False),
        row("x.1", None, "2020-11-01 09:00:00", "Direct", "(direct)", "(none)", False),    # unlinked device
    ])


@pytest.fixture(scope="module")
def dim() -> pd.DataFrame:
    out = run(CUSTOMERS_SQL, stg_crm__customers=stg_customers(), fct_orders=fct_orders(),
              stg_identity__links=links(), fct_sessions=fct_sessions())
    return out.set_index("customer_id")


def test_one_row_per_customer_including_those_without_orders(dim):
    assert sorted(dim.index) == ["C1", "C2", "C3", "C4"] and dim.index.is_unique


def test_order_summary(dim):
    r = dim.loc["C1"]
    assert (r["orders"], r["web_orders"], r["app_orders"], r["refunded_orders"], r["items"]) == (3, 2, 1, 1, 6)
    assert (r["gross_revenue_usd"], r["refund_usd"], r["net_revenue_usd"]) == (100.0, 20.0, 80.0)
    assert r["avg_order_value_usd"] == pytest.approx(100 / 3)
    assert (r["first_order_date"], r["last_order_date"]) == (D("2020-11-05"), D("2020-12-01"))
    assert bool(r["is_buyer"]) and bool(r["is_repeat_buyer"])
    assert not dim.loc["C2", "is_repeat_buyer"] and dim.loc["C2", "is_buyer"]


def test_first_order_fields_come_from_the_first_order_only(dim):
    r = dim.loc["C1"]
    assert (r["first_order_channel"], r["first_order_ga4_match_status"], r["first_order_channel_group"]) == \
        ("web", "matched", "Paid Search")
    assert dim.loc["C2", "first_order_channel_group"] == "Organic Search"


def test_customers_without_orders_get_zeros_not_nulls(dim):
    for cid in ("C3", "C4"):
        r = dim.loc[cid]
        assert (r["orders"], r["gross_revenue_usd"], r["net_revenue_usd"], r["items"]) == (0, 0.0, 0.0, 0)
        assert not r["is_buyer"] and pd.isna(r["first_order_date"]) and pd.isna(r["avg_order_value_usd"])
        assert pd.isna(r["first_order_channel"])


def test_linked_devices(dim):
    assert dim["linked_devices"].to_dict() == {"C1": 2, "C2": 0, "C3": 1, "C4": 0}
    assert dim["has_high_confidence_link"].to_dict() == {"C1": True, "C2": False, "C3": False, "C4": False}
    assert dim["has_linked_device"].to_dict() == {"C1": True, "C2": False, "C3": True, "C4": False}


def test_sessions_span_all_linked_devices_and_first_touch_is_the_earliest(dim):
    r = dim.loc["C1"]
    assert (r["sessions"], r["converted_sessions"]) == (3, 1)
    assert (r["first_session_date"], r["last_session_date"]) == (D("2020-11-01"), D("2020-11-05"))
    assert (r["first_session_channel_group"], r["first_session_source"], r["first_session_medium"]) == \
        ("Organic Search", "google", "organic")
    assert dim.loc["C3", "first_session_channel_group"] == "Referral"
    assert dim.loc["C2", "sessions"] == 0 and pd.isna(dim.loc["C2", "first_session_date"])


def test_signup_cohort_month(dim):
    assert dim.loc["C1", "created_month"] == D("2020-10-01") and dim.loc["C3", "created_month"] == D("2020-11-01")


def test_model_returns_exactly_the_documented_columns():
    models = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))["models"]
    doc = next(m for m in models if m["name"] == "dim_customers")
    got = output_columns(sqlglot.parse_one(render(CUSTOMERS_SQL), read="bigquery"))
    want = [c["name"] for c in doc["columns"]]
    assert sorted(got) == sorted(want), set(got) ^ set(want)
    assert all(c.get("description") for c in doc["columns"])


def test_the_model_never_reads_the_ground_truth():
    code = "\n".join(l for l in CUSTOMERS_SQL.splitlines() if not l.strip().startswith("--"))
    assert "ground_truth" not in code


# ----------------------------------------------------------------------------- singular dbt tests
NAMES = ["assert_customer_orders_tie_to_orders_mart", "assert_customer_profile_is_consistent",
         "assert_customer_sessions_tie_to_sessions_mart"]


def singular(name: str, dim: pd.DataFrame, **extra) -> pd.DataFrame:
    tables = dict(dim_customers=dim.reset_index(), fct_orders=fct_orders(), fct_sessions=fct_sessions(),
                  stg_crm__customers=stg_customers(), stg_identity__links=links())
    tables.update(extra)
    return run(SINGULAR[name], **tables)


@pytest.mark.parametrize("name", NAMES)
def test_singular_tests_pass_on_good_data(name, dim):
    assert singular(name, dim).empty


def test_catches_lost_or_changed_revenue(dim):
    broken = dim.copy()
    broken.loc["C1", "net_revenue_usd"] = 81.0
    assert not singular("assert_customer_orders_tie_to_orders_mart", broken).empty
    broken = dim.copy()
    broken.loc["C1", "orders"] = 2
    assert not singular("assert_customer_orders_tie_to_orders_mart", broken).empty


def test_catches_a_missing_customer(dim):
    assert list(singular("assert_customer_profile_is_consistent", dim.drop("C4"))["customer_id"]) == ["missing: C4"]


def test_catches_inconsistent_columns(dim):
    for col, val in (("is_buyer", False), ("refunded_orders", 9), ("has_linked_device", False),
                     ("converted_sessions", 9), ("net_revenue_usd", 99.0)):
        broken = dim.copy()
        broken.loc["C1", col] = val
        assert "C1" in list(singular("assert_customer_profile_is_consistent", broken)["customer_id"]), col
    broken = dim.copy()
    broken.loc["C4", "net_revenue_usd"] = 5.0
    assert "C4" in list(singular("assert_customer_profile_is_consistent", broken)["customer_id"])


def test_catches_lost_sessions_or_devices(dim):
    broken = dim.copy()
    broken.loc["C3", "sessions"] = 0
    assert not singular("assert_customer_sessions_tie_to_sessions_mart", broken).empty
    broken = dim.copy()
    broken.loc["C1", "linked_devices"] = 1
    assert not singular("assert_customer_sessions_tie_to_sessions_mart", broken).empty

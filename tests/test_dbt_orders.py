"""Tests for the orders mart (fct_orders) and its dbt tests.

Like the sessions tests, they run the real model SQL in DuckDB on small hand-built tables, so the
logic is checked without a BigQuery login: order numbering and gaps, how each order links to GA4,
that orders are neither lost nor doubled, and that the singular dbt tests pass on good data and
catch damaged data.
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

ORDERS_SQL = (DBT / "models" / "marts" / "fct_orders.sql").read_text(encoding="utf-8")


def stg_orders() -> pd.DataFrame:
    def row(oid, cust, ts, ch, txn, value, status="completed"):
        ts = pd.Timestamp(ts)
        refund = value if status == "refunded" else 0.0
        return dict(order_id=oid, customer_id=cust, order_ts=ts, order_date=ts.date(), order_channel=ch,
                    ga_transaction_id=txn, order_value_usd=value, item_count=1, status=status,
                    refund_usd=refund, is_refunded=status == "refunded", net_revenue_usd=value - refund)
    return pd.DataFrame([
        row("O3", "C1", "2020-12-01 09:00:00", "web", None, 20.0),            # listed out of order on purpose
        row("O1", "C1", "2020-11-05 10:00:00", "web", "T1", 50.0),
        row("O2", "C1", "2020-11-15 12:00:00", "app", None, 30.0),
        row("O4", "C2", "2020-11-10 08:00:00", "web", "T2", 40.0, "refunded"),
        row("O5", "C3", "2020-11-20 08:00:00", "web", "T9", 15.0),            # transaction not in GA4
    ])


def stg_customers() -> pd.DataFrame:
    return pd.DataFrame([dict(customer_id=c, country=k, created_at=pd.Timestamp("2020-10-01"))
                         for c, k in (("C1", "US"), ("C2", "IN"), ("C3", "GB"))])


def stg_purchases() -> pd.DataFrame:
    return pd.DataFrame([
        dict(transaction_id="T1", user_pseudo_id="d1", session_key="d1.1", revenue_usd=50.0),
        dict(transaction_id="T2", user_pseudo_id="d2", session_key="d2.1", revenue_usd=40.0),
    ])


def fct_sessions() -> pd.DataFrame:
    return pd.DataFrame([
        dict(session_key="d1.1", ga_session_number=2, session_date=pd.Timestamp("2020-11-05").date(),
             channel_group="Paid Search", source="google", medium="cpc", campaign="brand",
             customer_id="C1", is_converted=True),
        dict(session_key="d2.1", ga_session_number=1, session_date=pd.Timestamp("2020-11-10").date(),
             channel_group="Organic Search", source="google", medium="organic", campaign="(organic)",
             customer_id=None, is_converted=True),
    ])


def tracks() -> pd.DataFrame:
    o = stg_orders()
    return pd.DataFrame(dict(order_id=o["order_id"], customer_id=o["customer_id"], revenue_usd=o["order_value_usd"],
                             order_channel=o["order_channel"], order_status=o["status"],
                             event_name="Order Completed")).pipe(
        lambda d: pd.concat([d, pd.DataFrame([dict(order_id=None, customer_id="C1", revenue_usd=None,
                                                   order_channel=None, order_status=None, event_name="Signed Up")])]))


@pytest.fixture(scope="module")
def fct() -> pd.DataFrame:
    out = run(ORDERS_SQL, stg_crm__orders=stg_orders(), stg_crm__customers=stg_customers(),
              stg_ga4__purchases=stg_purchases(), fct_sessions=fct_sessions())
    return out.set_index("order_id")


def test_one_row_per_order(fct):
    assert len(fct) == 5 and fct.index.is_unique


def test_orders_are_numbered_in_time_order_per_customer(fct):
    assert fct.loc[["O1", "O2", "O3"], "order_number"].tolist() == [1, 2, 3]
    assert fct.loc[["O4", "O5"], "order_number"].tolist() == [1, 1]
    assert fct["is_first_order"].to_dict() == {"O1": True, "O2": False, "O3": False, "O4": True, "O5": True}


def test_gaps_between_orders(fct):
    assert fct.loc["O2", "days_since_previous_order"] == 10 and fct.loc["O3", "days_since_previous_order"] == 16
    assert fct.loc["O3", "days_since_first_order"] == 26
    assert pd.isna(fct.loc["O1", "days_since_previous_order"]) and fct.loc["O1", "days_since_first_order"] == 0


def test_ga4_match_status(fct):
    assert fct["ga4_match_status"].to_dict() == {"O1": "matched", "O2": "app_order", "O3": "web_no_transaction_id",
                                                 "O4": "matched", "O5": "web_unmatched"}


def test_matched_orders_carry_the_purchasing_session_and_channel(fct):
    row = fct.loc["O1"]
    assert (row["ga_user_pseudo_id"], row["ga_session_key"], row["purchase_channel_group"]) == ("d1", "d1.1", "Paid Search")
    assert (row["purchase_source"], row["purchase_medium"], row["purchase_campaign"]) == ("google", "cpc", "brand")
    assert row["purchase_session_number"] == 2 and row["ga_revenue_usd"] == 50.0
    assert fct.loc["O4", "purchase_channel_group"] == "Organic Search"


def test_unmatched_orders_have_no_ga4_fields(fct):
    for oid in ("O2", "O3", "O5"):
        assert fct.loc[oid, ["ga_user_pseudo_id", "ga_session_key", "purchase_channel_group"]].isna().all()


def test_money_columns_and_customer_fields(fct):
    assert fct.loc["O4", ["is_refunded", "order_value_usd", "refund_usd", "net_revenue_usd"]].tolist() == [True, 40.0, 40.0, 0.0]
    assert fct["customer_country"].to_dict() == {"O1": "US", "O2": "US", "O3": "US", "O4": "IN", "O5": "GB"}


def test_model_returns_exactly_the_documented_columns():
    models = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))["models"]
    doc = next(m for m in models if m["name"] == "fct_orders")
    got = output_columns(sqlglot.parse_one(render(ORDERS_SQL), read="bigquery"))
    want = [c["name"] for c in doc["columns"]]
    assert sorted(got) == sorted(want), set(got) ^ set(want)
    assert all(c.get("description") for c in doc["columns"])


def test_the_models_never_read_the_ground_truth():
    code = "\n".join(l for l in ORDERS_SQL.splitlines() if not l.strip().startswith("--"))
    assert "ground_truth" not in code


# ----------------------------------------------------------------------------- singular dbt tests
NAMES = ["assert_orders_cover_crm_orders", "assert_order_history_is_consistent",
         "assert_orders_match_segment_tracks", "assert_matched_orders_have_a_session"]


def singular(name: str, fct_orders: pd.DataFrame, **extra) -> pd.DataFrame:
    tables = dict(fct_orders=fct_orders.reset_index(), stg_crm__orders=stg_orders(), stg_segment__tracks=tracks(),
                  fct_sessions=fct_sessions())
    tables.update(extra)
    return run(SINGULAR[name], **tables)


def good(fct):
    # O5 is a deliberately broken order (transaction not in GA4); the session test must not flag it.
    return fct


@pytest.mark.parametrize("name", NAMES)
def test_singular_tests_pass_on_good_data(name, fct):
    assert singular(name, good(fct)).empty


def test_catches_a_lost_order(fct):
    assert not singular("assert_orders_cover_crm_orders", fct.drop("O1")).empty


def test_catches_a_changed_value(fct):
    broken = fct.copy()
    broken.loc["O1", "order_value_usd"] = 51.0
    assert not singular("assert_orders_cover_crm_orders", broken).empty


def test_catches_broken_order_numbering(fct):
    broken = fct.copy()
    broken.loc["O3", "order_number"] = 2
    assert not singular("assert_order_history_is_consistent", broken).empty
    broken = fct.copy()
    broken.loc["O2", "days_since_previous_order"] = -1
    assert not singular("assert_order_history_is_consistent", broken).empty


def test_catches_a_missing_or_wrong_track_event(fct):
    t = tracks()
    assert not singular("assert_orders_match_segment_tracks", fct, stg_segment__tracks=t[t["order_id"] != "O2"]).empty
    t = tracks()
    t.loc[t["order_id"] == "O1", "revenue_usd"] = 99.0
    assert not singular("assert_orders_match_segment_tracks", fct, stg_segment__tracks=t).empty
    t = tracks()
    t = pd.concat([t, pd.DataFrame([dict(order_id="O99", customer_id="C1", revenue_usd=5.0, order_channel="web",
                                         order_status="completed", event_name="Order Completed")])])
    assert not singular("assert_orders_match_segment_tracks", fct, stg_segment__tracks=t).empty


def test_catches_a_matched_order_whose_device_belongs_to_another_customer(fct):
    s = fct_sessions()
    s.loc[s["session_key"] == "d1.1", "customer_id"] = "C2"
    assert list(singular("assert_matched_orders_have_a_session", fct, fct_sessions=s)["order_id"]) == ["O1"]


def test_catches_a_matched_order_without_a_session_or_with_wrong_revenue(fct):
    s = fct_sessions()
    assert list(singular("assert_matched_orders_have_a_session", fct, fct_sessions=s[s["session_key"] != "d2.1"])["order_id"]) == ["O4"]
    broken = fct.copy()
    broken.loc["O1", "ga_revenue_usd"] = 10.0
    assert list(singular("assert_matched_orders_have_a_session", broken)["order_id"]) == ["O1"]

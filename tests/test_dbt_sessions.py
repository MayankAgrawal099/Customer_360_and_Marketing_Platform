"""Tests for the sessions models (int_ga4__sessions, fct_sessions) and the channel_group macro.

They run the real model SQL in DuckDB on small hand-built tables (the SQL is translated from BigQuery
with sqlglot), so the logic is checked without a BigQuery login: first non-empty source wins, sessions
without source stay Unassigned, revenue and purchases are neither lost nor doubled, the customer joins
on, and the macro agrees with the Python channel rules for hundreds of source/medium pairs. The
singular dbt tests are run too, on good data (they must return nothing) and on damaged data (they must
catch it).
"""

import itertools
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

duckdb = pytest.importorskip("duckdb")
sqlglot = pytest.importorskip("sqlglot")
jinja2 = pytest.importorskip("jinja2")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.synthetic import channels  # noqa: E402
from tests.test_dbt_staging import output_columns  # noqa: E402

DBT = ROOT / "dbt"
MACRO = (DBT / "macros" / "channel_group.sql").read_text(encoding="utf-8")
INT_SQL = (DBT / "models" / "intermediate" / "int_ga4__sessions.sql").read_text(encoding="utf-8")
FCT_SQL = (DBT / "models" / "marts" / "fct_sessions.sql").read_text(encoding="utf-8")
SINGULAR = {p.stem: p.read_text(encoding="utf-8") for p in (DBT / "tests").glob("*.sql")}


def render(sql: str) -> str:
    """Render the dbt Jinja (ref and the channel_group macro) into BigQuery SQL with plain table names."""
    env = jinja2.Environment()
    env.globals.update(ref=lambda name: name, config=lambda **kw: "")
    return env.from_string(MACRO + "\n" + sql).render()


def to_duck(sql: str) -> str:
    return sqlglot.transpile(render(sql), read="bigquery", write="duckdb")[0]


def run(sql: str, **tables: pd.DataFrame) -> pd.DataFrame:
    con = duckdb.connect()
    for name, df in tables.items():
        con.register(name, df)
    return con.execute(to_duck(sql)).df()


# ----------------------------------------------------------------------------- the channel macro
SOURCES = sorted(set(channels.DISPLAY_SOURCES) | set(channels.SOCIAL_SOURCES)) + [
    "google", "bing", "(direct)", "direct", "newsletter", "affiliate_net", "m.facebook.com", "T.CO", " Google ",
    "googleads.g.doubleclick.net", "doubleclick.net", "FACEBOOK", "", None,
    "shop.googlemerchandisestore.com", "googlemerchandisestore.com", "Shop.GoogleMerchandiseStore.com"]
MEDIUMS = ["cpc", "CPC ", "ppc", "paidsearch", "paid search", "cpm", "display", "banner", "paid_social", "paidsocial",
           "paid social", "social_paid", "organic", "email", "affiliate", "social", "organic_social", "social_organic",
           "referral", "(none)", "none", "(not set)", "weird", "", None]


def test_macro_agrees_with_the_python_channel_rules_on_every_pair():
    grid = pd.DataFrame(list(itertools.product(SOURCES, MEDIUMS)), columns=["src", "med"])
    sql = "select src, med, {{ channel_group('src', 'med') }} as ch from grid"
    got = run(sql, grid=grid)
    want = [channels.channel_group(s, m) for s, m in zip(grid["src"], grid["med"])]
    bad = [(s, m, g, w) for s, m, g, w in zip(grid["src"], grid["med"], got["ch"], want) if g != w]
    assert not bad, f"{len(bad)} pairs differ, for example {bad[:3]}"
    assert len(grid) > 500 and set(got["ch"]) >= {"Paid Search", "Display", "Paid Social", "Organic Search", "Email",
                                                  "Affiliate", "Organic Social", "Referral", "Direct", "Other", "Unassigned",
                                                      "Self Referral"}


def test_macro_leaves_missing_source_and_medium_unassigned():
    df = pd.DataFrame({"s": [None, "", "  ", "google"], "m": [None, "", None, None]})
    assert list(run("select {{ channel_group('s', 'm') }} as ch from df", df=df)["ch"]) == \
        ["Unassigned", "Unassigned", "Unassigned", "Other"]


# ----------------------------------------------------------------------------- fake data
T0 = pd.Timestamp("2020-11-05 10:00:00")
EVENT_COLS = ["event_date", "event_ts", "event_name", "user_pseudo_id", "ga_session_id", "ga_session_number",
              "page_location", "page_referrer", "session_source", "session_medium", "session_campaign",
              "has_gclid", "engagement_time_msec", "is_engaged_session", "country", "device_category",
              "first_touch_source", "first_touch_medium", "first_touch_campaign", "transaction_id",
              "purchase_revenue_usd"]


def ev(sec, name, dev, sid, **kw):
    ts = T0 + pd.Timedelta(seconds=sec)
    row = dict.fromkeys(EVENT_COLS)
    row.update(event_date=ts.date(), event_ts=ts, event_name=name, user_pseudo_id=dev, ga_session_id=sid,
               ga_session_number=1, has_gclid=False, page_location=f"https://shop/{sec}")
    row.update(kw)
    return row


def events() -> pd.DataFrame:
    rows = [
        # d1 session 1: source appears on the 2nd event; a later event names another source. Purchase T1 (50).
        ev(0, "page_view", "d1", 1, country="US", device_category="mobile"),
        ev(5, "page_view", "d1", 1, session_source="google", session_medium="cpc", session_campaign="brand",
           engagement_time_msec=1000, is_engaged_session=True, has_gclid=True),
        ev(6, "page_view", "d1", 1, session_source="bing", session_medium="cpc", engagement_time_msec=500),
        ev(10, "view_item", "d1", 1), ev(20, "add_to_cart", "d1", 1), ev(30, "begin_checkout", "d1", 1),
        ev(40, "purchase", "d1", 1, transaction_id="T1", purchase_revenue_usd=50.0),
        # d1 session 2: direct
        ev(3600, "page_view", "d1", 2, ga_session_number=2, session_source="(direct)", session_medium="(none)"),
        # d2: no source parameters at all
        ev(1, "page_view", "d2", 1), ev(2, "scroll", "d2", 1),
        # d3: email, no campaign
        ev(1, "page_view", "d3", 1, session_source="newsletter", session_medium="email"),
        # d4: a purchase event without a usable transaction id
        ev(1, "purchase", "d4", 1, transaction_id="(not set)", purchase_revenue_usd=0.0),
        # events with no session id are ignored
        ev(1, "page_view", "d5", None),
    ]
    return pd.DataFrame(rows, columns=EVENT_COLS).astype({"ga_session_id": "Int64"}).assign(
        session_key=lambda d: d["user_pseudo_id"] + "." + d["ga_session_id"].astype("string"))


def purchases() -> pd.DataFrame:
    return pd.DataFrame([dict(transaction_id="T1", user_pseudo_id="d1", session_key="d1.1", revenue_usd=50.0,
                              event_ts=T0 + pd.Timedelta(seconds=40))])


def links() -> pd.DataFrame:
    return pd.DataFrame([dict(user_pseudo_id="d1", customer_id="C1", link_rule="identify_verified", confidence="high")])


@pytest.fixture(scope="module")
def sessions_int():
    return run(INT_SQL, stg_ga4__events=events()).set_index("session_key")


@pytest.fixture(scope="module")
def fct(sessions_int):
    out = run(FCT_SQL, int_ga4__sessions=sessions_int.reset_index(), stg_ga4__purchases=purchases(),
              stg_identity__links=links())
    return out.set_index("session_key")


# ----------------------------------------------------------------------------- int_ga4__sessions
def test_one_row_per_session_and_events_without_a_session_id_are_dropped(sessions_int):
    assert sorted(sessions_int.index) == ["d1.1", "d1.2", "d2.1", "d3.1", "d4.1"]


def test_first_non_empty_value_wins(sessions_int):
    s = sessions_int.loc["d1.1"]
    assert (s["source"], s["medium"], s["campaign"]) == ("google", "cpc", "brand")      # bing came later
    assert s["country"] == "US" and s["device_category"] == "mobile"


def test_session_counts_flags_and_times(sessions_int):
    s = sessions_int.loc["d1.1"]
    assert (s["events"], s["page_views"], s["purchase_events"]) == (7, 3, 1)
    assert bool(s["viewed_item"]) and bool(s["added_to_cart"]) and bool(s["began_checkout"])
    assert bool(s["is_engaged"]) and s["engagement_time_msec"] == 1500 and bool(s["has_gclid"])
    assert (s["session_end_ts"] - s["session_start_ts"]).total_seconds() == 40
    assert not sessions_int.loc["d2.1", "viewed_item"] and sessions_int.loc["d2.1", "engagement_time_msec"] == 0


# ----------------------------------------------------------------------------- fct_sessions
def test_channels(fct):
    assert fct["channel_group"].to_dict() == {"d1.1": "Paid Search", "d1.2": "Direct", "d2.1": "Unassigned",
                                              "d3.1": "Email", "d4.1": "Unassigned"}


def test_paid_sessions_get_the_ad_spend_key_and_others_do_not(fct):
    assert fct.loc["d1.1", "ad_campaign_key"] == "Paid Search|google|cpc|brand"
    assert fct.loc["d3.1", "ad_campaign_key"] == "Email|newsletter|email|(not set)"     # missing campaign
    assert fct[~fct["is_paid"].astype(bool)]["ad_campaign_key"].isna().all()


def test_purchases_and_revenue_land_on_the_right_session(fct):
    assert fct.loc["d1.1", "valid_purchases"] == 1 and fct.loc["d1.1", "revenue_usd"] == 50.0
    assert bool(fct.loc["d1.1", "is_converted"])
    assert fct.loc["d4.1", "purchase_events"] == 1 and fct.loc["d4.1", "valid_purchases"] == 0   # invalid purchase
    assert not fct["is_converted"].drop("d1.1").any()
    assert fct["revenue_usd"].sum() == 50.0


def test_identity_joins_by_device_without_duplicating_sessions(fct):
    assert fct.loc[["d1.1", "d1.2"], "customer_id"].tolist() == ["C1", "C1"]      # all sessions of the device
    assert fct["customer_id"].drop(["d1.1", "d1.2"]).isna().all()
    assert fct.loc["d1.1", "identity_link_rule"] == "identify_verified" and bool(fct.loc["d1.1", "is_identified"])
    assert not fct.loc["d2.1", "is_identified"] and fct.index.is_unique


def test_derived_columns(fct):
    assert bool(fct.loc["d1.1", "is_first_session"]) and not fct.loc["d1.2", "is_first_session"]
    assert fct.loc["d1.1", "duration_seconds"] == 40


# ----------------------------------------------------------------------------- schema, columns, singular tests
def test_models_return_exactly_the_documented_columns():
    for path, yml, name in ((DBT / "models" / "intermediate", "_intermediate.yml", "int_ga4__sessions"),
                            (DBT / "models" / "marts", "_marts.yml", "fct_sessions")):
        doc = yaml.safe_load((path / yml).read_text(encoding="utf-8"))["models"][0]
        sql = INT_SQL if name == "int_ga4__sessions" else FCT_SQL
        got = output_columns(sqlglot.parse_one(render(sql), read="bigquery"))
        want = [c["name"] for c in doc["columns"]]
        assert doc["name"] == name and sorted(got) == sorted(want), f"{name}: {set(got) ^ set(want)}"
        assert all(c.get("description") for c in doc["columns"])


def test_channel_values_in_the_schema_match_the_python_rules():
    doc = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))["models"][0]
    col = next(c for c in doc["columns"] if c["name"] == "channel_group")
    listed = next(t for t in col["data_tests"] if isinstance(t, dict))["accepted_values"]["arguments"]["values"]
    produced = {channels.channel_group(s, m) for s, m in itertools.product(SOURCES, MEDIUMS)}
    assert set(listed) == produced and set(channels.PAID_CHANNELS) <= set(listed)


def ad_spend(clicks_brand=1, clicks_email=1, drop_email=False) -> pd.DataFrame:
    rows = [dict(date=T0.date(), campaign_key="Paid Search|google|cpc|brand", clicks=clicks_brand),
            dict(date=T0.date(), campaign_key="Email|newsletter|email|(not set)", clicks=clicks_email)]
    return pd.DataFrame(rows[:1] if drop_email else rows)


def singular(name: str, fct_df: pd.DataFrame, **extra) -> pd.DataFrame:
    tables = dict(fct_sessions=fct_df.reset_index(), stg_ga4__events=events(), stg_ga4__purchases=purchases(),
                  stg_ad_spend=ad_spend())
    tables.update(extra)
    return run(SINGULAR[name], **tables)


@pytest.mark.parametrize("name", ["assert_sessions_cover_all_events", "assert_session_revenue_matches_purchases",
                                  "assert_session_values_make_sense", "assert_paid_sessions_match_ad_spend"])
def test_singular_tests_pass_on_good_data(name, fct):
    assert singular(name, fct).empty


def test_singular_test_catches_a_lost_session(fct):
    assert not singular("assert_sessions_cover_all_events", fct.drop("d2.1")).empty


def test_singular_test_catches_lost_revenue(fct):
    broken = fct.copy()
    broken.loc["d1.1", "revenue_usd"] = 40.0
    assert not singular("assert_session_revenue_matches_purchases", broken).empty


def test_singular_test_catches_impossible_session_values(fct):
    broken = fct.copy()
    broken.loc["d2.1", "page_views"] = 99
    assert list(singular("assert_session_values_make_sense", broken)["session_key"]) == ["d2.1"]


def test_ad_spend_test_catches_missing_spend_and_wrong_clicks(fct):
    assert not singular("assert_paid_sessions_match_ad_spend", fct, stg_ad_spend=ad_spend(drop_email=True)).empty
    assert not singular("assert_paid_sessions_match_ad_spend", fct, stg_ad_spend=ad_spend(clicks_brand=5)).empty
    assert not singular("assert_paid_sessions_match_ad_spend", fct, stg_ad_spend=ad_spend(clicks_brand=0)).empty


def test_sessions_models_never_read_the_ground_truth():
    for sql in (INT_SQL, FCT_SQL, MACRO):
        assert "ground_truth" not in "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))

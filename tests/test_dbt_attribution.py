"""Tests for the attribution models: int_conversion_touchpoints, fct_attribution_credits, fct_attribution_by_channel,
fct_attribution_journeys and their dbt tests. The real model SQL runs in DuckDB on a small hand-built world in which
every rule has a case: skipping Self Referral, Direct and Unassigned, the 30-day look-back, borrowing the customer's
linked devices for app orders, the fallback buckets, and orders with no touchpoint at all."""

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

T = pd.Timestamp
TP_SQL = (DBT / "models" / "intermediate" / "int_conversion_touchpoints.sql").read_text(encoding="utf-8")
CR_SQL = (DBT / "models" / "marts" / "fct_attribution_credits.sql").read_text(encoding="utf-8")
CH_SQL = (DBT / "models" / "marts" / "fct_attribution_by_channel.sql").read_text(encoding="utf-8")
JR_SQL = (DBT / "models" / "marts" / "fct_attribution_journeys.sql").read_text(encoding="utf-8")


def sessions() -> pd.DataFrame:
    def s(key, dev, ts, ch, src, med):
        ts = T(ts)
        return dict(session_key=key, user_pseudo_id=dev, session_date=ts.date(), session_start_ts=ts, channel_group=ch,
                    source=src, medium=med, campaign="c", ad_campaign_key=f"{ch}|{src}|{med}|c" if ch == "Paid Search" else None,
                    is_paid=ch == "Paid Search")
    return pd.DataFrame([
        # customer C1: devices d1 and d1b
        s("d1.0", "d1", "2020-09-01 10:00:00", "Email", "mail", "email"),                   # too old for both orders
        s("d1.1", "d1", "2020-11-01 10:00:00", "Paid Search", "google", "cpc"),
        s("d1b.1", "d1b", "2020-11-03 10:00:00", "Self Referral", "shop", "referral"),
        s("d1.2", "d1", "2020-11-05 10:00:00", "Organic Search", "google", "organic"),
        s("d1.3", "d1", "2020-11-06 10:00:00", "Direct", "(direct)", "(none)"),              # O1's purchasing session
        s("d1.4", "d1", "2020-11-25 10:00:00", "Paid Social", "facebook", "paid_social"),   # after both orders
        # customer C2: only Self Referral, Direct and Unassigned
        s("d2.1", "d2", "2020-11-01 10:00:00", "Self Referral", "shop", "referral"),
        s("d2.2", "d2", "2020-11-02 10:00:00", "Direct", "(direct)", "(none)"),
        s("d2.3", "d2", "2020-11-03 10:00:00", "Unassigned", None, None),
        # unlinked device d5 (matched web order of C4), and d6 (purchasing session older than the window)
        s("d5.1", "d5", "2020-11-10 10:00:00", "Paid Search", "google", "cpc"),
        s("d6.1", "d6", "2020-10-01 10:00:00", "Referral", "blog.com", "referral"),
        s("d6.2", "d6", "2020-12-10 09:00:00", "Display", "ads", "display"),
        # someone else's session on a linked device? no: x.1 belongs to nobody in this world
        s("x.1", "x", "2020-11-05 10:00:00", "Organic Social", "facebook", "social"),
    ])


def orders() -> pd.DataFrame:
    def o(oid, cust, ts, ch, status, dev, ses, value, refund=0.0):
        ts = T(ts)
        return dict(order_id=oid, customer_id=cust, order_ts=ts, order_date=ts.date(), order_channel=ch,
                    ga4_match_status=status, is_refunded=refund > 0, order_value_usd=value, net_revenue_usd=value - refund,
                    ga_user_pseudo_id=dev, ga_session_key=ses)
    return pd.DataFrame([
        o("O1", "C1", "2020-11-06 12:00:00", "web", "matched", "d1", "d1.3", 100.0),
        o("O2", "C1", "2020-11-20 12:00:00", "app", "app_order", None, None, 60.0, 10.0),
        o("O3", "C2", "2020-11-04 12:00:00", "app", "app_order", None, None, 40.0),
        o("O4", "C3", "2020-11-04 12:00:00", "web", "web_no_transaction_id", None, None, 30.0),     # no linked device
        o("O5", "C4", "2020-11-10 11:00:00", "web", "matched", "d5", "d5.1", 80.0),
        o("O6", "C5", "2020-12-10 11:00:00", "web", "matched", "d6", "d6.1", 25.0),                  # purchasing session is 70 days old
    ])


def links() -> pd.DataFrame:
    return pd.DataFrame([dict(user_pseudo_id="d1", customer_id="C1"), dict(user_pseudo_id="d1b", customer_id="C1"),
                         dict(user_pseudo_id="d2", customer_id="C2")])


@pytest.fixture(scope="module")
def tp() -> pd.DataFrame:
    return run(TP_SQL, fct_orders=orders(), stg_identity__links=links(), fct_sessions=sessions())


@pytest.fixture(scope="module")
def cr(tp) -> pd.DataFrame:
    return run(CR_SQL, fct_orders=orders(), int_conversion_touchpoints=tp)


def keys(df, order):
    return sorted(df.loc[df["order_id"] == order, "session_key"])


# ----------------------------------------------------------------------------- the journey
def test_matched_order_journey_uses_the_customers_linked_devices_and_the_window(tp):
    assert keys(tp, "O1") == ["d1.1", "d1.2", "d1.3", "d1b.1"]      # d1.0 too old, d1.4 after the order


def test_app_order_borrows_the_linked_devices_sessions(tp):
    assert keys(tp, "O2") == ["d1.1", "d1.2", "d1.3", "d1b.1"]      # O2 is 2020-11-20: window opens 2020-10-21


def test_orders_without_any_session_have_no_rows(tp):
    assert "O4" not in set(tp["order_id"])


def test_unlinked_device_order_gets_only_its_own_device(tp):
    assert keys(tp, "O5") == ["d5.1"]


def test_the_purchasing_session_is_kept_even_outside_the_window(tp):
    assert keys(tp, "O6") == ["d6.1", "d6.2"]                        # d6.1 is 70 days old but is the purchasing session


def test_other_peoples_sessions_never_leak_in(tp):
    assert "x.1" not in set(tp["session_key"])


def test_has_source_flags(tp):
    flags = dict(zip(tp["session_key"], tp["has_source"]))
    assert flags["d1.1"] and flags["d1.2"] and flags["d5.1"] and flags["d6.2"]
    assert not any(flags[k] for k in ("d1b.1", "d1.3", "d2.1", "d2.2", "d2.3"))


def test_obfuscated_other_sessions_never_receive_credit():
    """'Other' is what GA4 hides in its public sample ('<Other>', '(data deleted)'): skipped like Direct."""
    def s(key, dev, ts, ch):
        ts = T(ts)
        return dict(session_key=key, user_pseudo_id=dev, session_date=ts.date(), session_start_ts=ts, channel_group=ch,
                    source="<Other>", medium="<Other>", campaign=None, ad_campaign_key=None, is_paid=False)
    ss = pd.DataFrame([s("a.1", "a", "2020-11-01 10:00:00", "Paid Social"), s("a.2", "a", "2020-11-03 10:00:00", "Other"),
                       s("b.1", "b", "2020-11-01 10:00:00", "Other")])
    o = lambda oid, c, ts: dict(order_id=oid, customer_id=c, order_ts=T(ts), order_date=T(ts).date(), order_channel="app",  # noqa: E731
                                ga4_match_status="app_order", is_refunded=False, order_value_usd=10.0, net_revenue_usd=10.0,
                                ga_user_pseudo_id=None, ga_session_key=None)
    od = pd.DataFrame([o("P1", "CA", "2020-11-04 10:00:00"), o("P2", "CB", "2020-11-04 10:00:00")])
    lk = pd.DataFrame([dict(user_pseudo_id="a", customer_id="CA"), dict(user_pseudo_id="b", customer_id="CB")])
    tp_ = run(TP_SQL, fct_orders=od, stg_identity__links=lk, fct_sessions=ss)
    cr_ = run(CR_SQL, fct_orders=od, int_conversion_touchpoints=tp_)
    got = {(r.conversion_id, r.model): (r.credited_channel, r.attribution_basis) for r in cr_.itertuples()}
    assert got[("P1", "first_touch")] == ("Paid Social", "known_source")
    assert got[("P1", "last_touch")] == ("Paid Social", "known_source")              # the later Other session is skipped
    assert got[("P2", "last_touch")] == ("Direct / Unknown", "direct_or_unknown")    # only Other: nothing to credit


def test_purchase_session_flag_is_never_null_even_for_orders_without_a_ga4_session(tp):
    assert tp["is_purchase_session"].notna().all()
    assert not tp[tp["order_id"].isin(["O2", "O3"])]["is_purchase_session"].any()      # app orders: no purchasing session


def test_purchase_session_flag_and_days(tp):
    r = tp[(tp["order_id"] == "O1") & (tp["session_key"] == "d1.3")].iloc[0]
    assert r["is_purchase_session"] and r["days_before_order"] == pytest.approx(2 / 24)
    assert not tp[(tp["order_id"] == "O1") & (tp["session_key"] == "d1.1")].iloc[0]["is_purchase_session"]


# ----------------------------------------------------------------------------- the credits
def credit(cr, order, model):
    return cr[(cr["conversion_id"] == order) & (cr["model"] == model)].iloc[0]


def test_every_order_has_one_row_per_model_with_full_credit(cr):
    assert len(cr) == 12 and cr.groupby(["conversion_id", "model"]).size().eq(1).all()
    assert (cr["credit"] == 1.0).all()


def test_first_touch_is_the_earliest_known_source_last_touch_the_latest(cr):
    assert credit(cr, "O1", "first_touch")["credited_channel"] == "Paid Search"
    assert credit(cr, "O1", "first_touch")["touchpoint_session_key"] == "d1.1"
    assert credit(cr, "O1", "last_touch")["credited_channel"] == "Organic Search"      # skips Direct (purchase session)
    assert credit(cr, "O1", "last_touch")["touchpoint_session_key"] == "d1.2"
    assert credit(cr, "O1", "last_touch")["attribution_basis"] == "known_source"


def test_app_order_gets_the_same_journey_through_linked_devices(cr):
    assert credit(cr, "O2", "first_touch")["credited_channel"] == "Paid Search"
    assert credit(cr, "O2", "last_touch")["credited_channel"] == "Organic Search"
    assert credit(cr, "O2", "last_touch")["ga4_match_status"] == "app_order"


def test_a_journey_with_only_unknown_sources_goes_to_direct_unknown(cr):
    f, l = credit(cr, "O3", "first_touch"), credit(cr, "O3", "last_touch")
    assert (f["credited_channel"], f["attribution_basis"], f["touchpoint_session_key"]) == ("Direct / Unknown", "direct_or_unknown", "d2.1")
    assert (l["credited_channel"], l["touchpoint_session_key"]) == ("Direct / Unknown", "d2.3")
    assert f["touchpoint_channel_group"] == "Self Referral"      # the session is still described as it was


def test_an_order_with_no_touchpoint_is_kept_as_no_touchpoint(cr):
    for m in ("first_touch", "last_touch"):
        r = credit(cr, "O4", m)
        assert (r["credited_channel"], r["attribution_basis"]) == ("No Touchpoint", "no_touchpoint")
        assert pd.isna(r["touchpoint_session_key"]) and not r["is_paid"]


def test_single_touch_orders_give_the_same_credit_under_both_models(cr):
    for m in ("first_touch", "last_touch"):
        assert credit(cr, "O5", m)["credited_channel"] == "Paid Search" and credit(cr, "O5", m)["is_paid"]
        assert credit(cr, "O5", m)["ad_campaign_key"] == "Paid Search|google|cpc|c"


def test_credited_revenue_is_net_revenue(cr):
    assert credit(cr, "O2", "first_touch")["credited_revenue_usd"] == 50.0 and credit(cr, "O2", "first_touch")["order_value_usd"] == 60.0
    assert cr.groupby("model")["credited_revenue_usd"].sum().to_dict() == {"first_touch": 325.0, "last_touch": 325.0}


# ----------------------------------------------------------------------------- the summaries
def test_by_channel_adds_up_and_shows_the_two_models_side_by_side(cr):
    out = run(CH_SQL, fct_attribution_credits=cr)
    for m, g in out.groupby("model"):
        assert g["attributed_orders"].sum() == 6 and g["share_of_orders"].sum() == pytest.approx(1)
        assert g["attributed_revenue_usd"].sum() == pytest.approx(325.0) and g["share_of_revenue"].sum() == pytest.approx(1)
    row = lambda m, c: out[(out["model"] == m) & (out["credited_channel"] == c)].iloc[0]   # noqa: E731
    assert row("first_touch", "Paid Search")["attributed_orders"] == 3          # O1, O2, O5
    assert row("last_touch", "Organic Search")["attributed_orders"] == 2        # O1, O2
    assert row("last_touch", "Display")["attributed_orders"] == 1 and row("first_touch", "Referral")["attributed_orders"] == 1
    assert out[(out["model"] == "first_touch") & (out["credited_channel"] == "Display")].empty


def test_journeys_show_where_the_models_disagree(tp, cr):
    out = run(JR_SQL, fct_orders=orders(), int_conversion_touchpoints=tp, fct_attribution_credits=cr).set_index("order_id")
    assert out.loc["O1", ["touchpoints", "source_touchpoints", "distinct_source_channels"]].tolist() == [4, 2, 2]
    assert out.loc["O1", "first_and_last_differ"] and not out.loc["O5", "first_and_last_differ"]
    assert out.loc["O4", "touchpoints"] == 0 and pd.isna(out.loc["O4", "days_from_first_touchpoint"])
    assert out.loc["O1", "days_from_first_touchpoint"] == pytest.approx(5 + 2 / 24)
    assert len(out) == 6


# ----------------------------------------------------------------------------- schema and hygiene
@pytest.mark.parametrize("model,sql,sub", [("int_conversion_touchpoints", TP_SQL, "intermediate"),
                                           ("fct_attribution_credits", CR_SQL, "marts"),
                                           ("fct_attribution_by_channel", CH_SQL, "marts"),
                                           ("fct_attribution_journeys", JR_SQL, "marts")])
def test_models_return_exactly_the_documented_columns(model, sql, sub):
    f = DBT / "models" / sub / ("_intermediate.yml" if sub == "intermediate" else "_marts.yml")
    doc = next(m for m in yaml.safe_load(f.read_text(encoding="utf-8"))["models"] if m["name"] == model)
    got = output_columns(sqlglot.parse_one(render(sql), read="bigquery"))
    want = [c["name"] for c in doc["columns"]]
    assert sorted(got) == sorted(want), set(got) ^ set(want)
    assert all(c.get("description") for c in doc["columns"])


def test_the_models_never_read_the_ground_truth():
    code = "\n".join(l for l in (TP_SQL + CR_SQL + CH_SQL + JR_SQL).splitlines() if not l.strip().startswith("--"))
    assert "ground_truth" not in code


def test_the_docs_page_describes_the_models_and_rules():
    text = (ROOT / "docs" / "attribution.md").read_text(encoding="utf-8")
    for needle in ("fct_attribution_credits", "fct_attribution_by_channel", "First touch", "Last touch", "Self Referral",
                   "Direct", "Unassigned", "Other", "No Touchpoint", "Direct / Unknown", "30 days"):
        assert needle in text, needle


# ----------------------------------------------------------------------------- singular dbt tests
def tables(tp, cr, **extra):
    t = dict(int_conversion_touchpoints=tp, fct_attribution_credits=cr, fct_orders=orders(),
             stg_identity__links=links(), fct_sessions=sessions())
    t.update(extra)
    return t


NAMES = ["assert_attribution_keys_are_unique", "assert_attribution_credits_conserve_orders_and_revenue", "assert_attribution_follows_its_rules",
         "assert_touchpoints_belong_to_the_journey"]


@pytest.mark.parametrize("name", NAMES)
def test_singular_tests_pass_on_good_data(name, tp, cr):
    assert run(SINGULAR[name], **tables(tp, cr, fct_attribution_by_channel=run(CH_SQL, fct_attribution_credits=cr))).empty


def test_catches_lost_or_inflated_credit(tp, cr):
    t = "assert_attribution_credits_conserve_orders_and_revenue"
    assert not run(SINGULAR[t], **tables(tp, cr[cr["conversion_id"] != "O1"])).empty
    broken = cr.copy()
    broken.loc[(broken["conversion_id"] == "O1") & (broken["model"] == "first_touch"), "credit"] = 0.5
    assert not run(SINGULAR[t], **tables(tp, broken)).empty
    broken = cr.copy()
    broken.loc[broken["conversion_id"] == "O1", "credited_revenue_usd"] = 1.0
    assert not run(SINGULAR[t], **tables(tp, broken)).empty
    assert not run(SINGULAR[t], **tables(tp, cr[cr["model"] == "first_touch"])).empty


def test_catches_a_credit_that_breaks_its_rule(tp, cr):
    t = "assert_attribution_follows_its_rules"

    def mutate(order, model, **changes):
        b = cr.copy()
        mask = (b["conversion_id"] == order) & (b["model"] == model)
        for k, v in changes.items():
            b.loc[mask, k] = v
        return b
    wrong = {
        "later session credited as first touch": mutate("O1", "first_touch", touchpoint_session_key="d1.2",
                                                         credited_channel="Organic Search"),
        "earlier session credited as last touch": mutate("O1", "last_touch", touchpoint_session_key="d1.1",
                                                          credited_channel="Paid Search"),
        "channel disagrees with its session": mutate("O1", "first_touch", credited_channel="Email"),
        "unknown-source session credited though a source exists": mutate("O1", "last_touch", touchpoint_session_key="d1.3",
                                                                          credited_channel="Direct"),
        "fallback although a known source exists": mutate("O1", "first_touch", attribution_basis="direct_or_unknown",
                                                           credited_channel="Direct / Unknown"),
        "no touchpoint although touchpoints exist": mutate("O1", "first_touch", attribution_basis="no_touchpoint",
                                                            credited_channel="No Touchpoint", touchpoint_session_key=None),
    }
    for why, broken in wrong.items():
        assert not run(SINGULAR[t], **tables(tp, broken)).empty, why


def test_catches_touchpoints_that_do_not_belong(tp, cr):
    t = "assert_touchpoints_belong_to_the_journey"
    row = lambda **kw: pd.concat([tp, pd.DataFrame([{**tp[(tp["order_id"] == "O1") & (tp["session_key"] == "d1.1")].iloc[0].to_dict(), **kw}])])  # noqa: E731
    cases = {
        "someone else's device": row(session_key="x.1", user_pseudo_id="x"),
        "after the order": row(session_key="d1.4", session_start_ts=T("2020-11-25 10:00:00")),
        "outside the window": row(session_key="d1.0", days_before_order=40.0),
        "duplicate": row(),
        "missing purchase session": tp[~((tp["order_id"] == "O1") & (tp["session_key"] == "d1.3"))],
    }
    for why, broken in cases.items():
        assert not run(SINGULAR[t], **tables(broken, cr)).empty, why


def test_catches_a_duplicated_key(tp, cr):
    t = "assert_attribution_keys_are_unique"
    by = run(CH_SQL, fct_attribution_credits=cr)
    good = dict(**tables(tp, cr), fct_attribution_by_channel=by)
    assert run(SINGULAR[t], **good).empty
    for name, bad in (("int_conversion_touchpoints", pd.concat([tp, tp.iloc[[0]]])),
                      ("fct_attribution_credits", pd.concat([cr, cr.iloc[[0]]])),
                      ("fct_attribution_by_channel", pd.concat([by, by.iloc[[0]]]))):
        out = run(SINGULAR[t], **{**good, name: bad})
        assert list(out["model"]) == [name]

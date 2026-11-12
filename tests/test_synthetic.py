"""Tests for the synthetic CRM, orders, ad-spend and Segment-style data generator.

A small fake GA4 extract stands in for the real one, so no Google Cloud login is needed.
The tests check that the output is repeatable, internally consistent (every order has a
customer, every identify event matches a ground-truth link), tied to the GA4 purchases it
came from, and that the assumptions in config.py show up in the numbers.
"""

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.synthetic import generate_crm as g  # noqa: E402
from src.synthetic.channels import PAID_CHANNELS, channel_group  # noqa: E402
from src.synthetic.config import Config  # noqa: E402


def fake_extract(n_users=4000, seed=7):
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2020-11-01", tz="UTC")
    end = pd.Timestamp("2021-01-31 23:00", tz="UTC")
    countries = ["United States", "India", "Canada", "United Kingdom", "(not set)"]
    first = start + pd.to_timedelta(rng.uniform(0, 85, n_users), unit="D")
    last = first + pd.to_timedelta(rng.uniform(0, 5, n_users), unit="D")
    last = last.where(last < end, end)
    users = pd.DataFrame({
        "user_pseudo_id": [f"{1000000 + i}.{2000000 + i}" for i in range(n_users)],
        "first_seen_ts": first, "last_seen_ts": last,
        "sessions": rng.integers(1, 6, n_users), "purchase_events": 0,
        "country": rng.choice(countries, n_users, p=[0.4, 0.2, 0.15, 0.15, 0.1]),
        "device_category": rng.choice(["desktop", "mobile"], n_users),
        "source": rng.choice(["google", "(direct)", "facebook", "shop.example"], n_users),
        "medium": rng.choice(["cpc", "organic", "(none)", "referral", "cpm"], n_users),
        "campaign": rng.choice(["(organic)", "(direct)", "Summer", "Winter", "<Other>"], n_users),
    })
    buyer_idx = rng.choice(n_users, size=int(n_users * 0.08), replace=False)
    rows = []
    for i in buyer_idx:
        for _ in range(int(rng.integers(1, 4))):
            ts = first[i] + (last[i] - first[i]) * float(rng.uniform(0.3, 1.0))
            rows.append({"transaction_id": f"T{len(rows):06d}", "user_pseudo_id": users.at[i, "user_pseudo_id"],
                         "event_ts": ts, "revenue_usd": round(float(rng.lognormal(4, 0.6)), 2),
                         "item_quantity": int(rng.integers(1, 5))})
    purchases = pd.DataFrame(rows)
    days = pd.date_range("2020-11-01", "2021-01-31")
    traffic = pd.DataFrame([
        {"date": d, "source": s, "medium": m, "campaign": c, "sessions": int(rng.integers(1, 400))}
        for d in days for s, m, c in [("google", "cpc", "Summer"), ("google", "organic", "(organic)"),
                                      ("(direct)", "(none)", "(direct)"), ("facebook", "cpm", "Winter")]])
    return users, purchases, traffic


@pytest.fixture(scope="module")
def data():
    return fake_extract()


@pytest.fixture(scope="module")
def result(data):
    return g.generate(*data)


def test_output_is_repeatable(data, tmp_path):
    a = g.generate(*data)
    b = g.generate(*data)
    pa, pb = tmp_path / "a", tmp_path / "b"
    g.write_outputs(a, pa)
    g.write_outputs(b, pb)
    for f in sorted(p.relative_to(pa) for p in pa.rglob("*") if p.is_file()):
        assert hashlib.sha256((pa / f).read_bytes()).hexdigest() == hashlib.sha256((pb / f).read_bytes()).hexdigest()


def test_different_seed_changes_output(data):
    a = g.generate(*data, Config(seed=1))["crm_customers"]
    b = g.generate(*data, Config(seed=2))["crm_customers"]
    assert not a["email"].equals(b["email"])


def test_every_order_has_a_customer_and_ids_are_unique(result):
    c, o = result["crm_customers"], result["crm_orders"]
    assert c["customer_id"].is_unique and o["order_id"].is_unique and c["email"].is_unique
    assert set(o["customer_id"]) <= set(c["customer_id"])


def test_web_orders_are_real_ga4_purchases(data, result):
    _, purchases, _ = data
    web = result["crm_orders"].query("order_channel == 'web'").dropna(subset=["ga_transaction_id"])
    merged = web.merge(purchases, left_on="ga_transaction_id", right_on="transaction_id")
    assert len(merged) == len(web) > 0
    assert (merged["order_value_usd"] - merged["revenue_usd"]).abs().max() < 0.01
    assert (pd.to_datetime(merged["order_ts"], utc=True) == merged["event_ts"].dt.floor("s")).all()


def test_guest_buyers_are_not_customers(data, result):
    _, purchases, _ = data
    in_crm = set(result["ground_truth_identity_links"]["user_pseudo_id"])
    guests = set(result["guest_buyers"])
    assert guests and not (guests & in_crm)
    guest_txns = set(purchases[purchases["user_pseudo_id"].isin(guests)]["transaction_id"])
    crm_txns = set(result["crm_orders"]["ga_transaction_id"].dropna())
    assert not (guest_txns & crm_txns)


def test_identify_events_match_ground_truth(result):
    gt = result["ground_truth_identity_links"]
    emitted = gt[gt["identify_emitted"]]
    pairs = {(e["anonymousId"], e["userId"]) for e in result["segment_identifies"]}
    assert pairs == set(zip(emitted["user_pseudo_id"], emitted["customer_id"]))
    assert len(result["segment_identifies"]) == len(emitted)


def test_segment_event_shapes(result):
    for e in result["segment_identifies"][:50]:
        assert e["type"] == "identify" and e["anonymousId"] and e["userId"] and "email" in e["traits"]
        assert e["timestamp"].endswith("Z")
    for e in result["segment_tracks"][:200]:
        assert e["type"] == "track" and e["event"] in ("Signed Up", "Order Completed")
        assert e["userId"] and "anonymousId" not in e
    ids = [e["messageId"] for e in result["segment_identifies"] + result["segment_tracks"]]
    assert len(ids) == len(set(ids))


def test_each_order_has_one_track_event(result):
    n_orders = len(result["crm_orders"])
    n_track = sum(1 for e in result["segment_tracks"] if e["event"] == "Order Completed")
    assert n_orders == n_track


def test_identify_comes_no_later_than_first_web_order_for_new_customers(data, result):
    """A new customer is identified on the device before that device's first purchase."""
    users, purchases, _ = data
    first = purchases.groupby("user_pseudo_id")["event_ts"].min()
    prim = result["segment_identifies"]
    late = [e for e in prim if e["anonymousId"] in first.index
            and pd.Timestamp(e["timestamp"]) > first[e["anonymousId"]] + pd.Timedelta(seconds=1)]
    assert not late


def test_rates_are_close_to_config(result):
    cfg = Config()
    gt = result["ground_truth_identity_links"]
    primary = gt[gt["device_role"] == "primary"]
    assert abs(primary["identify_emitted"].mean() - cfg.identify_capture_rate) < 0.05
    web = result["crm_orders"].query("order_channel == 'web'")
    assert abs(web["ga_transaction_id"].notna().mean() - cfg.txn_id_match_rate) < 0.04
    assert abs((result["crm_orders"]["status"] == "refunded").mean() - cfg.refund_rate) < 0.025
    second = (gt["device_role"] == "second").sum()
    assert 0.03 < second / len(result["crm_customers"]) < 0.12


def test_second_device_is_a_non_buyer_in_the_same_country(data, result):
    users, _, _ = data
    gt = result["ground_truth_identity_links"]
    sec = gt[gt["device_role"] == "second"]
    assert len(sec) > 0 and not sec["has_purchase"].any()
    country = users.set_index("user_pseudo_id")["country"]
    prim_dev = gt[gt["device_role"] == "primary"].set_index("customer_id")["user_pseudo_id"]
    for r in sec.itertuples():
        assert country[r.user_pseudo_id] == country[prim_dev[r.customer_id]]


def test_no_device_belongs_to_two_customers(result):
    gt = result["ground_truth_identity_links"]
    assert gt["user_pseudo_id"].is_unique


def test_ad_spend_only_paid_and_consistent(data, result):
    _, _, traffic = data
    a = result["ad_spend"]
    assert len(a) > 0
    assert set(a["channel"]) <= set(PAID_CHANNELS)
    assert (a["spend_usd"] > 0).all() and (a["impressions"] >= a["clicks"]).all()
    merged = a.merge(traffic.assign(date=traffic["date"].dt.strftime("%Y-%m-%d")), on=["date", "source", "medium", "campaign"])
    assert len(merged) == len(a)
    assert (merged["clicks"] >= merged["sessions"]).all()


def test_ad_spend_empty_without_paid_traffic(data):
    users, purchases, traffic = data
    organic = traffic[traffic["medium"].isin(["organic", "(none)"])]
    out = g.generate(users, purchases, organic)
    assert out["ad_spend"].empty and list(out["ad_spend"].columns)[0] == "date"


def test_written_files_and_ground_truth_location(result, tmp_path):
    paths = g.write_outputs(result, tmp_path)
    names = {p.name for p in paths}
    assert names == {"crm_customers.csv", "crm_orders.csv", "ad_spend.csv", "ground_truth_identity_links.csv",
                     "segment_identifies.jsonl", "segment_tracks.jsonl"}
    assert (tmp_path / "ground_truth" / "ground_truth_identity_links.csv").exists()
    first = (tmp_path / "segment_identifies.jsonl").read_text().splitlines()[0]
    assert json.loads(first)["type"] == "identify"


def test_channel_groups():
    assert channel_group("google", "cpc") == "Paid Search"
    assert channel_group("google", "organic") == "Organic Search"
    assert channel_group("(direct)", "(none)") == "Direct"
    assert channel_group("x", "<Other>") == "Other"
    assert channel_group("(data deleted)", "(data deleted)") == "Other"
    assert channel_group("facebook", "cpm") == "Display"
    assert channel_group("googleads.g.doubleclick.net", "referral") == "Display"
    assert channel_group("Partners", "affiliate") == "Affiliate"
    assert channel_group("Newsletter_January_2021", "email") == "Email"
    assert channel_group("l.facebook.com", "referral") == "Organic Social"
    assert channel_group("shop.googlemerchandisestore.com", "referral") == "Self Referral"
    assert channel_group("shop.googlemerchandisestore.com", "organic") == "Self Referral"
    assert channel_group("googlemerchandisestore.com", "referral") == "Self Referral"
    assert channel_group("analytics.google.com", "referral") == "Referral"


def test_nan_from_csv_is_treated_as_missing():
    nan = float("nan")
    assert channel_group(nan, nan) == "Unassigned"
    assert channel_group(nan, "organic") == "Organic Search"
    assert channel_group("google", nan) == "Other"


def test_ad_spend_handles_empty_csv_cells_and_keeps_one_cost_per_campaign(data, tmp_path):
    """Empty cells arrive as NaN after a CSV round trip; a campaign must keep one base cost per click."""
    users, purchases, traffic = data
    path = tmp_path / "t.csv"
    traffic.assign(campaign=None).to_csv(path, index=False)          # campaign column all empty
    back = pd.read_csv(path, parse_dates=["date"])
    spend = g.generate(users, purchases, back)["ad_spend"]
    assert len(spend) > 0
    cpc = spend["spend_usd"] / spend["clicks"]
    for _, grp in (spend.assign(cpc=cpc)).groupby(["channel", "source", "medium"]):
        # Daily noise is about 10%. A fresh cost drawn on every row would spread far wider (about 38%).
        assert grp["cpc"].std() / grp["cpc"].mean() < 0.2


def test_sessions_without_source_are_unassigned_not_guessed():
    assert channel_group(None, None) == "Unassigned"
    assert channel_group("", "") == "Unassigned"
    assert channel_group(None, "organic") == "Organic Search"


def test_cli_end_to_end(data, tmp_path, capsys):
    users, purchases, traffic = data
    ex = tmp_path / "ex"
    ex.mkdir()
    users.to_csv(ex / "users.csv", index=False)
    purchases.to_csv(ex / "purchases.csv", index=False)
    traffic.to_csv(ex / "daily_traffic.csv", index=False)
    assert g.main(["--extract-dir", str(ex), "--out-dir", str(tmp_path / "out")]) == 0
    assert "customers" in capsys.readouterr().out
    assert g.main(["--extract-dir", str(tmp_path / "nothing"), "--out-dir", str(tmp_path / "o2")]) == 1


# ------------------------------------------------------------ extract SQL

EXTRACT_SQL = sorted((ROOT / "sql" / "ga4_extract").glob("*.sql"))


def test_extract_files_and_names():
    from src.synthetic import ga4_extract as ex
    names = {name for name, _ in ex.load_extract_queries()}
    assert names == {"users.csv", "purchases.csv", "daily_traffic.csv"}
    assert ex.output_name("SELECT 1", "abc") == "abc.csv"


@pytest.mark.parametrize("path", EXTRACT_SQL, ids=lambda p: p.stem)
def test_extract_sql_is_read_only_public_data_and_valid(path):
    import re
    sql = path.read_text(encoding="utf-8")
    code = "\n".join(l for l in sql.splitlines() if not l.strip().startswith("--"))
    assert re.match(r"\s*(SELECT|WITH)\b", code, re.I)
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE)\b", code, re.I)
    assert set(re.findall(r"`([^`]+)`", code)) == {"bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*"}
    sqlglot = pytest.importorskip("sqlglot")
    sqlglot.parse_one(sql, read="bigquery")


def test_ids_keep_trailing_zeros_after_csv_round_trip(data, tmp_path):
    """GA4 ids such as '1234567.8901230' must not be read as numbers, or joins to GA4 silently fail."""
    users, purchases, traffic = data
    users = users.copy()
    purchases = purchases.copy()
    users.loc[users.index[:50], "user_pseudo_id"] = [f"{5000000 + i}.{1234500 + i * 10}0" for i in range(50)]
    purchases["user_pseudo_id"] = purchases["user_pseudo_id"].astype(str)
    purchases["transaction_id"] = ["0012%d" % i for i in range(len(purchases))]
    users.to_csv(tmp_path / "users.csv", index=False)
    purchases.to_csv(tmp_path / "purchases.csv", index=False)
    traffic.to_csv(tmp_path / "daily_traffic.csv", index=False)
    u, p, _ = g.read_extract(tmp_path)
    assert u["user_pseudo_id"].tolist() == users["user_pseudo_id"].tolist()
    assert p["transaction_id"].tolist() == purchases["transaction_id"].tolist()
    assert all(isinstance(v, str) for v in u["user_pseudo_id"])

"""Generate the synthetic CRM, orders, ad-spend and Segment-style event data.

Everything is built on real GA4 facts (users, purchases, daily traffic) from
``data/raw/ga4_extract/`` so the synthetic data lines up with the real sessions:

* CRM customers are real GA4 buyers (minus guest checkouts) plus a few non-buyers who register.
* CRM web orders are the real GA4 purchases (same time, same revenue), so website and CRM tell one story.
* Some customers use a second device (a different GA4 user), which identity resolution must link.
* Segment-style ``identify`` events connect a device (anonymousId) to a customer (userId), but are
  only captured for part of the links, so no step can find every match.
* Ad spend is generated for paid channels from the real daily sessions of those channels.
* ``ground_truth_identity_links.csv`` records the true links. It is for measuring accuracy only; no model may read it.

Run (repository root)::

    uv run python -m src.synthetic.generate_crm

All random choices come from one seed, so the output is identical on every run.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from src.synthetic.channels import PAID_CHANNELS, channel_group
from src.synthetic.config import Config

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EXTRACT = ROOT / "data" / "raw" / "ga4_extract"
DEFAULT_OUT = ROOT / "data" / "synthetic"


# ---------------------------------------------------------------- helpers

def _between(rng, start: pd.Timestamp, end: pd.Timestamp) -> pd.Timestamp:
    """A random moment between two timestamps (start if the range is empty)."""
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return start
    return start + pd.Timedelta(seconds=float(rng.uniform(0, seconds)))


def _iso(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _clean_country(value, fake) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)) or str(value) in ("(not set)", ""):
        return fake.country()
    return str(value)


def read_extract(extract_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    users = pd.read_csv(extract_dir / "users.csv")
    purchases = pd.read_csv(extract_dir / "purchases.csv")
    traffic = pd.read_csv(extract_dir / "daily_traffic.csv")
    for col in ("first_seen_ts", "last_seen_ts"):
        users[col] = pd.to_datetime(users[col], utc=True)
    purchases["event_ts"] = pd.to_datetime(purchases["event_ts"], utc=True)
    traffic["date"] = pd.to_datetime(traffic["date"])
    return users, purchases, traffic


# ---------------------------------------------------------------- customers, orders, events

def build_customers(users: pd.DataFrame, purchases: pd.DataFrame, cfg: Config, rng, fake):
    """Pick who becomes a customer and create customers, device links and identify events."""
    users = users.sort_values("user_pseudo_id").reset_index(drop=True)
    by_id = users.set_index("user_pseudo_id")
    first_purchase = purchases.groupby("user_pseudo_id")["event_ts"].min()

    buyers = sorted(first_purchase.index)
    guest = rng.random(len(buyers)) < cfg.guest_checkout_rate
    crm_buyers = [b for b, g in zip(buyers, guest) if not g]
    guest_buyers = [b for b, g in zip(buyers, guest) if g]

    buyer_set = set(buyers)
    nonbuyers = users[~users["user_pseudo_id"].isin(buyer_set)]
    signup = rng.random(len(nonbuyers)) < cfg.nonbuyer_signup_rate
    signup_ids = nonbuyers["user_pseudo_id"][signup].tolist()

    # Customer numbers follow the order in which customers first show up.
    primaries = crm_buyers + signup_ids
    primaries.sort(key=lambda d: (first_purchase.get(d, by_id.at[d, "first_seen_ts"]), d))

    # Second-device pool: non-buyers who did not register, grouped by country.
    used = set(primaries)
    pool: dict[str, list[str]] = {}
    for d, c in zip(nonbuyers["user_pseudo_id"], nonbuyers["country"]):
        if d not in used:
            pool.setdefault(str(c), []).append(d)
    for c in sorted(pool):
        pool[c] = [pool[c][i] for i in rng.permutation(len(pool[c]))]

    customers, links, identifies = [], [], []
    emails: set[str] = set()
    msg = 0

    def next_msg() -> str:
        nonlocal msg
        msg += 1
        return f"msg-{cfg.seed}-{msg:07d}"

    for n, dev in enumerate(primaries, 1):
        cid = f"C{n:06d}"
        u = by_id.loc[dev]
        is_buyer = dev in buyer_set
        existing = bool(rng.random() < cfg.existing_customer_rate) and is_buyer
        seen_first, seen_last = u["first_seen_ts"], u["last_seen_ts"]

        if is_buyer:
            fp = first_purchase[dev]
            if existing:
                created = seen_first - pd.Timedelta(days=int(rng.integers(30, 900)))
                ident_ts = min(seen_first + pd.Timedelta(seconds=float(rng.uniform(30, 600))), max(fp - pd.Timedelta(seconds=1), seen_first))
            else:
                if rng.random() < 0.65:
                    created = fp - pd.Timedelta(minutes=float(rng.uniform(1, 30)))
                else:
                    created = _between(rng, seen_first, fp - pd.Timedelta(minutes=1))
                created = min(max(created, seen_first), fp)
                ident_ts = created
        else:
            created = _between(rng, seen_first, seen_last)
            ident_ts = created

        first = fake.first_name()
        last = fake.last_name()
        base = f"{first}.{last}".lower().replace(" ", "").replace("'", "")
        email = f"{base}@{fake.free_email_domain()}"
        k = 1
        while email in emails:
            k += 1
            email = f"{base}{k}@{fake.free_email_domain()}"
        emails.add(email)
        email_hash = hashlib.sha256(email.encode()).hexdigest()
        country = _clean_country(u["country"], fake)
        customers.append({
            "customer_id": cid, "first_name": first, "last_name": last, "email": email,
            "email_sha256": email_hash, "phone": fake.phone_number(), "country": country,
            "created_at": created.strftime("%Y-%m-%d %H:%M:%S"),
            "marketing_opt_in": bool(rng.random() < cfg.marketing_opt_in_rate),
        })

        def add_link(device: str, role: str, when: pd.Timestamp, captured: bool):
            links.append({"customer_id": cid, "user_pseudo_id": device, "device_role": role,
                          "has_purchase": device in buyer_set, "identify_emitted": captured})
            if captured:
                identifies.append({
                    "type": "identify", "messageId": next_msg(), "timestamp": _iso(when),
                    "anonymousId": device, "userId": cid,
                    "traits": {"email": email, "emailSha256": email_hash, "firstName": first,
                               "lastName": last, "country": country, "createdAt": _iso(created)},
                    "context": {"library": {"name": "synthetic-segment-generator", "version": "1.0"}},
                })

        add_link(dev, "primary", ident_ts, bool(rng.random() < cfg.identify_capture_rate))

        second = None
        if rng.random() < cfg.multi_device_rate and pool.get(str(u["country"])):
            second = pool[str(u["country"])].pop()
        if second is not None:
            s = by_id.loc[second]
            add_link(second, "second", _between(rng, s["first_seen_ts"], s["last_seen_ts"]),
                     bool(rng.random() < cfg.second_device_capture_rate))

    return pd.DataFrame(customers), pd.DataFrame(links), identifies, guest_buyers


def build_orders(customers: pd.DataFrame, links: pd.DataFrame, purchases: pd.DataFrame,
                 window_start: pd.Timestamp, window_end: pd.Timestamp, cfg: Config, rng) -> pd.DataFrame:
    """Web orders come from real GA4 purchases; app orders are extra purchases GA4 never sees."""
    device_to_customer = links[links["device_role"] == "primary"].set_index("user_pseudo_id")["customer_id"]
    web = purchases[purchases["user_pseudo_id"].isin(device_to_customer.index)].copy()
    web["customer_id"] = web["user_pseudo_id"].map(device_to_customer)
    web = web.sort_values(["event_ts", "transaction_id"]).reset_index(drop=True)
    match = rng.random(len(web)) < cfg.txn_id_match_rate
    rows = [{
        "customer_id": r.customer_id, "order_ts": r.event_ts, "order_channel": "web",
        "ga_transaction_id": r.transaction_id if m else None,
        "order_value_usd": round(float(r.revenue_usd), 2),
        "item_count": int(r.item_quantity) if pd.notna(r.item_quantity) and r.item_quantity > 0 else 1,
    } for r, m in zip(web.itertuples(index=False), match)]

    values = web["revenue_usd"].to_numpy(dtype=float)
    created = pd.to_datetime(customers.set_index("customer_id")["created_at"], utc=True)
    for cid in customers["customer_id"]:
        for _ in range(int(rng.poisson(cfg.app_orders_mean))):
            start = max(created[cid], window_start)
            value = float(rng.choice(values) * rng.uniform(0.7, 1.3)) if len(values) else float(rng.lognormal(4, 0.5))
            rows.append({"customer_id": cid, "order_ts": _between(rng, start, window_end),
                         "order_channel": "app", "ga_transaction_id": None,
                         "order_value_usd": round(value, 2), "item_count": 1 + int(rng.poisson(1.0))})

    orders = pd.DataFrame(rows).sort_values(["order_ts", "customer_id"]).reset_index(drop=True)
    orders.insert(0, "order_id", [f"O{i:07d}" for i in range(1, len(orders) + 1)])
    refunded = rng.random(len(orders)) < cfg.refund_rate
    orders["status"] = np.where(refunded, "refunded", "completed")
    orders["refund_usd"] = np.where(refunded, orders["order_value_usd"], 0.0)
    orders["order_ts"] = orders["order_ts"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return orders


def build_tracks(customers: pd.DataFrame, orders: pd.DataFrame, window_start: pd.Timestamp, cfg: Config) -> list[dict]:
    """Segment-style track events sent from the server, so they carry userId only (no anonymousId)."""
    tracks, n = [], 0
    ctx = {"library": {"name": "synthetic-segment-generator", "version": "1.0"}}

    def mid() -> str:
        nonlocal n
        n += 1
        return f"trk-{cfg.seed}-{n:07d}"

    for c in customers.itertuples(index=False):
        created = pd.Timestamp(c.created_at, tz="UTC")
        if created >= window_start:
            tracks.append({"type": "track", "event": "Signed Up", "messageId": mid(),
                           "timestamp": _iso(created), "userId": c.customer_id,
                           "properties": {"email_opt_in": bool(c.marketing_opt_in)}, "context": ctx})
    for o in orders.itertuples(index=False):
        tracks.append({"type": "track", "event": "Order Completed", "messageId": mid(),
                       "timestamp": _iso(pd.Timestamp(o.order_ts, tz="UTC")), "userId": o.customer_id,
                       "properties": {"order_id": o.order_id, "revenue": o.order_value_usd, "currency": "USD",
                                      "channel": o.order_channel, "status": o.status},
                       "context": ctx})
    tracks.sort(key=lambda t: (t["timestamp"], t["messageId"]))
    return tracks


def build_ad_spend(traffic: pd.DataFrame, cfg: Config, rng) -> pd.DataFrame:
    """Daily spend for paid channels, sized from the real sessions each paid campaign received."""
    t = traffic.copy()
    for col in ("source", "medium", "campaign"):
        t[col] = pd.Series([None if pd.isna(v) else v for v in t[col]], index=t.index, dtype=object)
    t["channel"] = [channel_group(s, m) for s, m in zip(t["source"], t["medium"])]
    t = t[t["channel"].isin(PAID_CHANNELS)].sort_values(["date", "source", "medium", "campaign"])

    base: dict[tuple, tuple[float, float]] = {}
    rows = []
    for r in t.itertuples(index=False):
        key = (r.channel, r.source, r.medium, r.campaign)
        if key not in base:
            p = PAID_CHANNELS[r.channel]
            base[key] = (float(rng.uniform(*p["cpc"])), float(rng.uniform(*p["ctr"])))
        cpc, ctr = base[key]
        clicks = max(1, int(round(r.sessions * rng.uniform(cfg.click_per_session_low, cfg.click_per_session_high))))
        cpc_day = cpc * float(rng.lognormal(0, cfg.daily_noise_sigma))
        ctr_day = min(0.5, ctr * float(rng.lognormal(0, cfg.daily_noise_sigma)))
        rows.append({"date": r.date.strftime("%Y-%m-%d"), "channel": r.channel, "source": r.source,
                     "medium": r.medium, "campaign": r.campaign,
                     "impressions": int(round(clicks / ctr_day)), "clicks": clicks,
                     "spend_usd": round(clicks * cpc_day, 2)})
    cols = ["date", "channel", "source", "medium", "campaign", "impressions", "clicks", "spend_usd"]
    return pd.DataFrame(rows, columns=cols)


# ---------------------------------------------------------------- run

def generate(users: pd.DataFrame, purchases: pd.DataFrame, traffic: pd.DataFrame, cfg: Config = Config()) -> dict:
    rng = np.random.default_rng(cfg.seed)
    fake = Faker("en_US")
    fake.seed_instance(cfg.seed)

    window_start = users["first_seen_ts"].min().normalize()
    window_end = users["last_seen_ts"].max()

    customers, links, identifies, guests = build_customers(users, purchases, cfg, rng, fake)
    orders = build_orders(customers, links, purchases, window_start, window_end, cfg, rng)
    tracks = build_tracks(customers, orders, window_start, cfg)
    ad_spend = build_ad_spend(traffic, cfg, rng)
    identifies.sort(key=lambda e: (e["timestamp"], e["messageId"]))
    return {"crm_customers": customers, "crm_orders": orders, "ad_spend": ad_spend,
            "ground_truth_identity_links": links, "segment_identifies": identifies,
            "segment_tracks": tracks, "guest_buyers": guests}


def write_outputs(result: dict, out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for name in ("crm_customers", "crm_orders", "ad_spend"):
        p = out_dir / f"{name}.csv"
        result[name].to_csv(p, index=False, lineterminator="\n")
        written.append(p)
    gt_dir = out_dir / "ground_truth"
    gt_dir.mkdir(exist_ok=True)
    p = gt_dir / "ground_truth_identity_links.csv"
    result["ground_truth_identity_links"].to_csv(p, index=False, lineterminator="\n")
    written.append(p)
    for name in ("segment_identifies", "segment_tracks"):
        p = out_dir / f"{name}.jsonl"
        p.write_text("".join(json.dumps(e, sort_keys=True) + "\n" for e in result[name]), encoding="utf-8")
        written.append(p)
    return written


def summarise(result: dict) -> dict:
    c, o, a, g = (result[k] for k in ("crm_customers", "crm_orders", "ad_spend", "ground_truth_identity_links"))
    web = o[o["order_channel"] == "web"]
    return {
        "customers": len(c),
        "guest_buyers_not_in_crm": len(result["guest_buyers"]),
        "device_links": len(g),
        "second_device_links": int((g["device_role"] == "second").sum()),
        "identify_events": len(result["segment_identifies"]),
        "links_without_identify": int((~g["identify_emitted"]).sum()),
        "orders": len(o), "web_orders": len(web), "app_orders": int((o["order_channel"] == "app").sum()),
        "web_orders_with_txn_id": int(web["ga_transaction_id"].notna().sum()),
        "refunded_orders": int((o["status"] == "refunded").sum()),
        "track_events": len(result["segment_tracks"]),
        "ad_spend_rows": len(a), "paid_campaigns": int(a[["channel", "source", "medium", "campaign"]].drop_duplicates().shape[0]) if len(a) else 0,
        "total_ad_spend_usd": round(float(a["spend_usd"].sum()), 2) if len(a) else 0.0,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--extract-dir", type=Path, default=DEFAULT_EXTRACT)
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--seed", type=int, default=Config().seed)
    args = ap.parse_args(argv)

    needed = ["users.csv", "purchases.csv", "daily_traffic.csv"]
    missing = [f for f in needed if not (args.extract_dir / f).exists()]
    if missing:
        print(f"Missing {missing} in {args.extract_dir}. Run: uv run python -m src.synthetic.ga4_extract")
        return 1
    users, purchases, traffic = read_extract(args.extract_dir)
    result = generate(users, purchases, traffic, Config(seed=args.seed))
    for p in write_outputs(result, args.out_dir):
        print(f"wrote {p.relative_to(ROOT) if p.is_relative_to(ROOT) else p}")
    print()
    for k, v in summarise(result).items():
        print(f"{k:28s} {v:,}" if isinstance(v, int) else f"{k:28s} {v}")
    if result["ad_spend"].empty:
        print("\nWARNING: no paid-channel traffic found, so ad_spend.csv is empty. Send me the GA4 exploration results.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

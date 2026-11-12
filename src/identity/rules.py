"""Identity resolution: decide which GA4 devices (``user_pseudo_id``) belong to which CRM customer.

GA4 never tells us who a visitor is (``user_id`` is empty for every device in the sample), so the
link has to come from two other sources:

* Segment ``identify`` events: a device (``anonymousId``) is tied to a customer (``userId``),
  usually with the customer's hashed email (``traits.emailSha256``).
* CRM orders that carry the GA4 ``transaction_id``: the purchase event in GA4 tells us which
  device placed the order, and the order tells us which customer it was.

The rules below turn those signals into one row per (device, customer) link. Every rule is
deterministic. Nothing here guesses, and nothing here may read the ground-truth file: it exists
only to score the result (see ``score.py``).

Rule table (higher score = stronger evidence)::

    identify_verified    3   identify event whose userId is a customer AND whose email hash matches that customer
    order_match          3   CRM order's GA4 transaction id found on a GA4 purchase (earliest device if it fired on several)
    identify_unverified  2   identify event with a valid userId but no (or an unknown) email hash
    email_hash           2   identify event with no valid userId, but an email hash that matches one customer

An identify event whose userId and email hash point to DIFFERENT customers is rejected.
A device linked to several customers keeps the customer with the most evidence; the rest are rejected.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

RULE_SCORE = {"identify_verified": 3, "order_match": 3, "identify_unverified": 2, "email_hash": 2}
HIGH_CONFIDENCE_RULES = {"identify_verified", "order_match"}

LINK_COLUMNS = ["user_pseudo_id", "customer_id", "link_rule", "evidence_rules", "confidence",
                "evidence_count", "first_evidence_ts", "had_conflict"]
REJECTED_COLUMNS = ["source", "user_pseudo_id", "customer_id", "reason", "detail"]


@dataclass
class Result:
    links: pd.DataFrame       # one row per device that was linked to a customer
    rejected: pd.DataFrame    # evidence that was NOT used, with the reason


def _clean(series: pd.Series) -> pd.Series:
    """Blank and missing values become None, so they never match anything."""
    s = series.astype("object").where(series.notna(), None)
    return s.map(lambda v: None if v is None or str(v).strip() == "" else str(v).strip())


def _unique_hash_map(customers: pd.DataFrame) -> dict[str, str]:
    """email hash -> customer_id, only for hashes that belong to exactly one customer."""
    c = customers.assign(email_sha256=_clean(customers["email_sha256"])).dropna(subset=["email_sha256"])
    counts = c.groupby("email_sha256")["customer_id"].nunique()
    unique = set(counts[counts == 1].index)
    return {h: cid for h, cid in zip(c["email_sha256"], c["customer_id"]) if h in unique}


def identify_evidence(identifies: pd.DataFrame, customers: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    known = set(customers["customer_id"])
    by_hash = _unique_hash_map(customers)
    evidence, rejected = [], []
    ts = pd.to_datetime(identifies["timestamp"], utc=True, errors="coerce")
    for device, uid, h, t in zip(_clean(identifies["anonymousId"]), _clean(identifies["userId"]),
                                 _clean(identifies["email_sha256"]), ts):
        if device is None:
            rejected.append(dict(source="identify", user_pseudo_id=None, customer_id=uid,
                                 reason="no_device_id", detail="identify event without anonymousId"))
            continue
        user = uid if uid in known else None
        hash_customer = by_hash.get(h) if h else None
        if user and hash_customer and hash_customer != user:
            rejected.append(dict(source="identify", user_pseudo_id=device, customer_id=user, reason="hash_conflict",
                                 detail=f"userId {user} but email hash belongs to {hash_customer}"))
        elif user and hash_customer == user:
            evidence.append(dict(user_pseudo_id=device, customer_id=user, rule="identify_verified", ts=t))
        elif user:
            evidence.append(dict(user_pseudo_id=device, customer_id=user, rule="identify_unverified", ts=t))
        elif hash_customer:
            evidence.append(dict(user_pseudo_id=device, customer_id=hash_customer, rule="email_hash", ts=t))
        else:
            rejected.append(dict(source="identify", user_pseudo_id=device, customer_id=uid,
                                 reason="unknown_customer", detail="userId is not a customer and the email hash matches no one"))
    return evidence, rejected


def order_evidence(orders: pd.DataFrame, customers: pd.DataFrame, purchases: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    known = set(customers["customer_id"])
    p = purchases.assign(transaction_id=_clean(purchases["transaction_id"]),
                         event_ts=pd.to_datetime(purchases["event_ts"], utc=True, errors="coerce"))
    p = p.dropna(subset=["transaction_id", "user_pseudo_id"]).drop_duplicates(["transaction_id", "user_pseudo_id"])
    p = p.sort_values(["transaction_id", "event_ts", "user_pseudo_id"], na_position="last")
    devices_of = p.groupby("transaction_id")["user_pseudo_id"].apply(list).to_dict()
    when = {(r.transaction_id, r.user_pseudo_id): r.event_ts for r in p.itertuples()}

    evidence, rejected = [], []
    o = orders.assign(ga_transaction_id=_clean(orders["ga_transaction_id"])).dropna(subset=["ga_transaction_id"])
    for order_id, cid, txn in zip(o["order_id"], o["customer_id"], o["ga_transaction_id"]):
        devices = devices_of.get(txn, [])
        if cid not in known:
            rejected.append(dict(source="order", user_pseudo_id=None, customer_id=cid, reason="unknown_customer",
                                 detail=f"order {order_id} belongs to an unknown customer"))
        elif not devices:
            rejected.append(dict(source="order", user_pseudo_id=None, customer_id=cid, reason="transaction_not_in_ga4",
                                 detail=f"order {order_id}: transaction {txn} not found among GA4 purchases"))
        else:
            # The same transaction can be re-fired from another device. The earliest purchase event is the original.
            evidence.append(dict(user_pseudo_id=devices[0], customer_id=cid, rule="order_match",
                                 ts=when[(txn, devices[0])]))
            for later in devices[1:]:
                rejected.append(dict(source="order", user_pseudo_id=later, customer_id=cid, reason="duplicate_transaction_later_device",
                                     detail=f"order {order_id}: transaction {txn} also fired on this device after {devices[0]}"))
    return evidence, rejected


def resolve(identifies: pd.DataFrame, orders: pd.DataFrame, customers: pd.DataFrame,
            purchases: pd.DataFrame) -> Result:
    """Build the device-to-customer links.

    identifies  anonymousId, userId, timestamp, email_sha256
    orders      order_id, customer_id, ga_transaction_id
    customers   customer_id, email_sha256
    purchases   transaction_id, user_pseudo_id, event_ts   (valid GA4 purchases)
    """
    ev1, rej1 = identify_evidence(identifies, customers)
    ev2, rej2 = order_evidence(orders, customers, purchases)
    rejected = rej1 + rej2
    evidence = pd.DataFrame(ev1 + ev2, columns=["user_pseudo_id", "customer_id", "rule", "ts"])
    if evidence.empty:
        return Result(pd.DataFrame(columns=LINK_COLUMNS), pd.DataFrame(rejected, columns=REJECTED_COLUMNS))

    rows = []
    for (device, cid), g in evidence.groupby(["user_pseudo_id", "customer_id"], sort=True):
        rules = sorted(set(g["rule"]), key=lambda r: (-RULE_SCORE[r], r))
        rows.append(dict(user_pseudo_id=device, customer_id=cid, link_rule=rules[0],
                         evidence_rules=",".join(rules), score=sum(RULE_SCORE[r] for r in rules),
                         evidence_count=len(g), first_evidence_ts=g["ts"].min()))
    cand = pd.DataFrame(rows)

    cand["first_evidence_ts"] = pd.to_datetime(cand["first_evidence_ts"], utc=True)
    # Best candidate per device: most evidence, then earliest evidence, then customer id (so reruns never differ).
    cand = cand.sort_values(["user_pseudo_id", "score", "first_evidence_ts", "customer_id"],
                            ascending=[True, False, True, True], na_position="last")
    cand["rank"] = cand.groupby("user_pseudo_id").cumcount()
    n_cand = cand.groupby("user_pseudo_id")["customer_id"].transform("size")
    for r in cand[cand["rank"] > 0].itertuples():
        winner = cand[(cand["user_pseudo_id"] == r.user_pseudo_id) & (cand["rank"] == 0)].iloc[0]["customer_id"]
        rejected.append(dict(source="resolution", user_pseudo_id=r.user_pseudo_id, customer_id=r.customer_id,
                             reason="lost_conflict", detail=f"device kept for {winner}, which has more evidence"))
    links = cand[cand["rank"] == 0].copy()
    links["had_conflict"] = (n_cand[links.index] > 1).to_numpy()
    links["confidence"] = links["link_rule"].map(lambda r: "high" if r in HIGH_CONFIDENCE_RULES else "medium")
    links = links[LINK_COLUMNS].reset_index(drop=True)
    return Result(links, pd.DataFrame(rejected, columns=REJECTED_COLUMNS))

"""Score identity resolution against the synthetic ground truth.

This is the ONLY place the ground-truth file is read. The rules in ``rules.py`` never see it.

Terms
-----
precision        of the links we made, the share that are correct
recall           of the true device-to-customer links, the share we found
reachable        a true link that some rule COULD find: the device has a Segment identify event, or it
                 placed a CRM order that carries the GA4 transaction id. The rest cannot be found by any
                 deterministic rule, so recall can never reach 100%.
"""

from __future__ import annotations

import pandas as pd


def _share(a: float, b: float) -> float:
    return float(a) / float(b) if b else 0.0


def reachable_truth(truth: pd.DataFrame, orders: pd.DataFrame, purchases: pd.DataFrame) -> pd.Series:
    """True for each truth row that has identify evidence or a matching order on that device."""
    o = orders.dropna(subset=["ga_transaction_id"])[["customer_id", "ga_transaction_id"]]
    p = purchases[["transaction_id", "user_pseudo_id"]].drop_duplicates()
    via_order = o.merge(p, left_on="ga_transaction_id", right_on="transaction_id")[["customer_id", "user_pseudo_id"]]
    via_order = via_order.drop_duplicates().assign(_order=True)
    t = truth.merge(via_order, on=["customer_id", "user_pseudo_id"], how="left")
    return (t["identify_emitted"].astype(bool) | t["_order"].fillna(False).astype(bool)).to_numpy()


def score(links: pd.DataFrame, truth: pd.DataFrame, devices: pd.DataFrame, purchases: pd.DataFrame,
          orders: pd.DataFrame, customers: pd.DataFrame) -> dict:
    truth = truth.copy()
    truth["reachable"] = reachable_truth(truth, orders, purchases)
    pairs = links.merge(truth[["customer_id", "user_pseudo_id"]].assign(_ok=True),
                        on=["customer_id", "user_pseudo_id"], how="left")
    pairs["correct"] = pairs["_ok"].fillna(False).astype(bool)
    true_device = set(truth["user_pseudo_id"])
    pairs["wrong_customer"] = ~pairs["correct"] & pairs["user_pseudo_id"].isin(true_device)
    pairs["no_true_customer"] = ~pairs["correct"] & ~pairs["user_pseudo_id"].isin(true_device)

    found = truth.merge(links[["customer_id", "user_pseudo_id"]].assign(_found=True),
                        on=["customer_id", "user_pseudo_id"], how="left")
    found["found"] = found["_found"].fillna(False).astype(bool)

    out: dict = {
        "true_links": len(truth), "predicted_links": len(links), "correct_links": int(pairs["correct"].sum()),
        "wrong_customer_links": int(pairs["wrong_customer"].sum()),
        "links_on_devices_without_customer": int(pairs["no_true_customer"].sum()),
        "reachable_links": int(found["reachable"].sum()), "found_links": int(found["found"].sum()),
    }
    out["precision"] = _share(out["correct_links"], out["predicted_links"])
    out["recall"] = _share(out["found_links"], out["true_links"])
    out["recall_ceiling"] = _share(out["reachable_links"], out["true_links"])
    out["recall_of_reachable"] = _share(int(found.loc[found["reachable"], "found"].sum()), out["reachable_links"])
    out["missed_but_reachable"] = int((found["reachable"] & ~found["found"]).sum())
    out["missed_unreachable"] = int((~found["reachable"] & ~found["found"]).sum())

    by_rule = pairs.groupby("link_rule").agg(links=("correct", "size"), correct=("correct", "sum")).reset_index()
    by_rule["precision"] = by_rule["correct"] / by_rule["links"]
    out["by_rule"] = by_rule
    by_conf = pairs.groupby("confidence").agg(links=("correct", "size"), correct=("correct", "sum")).reset_index()
    by_conf["precision"] = by_conf["correct"] / by_conf["links"]
    out["by_confidence"] = by_conf
    by_role = found.groupby("device_role").agg(true_links=("found", "size"), found=("found", "sum"),
                                               reachable=("reachable", "sum")).reset_index()
    by_role["recall"] = by_role["found"] / by_role["true_links"]
    by_role["recall_ceiling"] = by_role["reachable"] / by_role["true_links"]
    out["by_role"] = by_role

    # customers
    per_cust_true = truth.groupby("customer_id").size()
    per_cust_found = found[found["found"]].groupby("customer_id").size()
    out["customers"] = len(customers)
    out["customers_with_a_device_found"] = int((per_cust_found > 0).sum())
    multi = per_cust_true[per_cust_true > 1].index
    out["multi_device_customers"] = len(multi)
    out["multi_device_customers_fully_found"] = int(
        sum(per_cust_found.get(c, 0) == per_cust_true[c] for c in multi))

    # sessions and revenue
    sess = devices.set_index("user_pseudo_id")["sessions"]
    total_sessions = float(sess.sum())
    link_dev = links["user_pseudo_id"].unique()
    ok_dev = pairs.loc[pairs["correct"], "user_pseudo_id"].unique()
    true_dev = truth["user_pseudo_id"].unique()
    reach_dev = truth.loc[truth["reachable"], "user_pseudo_id"].unique()
    out["sessions_total"] = int(total_sessions)
    out["sessions_linked"] = int(sess.reindex(link_dev).fillna(0).sum())
    out["sessions_correctly_linked"] = int(sess.reindex(ok_dev).fillna(0).sum())
    out["sessions_on_customer_devices"] = int(sess.reindex(true_dev).fillna(0).sum())
    out["sessions_reachable"] = int(sess.reindex(reach_dev).fillna(0).sum())

    rev = purchases.drop_duplicates(["transaction_id", "user_pseudo_id"]).groupby("user_pseudo_id")["revenue_usd"].sum()
    out["revenue_total"] = round(float(rev.sum()), 2)
    out["revenue_linked"] = round(float(rev.reindex(link_dev).fillna(0).sum()), 2)
    out["revenue_correctly_linked"] = round(float(rev.reindex(ok_dev).fillna(0).sum()), 2)
    out["revenue_on_customer_devices"] = round(float(rev.reindex(true_dev).fillna(0).sum()), 2)
    out["revenue_guest_or_unknown"] = round(out["revenue_total"] - out["revenue_on_customer_devices"], 2)

    # unmatched shares
    tx = purchases.drop_duplicates(["transaction_id", "user_pseudo_id"])
    out["devices_total"] = int(len(devices))
    out["devices_linked"] = int(len(link_dev))
    out["purchases_total"] = len(tx)
    out["purchases_linked"] = int(tx["user_pseudo_id"].isin(link_dev).sum())
    out["purchases_guest"] = int((~tx["user_pseudo_id"].isin(true_dev)).sum())
    out["customers_unmatched"] = out["customers"] - out["customers_with_a_device_found"]
    return out


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _table(df: pd.DataFrame, cols: list[str], fmt: dict) -> str:
    head = "| " + " | ".join(cols) + " |\n|" + "|".join("---" for _ in cols) + "|"
    rows = ["| " + " | ".join(fmt.get(c, str)(r[c]) for c in cols) + " |" for _, r in df.iterrows()]
    return "\n".join([head, *rows])


def render_report(m: dict, rejected: pd.DataFrame, generated: str, generator: str = "src/identity/run.py") -> str:
    n = lambda v: f"{int(v):,}"  # noqa: E731
    rej = (rejected.groupby(["source", "reason"]).size().reset_index(name="count")
           if len(rejected) else pd.DataFrame(columns=["source", "reason", "count"]))
    lines = [
        "# Identity resolution: accuracy report", "",
        f"Generated by `{generator}` on {generated}. Scored against the synthetic ground truth "
        "(`raw.ground_truth_identity_links`), which the rules never read.", "",
        "## Headline", "",
        "| Measure | Value |", "|---|---|",
        f"| Precision (links made that are correct) | **{_pct(m['precision'])}** ({n(m['correct_links'])} of {n(m['predicted_links'])}) |",
        f"| Recall (true links found) | **{_pct(m['recall'])}** ({n(m['found_links'])} of {n(m['true_links'])}) |",
        f"| Best possible recall for these rules | {_pct(m['recall_ceiling'])} ({n(m['reachable_links'])} links have a usable signal) |",
        f"| Recall of the links that have a usable signal | {_pct(m['recall_of_reachable'])} |",
        f"| Links missed although a signal existed | {n(m['missed_but_reachable'])} |",
        f"| Links missed with no usable signal | {n(m['missed_unreachable'])} |",
        f"| Links to the wrong customer | {n(m['wrong_customer_links'])} |",
        f"| Links on a device that has no true customer | {n(m['links_on_devices_without_customer'])} |", "",
        "Links with no usable signal are devices whose Segment identify event was never captured and "
        "that have no CRM order carrying the GA4 transaction id (mostly second devices). No deterministic "
        "rule can find them, and the rules do not guess.", "",
        "## What the links cover", "",
        "| Measure | Value |", "|---|---|",
        f"| Sessions on a linked device | {_pct(_share(m['sessions_linked'], m['sessions_total']))} ({n(m['sessions_linked'])} of {n(m['sessions_total'])}) |",
        f"| Sessions on the devices of real customers | {_pct(_share(m['sessions_on_customer_devices'], m['sessions_total']))} |",
        f"| Of those, sessions linked correctly | {_pct(_share(m['sessions_correctly_linked'], m['sessions_on_customer_devices']))} |",
        f"| Purchase revenue on a linked device | {_pct(_share(m['revenue_linked'], m['revenue_total']))} (${m['revenue_linked']:,.0f} of ${m['revenue_total']:,.0f}) |",
        f"| Revenue from guests or unknown devices (cannot be linked) | {_pct(_share(m['revenue_guest_or_unknown'], m['revenue_total']))} |",
        f"| Customers with at least one device found | {_pct(_share(m['customers_with_a_device_found'], m['customers']))} ({n(m['customers_with_a_device_found'])} of {n(m['customers'])}) |",
        f"| Customers with 2+ devices where all were found | {_pct(_share(m['multi_device_customers_fully_found'], m['multi_device_customers']))} ({n(m['multi_device_customers_fully_found'])} of {n(m['multi_device_customers'])}) |", "",
        "## Unmatched share", "",
        "| What | Unmatched | Of which cannot be matched by any rule |", "|---|---|---|",
        f"| GA4 devices | {_pct(1 - _share(m['devices_linked'], m['devices_total']))} ({n(m['devices_total'] - m['devices_linked'])} of {n(m['devices_total'])}) | Most are anonymous visitors who never became customers |",
        f"| Sessions | {_pct(1 - _share(m['sessions_linked'], m['sessions_total']))} ({n(m['sessions_total'] - m['sessions_linked'])} of {n(m['sessions_total'])}) | Same reason |",
        f"| Customers (no device found) | {_pct(_share(m['customers_unmatched'], m['customers']))} ({n(m['customers_unmatched'])} of {n(m['customers'])}) | All have no usable signal |",
        f"| True device-to-customer links | {_pct(1 - m['recall'])} ({n(m['true_links'] - m['found_links'])} of {n(m['true_links'])}) | {n(m['missed_unreachable'])} have no usable signal; {n(m['missed_but_reachable'])} should have been found |",
        f"| GA4 purchases (valid transactions) | {_pct(1 - _share(m['purchases_linked'], m['purchases_total']))} ({n(m['purchases_total'] - m['purchases_linked'])} of {n(m['purchases_total'])}) | {n(m['purchases_guest'])} are guest checkouts with no CRM record |",
        f"| Purchase revenue | {_pct(1 - _share(m['revenue_linked'], m['revenue_total']))} (${m['revenue_total'] - m['revenue_linked']:,.0f}) | ${m['revenue_guest_or_unknown']:,.0f} is guest or unknown |", "",
        "## By rule", "",
        _table(m["by_rule"], ["link_rule", "links", "correct", "precision"], {"links": n, "correct": n, "precision": _pct}), "",
        "## By confidence", "",
        _table(m["by_confidence"], ["confidence", "links", "correct", "precision"], {"links": n, "correct": n, "precision": _pct}), "",
        "## By device role", "",
        _table(m["by_role"], ["device_role", "true_links", "found", "recall", "recall_ceiling"],
               {"true_links": n, "found": n, "recall": _pct, "recall_ceiling": _pct}), "",
        "## Evidence that was not used", "",
        _table(rej, ["source", "reason", "count"], {"count": n}) if len(rej) else "_None._", "",
    ]
    return "\n".join(lines)

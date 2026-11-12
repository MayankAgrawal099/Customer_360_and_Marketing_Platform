"""Stress-test identity resolution with damaged inputs.

On clean synthetic data the signals never contradict each other, so precision is 100% almost by
construction. That says the rules are logically sound, not that they cope with messy data. Here the
same inputs are damaged in known ways (fixed seed), the rules are re-run, and the result is scored
against the same ground truth.

Scenarios
---------
baseline                    inputs as generated
drop_30pct_identifies       30% of identify events are lost
strip_all_hashes            no identify event carries an email hash
no_order_transaction_ids    no CRM order carries a GA4 transaction id (identify events only)
wrong_userid_with_hash_5    5% of identify events name the wrong customer, hash still correct (detectable)
wrong_userid_no_hash_5      5% name the wrong customer and carry no hash (undetectable from identify alone)
wrong_userid_no_hash_5_no_orders   same, and no order evidence to outvote them (worst case)
shared_device_5             5% of identify events are followed, a day later, by a second customer on the same device
shared_device_5_claimant_first   the same, but the second customer's claim comes a day BEFORE the owner's (worst case for the tie-break)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.identity.rules import resolve
from src.identity.score import score

SEED = 42

SCENARIOS = {
    "baseline": "Inputs as generated",
    "drop_30pct_identifies": "30% of identify events lost",
    "strip_all_hashes": "No identify event has an email hash",
    "no_order_transaction_ids": "No order carries a GA4 transaction id",
    "wrong_userid_with_hash_5": "5% of identify events name the wrong customer; hash still correct",
    "wrong_userid_no_hash_5": "5% name the wrong customer and carry no hash",
    "wrong_userid_no_hash_5_no_orders": "Same as above, with no order evidence to outvote them",
    "shared_device_5": "5% of devices are also claimed, a day later, by a second customer",
    "shared_device_5_claimant_first": "Same, but the second customer's claim comes a day before the owner's",
}


def _pick(n: int, frac: float, rng) -> np.ndarray:
    k = int(round(n * frac))
    return rng.choice(n, size=k, replace=False) if k else np.array([], dtype=int)


def _other_customers(current: pd.Series, customers: pd.DataFrame, rng) -> list[str]:
    ids = customers["customer_id"].to_numpy()
    new = rng.choice(ids, size=len(current))
    # Never "wrong" by accident: if the draw equals the true customer, take the next customer instead.
    pos = {c: i for i, c in enumerate(ids)}
    return [ids[(pos[n] + 1) % len(ids)] if n == c else n for n, c in zip(new, current)]


def perturb(name: str, identifies: pd.DataFrame, orders: pd.DataFrame, customers: pd.DataFrame,
            seed: int = SEED) -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    ids, ords = identifies.copy().reset_index(drop=True), orders.copy()
    if name == "baseline":
        pass
    elif name == "drop_30pct_identifies":
        ids = ids.drop(index=_pick(len(ids), 0.30, rng)).reset_index(drop=True)
    elif name == "strip_all_hashes":
        ids["email_sha256"] = None
    elif name == "no_order_transaction_ids":
        ords["ga_transaction_id"] = None
    elif name.startswith("wrong_userid"):
        rows = _pick(len(ids), 0.05, rng)
        ids.loc[rows, "userId"] = _other_customers(ids.loc[rows, "userId"], customers, rng)
        if "no_hash" in name:
            ids.loc[rows, "email_sha256"] = None
        if name.endswith("no_orders"):
            ords["ga_transaction_id"] = None
    elif name.startswith("shared_device_5"):
        rows = _pick(len(ids), 0.05, rng)
        extra = ids.loc[rows].copy()
        extra["userId"] = _other_customers(extra["userId"], customers, rng)
        hashes = customers.set_index("customer_id")["email_sha256"]
        extra["email_sha256"] = extra["userId"].map(hashes)
        shift = pd.Timedelta(days=-1 if name.endswith("claimant_first") else 1)
        extra["timestamp"] = pd.to_datetime(extra["timestamp"], utc=True) + shift
        ids = pd.concat([ids, extra], ignore_index=True)
    else:
        raise ValueError(f"unknown scenario {name}")
    return ids, ords


def run_scenarios(frames: dict[str, pd.DataFrame], names: list[str] | None = None) -> pd.DataFrame:
    rows = []
    for name in names or list(SCENARIOS):
        ids, ords = perturb(name, frames["identifies"], frames["orders"], frames["customers"])
        res = resolve(ids, ords, frames["customers"], frames["purchases"])
        m = score(res.links, frames["truth"], frames["devices"], frames["purchases"], ords, frames["customers"])
        rej = res.rejected["reason"].value_counts()
        rows.append({
            "scenario": name, "description": SCENARIOS[name], "links": m["predicted_links"],
            "precision": m["precision"], "recall": m["recall"], "wrong_links": m["wrong_customer_links"],
            "hash_conflicts_caught": int(rej.get("hash_conflict", 0)),
            "conflicts_resolved": int(rej.get("lost_conflict", 0)),
        })
    return pd.DataFrame(rows)


def render_stress(df: pd.DataFrame) -> str:
    head = ("| Scenario | What was damaged | Links | Precision | Recall | Wrong links | Hash conflicts caught | "
            "Device conflicts resolved |\n|---|---|---|---|---|---|---|---|")
    rows = [f"| `{r.scenario}` | {r.description} | {r.links:,} | {r.precision * 100:.1f}% | {r.recall * 100:.1f}% | "
            f"{r.wrong_links:,} | {r.hash_conflicts_caught:,} | {r.conflicts_resolved:,} |" for r in df.itertuples()]
    return "\n".join([head, *rows])

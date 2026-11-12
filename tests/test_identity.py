"""Tests for identity resolution (src/identity). No Google Cloud login needed.

They check each rule on small hand-made cases, that the result does not depend on row order, that the
rules never read the ground truth, and (end to end) that rules run on the generated synthetic data
make no wrong links and miss only links that have no usable signal.
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.identity import rules, run, score as sc  # noqa: E402
from src.synthetic import generate_crm as g  # noqa: E402
from tests.test_synthetic import fake_extract  # noqa: E402

H1, H2 = "a" * 64, "b" * 64


def customers():
    return pd.DataFrame({"customer_id": ["C1", "C2", "C3"], "email_sha256": [H1, H2, None]})


def identifies(rows):
    return pd.DataFrame(rows, columns=["anonymousId", "userId", "timestamp", "email_sha256"])


def orders(rows=()):
    return pd.DataFrame(list(rows), columns=["order_id", "customer_id", "ga_transaction_id"])


def purchases(rows=()):
    return pd.DataFrame(list(rows), columns=["transaction_id", "user_pseudo_id", "event_ts"])


def link_of(res, device):
    m = res.links[res.links["user_pseudo_id"] == device]
    return m.iloc[0] if len(m) else None


def reasons(res):
    return sorted(res.rejected["reason"])


def test_identify_with_matching_email_hash_is_verified():
    res = rules.resolve(identifies([("d1", "C1", "2020-11-02T10:00:00Z", H1)]), orders(), customers(), purchases())
    row = link_of(res, "d1")
    assert (row["customer_id"], row["link_rule"], row["confidence"]) == ("C1", "identify_verified", "high")


def test_identify_without_email_hash_is_unverified_and_medium():
    res = rules.resolve(identifies([("d1", "C3", "2020-11-02T10:00:00Z", None)]), orders(), customers(), purchases())
    row = link_of(res, "d1")
    assert (row["link_rule"], row["confidence"]) == ("identify_unverified", "medium")


def test_userid_and_hash_pointing_to_different_customers_is_rejected():
    res = rules.resolve(identifies([("d1", "C1", "2020-11-02T10:00:00Z", H2)]), orders(), customers(), purchases())
    assert link_of(res, "d1") is None and reasons(res) == ["hash_conflict"]


def test_email_hash_alone_links_when_userid_is_not_a_customer():
    res = rules.resolve(identifies([("d1", "C999", "2020-11-02T10:00:00Z", H2)]), orders(), customers(), purchases())
    row = link_of(res, "d1")
    assert (row["customer_id"], row["link_rule"]) == ("C2", "email_hash")


def test_unknown_userid_and_unknown_hash_is_rejected():
    res = rules.resolve(identifies([("d1", "C999", "2020-11-02T10:00:00Z", "c" * 64)]), orders(), customers(), purchases())
    assert link_of(res, "d1") is None and reasons(res) == ["unknown_customer"]


def test_email_hash_shared_by_two_customers_is_never_used():
    shared = pd.DataFrame({"customer_id": ["C1", "C2"], "email_sha256": [H1, H1]})
    res = rules.resolve(identifies([("d1", "C999", "2020-11-02T10:00:00Z", H1)]), orders(), shared, purchases())
    assert link_of(res, "d1") is None


def test_order_with_ga4_transaction_links_the_purchasing_device():
    res = rules.resolve(identifies([]), orders([("O1", "C1", "T1")]), customers(),
                        purchases([("T1", "d7", "2020-11-03T10:00:00Z")]))
    row = link_of(res, "d7")
    assert (row["customer_id"], row["link_rule"], row["confidence"]) == ("C1", "order_match", "high")


def test_order_without_transaction_id_is_ignored():
    res = rules.resolve(identifies([]), orders([("O1", "C1", None)]), customers(), purchases([("T1", "d7", "2020-11-03")]))
    assert res.links.empty


def test_transaction_missing_from_ga4_is_reported():
    res = rules.resolve(identifies([]), orders([("O1", "C1", "T9")]), customers(), purchases())
    assert res.links.empty and reasons(res) == ["transaction_not_in_ga4"]


def test_transaction_fired_on_two_devices_uses_the_earliest():
    res = rules.resolve(identifies([]), orders([("O1", "C1", "T1")]), customers(),
                        purchases([("T1", "late", "2020-11-03T12:00:00Z"), ("T1", "early", "2020-11-03T10:00:00Z")]))
    assert list(res.links["user_pseudo_id"]) == ["early"]
    assert reasons(res) == ["duplicate_transaction_later_device"]


def test_two_signals_for_the_same_pair_are_combined():
    res = rules.resolve(identifies([("d1", "C1", "2020-11-02T10:00:00Z", H1)]), orders([("O1", "C1", "T1")]), customers(),
                        purchases([("T1", "d1", "2020-11-03T10:00:00Z")]))
    row = link_of(res, "d1")
    assert row["evidence_rules"] == "identify_verified,order_match" and row["evidence_count"] == 2
    assert len(res.links) == 1 and not row["had_conflict"]


def test_device_claimed_by_two_customers_keeps_the_one_with_more_evidence():
    res = rules.resolve(
        identifies([("d1", "C1", "2020-11-02T10:00:00Z", H1), ("d1", "C2", "2020-11-02T09:00:00Z", None)]),
        orders([("O1", "C1", "T1")]), customers(), purchases([("T1", "d1", "2020-11-03T10:00:00Z")]))
    row = link_of(res, "d1")
    assert row["customer_id"] == "C1" and bool(row["had_conflict"])
    lost = res.rejected[res.rejected["reason"] == "lost_conflict"]
    assert list(lost["customer_id"]) == ["C2"]


def test_conflict_with_equal_evidence_keeps_the_earlier_one():
    res = rules.resolve(
        identifies([("d1", "C1", "2020-11-02T10:00:00Z", H1), ("d1", "C2", "2020-11-02T09:00:00Z", H2)]),
        orders(), customers(), purchases())
    assert link_of(res, "d1")["customer_id"] == "C2"


def test_result_does_not_depend_on_row_order():
    ids = identifies([("d1", "C1", "2020-11-02T10:00:00Z", H1), ("d1", "C2", "2020-11-02T10:00:00Z", H2),
                      ("d2", "C3", "2020-11-02T11:00:00Z", None)])
    a = rules.resolve(ids, orders(), customers(), purchases()).links
    b = rules.resolve(ids.iloc[::-1].reset_index(drop=True), orders(), customers().iloc[::-1], purchases()).links
    pd.testing.assert_frame_equal(a.sort_values("user_pseudo_id").reset_index(drop=True),
                                  b.sort_values("user_pseudo_id").reset_index(drop=True))


def test_empty_inputs_give_empty_results():
    res = rules.resolve(identifies([]), orders(), customers(), purchases())
    assert res.links.empty and list(res.links.columns) == rules.LINK_COLUMNS


def test_rules_never_touch_the_ground_truth():
    text = (ROOT / "src" / "identity" / "rules.py").read_text(encoding="utf-8")
    assert not re.search(r"ground_truth|score import|import score", text)
    assert "truth" not in "".join(re.findall(r"def resolve\((.*?)\)", text, re.S))


# ----------------------------------------------------------------------------- end to end
@pytest.fixture(scope="module")
def world(tmp_path_factory):
    d = tmp_path_factory.mktemp("identity")
    users, purch, traffic = fake_extract()
    ex = d / "extract"
    ex.mkdir()
    users.to_csv(ex / "users.csv", index=False)
    purch.to_csv(ex / "purchases.csv", index=False)
    traffic.to_csv(ex / "daily_traffic.csv", index=False)
    out = d / "out"
    g.write_outputs(g.generate(*g.read_extract(ex)), out)
    ids = pd.json_normalize([json.loads(x) for x in (out / "segment_identifies.jsonl").read_text().splitlines()])
    frames = {
        "identifies": ids.rename(columns={"traits.emailSha256": "email_sha256"})[["anonymousId", "userId", "timestamp", "email_sha256"]],
        "customers": pd.read_csv(out / "crm_customers.csv", dtype=str)[["customer_id", "email_sha256"]],
        "orders": pd.read_csv(out / "crm_orders.csv", dtype=str)[["order_id", "customer_id", "ga_transaction_id"]],
        "truth": pd.read_csv(out / "ground_truth" / "ground_truth_identity_links.csv", dtype={"user_pseudo_id": str}),
        "purchases": purch[["transaction_id", "user_pseudo_id", "event_ts", "revenue_usd"]],
        "devices": users[["user_pseudo_id", "sessions"]],
    }
    return frames, *run.run_pipeline(frames)


def test_end_to_end_makes_no_wrong_links(world):
    frames, result, m = world
    assert m["precision"] == 1.0 and m["wrong_customer_links"] == 0 and m["links_on_devices_without_customer"] == 0
    assert m["predicted_links"] == m["correct_links"] > 0


def test_end_to_end_misses_only_links_with_no_usable_signal(world):
    _, _, m = world
    assert m["missed_but_reachable"] == 0 and m["recall_of_reachable"] == 1.0
    assert m["recall"] == m["recall_ceiling"] < 1.0          # the unreachable links really exist
    assert 0.75 < m["recall"] < 1.0


def test_end_to_end_every_link_has_a_known_rule_and_confidence(world):
    _, result, _ = world
    assert set(result.links["link_rule"]) <= set(rules.RULE_SCORE)
    assert set(result.links["confidence"]) <= {"high", "medium"}
    assert result.links["user_pseudo_id"].is_unique


def test_score_counts_a_wrong_link(world):
    frames, result, _ = world
    bad = result.links.copy()
    bad.loc[0, "customer_id"] = "C_WRONG"
    m = sc.score(bad, frames["truth"], frames["devices"], frames["purchases"], frames["orders"], frames["customers"])
    assert m["wrong_customer_links"] == 1 and m["precision"] < 1.0


def test_report_renders_with_all_sections(world):
    _, result, m = world
    text = sc.render_report(m, result.rejected, "2026-11-12")
    for heading in ("## Headline", "## What the links cover", "## By rule", "## By confidence", "## By device role",
                    "## Evidence that was not used"):
        assert heading in text
    assert "Precision" in text and "Recall" in text


# ----------------------------------------------------------------------------- BigQuery queries
@pytest.mark.parametrize("name", sorted(run.QUERIES))
def test_queries_are_read_only_bigquery_sql(name):
    sql = run.QUERIES[name].format(ds="proj.raw")
    assert re.match(r"\s*(SELECT|WITH)\b", sql, re.I)
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE)\b", sql, re.I)
    sqlglot = pytest.importorskip("sqlglot")
    sqlglot.parse_one(sql, read="bigquery")


def test_output_schemas_match_the_columns_written():
    assert [c for c, _ in run.SCHEMAS["identity_links"]] == rules.LINK_COLUMNS
    assert [c for c, _ in run.SCHEMAS["identity_rejected"]] == rules.REJECTED_COLUMNS


# ----------------------------------------------------------------------------- stress tests and unmatched share
from src.identity import accuracy, stress  # noqa: E402


@pytest.fixture(scope="module")
def stressed(world):
    frames, _, _ = world
    return stress.run_scenarios(frames).set_index("scenario")


def test_every_scenario_runs_and_is_scored(stressed):
    assert set(stressed.index) == set(stress.SCENARIOS)
    assert stressed.loc["baseline", "precision"] == 1.0


def test_detectable_wrong_userids_are_caught_by_the_email_hash(stressed):
    row = stressed.loc["wrong_userid_with_hash_5"]
    assert row["precision"] == 1.0 and row["wrong_links"] == 0 and row["hash_conflicts_caught"] > 0


def test_lost_identify_events_lower_recall_not_precision(stressed):
    row = stressed.loc["drop_30pct_identifies"]
    assert row["precision"] == 1.0 and row["recall"] < stressed.loc["baseline", "recall"]


def test_removing_hashes_does_not_change_the_links(stressed):
    assert stressed.loc["strip_all_hashes", "recall"] == stressed.loc["baseline", "recall"]
    assert stressed.loc["strip_all_hashes", "precision"] == 1.0


def test_orders_outvote_undetectable_wrong_userids(stressed):
    """Without a hash an identify error looks fine, but a matching order (score 3) beats it (score 2)."""
    with_orders = stressed.loc["wrong_userid_no_hash_5"]
    without = stressed.loc["wrong_userid_no_hash_5_no_orders"]
    assert without["wrong_links"] > 0                       # the worst case really does produce wrong links
    assert with_orders["wrong_links"] < without["wrong_links"]
    assert 0.8 < without["precision"] < 1.0


def test_second_claimant_on_a_device_loses_to_the_owner(stressed):
    row = stressed.loc["shared_device_5"]
    assert row["precision"] == 1.0 and row["conflicts_resolved"] > 0


def test_stress_inputs_are_reproducible(world):
    frames, _, _ = world
    a = stress.perturb("wrong_userid_no_hash_5", frames["identifies"], frames["orders"], frames["customers"])[0]
    b = stress.perturb("wrong_userid_no_hash_5", frames["identifies"], frames["orders"], frames["customers"])[0]
    pd.testing.assert_frame_equal(a, b)


def test_unmatched_shares_add_up(world):
    _, _, m = world
    assert m["customers_unmatched"] + m["customers_with_a_device_found"] == m["customers"]
    assert m["missed_unreachable"] + m["missed_but_reachable"] == m["true_links"] - m["found_links"]
    assert m["purchases_linked"] + m["purchases_guest"] <= m["purchases_total"]
    assert m["devices_linked"] == m["predicted_links"]


def test_accuracy_report_has_unmatched_and_stress_sections(world):
    frames, _, _ = world
    text, numbers = accuracy.build_report(frames, "2026-11-12")
    for heading in ("## Headline", "## Unmatched share", "## Stress test"):
        assert heading in text
    assert len(numbers["stress"]) == len(stress.SCENARIOS) and "precision" in numbers


def test_tie_break_by_earliest_evidence_is_a_real_weakness(stressed):
    """If the second claimant is earlier and nothing else breaks the tie, the owner can lose. The report must show it."""
    later, first = stressed.loc["shared_device_5"], stressed.loc["shared_device_5_claimant_first"]
    assert later["wrong_links"] == 0
    assert first["wrong_links"] >= 0 and first["conflicts_resolved"] > 0
    assert first["precision"] <= later["precision"]


def test_accuracy_report_names_its_own_generator(world):
    frames, _, _ = world
    text, _ = accuracy.build_report(frames, "2026-11-12")
    assert "src/identity/accuracy.py" in text.splitlines()[2]

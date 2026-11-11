"""Tests for the BigQuery loader (src/load_to_bigquery.py).

No Google Cloud login is needed. They prove that the table definitions match the files the
generator really writes (so a load cannot fail on a column mismatch), that the checks are
valid read-only BigQuery SQL, and that device ids survive as text from extract to Segment file.
"""

import json
import re
import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import load_to_bigquery as lb  # noqa: E402
from src.synthetic import generate_crm as g  # noqa: E402
from tests.test_synthetic import fake_extract  # noqa: E402

FILE_TABLES = [t for t in lb.TABLES if t.kind != "ga4"]


@pytest.fixture(scope="module")
def out_dir(tmp_path_factory):
    d = tmp_path_factory.mktemp("synthetic")
    users, purchases, traffic = fake_extract()
    renamed = {old: f"{7000000 + i}.{3000010 + i * 10}" for i, old in enumerate(users["user_pseudo_id"][:30])}
    users["user_pseudo_id"] = users["user_pseudo_id"].replace(renamed)       # ids ending in 0, as in real GA4
    purchases["user_pseudo_id"] = purchases["user_pseudo_id"].replace(renamed)
    ex = d / "extract"
    ex.mkdir()
    users.to_csv(ex / "users.csv", index=False)
    purchases.to_csv(ex / "purchases.csv", index=False)
    traffic.to_csv(ex / "daily_traffic.csv", index=False)
    g.write_outputs(g.generate(*g.read_extract(ex)), d / "out")
    return d / "out"


def test_table_names_are_unique_and_complete():
    names = [t.name for t in lb.TABLES]
    assert len(names) == len(set(names))
    assert set(names) == {"ga4_events", "crm_customers", "crm_orders", "ad_spend",
                          "ground_truth_identity_links", "segment_identifies", "segment_tracks"}
    for t in FILE_TABLES:
        assert t.path and t.schema and t.description


@pytest.mark.parametrize("table", FILE_TABLES, ids=lambda t: t.name)
def test_generated_file_matches_schema(table, out_dir):
    assert lb.check_local_file(table, out_dir) == []


def test_missing_file_is_reported(tmp_path):
    problems = lb.check_local_file(lb.TABLE_BY_NAME["crm_orders"], tmp_path)
    assert problems and "not found" in problems[0]


def test_header_mismatch_is_reported(tmp_path):
    (tmp_path / "ad_spend.csv").write_text("date,channel\n2020-11-01,Paid Search\n", encoding="utf-8")
    problems = lb.check_local_file(lb.TABLE_BY_NAME["ad_spend"], tmp_path)
    assert problems and "does not match schema" in problems[0]


def test_unknown_json_field_is_reported(tmp_path):
    line = {"type": "track", "userId": "C1", "properties": {"surprise": 1}, "extra": True}
    (tmp_path / "segment_tracks.jsonl").write_text(json.dumps(line) + "\n", encoding="utf-8")
    problems = lb.check_local_file(lb.TABLE_BY_NAME["segment_tracks"], tmp_path)
    assert any("extra" in p for p in problems) and any("properties.surprise" in p for p in problems)


def test_device_ids_stay_text_from_extract_to_segment_file(out_dir):
    """A float-formatted id would not match GA4 and every identity join would silently fail."""
    ids = [json.loads(line)["anonymousId"] for line in (out_dir / "segment_identifies.jsonl").read_text().splitlines()]
    assert ids and all(isinstance(i, str) for i in ids)
    gt = pd.read_csv(out_dir / "ground_truth" / "ground_truth_identity_links.csv", dtype=str)
    assert gt["user_pseudo_id"].str.fullmatch(r"\d+\.\d+").all()
    assert gt["user_pseudo_id"].str.endswith("0").any()          # trailing zeros kept


def test_local_summary_counts_rows_and_totals(out_dir):
    s = lb.local_summary(lb.TABLE_BY_NAME["crm_orders"], out_dir)
    orders = pd.read_csv(out_dir / "crm_orders.csv")
    assert s["rows"] == len(orders)
    assert s["order_value_usd"] == round(orders["order_value_usd"].sum(), 2)
    assert s["web_orders_without_txn_id"] == int(((orders["order_channel"] == "web") & orders["ga_transaction_id"].isna()).sum())
    n = lb.local_summary(lb.TABLE_BY_NAME["segment_tracks"], out_dir)["rows"]
    assert n == len((out_dir / "segment_tracks.jsonl").read_text().splitlines())


def test_ga4_copy_is_unpartitioned_clustered_and_bounded():
    sql = lb.ga4_copy_sql()
    assert "ga4_obfuscated_sample_ecommerce.events_*" in sql and "_TABLE_SUFFIX BETWEEN '20201101' AND '20210131'" in sql
    assert lb.GA4_CLUSTER_BY == ["event_name", "user_pseudo_id"]
    assert "PARTITION" not in sql.upper()


CHECKS = lb.format_checks("proj.raw")


@pytest.mark.parametrize("name,sql", CHECKS, ids=[c[0] for c in CHECKS])
def test_checks_are_read_only_bigquery_sql(name, sql):
    assert re.match(r"\s*SELECT\b", sql, re.I)
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE)\b", sql, re.I)
    refs = set(re.findall(r"`([^`]+)`", sql))
    assert refs and all(r.split(".")[-1] in lb.TABLE_BY_NAME and r.startswith("proj.raw.") for r in refs)
    sqlglot = pytest.importorskip("sqlglot")
    sqlglot.parse_one(sql, read="bigquery")


def test_unknown_table_name_is_rejected(capsys):
    assert lb.main(["--only", "nope", "--dry-run"]) == 1
    assert "Unknown table" in capsys.readouterr().out


def test_missing_files_stop_before_any_login(tmp_path, capsys):
    assert lb.main(["--only", "crm_orders", "--data-dir", str(tmp_path)]) == 1
    assert "FIX" in capsys.readouterr().out

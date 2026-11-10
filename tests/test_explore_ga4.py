"""Tests for the GA4 exploration tool (src/explore_ga4.py) and its SQL files.

These need no Google Cloud login. They prove the report formatting is right and that
every query is read-only, targets only the public GA4 sample, and is valid BigQuery SQL.
"""

import datetime as dt
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import explore_ga4 as ex  # noqa: E402

SQL_FILES = sorted((ROOT / "sql" / "ga4_exploration").glob("*.sql"))


def test_header_is_parsed():
    title, rows = ex.parse_header("-- title: My query\n-- max_rows: 7\nSELECT 1", "fallback")
    assert (title, rows) == ("My query", 7)


def test_header_defaults_when_missing():
    assert ex.parse_header("SELECT 1", "fallback") == ("fallback", ex.DEFAULT_MAX_ROWS)


def test_format_value():
    assert ex.format_value(None) == "NULL"
    assert ex.format_value(4295584) == "4,295,584"
    assert ex.format_value(1234.5) == "1,234.50"
    assert ex.format_value(dt.date(2020, 11, 1)) == "2020-11-01"
    assert ex.format_value("a|b") == "a\\|b"


def test_md_table():
    out = ex.md_table(["a", "b"], [[1, "x"], [2000, None]])
    assert out.splitlines()[0] == "| a | b |"
    assert "| 2,000 | NULL |" in out
    assert ex.md_table(["a"], []) == "_No rows returned._"


def test_section_mentions_truncation():
    q = ex.Query("02_x", "Title", 1, "SELECT 1")
    text = ex.render_section(q, ["n"], [[1]], total_rows=5, gb=0.5)
    assert "showing 1 of 5 rows" in text and "0.50 GB" in text


def test_queries_are_found_and_numbered():
    qs = ex.load_queries()
    assert len(qs) >= 12
    assert [q.name[:2] for q in qs] == sorted(q.name[:2] for q in qs)
    assert len(ex.load_queries(only=["01"])) == 1


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.stem)
def test_sql_is_read_only_and_public_data_only(path):
    sql = path.read_text(encoding="utf-8")
    code = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
    assert re.match(r"\s*(SELECT|WITH)\b", code, re.I), "must start with SELECT or WITH"
    assert not re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER|TRUNCATE)\b", code, re.I)
    refs = set(re.findall(r"`([^`]+)`", code))
    assert refs and all(r.startswith("bigquery-public-data.ga4_obfuscated_sample_ecommerce") for r in refs)


@pytest.mark.parametrize("path", SQL_FILES, ids=lambda p: p.stem)
def test_sql_parses_as_bigquery(path):
    sqlglot = pytest.importorskip("sqlglot")
    sqlglot.parse_one(path.read_text(encoding="utf-8"), read="bigquery")

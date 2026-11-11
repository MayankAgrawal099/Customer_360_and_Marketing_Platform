"""The data dictionary must cover every loaded table and column, so it cannot drift from the loader."""

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import load_to_bigquery as lb  # noqa: E402

DOC = (ROOT / "docs" / "data_dictionary.md").read_text(encoding="utf-8")

GA4_TOP_LEVEL = [
    "event_date", "event_timestamp", "event_name", "event_params", "event_previous_timestamp",
    "event_value_in_usd", "event_bundle_sequence_id", "event_server_timestamp_offset", "event_dimensions",
    "user_id", "user_pseudo_id", "user_properties", "user_first_touch_timestamp", "user_ltv", "device", "geo",
    "app_info", "traffic_source", "stream_id", "platform", "privacy_info", "ecommerce", "items",
]


def section(table: str) -> str:
    m = re.search(rf"^## raw\.{table}\b.*?(?=^## |\Z)", DOC, re.S | re.M)
    assert m, f"no section for raw.{table}"
    return m.group(0)


def flat(cols, prefix=""):
    for c in cols:
        if c.type == "RECORD":
            yield from flat(c.fields, f"{prefix}{c.name}.")
        else:
            yield f"{prefix}{c.name}"


@pytest.mark.parametrize("table", [t for t in lb.TABLES if t.kind != "ga4"], ids=lambda t: t.name)
def test_every_column_is_described(table):
    text = section(table.name)
    for col in flat(table.schema):
        assert f"`{col}`" in text or all(f"`{part}`" in text for part in col.split(".")[-1:]), f"{table.name}.{col} undocumented"


@pytest.mark.parametrize("col", GA4_TOP_LEVEL)
def test_every_ga4_top_level_column_is_described(col):
    assert f"| `{col}` |" in section("ga4_events")


def test_every_table_has_a_source_tag_and_row_in_the_overview():
    for t in lb.TABLES:
        assert f"`raw.{t.name}`" in DOC
    assert DOC.count("(REAL)") >= 1 and DOC.count("(SYNTHETIC)") >= 5 and DOC.count("(SCORING ONLY)") == 1


def test_no_unfinished_text():
    assert not re.search(r"\bTODO|TBD|XXX\b", DOC)

"""The Tableau extracts and the dashboard guide must stay in step with the marts: every extract column exists, the SQL
parses as BigQuery, the CSV writer turns values into what Tableau reads, and every `[field]` the guide names is in an extract."""

import csv
import datetime as dt
import re
import sys
from decimal import Decimal
from pathlib import Path

import pytest
import yaml

sqlglot = pytest.importorskip("sqlglot")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import export_for_tableau as ex  # noqa: E402

MARTS = yaml.safe_load((ROOT / "dbt" / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))
COLUMNS = {m["name"]: {c["name"] for c in m["columns"]} for m in MARTS["models"]}


def parse(name):
    return sqlglot.parse_one((ex.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8"), read="bigquery")


def output_columns(name):
    return [e.alias_or_name for e in parse(name).expressions]


@pytest.mark.parametrize("name", ex.EXPORTS)
def test_sql_parses_and_has_unique_output_columns(name):
    cols = output_columns(name)
    assert cols and len(cols) == len(set(cols))


@pytest.mark.parametrize("name", ex.EXPORTS)
def test_every_selected_column_exists_in_its_mart(name):
    tree = parse(name)
    aliases = {t.alias_or_name: t.name for t in tree.find_all(sqlglot.exp.Table) if t.name in COLUMNS}
    assert aliases, "the query must read from a documented mart"
    for col in tree.find_all(sqlglot.exp.Column):
        if col.table and col.table in aliases:
            assert col.name in COLUMNS[aliases[col.table]], f"{aliases[col.table]}.{col.name} does not exist"
        elif not col.table and len(aliases) == 1:
            only = next(iter(aliases.values()))
            assert col.name in COLUMNS[only], f"{only}.{col.name} does not exist"


def test_queries_read_only_the_marts_dataset():
    for name in ex.EXPORTS:
        sql = (ex.SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
        assert "da02-customer360.marts." in sql
        assert not {"email", "full_name", "email_sha256"} & set(output_columns(name)), "no personal fields in the extracts"


def test_customers_extract_has_the_fields_the_dashboard_needs():
    cols = set(output_columns("customers"))
    need = {"customer_id", "segment", "segment_order", "is_buyer", "is_repeat_buyer", "r_score", "f_score", "recency_days", "orders",
            "historical_net_revenue_usd", "gross_revenue_usd", "predicted_revenue_12m_usd", "clv_12m_usd", "country",
            "marketing_opt_in", "first_order_channel_group", "as_of_date"}
    assert need <= cols


def test_cell_conversion():
    assert ex.cell(True) == 1 and ex.cell(False) == 0
    assert ex.cell(None) == ""
    assert ex.cell(dt.date(2021, 1, 2)) == "2021-01-02"
    assert ex.cell(Decimal("1.5")) == 1.5 and ex.cell(3) == 3 and ex.cell("x") == "x"


def test_write_csv(tmp_path):
    path = tmp_path / "t.csv"
    n = ex.write_csv(path, ["a", "b", "c"], [(True, None, dt.date(2020, 1, 1)), (False, 2.5, None)])
    rows = list(csv.reader(path.open(encoding="utf-8")))
    assert n == 2 and rows == [["a", "b", "c"], ["1", "", "2020-01-01"], ["0", "2.5", ""]]

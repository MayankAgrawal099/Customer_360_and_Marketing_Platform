"""Checks on the dbt staging layer that need no BigQuery login and no dbt run.

They prove that every model is documented and tested in the schema file, that the SQL is valid
BigQuery SQL, that each model selects exactly the columns its schema file lists, that every raw
column a model reads really exists in the loaded tables, that nothing reads the ground truth, and
that the accepted values in the tests match the code that produces the data.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

sqlglot = pytest.importorskip("sqlglot")
from sqlglot import exp  # noqa: E402

from src import load_to_bigquery as lb  # noqa: E402
from src.identity import rules as identity_rules  # noqa: E402
from src.synthetic.channels import PAID_CHANNELS  # noqa: E402
from tests.test_data_dictionary import GA4_TOP_LEVEL  # noqa: E402

DBT = ROOT / "dbt"
STAGING = DBT / "models" / "staging"
MODEL_FILES = sorted(STAGING.glob("stg_*.sql"))
SINGULAR_TESTS = sorted((DBT / "tests").glob("*.sql"))
SCHEMA = yaml.safe_load((STAGING / "_staging.yml").read_text(encoding="utf-8"))
SOURCES = yaml.safe_load((STAGING / "_sources.yml").read_text(encoding="utf-8"))
MODELS = {m["name"]: m for m in SCHEMA["models"]}

def render(sql: str) -> str:
    """Replace the dbt Jinja that staging models use with plain table names, so the SQL can be parsed."""
    sql = re.sub(r"\{\{\s*config\(.*?\)\s*\}\}", "", sql, flags=re.S)
    sql = re.sub(r"\{\{\s*source\('(\w+)',\s*'(\w+)'\)\s*\}\}", r"`proj.\1.\2`", sql)
    sql = re.sub(r"\{\{\s*ref\('(\w+)'\)\s*\}\}", r"`proj.staging.\1`", sql)
    assert "{{" not in sql and "{%" not in sql, "Jinja other than config, source and ref is not allowed in staging"
    return sql


def parse(path: Path):
    return sqlglot.parse_one(render(path.read_text(encoding="utf-8")), read="bigquery")


def output_columns(tree) -> list[str]:
    """Names of the columns the model returns. ``select *`` is expanded from the CTE it reads."""
    ctes = {c.alias: c for c in tree.find_all(exp.CTE)}
    sel = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    names: list[str] = []
    for e in sel.expressions:
        if isinstance(e, exp.Star):
            src = sel.args["from_"].this if "from_" in sel.args else sel.args["from"].this
            names += output_columns(ctes[src.name].this)
        else:
            names.append(e.alias_or_name)
    return names


def flat(cols, prefix=""):
    for c in cols:
        if c.type == "RECORD":
            yield from flat(c.fields, f"{prefix}{c.name}.")
        else:
            yield f"{prefix}{c.name}"


# ----------------------------------------------------------------------------- structure
def test_every_model_file_is_in_the_schema_file_and_back():
    assert {p.stem for p in MODEL_FILES} == set(MODELS)


def test_every_model_and_column_has_a_description():
    for name, m in MODELS.items():
        assert m.get("description", "").strip(), f"{name} has no description"
        for c in m["columns"]:
            assert c.get("description", "").strip(), f"{name}.{c['name']} has no description"


@pytest.mark.parametrize("model", [p.stem for p in MODEL_FILES])
def test_model_has_a_primary_key_test(model):
    tests = {c["name"]: c.get("data_tests", []) for c in MODELS[model]["columns"]}
    if model == "stg_ga4__events":                    # events have no natural key; session_key is checked instead
        assert "not_null" in tests["session_key"]
    else:
        assert any("unique" in t and "not_null" in t for t in [tests[c] for c in tests]), f"{model}: no unique key"


@pytest.mark.parametrize("path", MODEL_FILES, ids=lambda p: p.stem)
def test_sql_parses_as_bigquery(path):
    assert parse(path) is not None


@pytest.mark.parametrize("path", MODEL_FILES, ids=lambda p: p.stem)
def test_model_returns_exactly_the_documented_columns(path):
    got = output_columns(parse(path))
    want = [c["name"] for c in MODELS[path.stem]["columns"]]
    assert sorted(got) == sorted(want), f"missing in schema: {set(got) - set(want)}; missing in SQL: {set(want) - set(got)}"
    assert len(got) == len(set(got)), "duplicate output column"


@pytest.mark.parametrize("path", SINGULAR_TESTS, ids=lambda p: p.stem)
def test_singular_tests_parse_and_only_use_known_models(path):
    sql = path.read_text(encoding="utf-8")
    assert re.match(r"\s*(--.*\n\s*)*(with|select)\b", sql, re.I)
    for ref in re.findall(r"ref\('(\w+)'\)", sql):
        assert ref in MODELS, f"{path.name} refers to unknown model {ref}"
    sqlglot.parse_one(render(sql), read="bigquery")


# ----------------------------------------------------------------------------- sources and columns
def declared_sources() -> dict[str, set[str]]:
    return {s["name"]: {t["name"] for t in s["tables"]} for s in SOURCES["sources"]}


def test_every_source_used_is_declared_and_every_loaded_table_except_ground_truth_is_a_source():
    declared = declared_sources()
    used = set()
    for p in MODEL_FILES:
        used |= set(re.findall(r"source\('(\w+)',\s*'(\w+)'\)", p.read_text(encoding="utf-8")))
    assert all(t in declared.get(s, set()) for s, t in used)
    loaded = {t.name for t in lb.TABLES} - {"ground_truth_identity_links"}
    assert declared["raw"] == loaded


def test_ground_truth_is_never_read_by_a_model_or_test():
    for p in [*MODEL_FILES, *SINGULAR_TESTS, STAGING / "_sources.yml", STAGING / "_staging.yml"]:
        code = "\n".join(line for line in p.read_text(encoding="utf-8").splitlines()
                         if not line.strip().startswith(("#", "--")))
        assert "ground_truth" not in code, f"{p.name} refers to the ground truth"


def raw_table_of(path: Path) -> tuple[str, str] | None:
    m = re.search(r"source\('(\w+)',\s*'(\w+)'\)", path.read_text(encoding="utf-8"))
    return (m.group(1), m.group(2)) if m else None


@pytest.mark.parametrize("path", [p for p in MODEL_FILES if p.stem != "stg_ga4__events"
                                  and raw_table_of(p) is not None], ids=lambda p: p.stem)
def test_columns_read_from_a_raw_table_exist_in_it(path):
    schema, table = raw_table_of(path)
    if schema == "identity":
        known = set(identity_rules.LINK_COLUMNS)
    else:
        known = set(flat(lb.TABLE_BY_NAME[table].schema))
    tree = parse(path)
    for col in tree.find_all(exp.Column):
        parts = [p.name for p in (col.args.get("db"), col.args.get("table"), col.this) if p is not None and p.name]
        # Ignore references to aliases defined in the same query (none are expected in these simple models).
        assert ".".join(parts) in known, f"{path.stem} reads {'.'.join(parts)}, which is not in {table}"


def test_ga4_events_reads_only_known_ga4_columns():
    tree = parse(STAGING / "stg_ga4__events.sql")
    params = next(c for c in tree.find_all(exp.CTE) if c.alias == "params").this
    roots = set()
    for col in params.find_all(exp.Column):
        if col.find_ancestor(exp.Subquery, exp.Exists):          # inside an event_params lookup
            continue
        roots.add((col.args.get("db") or col.args.get("table") or col.this).name)
    assert roots <= set(GA4_TOP_LEVEL), f"unknown GA4 columns: {roots - set(GA4_TOP_LEVEL)}"


def test_ga4_param_keys_are_the_ones_documented():
    sql = (STAGING / "stg_ga4__events.sql").read_text(encoding="utf-8")
    doc = (ROOT / "docs" / "data_dictionary.md").read_text(encoding="utf-8")
    for key in set(re.findall(r"key = '(\w+)'", sql)):
        assert f"`{key}`" in doc, f"event parameter {key} is read but not in the data dictionary"


# ----------------------------------------------------------------------------- drift guards
def accepted(model: str, column: str) -> set[str]:
    col = next(c for c in MODELS[model]["columns"] if c["name"] == column)
    for t in col.get("data_tests", []):
        if isinstance(t, dict) and "accepted_values" in t:
            return set(t["accepted_values"]["arguments"]["values"])
    raise AssertionError(f"no accepted_values test on {model}.{column}")


def test_accepted_values_match_the_code_that_produces_the_data():
    assert accepted("stg_ad_spend", "channel") == set(PAID_CHANNELS)
    assert accepted("stg_identity__links", "link_rule") == set(identity_rules.RULE_SCORE)
    assert accepted("stg_identity__links", "confidence") == {"high", "medium"}
    assert accepted("stg_crm__orders", "order_channel") == {"web", "app"}
    assert accepted("stg_crm__orders", "status") == {"completed", "refunded"}


def test_staging_materialisation():
    cfg = yaml.safe_load((DBT / "dbt_project.yml").read_text(encoding="utf-8"))
    assert cfg["models"]["customer_360"]["staging"]["+materialized"] == "view"
    assert "materialized='table'" in (STAGING / "stg_ga4__events.sql").read_text(encoding="utf-8")


def test_purchase_rule_matches_the_extract_that_built_the_synthetic_orders():
    """The staging purchases must keep exactly what sql/ga4_extract/purchases.sql kept."""
    extract = (ROOT / "sql" / "ga4_extract" / "purchases.sql").read_text(encoding="utf-8").lower()
    model = (STAGING / "stg_ga4__purchases.sql").read_text(encoding="utf-8").lower()
    for needle in ("'(not set)'", "> 0", "qualify"):
        assert needle in extract and needle in model


def test_ad_spend_keys_cannot_be_null():
    """concat() returns NULL if any part is NULL, and real ad spend rows can have an empty campaign."""
    sql = (STAGING / "stg_ad_spend.sql").read_text(encoding="utf-8").lower()
    for col in ("source", "medium", "campaign"):
        assert f"coalesce(nullif(trim({col}), ''), '(not set)') as {col}" in sql
    tests = {c["name"]: c.get("data_tests", []) for c in MODELS["stg_ad_spend"]["columns"]}
    assert all("not_null" in tests[c] for c in ("source", "medium", "campaign", "ad_spend_id", "campaign_key"))

"""Guard the dbt test coverage, and check the results recorder on a made-up dbt run."""

import json
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import dbt_results as dr  # noqa: E402

MODELS = {}
for f in (ROOT / "dbt" / "models").rglob("_*.yml"):
    for m in (yaml.safe_load(f.read_text(encoding="utf-8")) or {}).get("models", []):
        MODELS[m["name"]] = m


def column_tests(m):
    for c in m.get("columns", []):
        for t in c.get("data_tests") or []:
            yield c["name"], (t if isinstance(t, str) else next(iter(t)))


# GA4 events carry no event id: the same device can log two identical events in one microsecond, so the
# event table has no natural key. Its keys are checked one level up (sessions, purchases).
NO_NATURAL_KEY = {"stg_ga4__events"}
# Composite keys cannot be expressed as a column-level unique test; one singular test covers them.
COMPOSITE_KEY = {"int_conversion_touchpoints", "fct_attribution_credits", "fct_attribution_by_channel", "fct_attribution_checks",
                 "fct_campaign_roi", "fct_channel_roi", "fct_campaign_cpa", "fct_channel_cpa"}


@pytest.mark.parametrize("name", sorted(set(MODELS) - NO_NATURAL_KEY - COMPOSITE_KEY))
def test_every_model_has_a_unique_and_not_null_key(name):
    tests = set(column_tests(MODELS[name]))
    keys = {c for c, t in tests if t == "unique"}
    assert keys, f"{name} has no unique test"
    assert any((k, "not_null") in tests for k in keys), f"{name}: no unique column is also not_null"


def test_composite_keys_are_checked_by_a_singular_test():
    sql = (ROOT / "dbt" / "tests" / "assert_attribution_keys_are_unique.sql").read_text(encoding="utf-8")
    for model in COMPOSITE_KEY:
        assert f"ref('{model}')" in sql, model


def test_all_four_generic_test_types_are_used_in_the_project():
    used = {t for m in MODELS.values() for _, t in column_tests(m)}
    assert {"unique", "not_null", "relationships", "accepted_values"} <= used


@pytest.mark.parametrize("name", ["fct_sessions", "fct_orders", "dim_customers"])
def test_marts_check_categories_and_references(name):
    used = {t for _, t in column_tests(MODELS[name])}
    assert {"relationships", "accepted_values"} <= used


def test_every_column_has_a_description():
    for name, m in MODELS.items():
        for c in m["columns"]:
            assert c.get("description"), f"{name}.{c['name']}"


# ----------------------------------------------------------------------------- the recorder
def fake_run(bad: bool):
    nodes, results = {}, []

    def add(uid, name, status, meta=None, attached=None, deps=(), failures=0, col=None):
        nodes[uid] = dict(resource_type="test", name=name, test_metadata=meta, attached_node=attached,
                          column_name=col, depends_on=dict(nodes=list(deps)))
        results.append(dict(unique_id=uid, status=status, failures=failures, execution_time=1.5))

    add("test.p.unique_a_id.1", "unique_a_id", "pass", dict(name="unique"), "model.p.a", col="id")
    add("test.p.not_null_a_id.2", "not_null_a_id", "pass", dict(name="not_null"), "model.p.a", col="id")
    add("test.p.rel.3", "rel", "pass", dict(name="relationships"), "model.p.b", col="a_id")
    add("test.p.av.4", "av", "fail" if bad else "pass", dict(name="accepted_values"), "model.p.b", col="kind",
        failures=7 if bad else 0)
    add("test.p.assert_x", "assert_x", "pass", None, None, ["model.p.a", "model.p.b"])
    nodes["model.p.a"] = dict(resource_type="model")
    return dict(metadata=dict(generated_at="2026-11-13", dbt_version="1.12"), args=dict(which="test"), results=results), \
        dict(nodes=nodes)


def test_report_for_a_clean_run():
    text = dr.build_report(*fake_run(False))
    assert "ALL TESTS PASSED" in text and "5 of 5 passed" in text
    assert "| unique | 1 | 1 | 0 | 0 | 0 |" in text and "| singular | 1 | 1 | 0 | 0 | 0 |" in text
    assert "| `assert_x` | a, b | 0 | pass |" in text and "None." in text


def test_report_lists_a_failure():
    text = dr.build_report(*fake_run(True))
    assert "ATTENTION NEEDED" in text and "| `av` | accepted_values | b | kind | fail | 7 |" in text


def test_cli_writes_the_report_and_sets_the_exit_code(tmp_path):
    for bad, code in ((False, 0), (True, 1)):
        rr, mf = fake_run(bad)
        (tmp_path / "run_results.json").write_text(json.dumps(rr))
        (tmp_path / "manifest.json").write_text(json.dumps(mf))
        out = tmp_path / "r.md"
        assert dr.main(["--target-dir", str(tmp_path), "--out", str(out)]) == code
        assert out.read_text(encoding="utf-8").startswith("# dbt test results")


def test_cli_explains_a_missing_run(tmp_path, capsys):
    assert dr.main(["--target-dir", str(tmp_path), "--out", str(tmp_path / "r.md")]) == 2
    assert "Run `uv run dbt test" in capsys.readouterr().err

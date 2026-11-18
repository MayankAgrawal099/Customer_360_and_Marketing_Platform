"""docs/test_results.md matches the recorded results, and the recorded dbt result matches the dbt project."""

import json
import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import test_summary as ts  # noqa: E402

PAGE = (ROOT / "docs" / "test_results.md").read_text(encoding="utf-8")
DBT = ts.read_dbt(ts.DBT_MD.read_text(encoding="utf-8"))
IDENTITY = json.loads(ts.IDENTITY_JSON.read_text(encoding="utf-8"))
ATTRIBUTION = json.loads(ts.ATTRIBUTION_JSON.read_text(encoding="utf-8"))


def _expected_dbt_tests() -> tuple[int, int]:
    generic = 0
    for yml in (ROOT / "dbt" / "models").glob("*/_*.yml"):
        doc = yaml.safe_load(yml.read_text(encoding="utf-8")) or {}
        for section in ("models", "sources"):
            for item in doc.get(section, []) or []:
                generic += len(item.get("data_tests", item.get("tests", [])) or [])
                for col in item.get("columns", []) or []:
                    generic += len(col.get("data_tests", col.get("tests", [])) or [])
                for table in item.get("tables", []) or []:
                    for col in table.get("columns", []) or []:
                        generic += len(col.get("data_tests", col.get("tests", [])) or [])
    return generic, len(list((ROOT / "dbt" / "tests").glob("*.sql")))


def test_the_page_is_up_to_date():
    recorded = re.search(r"^\| pytest suite \| (.+?) \|", PAGE, flags=re.M).group(1)
    line = None if recorded.startswith("run `") else recorded
    assert ts.build(line) == PAGE, "run: uv run python -m src.test_summary"


def test_the_recorded_dbt_run_covers_every_test_in_the_project():
    generic, singular = _expected_dbt_tests()
    assert DBT["by_type"]["singular"][0] == singular, "docs/dbt_test_results.md is stale: run  uv run python -m src.dbt_results --run"
    assert DBT["total"] == generic + singular, "docs/dbt_test_results.md is stale: run  uv run python -m src.dbt_results --run"


def test_every_dbt_test_passed():
    assert DBT["passed"] == DBT["total"] and DBT["warn"] == DBT["fail"] == DBT["error"] == 0
    assert sum(t[0] for t in DBT["by_type"].values()) == DBT["total"]


def test_all_attribution_checks_passed():
    assert ATTRIBUTION["checks_passed"] == ATTRIBUTION["checks"] and not ATTRIBUTION["failed_checks"]
    totals = ATTRIBUTION["total_revenue_by_model"].values()
    assert max(totals) - min(totals) < 0.01


def test_identity_numbers_in_the_page_match_the_report():
    assert f"{IDENTITY['correct_links']:,} of {IDENTITY['predicted_links']:,}" in PAGE
    assert f"{IDENTITY['found_links']:,} of {IDENTITY['true_links']:,}" in PAGE
    assert IDENTITY["wrong_customer_links"] == 0 and IDENTITY["precision"] == 1.0
    assert IDENTITY["recall"] <= IDENTITY["recall_ceiling"] + 1e-9


def test_the_page_states_the_data_is_partly_synthetic():
    assert "synthetic" in PAGE and "real GA4" in PAGE


def test_the_readme_headlines_match_the_page():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert f"{ATTRIBUTION['checks_passed']} of {ATTRIBUTION['checks']} checks pass" in readme
    assert f"{IDENTITY['correct_links']:,} of {IDENTITY['predicted_links']:,}" in readme
    assert "docs/test_results.md" in readme
    assert "test_results.md" in (ROOT / "docs" / "README.md").read_text(encoding="utf-8")


def test_links_in_the_page_exist():
    for link in re.findall(r"\]\(([\w./-]+\.md)(?:#[\w-]+)?\)", PAGE):
        assert (ROOT / "docs" / link).resolve().exists(), link

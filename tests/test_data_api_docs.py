"""docs/data_api_docs.md is generated from the project and must match it."""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import build_data_api_docs as gen  # noqa: E402
from src import export_for_tableau  # noqa: E402

DOC = (ROOT / "docs" / "data_api_docs.md").read_text(encoding="utf-8")


def test_the_document_is_up_to_date():
    assert gen.build() == DOC, "run: uv run python -m src.build_data_api_docs"
    assert gen.main(["--check"]) == 0


def test_every_model_file_has_a_documented_entry_and_the_reverse():
    documented = set(gen.load_models())
    assert gen.sql_files_without_yaml() == documented, gen.sql_files_without_yaml() ^ documented


def test_every_model_has_a_section_and_every_column_a_row():
    for name, m in gen.load_models().items():
        assert f"#### {name}\n" in DOC, name
        section = DOC.split(f"#### {name}\n", 1)[1].split("\n#### ", 1)[0].split("\n### ", 1)[0].split("\n## ", 1)[0]
        for col, _, _ in m["columns"]:
            assert f"| `{col}` |" in section, (name, col)


def test_every_column_of_every_model_has_a_description():
    for name, m in gen.load_models().items():
        assert m["description"], name
        for col, desc, _ in m["columns"]:
            assert desc, (name, col)


def test_layers_and_materializations_match_dbt_project():
    cfg = yaml.safe_load((ROOT / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))["models"]["customer_360"]
    for layer, (schema, mat, _) in gen.LAYERS.items():
        assert cfg[layer]["+schema"] == schema and cfg[layer]["+materialized"] == mat


def test_lineage_only_names_real_models_and_sources():
    models = gen.load_models()
    for name, m in models.items():
        for ref in m["refs"]:
            assert ref in models, (name, ref)
    sources = yaml.safe_load((ROOT / "dbt" / "models" / "staging" / "_sources.yml").read_text(encoding="utf-8"))["sources"]
    known = {f"{s['name']}.{t['name']}" for s in sources for t in s["tables"]}
    for name, m in models.items():
        for src in m["sources"]:
            assert src in known, (name, src)


def test_the_ground_truth_table_is_not_read_by_any_model():
    for m in gen.load_models().values():
        assert not any("ground_truth" in s for s in m["sources"])
    assert "ground_truth" not in "".join((ROOT / m["path"]).read_text(encoding="utf-8") for m in gen.load_models().values())


def test_the_tableau_files_listed_are_exactly_the_ones_exported():
    assert list(gen.TABLEAU_FILES) == export_for_tableau.ALL_EXPORTS
    for f in export_for_tableau.ALL_EXPORTS:
        cols, _ = gen.tableau_columns(f)
        assert cols and f"`{f}.csv`** ({len(cols)} columns)" in DOC
        assert not {"email", "first_name", "last_name", "name"} & set(cols), f


def test_every_command_is_a_real_module_and_documented():
    for module, *_ in gen.COMMANDS:
        assert (ROOT / (module.replace(".", "/") + ".py")).exists(), module
        assert f"### `{module}`" in DOC


def test_every_cli_flag_is_in_the_document():
    for module, *_ in gen.COMMANDS:
        if module == "src.build_data_api_docs":
            continue
        for flag, _, _ in gen.command_flags(module):
            assert f"`{flag}`" in DOC, (module, flag)


def test_reports_listed_exist_in_the_repository_or_are_generated():
    for path, module, _ in gen.REPORTS:
        assert (ROOT / (module.replace(".", "/") + ".py")).exists(), module
        if path.startswith("reports/") or path.startswith("docs/"):
            assert (ROOT / path).exists(), path


def test_the_singular_test_count_is_the_real_count():
    n = len(list((ROOT / "dbt" / "tests").glob("*.sql")))
    assert f"**{n} singular tests**" in DOC
    assert len(re.findall(r"^\| `assert_", DOC, flags=re.M)) == n


def test_the_docs_index_lists_the_document_and_the_doc_names_no_missing_file():
    index = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    assert "data_api_docs.md" in index
    for link in re.findall(r"\]\(([\w./-]+\.md)\)", DOC):
        assert (ROOT / "docs" / link).exists(), link

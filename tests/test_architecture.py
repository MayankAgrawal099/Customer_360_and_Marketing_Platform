"""The architecture diagram names only things that exist in the repository."""

import importlib.util
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCH = ROOT / "docs" / "architecture"


def _diagram():
    spec = importlib.util.spec_from_file_location("build_diagram", ARCH / "build_diagram.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


D = _diagram()
MODEL_FILES = {p.stem for p in (ROOT / "dbt" / "models").rglob("*.sql")}


def _names(items):
    return [re.split(r"\s", i.strip())[0] for i in items]


def test_every_dbt_model_in_the_diagram_exists():
    for group in (D.STAGING, D.INTERMEDIATE, D.MARTS_CORE, D.MARTS_SCORING, D.MARTS_ATTRIBUTION, D.MARTS_RETURN):
        for name in _names(group):
            assert name in MODEL_FILES, name


def test_every_dbt_model_is_in_the_diagram():
    drawn = set(_names(D.STAGING + D.INTERMEDIATE + D.MARTS_CORE + D.MARTS_SCORING + D.MARTS_ATTRIBUTION + D.MARTS_RETURN))
    assert MODEL_FILES == drawn, MODEL_FILES ^ drawn


def test_raw_tables_are_loaded_by_the_loader():
    loader = (ROOT / "src" / "load_to_bigquery.py").read_text(encoding="utf-8")
    for table, _ in D.RAW_TABLES:
        assert table.split()[0] in loader, table


def test_identity_tables_are_written_by_the_identity_step():
    run = (ROOT / "src" / "identity" / "run.py").read_text(encoding="utf-8")
    for name in _names(D.IDENTITY_TABLES):
        assert name in run, name


def test_python_commands_are_real_modules():
    for cmd in D.PY_COMMANDS:
        assert (ROOT / (cmd.replace(".", "/") + ".py")).exists() or (ROOT / cmd.replace(".", "/") / "__main__.py").exists() or (ROOT / cmd.replace(".", "/") / "run.py").exists(), cmd


def test_the_counts_stated_in_the_picture_are_true():
    svg = (ARCH / "architecture.svg").read_text(encoding="utf-8")
    singular = list((ROOT / "dbt" / "tests").glob("*.sql"))
    assert f"{len(singular)} singular tests" in svg
    from src import export_for_tableau as e
    assert f"{len(e.ALL_EXPORTS)} CSV files" in svg


def test_files_exist_and_the_svg_is_current():
    assert (ARCH / "architecture.png").stat().st_size > 20_000
    svg = (ARCH / "architecture.svg").read_text(encoding="utf-8")
    for name in _names(D.MARTS_RETURN):
        assert name in svg


def test_the_readme_embeds_the_image_and_the_mermaid_block_is_gone():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "](docs/architecture/architecture.png)" in readme
    assert "```mermaid" not in readme
    assert (ARCH / "README.md").exists()

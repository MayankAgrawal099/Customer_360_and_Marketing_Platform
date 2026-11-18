"""The READMEs must tell the truth: every command points at a real module and flag, every link and image exists, the
real-versus-synthetic statement is present, and the headline numbers match the generated reports."""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
READMES = [ROOT / "README.md", ROOT / "tableau" / "README.md", ROOT / "docs" / "README.md"]
TEXT = {p.relative_to(ROOT).as_posix(): p.read_text(encoding="utf-8") for p in READMES}
ROOT_README = TEXT["README.md"]
TABLEAU_README = TEXT["tableau/README.md"]

CUSTOMER_URL = "customer_360/Customer360andSegments"
ATTRIBUTION_URL = "attribution_roi_cpa/AttributionROIandCPA"


# ----------------------------------------------------------------------------- the data statement
def test_root_readme_says_ga4_is_real_and_the_rest_is_synthetic():
    box = ROOT_README.split("## What it does")[0]
    rows = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"^> \| \*{0,2}([^|]+?)\*{0,2} \| \*{0,2}(Real|Synthetic)\*{0,2} \|", box, re.M)}
    assert rows.get("Website sessions, events and purchases (GA4)") == "Real"
    assert rows.get("CRM customers and orders") == "Synthetic"
    assert rows.get("Ad spend") == "Synthetic"
    assert rows.get("Segment events and the identity ground truth") == "Synthetic"
    assert "bigquery-public-data.ga4_obfuscated_sample_ecommerce" in box
    assert "Faker" in box and "fixed seed (42)" in box


def test_tableau_readme_repeats_the_statement():
    assert "GA4 website data is real" in TABLEAU_README and "synthetic" in TABLEAU_README


# ----------------------------------------------------------------------------- setup commands
def commands(text):
    return re.findall(r"uv run python -m (src[\w.]+)([^\n`|]*)", text)


def test_every_python_command_points_at_a_real_module_and_flag():
    found = commands(ROOT_README) + commands(TABLEAU_README) + commands(TEXT["docs/README.md"])
    assert len(found) >= 8
    for module, rest in found:
        path = ROOT / (module.replace(".", "/") + ".py")
        assert path.is_file(), f"{module} does not exist"
        source = path.read_text(encoding="utf-8")
        for flag in re.findall(r"(--[a-z][a-z-]*)", rest):
            assert f'"{flag}"' in source, f"{module} has no {flag} option"


def test_dbt_commands_use_the_project_and_profile_folders():
    dbt = re.findall(r"uv run dbt (\w+)([^\n`|]*)", ROOT_README)
    assert {c for c, _ in dbt} >= {"debug", "run", "test"}
    for cmd, rest in dbt:
        assert "--project-dir dbt" in rest and "--profiles-dir dbt" in rest, f"dbt {cmd} lacks the folders"


def test_setup_matches_the_project_files():
    py = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    assert f"Python {py}" in ROOT_README
    assert 'requires-python = ">=3.12"' in (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    project = re.search(r"GCP_PROJECT=(\S+)", (ROOT / ".env.example").read_text(encoding="utf-8")).group(1)
    assert project in ROOT_README
    assert f'DEFAULT_PROJECT = "{project}"' in (ROOT / "src" / "identity" / "run.py").read_text(encoding="utf-8")
    assert "uv sync" in ROOT_README and "gcloud auth application-default login" in ROOT_README
    assert "pytest" in ROOT_README


def test_no_secret_is_described_as_needed():
    low = ROOT_README.lower()
    for word in ("keyfile", "service account key", "service-account", "json key"):
        assert word not in low


# ----------------------------------------------------------------------------- links and files
def local_targets(text):
    for target in re.findall(r"\]\(([^)\s]+)\)", text):
        if target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        yield target.split("#")[0]


@pytest.mark.parametrize("name", sorted(TEXT))
def test_every_relative_link_and_image_exists(name):
    base = (ROOT / name).parent
    bad = [t for t in local_targets(TEXT[name]) if t and not (base / t).exists()]
    assert not bad, f"{name}: broken links {bad}"


def test_docs_index_lists_only_files_that_exist():
    docs = ROOT / "docs"
    for filename in re.findall(r"`([\w]+\.md)`", TEXT["docs/README.md"]):
        assert (docs / filename).is_file(), f"docs/{filename} is listed but missing"


def test_the_tableau_readme_holds_the_dashboards_and_the_root_readme_redirects():
    # either link form works (/views/... or /app/profile/<name>/viz/...); both must point at public.tableau.com
    assert "https://public.tableau.com/" in TABLEAU_README
    assert CUSTOMER_URL in TABLEAU_README and ATTRIBUTION_URL in TABLEAU_README
    assert "tableau_customer_360.png" in TABLEAU_README and "tableau_attribution_roi.png" in TABLEAU_README
    for workbook in ("customer_360.twbx", "attribution_roi_cpa.twbx"):
        assert (ROOT / "tableau" / "workbooks" / workbook).is_file()
        assert f"workbooks/{workbook}" in TABLEAU_README
    section = ROOT_README.split("## Dashboards (Tableau Public)")[1].split("\n## ")[0]
    assert "(tableau/README.md)" in section
    assert "![" not in section and "public.tableau.com" not in section, "the root README only points to the Tableau README"
    assert len(section.strip().splitlines()) <= 6
    assert "Customer 360 and Segments" in section and "Attribution, ROI and CPA" in section


def test_the_workbooks_are_not_duplicated_outside_the_workbooks_folder():
    stray = [p.name for p in (ROOT / "tableau").glob("*.twbx")]
    assert not stray, f"move {stray} into tableau/workbooks/"


def test_the_tableau_readme_lists_every_extract():
    from src import export_for_tableau as ex  # noqa: PLC0415
    for name in ex.ALL_EXPORTS:
        assert f"`{name}.csv`" in TABLEAU_README, f"{name}.csv is not described"
        assert (ROOT / "sql" / "tableau" / f"{name}.sql").is_file()


# ----------------------------------------------------------------------------- numbers match the generated reports
def test_headline_numbers_match_the_reports():
    identity = (ROOT / "reports" / "identity_accuracy_report.md").read_text(encoding="utf-8")
    attribution = (ROOT / "reports" / "attribution_comparison.md").read_text(encoding="utf-8")
    for fragment in ("5,931 of 5,931", "5,931 of 6,529", "85.3%", "598"):
        assert fragment in identity, f"{fragment} is not in the identity report"
        assert fragment in ROOT_README, f"{fragment} is not in the README"
    assert "100.0%" in identity and "100.0%" in ROOT_README and "90.8%" in ROOT_README
    assert "30 of 30 checks passed" in attribution and "30 of 30 checks pass" in ROOT_README
    assert "$344,692" in attribution and "$344,692" in ROOT_README and "5,120" in ROOT_README
    assert "6,003" in identity and "6,003" in ROOT_README


def test_the_readme_dbt_test_count_is_not_hard_coded():
    # the dbt test count changes with every model; the README must point at the recorded result instead
    assert re.search(r"\b\d{3} (dbt )?tests\b", ROOT_README) is None
    assert "docs/dbt_test_results.md" in ROOT_README

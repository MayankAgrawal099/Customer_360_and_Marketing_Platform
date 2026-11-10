"""Checks that the repository skeleton is in place and the dbt project files are valid.

These tests need no Google Cloud login. They catch a missing folder, a broken
dbt_project.yml or a profile that has crept in with a secret.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

REQUIRED_DIRS = [
    "dbt/models/staging", "dbt/models/intermediate", "dbt/models/marts", "dbt/macros",
    "src", "sql", "data/synthetic", "docs/architecture", "docs/screenshots",
    "tableau/workbooks", "tableau/exports", "tests", "reports",
]


def test_required_folders_exist():
    missing = [d for d in REQUIRED_DIRS if not (ROOT / d).is_dir()]
    assert not missing, f"Missing folders: {missing}"


def test_dbt_project_file_is_valid():
    cfg = yaml.safe_load((ROOT / "dbt" / "dbt_project.yml").read_text(encoding="utf-8"))
    assert cfg["name"] == "customer_360"
    assert cfg["profile"] == "customer_360"
    layers = cfg["models"]["customer_360"]
    assert set(layers) == {"staging", "intermediate", "marts"}
    assert layers["marts"]["+materialized"] == "table"


def test_profile_uses_login_not_secrets():
    text = (ROOT / "dbt" / "profiles.yml").read_text(encoding="utf-8")
    prof = yaml.safe_load(text)["customer_360"]["outputs"]["dev"]
    assert prof["type"] == "bigquery" and prof["method"] == "oauth"
    assert prof["location"] == "US"
    for word in ("keyfile", "password", "private_key"):
        assert word not in text.lower().replace("no secrets here", "")


def test_gitignore_blocks_secrets():
    ignored = (ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in (".env", ".venv/", "dbt/target/"):
        assert entry in ignored

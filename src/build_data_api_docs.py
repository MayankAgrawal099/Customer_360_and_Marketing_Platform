"""Write docs/data_api_docs.md: the reference for every table, dbt model, output file and command.

    uv run python -m src.build_data_api_docs            # rewrite docs/data_api_docs.md
    uv run python -m src.build_data_api_docs --check    # exit 1 if the file is out of date (used by tests)

Nothing is typed in by hand except the short "what it is for" lines at the top of this file. The model list, grains,
descriptions, columns, tests and lineage come from dbt/models/*.yml and the model SQL; the Tableau file columns come from
sql/tableau/*.sql; the command flags come from each module's argparse calls. When a model, column or flag changes, run this
command and the document follows. Needs PyYAML and sqlglot (both in the dev group that `uv sync` installs).
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import defaultdict
from pathlib import Path

import sqlglot
import yaml
from sqlglot import exp

ROOT = Path(__file__).resolve().parents[1]
MODELS = ROOT / "dbt" / "models"
SINGULAR = ROOT / "dbt" / "tests"
TABLEAU_SQL = ROOT / "sql" / "tableau"
OUT = ROOT / "docs" / "data_api_docs.md"

# ---------------------------------------------------------------------------------------------- hand-written context
# Layer of each model folder: dataset, materialization (also read from dbt_project.yml by the test).
LAYERS = {
    "staging": ("staging", "view", "One cleaned copy of each raw table. No business logic."),
    "intermediate": ("intermediate", "view", "Sessions and touchpoints: the building blocks of the marts."),
    "marts": ("marts", "table", "Business-ready tables. Dashboards and reports read these."),
}

DATASETS = [
    ("raw", "src.load_to_bigquery", "Source data exactly as loaded: the real GA4 events and the synthetic tables.", "7 tables"),
    ("identity", "src.identity.run", "Device-to-customer links found by the Python rules, and the evidence that was rejected.", "2 tables"),
    ("staging", "dbt run", "Views over raw and identity.", "{staging} views"),
    ("intermediate", "dbt run", "Views for sessions and conversion touchpoints.", "{intermediate} views"),
    ("marts", "dbt run", "Tables for customers, scoring, attribution and campaign return.", "{marts} tables"),
]

TABLEAU_FILES = {
    "customers": ("one CRM customer", "Customer 360 and Segments", "Segment, RFM, CLV and profile in one flat table. No name or email."),
    "segments": ("one segment", "Customer 360 and Segments", "Segment definition, rule and recommended action."),
    "orders": ("one CRM order", "Customer 360 and Segments", "Order with refund status and first-order channel."),
    "attribution_by_channel": ("one model x credited channel", "Attribution, ROI and CPA", "Credited orders, revenue and share for each channel."),
    "channel_performance": ("one model x paid channel", "Attribution, ROI and CPA", "Spend, credit, ROAS, cost per order and per new customer by paid channel."),
    "campaign_performance": ("one model x paid campaign", "Attribution, ROI and CPA", "The same measures for each paid campaign."),
    "budget_recommendations": ("one channel or campaign", "Attribution, ROI and CPA", "ROAS range across the five views and the rule-based recommendation."),
}

REPORTS = [
    ("reports/identity_resolution_report.md", "src.identity.run", "Accuracy of the identity rules on this run (Markdown)."),
    ("reports/identity_accuracy_report.md", "src.identity.accuracy", "Precision, recall, coverage by rule, role and revenue (Markdown)."),
    ("reports/identity_accuracy.json", "src.identity.accuracy", "The same numbers as JSON."),
    ("reports/attribution_comparison.md", "src.attribution_report", "Revenue by channel under four models, spread, introduces or closes, checks (Markdown)."),
    ("reports/attribution_comparison.json", "src.attribution_report", "The same numbers as JSON."),
    ("docs/test_results.md", "src.test_summary", "All final check results on one page: dbt, identity accuracy, attribution, pytest."),
    ("docs/dbt_test_results.md", "src.dbt_results", "Every dbt test and its result from the last full `dbt test`."),
    ("docs/ga4_exploration.md", "src.explore_ga4", "What the GA4 sample contains (Markdown, from 16 queries)."),
]

# command -> (what it does, reads, writes, needs BigQuery)
COMMANDS = [
    ("src.synthetic.ga4_extract", "Pull small real-data summaries from the GA4 sample to size the synthetic data.", "GA4 public dataset", "data/raw/ga4_extract/ (git-ignored)", True),
    ("src.synthetic.generate_crm", "Generate the synthetic CRM, orders, ad spend, Segment events and ground truth (Faker, fixed seed).", "data/raw/ga4_extract/", "data/synthetic/", False),
    ("src.load_to_bigquery", "Load the raw layer into BigQuery and verify row counts, totals and shared keys.", "data/synthetic/, GA4 public dataset", "BigQuery dataset raw", True),
    ("src.identity.run", "Resolve identity with the two rules and write the links.", "raw.*", "identity.identity_links, identity.identity_rejected, data/identity/, reports/identity_resolution_report.md", True),
    ("src.identity.accuracy", "Score identity resolution against the ground truth.", "raw.*, identity.*", "reports/identity_accuracy_report.md, reports/identity_accuracy.json", True),
    ("src.attribution_report", "Write the attribution comparison report from the marts.", "marts.fct_attribution_model_comparison, marts.fct_attribution_checks", "reports/attribution_comparison.md and .json", True),
    ("src.dbt_results", "Record the result of `dbt test` (with --run it runs the tests first).", "dbt/target/run_results.json, manifest.json", "docs/dbt_test_results.md", False),
    ("src.export_for_tableau", "Export the marts to the CSV files Tableau reads.", "marts.* (through sql/tableau/*.sql)", "tableau/data/*.csv (git-ignored)", True),
    ("src.explore_ga4", "Run the 16 exploration queries on the GA4 sample and write the findings.", "GA4 public dataset (sql/ga4_exploration/)", "docs/ga4_exploration.md", True),
    ("src.test_summary", "Collect the final results of the dbt, identity and attribution checks into one page (with --run-pytest it also records the pytest count).", "docs/dbt_test_results.md, reports/identity_accuracy.json, reports/attribution_comparison.json", "docs/test_results.md", False),
    ("src.build_data_api_docs", "Rebuild this document.", "dbt/models/, sql/tableau/, src/", "docs/data_api_docs.md", False),
]

PIPELINE = [
    ("1", "`uv run python -m src.synthetic.ga4_extract` then `src.synthetic.generate_crm`", "optional: the generated CSVs are committed", "data/synthetic/"),
    ("2", "`uv run python -m src.load_to_bigquery`", "raw", "`raw.*`"),
    ("3", "`uv run python -m src.identity.run`", "raw", "`identity.*`"),
    ("4", "`uv run dbt run --project-dir dbt --profiles-dir dbt`", "raw, identity", "`staging`, `intermediate`, `marts`"),
    ("5", "`uv run dbt test --project-dir dbt --profiles-dir dbt`", "every model", "pass or fail"),
    ("6", "`uv run python -m src.identity.accuracy`, `src.attribution_report`, `src.dbt_results --run`", "identity, marts, dbt", "`reports/`, `docs/dbt_test_results.md`"),
    ("7", "`uv run python -m src.export_for_tableau`", "marts", "`tableau/data/*.csv`"),
]


# ---------------------------------------------------------------------------------------------- reading the project
def load_models() -> dict[str, dict]:
    """name -> {layer, description, columns[(name, description, [tests])], refs, sources, path}"""
    models: dict[str, dict] = {}
    for layer in LAYERS:
        for yml in sorted((MODELS / layer).glob("_*.yml")):
            if yml.name == "_sources.yml":
                continue
            for m in (yaml.safe_load(yml.read_text(encoding="utf-8")) or {}).get("models", []):
                cols = []
                for c in m.get("columns", []):
                    tests = []
                    for t in c.get("data_tests", c.get("tests", [])) or []:
                        tests.append(t if isinstance(t, str) else next(iter(t)))
                    cols.append((c["name"], " ".join(str(c.get("description", "")).split()), tests))
                models[m["name"]] = {"layer": layer, "description": " ".join(str(m.get("description", "")).split()), "columns": cols}
    for name, info in models.items():
        sql_path = next((MODELS / info["layer"]).glob(f"{name}.sql"))
        text = sql_path.read_text(encoding="utf-8")
        info["path"] = sql_path.relative_to(ROOT).as_posix()
        info["refs"] = sorted(set(re.findall(r"ref\(\s*'([^']+)'\s*\)", text)))
        info["sources"] = sorted(set(f"{a}.{b}" for a, b in re.findall(r"source\(\s*'([^']+)'\s*,\s*'([^']+)'\s*\)", text)))
    return models


def sql_files_without_yaml() -> set[str]:
    return {p.stem for layer in LAYERS for p in (MODELS / layer).glob("*.sql")}


def tableau_columns(name: str) -> tuple[list[str], list[str]]:
    """Output column names of a sql/tableau query, and the marts tables it reads."""
    sql = (TABLEAU_SQL / f"{name}.sql").read_text(encoding="utf-8")
    tree = sqlglot.parse_one(sql, read="bigquery")
    cols = [s.alias_or_name for s in tree.expressions]
    tables = sorted({t.name for t in tree.find_all(exp.Table) if t.name and t.db})
    cte_names = {c.alias for c in tree.find_all(exp.CTE)}
    tables = [t for t in tables if t not in cte_names]
    return cols, tables


GENERIC_HELP = {
    "--project": "Google Cloud project to read from and write to.",
    "--out-dir": "Folder the output files are written to.",
    "--out": "File the result is written to.",
    "--report": "Markdown report to write.",
    "--json": "JSON copy of the report's numbers to write.",
    "--max-gb": "Most data one query may bill, in GB.",
    "--dry-run": "Check and report what would happen; write nothing.",
    "--dataset": "BigQuery dataset to load into.",
    "--data-dir": "Folder holding the local source files.",
    "--only": "Limit the run to some tables or queries.",
    "--extract-dir": "Folder holding the GA4 summaries from `ga4_extract`.",
    "--seed": "Random seed; the same seed gives the same synthetic data.",
    "--target-dir": "dbt target folder holding run_results.json and manifest.json.",
    "--verify-only": "Run the load checks without loading.",
}


def _module_constants(tree: ast.AST) -> dict[str, str]:
    """Module-level NAME = ... assignments, with ROOT / "a" / "b" shown as a/b."""
    consts: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            value = node.value
            parts = []
            while isinstance(value, ast.BinOp) and isinstance(value.op, ast.Div):
                if isinstance(value.right, ast.Constant):
                    parts.append(str(value.right.value))
                value = value.left
            if parts and isinstance(value, ast.Name) and value.id == "ROOT":
                consts[node.targets[0].id] = "/".join(reversed(parts))
            elif isinstance(value, ast.Constant):
                consts[node.targets[0].id] = str(value.value)
    return consts


def _default_text(node: ast.AST, consts: dict[str, str]) -> str:
    text = ast.unparse(node)
    m = re.match(r"os\.environ\.get\('(\w+)', (\w+(?:\.\w+)*)\)", text)
    if m:
        return f"`${m.group(1)}`, else `{consts.get(m.group(2).split('.')[-1], 'da02-customer360')}`"
    m = re.match(r"(?:str\()?(\w+)\)?$", text)
    if m and m.group(1) in consts:
        return f"`{consts[m.group(1)]}`"
    if text == "Config().seed":
        return "`42`"
    return f"`{text.strip(chr(39))}`"


def command_flags(module: str) -> list[tuple[str, str, str]]:
    """(flag, default, help) for every add_argument call of a module."""
    path = ROOT / (module.replace(".", "/") + ".py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    consts = _module_constants(tree)
    flags = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "add_argument":
            names = [a.value for a in node.args if isinstance(a, ast.Constant) and isinstance(a.value, str)]
            if not names:
                continue
            kw = {k.arg: k.value for k in node.keywords}
            default = ""
            if "default" in kw and ast.unparse(kw["default"]) in ("None",):
                default = "none"
            elif "default" in kw:
                default = _default_text(kw["default"], consts)
            elif "action" in kw and ast.unparse(kw["action"]) in ("'store_true'", '"store_true"'):
                default = "off"
            help_text = kw["help"].value if "help" in kw and isinstance(kw["help"], ast.Constant) else ""
            if "choices" in kw:
                help_text = (help_text + " " if help_text else "") + "Choices: " + ", ".join(str(c) for c in ast.literal_eval(kw["choices"])) + "."
            help_text = help_text or GENERIC_HELP.get(names[0], "")
            flags.append((names[0], default, help_text))
    return flags


def first_sentence(text: str) -> str:
    text = " ".join(text.split())
    m = re.match(r"(.+?[.!?])(\s|$)", text)
    return m.group(1) if m else text


def test_summary(path: Path) -> str:
    """The leading `--` comment block of a singular test, cut at the first full sentence."""
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("--"):
            break
        lines.append(line.lstrip("-").strip())
    text = " ".join(lines)
    m = re.match(r"(.+?\.)(\s|$)", text)
    text = " ".join((m.group(1) if m else text).rstrip(":").split())
    if len(text) > 200:
        text = text[:200].rsplit(" ", 1)[0].rstrip(",;:") + " ..."
    return text


def esc(text: str) -> str:
    return text.replace("|", "\\|")


# ---------------------------------------------------------------------------------------------- the document
def build() -> str:
    models = load_models()
    used_by: dict[str, list[str]] = defaultdict(list)
    for name, m in models.items():
        for r in m["refs"]:
            used_by[r].append(name)
    by_layer = {layer: [n for n, m in models.items() if m["layer"] == layer] for layer in LAYERS}
    singular = sorted(p.stem for p in SINGULAR.glob("*.sql"))
    n_columns = sum(len(m["columns"]) for m in models.values())
    n_generic = sum(len(c[2]) for m in models.values() for c in m["columns"])

    L: list[str] = []
    a = L.append
    a("# Data and API documentation")
    a("")
    a("The reference for everything the project stores and every command that makes it: BigQuery datasets, dbt models, output files and the command line.")
    a("")
    a("This project has **no web API**. Its interfaces are the BigQuery tables (read by dbt, Tableau exports and reports), the CSV files Tableau reads, "
      "the reports, and the command line. This page is generated by `uv run python -m src.build_data_api_docs` from the dbt files, the SQL and the "
      "command definitions, and a test fails if it is out of date, so it matches the code.")
    a("")
    a("For the meaning of each measure see the [metric dictionary](metric_dictionary.md); for the raw tables in detail see the [data dictionary](data_dictionary.md); "
      "for which data is real and which is synthetic see [synthetic data](synthetic_data.md).")
    a("")
    a("**Contents:** [Conventions](#conventions) · [Datasets](#datasets) · [Run order](#run-order) · [dbt models](#dbt-models) · [Tests](#tests) · "
      "[Output files](#output-files) · [Command reference](#command-reference)")
    a("")
    a("## Conventions")
    a("")
    a("| Topic | Rule |")
    a("|---|---|")
    a("| Data | GA4 events are **real**; CRM customers and orders, ad spend, Segment events and the identity ground truth are **synthetic** (Faker, seed 42). |")
    a("| Money | US dollars. `net` revenue is after refunds. ROAS is revenue divided by spend, not profit. |")
    a("| Time | UTC. Dates are `DATE`, timestamps are `TIMESTAMP`. The GA4 window is 2020-11-01 to 2021-01-31; \"as of\" is 2021-02-01. |")
    a("| Keys | `customer_id` (CRM), `user_pseudo_id` (GA4 device), `session_key` (device + GA4 session id), `order_id`. |")
    a("| Models | The four attribution models are `first_touch`, `last_touch`, `linear`, `time_decay`. `ga4_session` is a fifth view used only as a benchmark in ROI and budget tables. |")
    a("| Names | `stg_` staging, `int_` intermediate, `fct_` fact (events or measures), `dim_` dimension (descriptions). Double underscore separates source from entity (`stg_crm__orders`). |")
    a("| Privacy | No output file contains a name or email. The ground-truth table is read only by the scoring step, never by a dbt model. |")
    a("")
    a("## Datasets")
    a("")
    a("| BigQuery dataset | Made by | Holds | Objects |")
    a("|---|---|---|---|")
    counts = {k: len(v) for k, v in by_layer.items()}
    for ds, by, what, n in DATASETS:
        a(f"| `{ds}` | `{by}` | {what} | {n.format(**counts)} |")
    a("")
    a(f"Project `da02-customer360` (set `GCP_PROJECT` to use another), location US. dbt writes staging and intermediate as views and marts as tables; "
      f"the schema names come from `dbt/macros/generate_schema_name.sql`.")
    a("")
    a("**Raw tables.** `raw.ga4_events` (real), `raw.crm_customers`, `raw.crm_orders`, `raw.ad_spend`, `raw.segment_identifies`, `raw.segment_tracks` "
      "(synthetic) and `raw.ground_truth_identity_links` (scoring only). **Identity tables.** `identity.identity_links` (one row per device linked to a customer) and "
      "`identity.identity_rejected` (evidence not used, with the reason). Columns are in the [data dictionary](data_dictionary.md).")
    a("")
    a("## Run order")
    a("")
    a("Run from the repository root with the virtual environment active and `gcloud auth application-default login` done.")
    a("")
    a("| Step | Command | Reads | Writes |")
    a("|---|---|---|---|")
    for s, c, r, w in PIPELINE:
        a(f"| {s} | {c} | {r} | {w} |")
    a("")
    a("## dbt models")
    a("")
    a(f"{len(models)} models ({counts['staging']} staging, {counts['intermediate']} intermediate, {counts['marts']} marts) with {n_columns} documented columns "
      f"and {n_generic} column tests. Each section lists what the model is built from and what uses it, then its columns and the tests on each.")
    a("")
    a("| Model | Layer | Built as | What it is |")
    a("|---|---|---|---|")
    for layer, (_, mat, _) in LAYERS.items():
        for n in by_layer[layer]:
            a(f"| [`{n}`](#{n}) | {layer} | {mat} | {esc(first_sentence(models[n]['description']))} |")
    a("")
    for layer, (ds, mat, blurb) in LAYERS.items():
        a(f"### {layer.capitalize()} models")
        a("")
        a(f"Dataset `{ds}`, built as a {mat}. {blurb}")
        a("")
        for n in by_layer[layer]:
            m = models[n]
            a(f"#### {n}")
            a("")
            a(m["description"])
            a("")
            built = [f"`{s}`" for s in m["sources"]] + [f"`{r}`" for r in m["refs"]]
            a(f"- **File:** `{m['path']}`")
            a(f"- **Built from:** {', '.join(built) if built else 'nothing (a literal rules table written in the model)'}")
            users = sorted(used_by.get(n, []))
            a(f"- **Used by:** {', '.join(f'`{u}`' for u in users) if users else 'dashboards, reports or the Tableau exports only'}")
            a("")
            a("| Column | Meaning | Tests |")
            a("|---|---|---|")
            for c, d, t in m["columns"]:
                a(f"| `{c}` | {esc(d)} | {', '.join(t)} |")
            a("")
    a("## Tests")
    a("")
    a(f"Two kinds of dbt test protect the models: the **column tests** above (`unique`, `not_null`, `relationships`, `accepted_values`) and **{len(singular)} singular tests** "
      f"in `dbt/tests/`, each a query that returns rows only when something is wrong. The recorded result of the last full run is in [dbt_test_results.md](dbt_test_results.md). "
      "Python tests in `tests/` (pytest) run the real model SQL on small hand-built tables.")
    a("")
    a("| Singular test | What it protects |")
    a("|---|---|")
    for t in singular:
        a(f"| `{t}` | {esc(test_summary(SINGULAR / f'{t}.sql'))} |")
    a("")
    a("## Output files")
    a("")
    a("### Tableau extracts (`tableau/data/`, git-ignored)")
    a("")
    a("Written by `src.export_for_tableau`. Each file is one query in `sql/tableau/`. Flags are written as 1/0, NULL as an empty cell, dates as ISO text.")
    a("")
    a("| File | One row is | Used by | Reads |")
    a("|---|---|---|---|")
    cols_by_file = {}
    for f, (grain, dash, _) in TABLEAU_FILES.items():
        cols, tables = tableau_columns(f)
        cols_by_file[f] = cols
        a(f"| `{f}.csv` | {grain} | {dash} | {', '.join(f'`{t}`' for t in tables)} |")
    a("")
    for f, (grain, dash, what) in TABLEAU_FILES.items():
        cols = cols_by_file[f]
        a(f"**`{f}.csv`** ({len(cols)} columns). {what}")
        a("")
        a(", ".join(f"`{c}`" for c in cols))
        a("")
    a("### Identity files (`data/identity/`)")
    a("")
    a("`identity_links.csv` and `identity_rejected.csv` are file copies of the two `identity` tables, written by `src.identity.run`.")
    a("")
    a("### Reports")
    a("")
    a("| File | Made by | Contents |")
    a("|---|---|---|")
    for p, by, what in REPORTS:
        a(f"| `{p}` | `{by}` | {what} |")
    a("")
    a("The JSON reports hold every number printed in their Markdown twin, so a number can be read by a program without parsing text.")
    a("")
    a("## Command reference")
    a("")
    a("Every command is run as `uv run python -m <module>` from the repository root. Commands marked **BigQuery** need `gcloud auth application-default login` and a project; "
      "the GA4 steps are capped by `--max-gb` (default 20) and run safely with `--dry-run` first where offered.")
    a("")
    for mod, what, reads, writes, bq in COMMANDS:
        a(f"### `{mod}`")
        a("")
        a(what)
        a("")
        a(f"- **Reads:** {reads}")
        a(f"- **Writes:** {writes}")
        a(f"- **Needs BigQuery:** {'yes' if bq else 'no'}")
        flags = command_flags(mod) if mod != "src.build_data_api_docs" else [("--check", "off", "Exit 1 if docs/data_api_docs.md is out of date.")]
        if flags:
            a("")
            a("| Flag | Default | Meaning |")
            a("|---|---|---|")
            for fl, d, h in flags:
                a(f"| `{fl}` | {esc(d) if d else ''} | {esc(h)} |")
        a("")
    a("### dbt")
    a("")
    a("```bash")
    a("uv run dbt run  --project-dir dbt --profiles-dir dbt                  # build everything")
    a("uv run dbt test --project-dir dbt --profiles-dir dbt                  # all column and singular tests")
    a("uv run dbt run  --project-dir dbt --profiles-dir dbt --select +fct_campaign_roi   # one model and everything it needs")
    a("```")
    a("")
    a("The profile is `customer_360` (oauth, location US, project from `GCP_PROJECT`).")
    a("")
    return "\n".join(L).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="exit 1 if docs/data_api_docs.md is out of date")
    args = ap.parse_args(argv)
    text = build()
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != text:
            print("docs/data_api_docs.md is out of date: run  uv run python -m src.build_data_api_docs")
            return 1
        print("docs/data_api_docs.md is up to date")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)} ({len(text.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

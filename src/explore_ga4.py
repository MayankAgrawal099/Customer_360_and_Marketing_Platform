"""Run the GA4 exploration queries and write the results to a Markdown file.

Each query lives in ``sql/ga4_exploration/*.sql``. The first lines of a file may hold
``-- title: ...`` and ``-- max_rows: N`` (how many result rows to keep in the report).

Usage (from the repository root, after ``gcloud auth application-default login``)::

    uv run python src/explore_ga4.py
    uv run python src/explore_ga4.py --only 01,08          # run just some queries
    uv run python src/explore_ga4.py --dry-run             # show data scanned, run nothing

The report goes to ``docs/ga4_exploration.md``. Every query has a cap on the data it may
bill (default 20 GB), so a mistake cannot use up the monthly free allowance.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql" / "ga4_exploration"
DEFAULT_OUT = ROOT / "docs" / "ga4_exploration.md"
DEFAULT_PROJECT = "da02-customer360"
DEFAULT_MAX_ROWS = 25


@dataclass
class Query:
    name: str          # file name without .sql, e.g. "01_overview"
    title: str
    max_rows: int
    sql: str


def parse_header(sql: str, default_title: str) -> tuple[str, int]:
    """Read ``-- title:`` and ``-- max_rows:`` from the comment lines at the top of a query."""
    title, max_rows = default_title, DEFAULT_MAX_ROWS
    for line in sql.splitlines():
        if not line.startswith("--"):
            break
        m = re.match(r"--\s*(title|max_rows)\s*:\s*(.+)$", line)
        if not m:
            continue
        if m.group(1) == "title":
            title = m.group(2).strip()
        elif m.group(2).strip().isdigit():
            max_rows = int(m.group(2).strip())
    return title, max_rows


def load_queries(sql_dir: Path = SQL_DIR, only: list[str] | None = None) -> list[Query]:
    """Load the ``.sql`` files in name order. ``only`` keeps files whose name starts with one of the prefixes."""
    queries = []
    for path in sorted(sql_dir.glob("*.sql")):
        if only and not any(path.stem.startswith(p) for p in only):
            continue
        sql = path.read_text(encoding="utf-8").strip()
        title, max_rows = parse_header(sql, path.stem)
        queries.append(Query(path.stem, title, max_rows, sql))
    return queries


def format_value(v) -> str:
    """Format one cell for a Markdown table."""
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, int):
        return f"{v:,}"
    if isinstance(v, float):
        return f"{v:,.2f}"
    if isinstance(v, (dt.date, dt.datetime)):
        return v.isoformat()
    return str(v).replace("|", "\\|").replace("\n", " ")


def md_table(columns: list[str], rows: list[list]) -> str:
    """Render a Markdown table. An empty result becomes a one-line note."""
    if not rows:
        return "_No rows returned._"
    head = "| " + " | ".join(columns) + " |"
    sep = "|" + "|".join("---" for _ in columns) + "|"
    body = ["| " + " | ".join(format_value(v) for v in r) + " |" for r in rows]
    return "\n".join([head, sep, *body])


def render_section(q: Query, columns: list[str], rows: list[list], total_rows: int, gb: float) -> str:
    shown = f"showing {len(rows)} of {total_rows} rows, " if total_rows > len(rows) else ""
    return "\n".join([
        f"## {q.name.split('_', 1)[0]}. {q.title}",
        "",
        md_table(columns, rows),
        "",
        f"_File: `sql/ga4_exploration/{q.name}.sql` ({shown}{gb:.2f} GB scanned)_",
        "",
    ])


def run(project: str, queries: list[Query], out: Path, max_gb: float, dry_run: bool) -> int:
    from google.cloud import bigquery  # imported here so the helpers above work without a login

    try:
        client = bigquery.Client(project=project)
    except Exception as exc:  # noqa: BLE001 - usually "not logged in"
        print(f"Could not connect to BigQuery: {exc}\nRun: gcloud auth application-default login")
        return 1
    limit_bytes = int(max_gb * 1024 ** 3)
    sections, failures, total_gb = [], 0, 0.0

    for q in queries:
        try:
            dry = client.query(q.sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            gb = dry.total_bytes_processed / 1024 ** 3
            if dry_run:
                print(f"{q.name:28s} would scan {gb:7.2f} GB")
                total_gb += gb
                continue
            cfg = bigquery.QueryJobConfig(maximum_bytes_billed=limit_bytes)
            result = client.query(q.sql, job_config=cfg).result()
            columns = [f.name for f in result.schema]
            all_rows = [list(r.values()) for r in result]
            sections.append(render_section(q, columns, all_rows[: q.max_rows], len(all_rows), gb))
            total_gb += gb
            print(f"OK    {q.name:28s} {len(all_rows):5d} rows  {gb:6.2f} GB")
        except Exception as exc:  # noqa: BLE001 - keep going so one bad query does not hide the rest
            failures += 1
            print(f"FAIL  {q.name}: {exc}")
            sections.append(f"## {q.name.split('_', 1)[0]}. {q.title}\n\n**Query failed:** `{str(exc)[:400]}`\n")

    if dry_run:
        print(f"Total: about {total_gb:.2f} GB")
        return 0

    header = [
        "# GA4 sample dataset: exploration results",
        "",
        "Dataset: `bigquery-public-data.ga4_obfuscated_sample_ecommerce` (real, obfuscated Google Merchandise Store data).",
        f"Generated by `src/explore_ga4.py` on {dt.date.today().isoformat()}. Total scanned: {total_gb:.2f} GB.",
        "",
    ]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(header + sections), encoding="utf-8")
    print(f"\nWrote {out}  ({len(queries) - failures} ok, {failures} failed)")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", DEFAULT_PROJECT))
    ap.add_argument("--only", help="comma-separated file-name prefixes, e.g. 01,08")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-gb", type=float, default=20.0, help="most data one query may bill (default 20)")
    ap.add_argument("--dry-run", action="store_true", help="only report how much data each query would scan")
    args = ap.parse_args(argv)

    only = [p.strip() for p in args.only.split(",")] if args.only else None
    queries = load_queries(only=only)
    if not queries:
        print("No queries found.")
        return 1
    return run(args.project, queries, args.out, args.max_gb, args.dry_run)


if __name__ == "__main__":
    sys.exit(main())

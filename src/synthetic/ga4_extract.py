"""Download the GA4 facts the synthetic data is built on, as local CSV files.

Runs the queries in ``sql/ga4_extract/`` and writes ``users.csv``, ``purchases.csv`` and
``daily_traffic.csv`` into ``data/raw/ga4_extract/`` (git-ignored). The GA4 sample is fixed
public data, so everyone who runs this gets the same files.

Usage (repository root, after ``gcloud auth application-default login``)::

    uv run python -m src.synthetic.ga4_extract
    uv run python -m src.synthetic.ga4_extract --dry-run
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SQL_DIR = ROOT / "sql" / "ga4_extract"
DEFAULT_OUT = ROOT / "data" / "raw" / "ga4_extract"
DEFAULT_PROJECT = "da02-customer360"


def output_name(sql: str, fallback: str) -> str:
    """File name given by the ``-- file: name.csv`` line at the top of a query."""
    m = re.search(r"^--\s*file\s*:\s*(\S+)", sql, re.M)
    return m.group(1) if m else fallback + ".csv"


def load_extract_queries(sql_dir: Path = SQL_DIR) -> list[tuple[str, str]]:
    return [(output_name(p.read_text(encoding="utf-8"), p.stem), p.read_text(encoding="utf-8").strip())
            for p in sorted(sql_dir.glob("*.sql"))]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", DEFAULT_PROJECT))
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--max-gb", type=float, default=20.0)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only", help="comma-separated names to run, e.g. daily_traffic")
    args = ap.parse_args(argv)
    only = [x.strip() for x in args.only.split(",")] if args.only else None

    from google.cloud import bigquery

    try:
        client = bigquery.Client(project=args.project)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not connect to BigQuery: {exc}\nRun: gcloud auth application-default login")
        return 1

    args.out_dir.mkdir(parents=True, exist_ok=True)
    failures = 0
    for name, sql in load_extract_queries():
        if only and name.removesuffix(".csv") not in only:
            continue
        try:
            dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
            gb = dry.total_bytes_processed / 1024 ** 3
            if args.dry_run:
                print(f"{name:22s} would scan {gb:6.2f} GB")
                continue
            cfg = bigquery.QueryJobConfig(maximum_bytes_billed=int(args.max_gb * 1024 ** 3))
            df = client.query(sql, job_config=cfg).result().to_dataframe()
            df.to_csv(args.out_dir / name, index=False)
            print(f"OK    {name:22s} {len(df):8,d} rows  {gb:5.2f} GB")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"FAIL  {name}: {exc}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())

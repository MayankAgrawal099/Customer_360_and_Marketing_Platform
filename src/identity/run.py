"""Run identity resolution on the BigQuery ``raw`` dataset, score it, and save the results.

Reads the small tables it needs from ``raw`` (Segment identifies, CRM customers and orders, the GA4
purchase events, and session counts per device), applies the rules in ``rules.py``, writes:

* ``identity.identity_links``     one row per device linked to a customer (BigQuery)
* ``identity.identity_rejected``  evidence that was not used, with the reason (BigQuery)
* ``data/identity/*.csv``         the same two tables as files
* ``reports/identity_resolution_report.md``   accuracy against the ground truth

Usage (repository root, after ``gcloud auth application-default login``)::

    uv run python -m src.identity.run --dry-run     # show how much data the queries scan; write nothing
    uv run python -m src.identity.run               # resolve, score, write tables and report

Safe to re-run: both tables are replaced.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
from pathlib import Path

import pandas as pd

from src.identity.rules import LINK_COLUMNS, REJECTED_COLUMNS, resolve
from src.identity.score import render_report, score

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT = "da02-customer360"
RAW, OUT_DATASET = "raw", "identity"
LOCATION = "US"
DEFAULT_OUT = ROOT / "data" / "identity"
DEFAULT_REPORT = ROOT / "reports" / "identity_resolution_report.md"

QUERIES = {
    "identifies": "SELECT anonymousId, userId, timestamp, traits.emailSha256 AS email_sha256 FROM `{ds}.segment_identifies`",
    "customers": "SELECT customer_id, email_sha256 FROM `{ds}.crm_customers`",
    "orders": "SELECT order_id, customer_id, ga_transaction_id FROM `{ds}.crm_orders`",
    "truth": "SELECT customer_id, user_pseudo_id, device_role, has_purchase, identify_emitted FROM `{ds}.ground_truth_identity_links`",
    # Valid purchases only: real transaction id, revenue above zero (same rule as the synthetic extract).
    "purchases": """
        SELECT ecommerce.transaction_id AS transaction_id, user_pseudo_id,
               MIN(TIMESTAMP_MICROS(event_timestamp)) AS event_ts,
               MAX(ecommerce.purchase_revenue_in_usd) AS revenue_usd
        FROM `{ds}.ga4_events`
        WHERE event_name = 'purchase' AND ecommerce.transaction_id IS NOT NULL
          AND ecommerce.transaction_id != '(not set)' AND ecommerce.purchase_revenue_in_usd > 0
        GROUP BY transaction_id, user_pseudo_id""",
    # A session is a device plus its ga_session_id. The id is read in a CTE, not inside COUNT(DISTINCT ...).
    "devices": """
        WITH ev AS (
          SELECT user_pseudo_id,
                 (SELECT value.int_value FROM UNNEST(event_params) WHERE key = 'ga_session_id') AS sid
          FROM `{ds}.ga4_events`)
        SELECT user_pseudo_id, COUNT(DISTINCT sid) AS sessions FROM ev GROUP BY user_pseudo_id""",
}

SCHEMAS = {
    "identity_links": [("user_pseudo_id", "STRING"), ("customer_id", "STRING"), ("link_rule", "STRING"),
                       ("evidence_rules", "STRING"), ("confidence", "STRING"), ("evidence_count", "INTEGER"),
                       ("first_evidence_ts", "TIMESTAMP"), ("had_conflict", "BOOLEAN")],
    "identity_rejected": [("source", "STRING"), ("user_pseudo_id", "STRING"), ("customer_id", "STRING"),
                          ("reason", "STRING"), ("detail", "STRING")],
}
DESCRIPTIONS = {
    "identity_links": "Device (user_pseudo_id) to customer links from deterministic identity-resolution rules. One row per linked device.",
    "identity_rejected": "Identity evidence that was not used (conflicts, unknown customers, duplicates) and why.",
}


def read_inputs(client, dataset_ref: str, max_gb: float, dry_run: bool) -> dict[str, pd.DataFrame] | None:
    from google.cloud import bigquery

    frames: dict[str, pd.DataFrame] = {}
    total = 0.0
    for name, sql in QUERIES.items():
        sql = sql.format(ds=dataset_ref)
        dry = client.query(sql, job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
        gb = dry.total_bytes_processed / 1024 ** 3
        total += gb
        if dry_run:
            print(f"DRY   {name:<11} would scan {gb:6.2f} GB")
            continue
        cfg = bigquery.QueryJobConfig(maximum_bytes_billed=int(max_gb * 1024 ** 3))
        frames[name] = client.query(sql, job_config=cfg).result().to_dataframe()
        print(f"OK    read {name:<11} {len(frames[name]):>9,} rows  {gb:5.2f} GB")
    if dry_run:
        print(f"Total: about {total:.2f} GB")
        return None
    return frames


def write_outputs(links: pd.DataFrame, rejected: pd.DataFrame, out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = {}
    for name, df, cols in (("identity_links", links, LINK_COLUMNS), ("identity_rejected", rejected, REJECTED_COLUMNS)):
        p = out_dir / f"{name}.csv"
        df[cols].to_csv(p, index=False, lineterminator="\n")
        paths[name] = p
    return paths


def load_to_bigquery(client, project: str, paths: dict[str, Path]) -> None:
    from google.cloud import bigquery

    ds = bigquery.Dataset(f"{project}.{OUT_DATASET}")
    ds.location = LOCATION
    client.create_dataset(ds, exists_ok=True)
    for name, path in paths.items():
        cfg = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV, skip_leading_rows=1, write_disposition="WRITE_TRUNCATE",
            schema=[bigquery.SchemaField(c, t) for c, t in SCHEMAS[name]])
        with path.open("rb") as fh:
            client.load_table_from_file(fh, f"{project}.{OUT_DATASET}.{name}", job_config=cfg, location=LOCATION).result()
        tbl = client.get_table(f"{project}.{OUT_DATASET}.{name}")
        tbl.description = DESCRIPTIONS[name]
        client.update_table(tbl, ["description"])
        print(f"OK    wrote {OUT_DATASET}.{name:<18} {tbl.num_rows:>7,} rows")


def run_pipeline(frames: dict[str, pd.DataFrame]):
    """Resolve and score. Only ``score`` is given the ground truth."""
    result = resolve(frames["identifies"], frames["orders"], frames["customers"], frames["purchases"])
    metrics = score(result.links, frames["truth"], frames["devices"], frames["purchases"],
                    frames["orders"], frames["customers"])
    return result, metrics


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", DEFAULT_PROJECT))
    ap.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--max-gb", type=float, default=20.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    from google.cloud import bigquery

    try:
        client = bigquery.Client(project=args.project)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not connect to BigQuery: {exc}\nRun: gcloud auth application-default login")
        return 1
    frames = read_inputs(client, f"{args.project}.{RAW}", args.max_gb, args.dry_run)
    if frames is None:
        return 0

    result, metrics = run_pipeline(frames)
    paths = write_outputs(result.links, result.rejected, args.out_dir)
    load_to_bigquery(client, args.project, paths)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(render_report(metrics, result.rejected, dt.date.today().isoformat()), encoding="utf-8")
    print(f"OK    wrote {args.report.relative_to(ROOT) if args.report.is_relative_to(ROOT) else args.report}")
    print(f"\nPrecision {metrics['precision']:.1%}   Recall {metrics['recall']:.1%}   "
          f"(best possible {metrics['recall_ceiling']:.1%})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

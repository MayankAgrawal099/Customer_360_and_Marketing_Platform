"""Load the raw layer into BigQuery: a copy of the GA4 sample plus the synthetic tables.

Creates the dataset ``raw`` (location US) in your project and fills it with:

* ``ga4_events``                    copy of the public GA4 sample events (about 4.3 million rows)
* ``crm_customers``, ``crm_orders``, ``ad_spend``            synthetic CRM and ad spend (CSV)
* ``segment_identifies``, ``segment_tracks``                 Segment-style events (JSON lines)
* ``ground_truth_identity_links``   the true device-to-customer links. For scoring identity
                                    resolution only: no model may read it.

Then it checks the load: row counts and totals against the local files, and that every key
shared between tables (device ids, transaction ids, customer ids) really exists on the other side.

Usage (repository root, after ``gcloud auth application-default login``)::

    uv run python -m src.load_to_bigquery --dry-run      # files, schemas and GA4 scan size; writes nothing
    uv run python -m src.load_to_bigquery                # load everything and verify
    uv run python -m src.load_to_bigquery --only crm_customers,crm_orders
    uv run python -m src.load_to_bigquery --verify-only  # re-run the checks without loading

Safe to re-run: every table is replaced. The GA4 copy is the only step that reads billed data
(about 3 GB of the 1 TB monthly free allowance) and is capped by ``--max-gb``.

BigQuery sandbox note: tables expire 60 days after creation. Re-running this script rebuilds the
whole raw layer in a few minutes. The GA4 copy is deliberately NOT partitioned by date: sandbox
partitions older than 60 days would be deleted straight away, and these dates are from 2020-21.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = ROOT / "data" / "synthetic"
DEFAULT_PROJECT = "da02-customer360"
DEFAULT_DATASET = "raw"
LOCATION = "US"
GA4_SOURCE = "bigquery-public-data.ga4_obfuscated_sample_ecommerce.events_*"
GA4_FIRST_DAY, GA4_LAST_DAY = "20201101", "20210131"
GA4_CLUSTER_BY = ["event_name", "user_pseudo_id"]


# ------------------------------------------------------------------ table definitions
@dataclass(frozen=True)
class Col:
    name: str
    type: str
    fields: tuple["Col", ...] = ()


@dataclass(frozen=True)
class Table:
    name: str
    kind: str                          # "csv", "jsonl" or "ga4"
    description: str
    path: str = ""                     # relative to the data directory
    schema: tuple[Col, ...] = ()
    totals: tuple[str, ...] = ()       # numeric columns whose sum is compared with the local file


S, I, F_, B, T, D = "STRING", "INTEGER", "FLOAT", "BOOLEAN", "TIMESTAMP", "DATE"

_CONTEXT = Col("context", "RECORD", (Col("library", "RECORD", (Col("name", S), Col("version", S))),))

TABLES: tuple[Table, ...] = (
    Table("ga4_events", "ga4", "Copy of the public GA4 obfuscated e-commerce sample, 2020-11-01 to 2021-01-31."),
    Table("crm_customers", "csv", "Synthetic CRM customers (one row per customer).", "crm_customers.csv", (
        Col("customer_id", S), Col("first_name", S), Col("last_name", S), Col("email", S),
        Col("email_sha256", S), Col("phone", S), Col("country", S), Col("created_at", T),
        Col("marketing_opt_in", B))),
    Table("crm_orders", "csv", "Synthetic CRM orders. Web orders match real GA4 purchases; app orders do not.",
          "crm_orders.csv", (
              Col("order_id", S), Col("customer_id", S), Col("order_ts", T), Col("order_channel", S),
              Col("ga_transaction_id", S), Col("order_value_usd", F_), Col("item_count", I),
              Col("status", S), Col("refund_usd", F_)),
          totals=("order_value_usd", "refund_usd")),
    Table("ad_spend", "csv", "Synthetic daily ad spend per paid campaign, sized from real GA4 sessions.",
          "ad_spend.csv", (
              Col("date", D), Col("channel", S), Col("source", S), Col("medium", S), Col("campaign", S),
              Col("impressions", I), Col("clicks", I), Col("spend_usd", F_)),
          totals=("spend_usd", "clicks")),
    Table("ground_truth_identity_links", "csv",
          "TRUE device-to-customer links. For scoring identity resolution only; never an input.",
          "ground_truth/ground_truth_identity_links.csv", (
              Col("customer_id", S), Col("user_pseudo_id", S), Col("device_role", S),
              Col("has_purchase", B), Col("identify_emitted", B))),
    Table("segment_identifies", "jsonl", "Segment-style identify events: link a device (anonymousId) to a customer.",
          "segment_identifies.jsonl", (
              Col("type", S), Col("messageId", S), Col("timestamp", T), Col("anonymousId", S), Col("userId", S),
              Col("traits", "RECORD", (Col("email", S), Col("emailSha256", S), Col("firstName", S),
                                       Col("lastName", S), Col("country", S), Col("createdAt", T))),
              _CONTEXT)),
    Table("segment_tracks", "jsonl", "Segment-style server-side track events (userId only, no device).",
          "segment_tracks.jsonl", (
              Col("type", S), Col("event", S), Col("messageId", S), Col("timestamp", T), Col("userId", S),
              Col("properties", "RECORD", (Col("email_opt_in", B), Col("order_id", S), Col("revenue", F_),
                                           Col("currency", S), Col("channel", S), Col("status", S))),
              _CONTEXT)),
)
TABLE_BY_NAME = {t.name: t for t in TABLES}


def to_bq_schema(cols: tuple[Col, ...]):
    from google.cloud import bigquery

    return [bigquery.SchemaField(c.name, c.type, mode="NULLABLE", fields=to_bq_schema(c.fields)) for c in cols]


# ------------------------------------------------------------------ local checks (no login needed)
def column_names(cols: tuple[Col, ...]) -> list[str]:
    return [c.name for c in cols]


def check_local_file(table: Table, data_dir: Path) -> list[str]:
    """Return problems found in the local file for ``table`` (empty list means it is ready to load)."""
    path = data_dir / table.path
    if not path.is_file():
        return [f"{table.name}: file not found: {path}  (run: uv run python -m src.synthetic.generate_crm)"]
    problems: list[str] = []
    if table.kind == "csv":
        header = path.read_text(encoding="utf-8").split("\n", 1)[0].strip().split(",")
        if header != column_names(table.schema):
            problems.append(f"{table.name}: header {header} does not match schema {column_names(table.schema)}")
    elif table.kind == "jsonl":
        problems += _check_jsonl_keys(table, path)
    return problems


def _check_jsonl_keys(table: Table, path: Path) -> list[str]:
    """Every key in every line must exist in the schema, or BigQuery would reject the load."""
    problems: list[str] = []

    def walk(value: dict, cols: tuple[Col, ...], where: str) -> None:
        known = {c.name: c for c in cols}
        for k, v in value.items():
            if k not in known:
                problems.append(f"{table.name}: unexpected field '{where}{k}'")
            elif known[k].type == "RECORD" and isinstance(v, dict):
                walk(v, known[k].fields, f"{where}{k}.")

    with path.open(encoding="utf-8") as fh:
        for n, line in enumerate(fh, 1):
            if not line.strip():
                continue
            obj = json.loads(line)
            walk(obj, table.schema, "")
            if len(problems) >= 5:
                break
    return problems


def local_summary(table: Table, data_dir: Path) -> dict:
    """Row count and control totals of a local file, to compare with what BigQuery holds."""
    path = data_dir / table.path
    if table.kind == "jsonl":
        with path.open(encoding="utf-8") as fh:
            return {"rows": sum(1 for line in fh if line.strip())}
    import pandas as pd

    df = pd.read_csv(path, dtype=str)
    out = {"rows": len(df)}
    for col in table.totals:
        out[col] = round(float(pd.to_numeric(df[col]).sum()), 2)
    if table.name == "crm_orders":
        out["web_orders_without_txn_id"] = int(((df["order_channel"] == "web") & df["ga_transaction_id"].isna()).sum())
    return out


# ------------------------------------------------------------------ checks that run in BigQuery
# Each query returns one number: how many records break the rule. The expected value is 0.
RELATION_CHECKS: tuple[tuple[str, str], ...] = (
    ("every ground-truth device exists in GA4",
     "SELECT COUNT(DISTINCT g.user_pseudo_id) FROM `{ds}.ground_truth_identity_links` g "
     "LEFT JOIN (SELECT DISTINCT user_pseudo_id FROM `{ds}.ga4_events`) e USING (user_pseudo_id) "
     "WHERE e.user_pseudo_id IS NULL"),
    ("every Segment identify device exists in GA4",
     "SELECT COUNT(DISTINCT i.anonymousId) FROM `{ds}.segment_identifies` i "
     "LEFT JOIN (SELECT DISTINCT user_pseudo_id FROM `{ds}.ga4_events`) e ON e.user_pseudo_id = i.anonymousId "
     "WHERE e.user_pseudo_id IS NULL"),
    ("every web order's transaction id is a GA4 purchase",
     "SELECT COUNT(*) FROM `{ds}.crm_orders` o "
     "LEFT JOIN (SELECT DISTINCT ecommerce.transaction_id AS tid FROM `{ds}.ga4_events` WHERE event_name = 'purchase') p "
     "ON p.tid = o.ga_transaction_id WHERE o.ga_transaction_id IS NOT NULL AND p.tid IS NULL"),
    ("every order belongs to a customer",
     "SELECT COUNT(*) FROM `{ds}.crm_orders` o LEFT JOIN `{ds}.crm_customers` c USING (customer_id) "
     "WHERE c.customer_id IS NULL"),
    ("every identify and track user is a customer",
     "SELECT COUNT(*) FROM (SELECT userId FROM `{ds}.segment_identifies` UNION ALL SELECT userId FROM `{ds}.segment_tracks`) s "
     "LEFT JOIN `{ds}.crm_customers` c ON c.customer_id = s.userId WHERE c.customer_id IS NULL"),
    ("every ground-truth customer exists in the CRM",
     "SELECT COUNT(*) FROM `{ds}.ground_truth_identity_links` g LEFT JOIN `{ds}.crm_customers` c USING (customer_id) "
     "WHERE c.customer_id IS NULL"),
    ("ad spend dates fall inside the GA4 window",
     "SELECT COUNT(*) FROM `{ds}.ad_spend` WHERE date NOT BETWEEN DATE '2020-11-01' AND DATE '2021-01-31'"),
)


def format_checks(dataset_ref: str) -> list[tuple[str, str]]:
    return [(name, sql.format(ds=dataset_ref)) for name, sql in RELATION_CHECKS]


# ------------------------------------------------------------------ BigQuery work
@dataclass
class Report:
    lines: list[str] = field(default_factory=list)
    failures: int = 0

    def ok(self, msg: str) -> None:
        self.lines.append(f"OK    {msg}")
        print(self.lines[-1])

    def fail(self, msg: str) -> None:
        self.failures += 1
        self.lines.append(f"FAIL  {msg}")
        print(self.lines[-1])


def ga4_copy_sql() -> str:
    return (f"SELECT * FROM `{GA4_SOURCE}` "
            f"WHERE _TABLE_SUFFIX BETWEEN '{GA4_FIRST_DAY}' AND '{GA4_LAST_DAY}'")


def load_ga4(client, dataset: str, project: str, max_gb: float, rep: Report) -> None:
    from google.cloud import bigquery

    dest = bigquery.TableReference.from_string(f"{project}.{dataset}.ga4_events")
    cfg = bigquery.QueryJobConfig(
        destination=dest, write_disposition="WRITE_TRUNCATE", clustering_fields=GA4_CLUSTER_BY,
        maximum_bytes_billed=int(max_gb * 1024 ** 3), use_query_cache=False)
    client.query(ga4_copy_sql(), job_config=cfg, location=LOCATION).result()
    tbl = client.get_table(dest)
    tbl.description = TABLE_BY_NAME["ga4_events"].description
    client.update_table(tbl, ["description"])
    rep.ok(f"ga4_events          {tbl.num_rows:>10,} rows loaded")


def load_file(client, dataset: str, project: str, table: Table, data_dir: Path, rep: Report) -> None:
    from google.cloud import bigquery

    fmt = bigquery.SourceFormat.CSV if table.kind == "csv" else bigquery.SourceFormat.NEWLINE_DELIMITED_JSON
    cfg = bigquery.LoadJobConfig(
        source_format=fmt, schema=to_bq_schema(table.schema), write_disposition="WRITE_TRUNCATE",
        ignore_unknown_values=False, max_bad_records=0)
    if table.kind == "csv":
        cfg.skip_leading_rows = 1
    dest = f"{project}.{dataset}.{table.name}"
    with (data_dir / table.path).open("rb") as fh:
        client.load_table_from_file(fh, dest, job_config=cfg, location=LOCATION).result()
    tbl = client.get_table(dest)
    tbl.description = table.description
    client.update_table(tbl, ["description"])
    rep.ok(f"{table.name:<19} {tbl.num_rows:>10,} rows loaded")


def verify(client, dataset: str, project: str, tables: list[Table], data_dir: Path, rep: Report) -> None:
    ds = f"{project}.{dataset}"
    # 1. row counts and control totals against the local files
    for t in tables:
        if t.kind == "ga4":
            rows = list(client.query(f"SELECT COUNT(*) FROM `{ds}.ga4_events`").result())[0][0]
            src = list(client.query(
                f"SELECT COUNT(*) FROM `{GA4_SOURCE}` WHERE _TABLE_SUFFIX BETWEEN '{GA4_FIRST_DAY}' AND '{GA4_LAST_DAY}'"
            ).result())[0][0]
            (rep.ok if rows == src else rep.fail)(f"ga4_events rows {rows:,} vs public source {src:,}")
            continue
        local = local_summary(t, data_dir)
        got = {"rows": list(client.query(f"SELECT COUNT(*) FROM `{ds}.{t.name}`").result())[0][0]}
        for col in t.totals:
            got[col] = round(float(list(client.query(f"SELECT SUM({col}) FROM `{ds}.{t.name}`").result())[0][0] or 0), 2)
        if t.name == "crm_orders":
            got["web_orders_without_txn_id"] = list(client.query(
                f"SELECT COUNTIF(order_channel = 'web' AND ga_transaction_id IS NULL) FROM `{ds}.crm_orders`"
            ).result())[0][0]
        for key, want in local.items():
            if abs(float(got[key]) - float(want)) < 0.01:
                rep.ok(f"{t.name}.{key} = {want:,}")
            else:
                rep.fail(f"{t.name}.{key}: BigQuery {got[key]:,} vs file {want:,}")
    # 2. keys shared between tables
    have = {t.name for t in tables}
    needed = {"ga4_events", "crm_customers", "crm_orders", "ad_spend", "ground_truth_identity_links",
              "segment_identifies", "segment_tracks"}
    if not needed <= have:
        rep.ok("relationship checks skipped (not all tables selected)")
        return
    for name, sql in format_checks(ds):
        bad = list(client.query(sql).result())[0][0]
        (rep.ok if bad == 0 else rep.fail)(f"{name}: {bad:,} broken")


def run(args) -> int:
    from google.cloud import bigquery

    tables = [t for t in TABLES if not args.only or t.name in args.only]
    data_dir = Path(args.data_dir)
    problems = [p for t in tables if t.kind != "ga4" for p in check_local_file(t, data_dir)]
    if problems:
        print("\n".join(f"FIX   {p}" for p in problems))
        return 1
    try:
        client = bigquery.Client(project=args.project)
    except Exception as exc:  # noqa: BLE001 - usually "not logged in"
        print(f"Could not connect to BigQuery: {exc}\nRun: gcloud auth application-default login")
        return 1

    if args.dry_run:
        for t in tables:
            if t.kind == "ga4":
                job = client.query(ga4_copy_sql(), job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False))
                print(f"DRY   ga4_events          would scan {job.total_bytes_processed / 1024 ** 3:6.2f} GB (limit {args.max_gb} GB)")
            else:
                print(f"DRY   {t.name:<19} {local_summary(t, data_dir)['rows']:>10,} rows ready from {t.path}")
        return 0

    rep = Report()
    if not args.verify_only:
        ds = bigquery.Dataset(f"{args.project}.{args.dataset}")
        ds.location = LOCATION
        client.create_dataset(ds, exists_ok=True)
        for t in tables:
            try:
                if t.kind == "ga4":
                    load_ga4(client, args.dataset, args.project, args.max_gb, rep)
                else:
                    load_file(client, args.dataset, args.project, t, data_dir, rep)
            except Exception as exc:  # noqa: BLE001 - keep going so one failure does not hide the rest
                rep.fail(f"{t.name}: {str(exc)[:300]}")
    print("\nVerifying the load")
    verify(client, args.dataset, args.project, tables, data_dir, rep)
    for t in tables:
        try:
            tbl = client.get_table(f"{args.project}.{args.dataset}.{t.name}")
            if tbl.expires:
                print(f"NOTE  {t.name} expires {tbl.expires:%Y-%m-%d} (sandbox). Re-run this script to rebuild.")
                break
        except Exception:  # noqa: BLE001
            pass
    print(f"\n{'Load verified: no problems.' if not rep.failures else f'{rep.failures} problem(s) found.'}")
    return 1 if rep.failures else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", DEFAULT_PROJECT))
    ap.add_argument("--dataset", default=DEFAULT_DATASET)
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--only", type=lambda s: [x.strip() for x in s.split(",")],
                    help="comma-separated table names, e.g. crm_customers,crm_orders")
    ap.add_argument("--max-gb", type=float, default=20.0, help="most data the GA4 copy may bill (default 20)")
    ap.add_argument("--dry-run", action="store_true", help="check files and GA4 scan size; write nothing")
    ap.add_argument("--verify-only", action="store_true", help="run the checks without loading")
    args = ap.parse_args(argv)
    unknown = [n for n in (args.only or []) if n not in TABLE_BY_NAME]
    if unknown:
        print(f"Unknown table(s): {', '.join(unknown)}. Choose from: {', '.join(TABLE_BY_NAME)}")
        return 1
    return run(args)


if __name__ == "__main__":
    sys.exit(main())

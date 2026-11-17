"""Export the flat tables the Tableau dashboards read, from the BigQuery marts to CSV.

    uv run python -m src.export_for_tableau                 # all seven files into tableau/data/
    uv run python -m src.export_for_tableau --only roi      # just the marketing files (attribution_by_channel, channel_performance,
                                                            #   campaign_performance, budget_recommendations)
    uv run python -m src.export_for_tableau --only customers  # just customers, segments, orders
    uv run python -m src.export_for_tableau --project my-project --out-dir somewhere

Each file comes from one query in sql/tableau/. True/False flags are written as 1/0 so Tableau reads them as numbers.
Needs `gcloud auth application-default login` and the google-cloud-bigquery package (already used by load_to_bigquery).
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "sql" / "tableau"
DEFAULT_OUT = ROOT / "tableau" / "data"
DEFAULT_PROJECT = "da02-customer360"
EXPORTS = ["customers", "segments", "orders"]                       # the Customer 360 dashboard
ROI_EXPORTS = ["attribution_by_channel", "channel_performance", "campaign_performance", "budget_recommendations"]
ALL_EXPORTS = EXPORTS + ROI_EXPORTS                                 # the attribution, ROI, CPA and budget dashboard


def cell(value):
    """One value as CSV text: flags as 1/0, empty for NULL, dates as ISO, numbers unrounded."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    return value


def write_csv(path: Path, columns: list[str], rows) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(columns)
        for row in rows:
            writer.writerow([cell(v) for v in row])
            count += 1
    return count


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--project", default=DEFAULT_PROJECT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--only", choices=["customers", "roi", "all"], default="all", help="which dashboard's files to write")
    args = parser.parse_args()

    from google.cloud import bigquery  # imported here so the module can be imported (and tested) without credentials

    client = bigquery.Client(project=args.project)
    names = {"customers": EXPORTS, "roi": ROI_EXPORTS, "all": ALL_EXPORTS}[args.only]
    for name in names:
        sql = (SQL_DIR / f"{name}.sql").read_text(encoding="utf-8")
        result = client.query(sql).result()
        columns = [field.name for field in result.schema]
        path = args.out_dir / f"{name}.csv"
        rows = write_csv(path, columns, (tuple(r.values()) for r in result))
        print(f"{name:24s} {rows:>8,d} rows  {len(columns):>2d} columns  -> {path}")


if __name__ == "__main__":
    main()

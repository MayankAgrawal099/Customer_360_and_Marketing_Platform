"""Measure identity-resolution accuracy against the known ground truth.

Writes ``reports/identity_accuracy_report.md`` (and ``reports/identity_accuracy.json`` with the numbers)
containing:

1. Precision, recall and the best possible recall for the rules.
2. The unmatched share of devices, sessions, customers, purchases and revenue, with the reason.
3. A stress test: the same rules on deliberately damaged inputs.

It reads the same small ``raw`` tables as ``src/identity/run.py`` and does not change any table.

Usage (repository root, after ``gcloud auth application-default login``)::

    uv run python -m src.identity.accuracy --dry-run
    uv run python -m src.identity.accuracy
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import pandas as pd

from src.identity import run as identity_run
from src.identity.score import render_report
from src.identity.stress import render_stress, run_scenarios

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT = ROOT / "reports" / "identity_accuracy_report.md"
DEFAULT_JSON = ROOT / "reports" / "identity_accuracy.json"


def build_report(frames: dict[str, pd.DataFrame], generated: str) -> tuple[str, dict]:
    result, metrics = identity_run.run_pipeline(frames)
    stress = run_scenarios(frames)
    text = render_report(metrics, result.rejected, generated, "src/identity/accuracy.py").replace(
        "# Identity resolution: accuracy report", "# Identity resolution: accuracy against the ground truth", 1)
    text += "\n".join([
        "", "## Stress test: the same rules on damaged inputs", "",
        "Clean synthetic signals never contradict each other, so the baseline precision is close to 100% by "
        "construction. These scenarios damage the inputs in known ways (fixed seed) and score the result against "
        "the same ground truth.", "",
        render_stress(stress), "",
        "How to read it: *hash conflicts caught* are identify events rejected because the `userId` and the email "
        "hash named different customers. *Device conflicts resolved* are devices claimed by two customers where the "
        "one with more evidence was kept. Wrong links that remain are cases where the only evidence was wrong.", "",
    ])
    numbers = {k: (v if not isinstance(v, pd.DataFrame) else v.to_dict("records")) for k, v in metrics.items()}
    numbers["stress"] = stress.to_dict("records")
    return text, numbers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", identity_run.DEFAULT_PROJECT))
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    ap.add_argument("--max-gb", type=float, default=20.0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    from google.cloud import bigquery

    try:
        client = bigquery.Client(project=args.project)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not connect to BigQuery: {exc}\nRun: gcloud auth application-default login")
        return 1
    frames = identity_run.read_inputs(client, f"{args.project}.{identity_run.RAW}", args.max_gb, args.dry_run)
    if frames is None:
        return 0
    text, numbers = build_report(frames, dt.date.today().isoformat())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(text, encoding="utf-8")
    args.json.write_text(json.dumps(numbers, indent=2, default=str), encoding="utf-8")
    print(f"OK    wrote {args.report}\nOK    wrote {args.json}")
    print("\nscenario                              precision   recall   wrong links")
    for r in numbers["stress"]:
        print(f"{r['scenario']:<36} {r['precision']:>9.1%} {r['recall']:>8.1%} {r['wrong_links']:>11,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

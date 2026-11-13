"""Record the results of ``dbt test`` in docs/dbt_test_results.md.

dbt writes dbt/target/run_results.json (what happened) and manifest.json (what each test is). This script
joins them into a readable report: totals, results by test type (unique, not_null, relationships,
accepted_values, singular), results by model, every singular test, and any warning or failure.

Run from the repository root. run_results.json is overwritten by every dbt command, so record the results
of a FULL ``dbt test`` (no --select):

    uv run dbt test --project-dir dbt --profiles-dir dbt
    uv run python -m src.dbt_results
or in one step (runs the tests, then records them; the exit code is 0 only if every test passed):
    uv run python -m src.dbt_results --run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "dbt" / "target"
OUT = ROOT / "docs" / "dbt_test_results.md"
GENERIC = ["unique", "not_null", "relationships", "accepted_values"]
TYPE_ORDER = GENERIC + ["singular"]
STATUSES = ["pass", "warn", "fail", "error"]


def short(unique_id: str) -> str:
    """model.proj.fct_orders -> fct_orders"""
    return unique_id.split(".")[2]


def classify(results: list[dict], manifest: dict) -> list[dict]:
    rows = []
    for r in results:
        node = manifest["nodes"].get(r["unique_id"])
        if not node or node.get("resource_type") != "test":
            continue
        meta = node.get("test_metadata") or {}
        kind = meta.get("name", "singular")
        if kind not in GENERIC:
            kind = "generic_other" if meta else "singular"
        attached = node.get("attached_node")
        models = [short(attached)] if attached else sorted(short(d) for d in node["depends_on"]["nodes"]
                                                            if d.startswith(("model.", "source.")))
        rows.append(dict(name=node["name"], kind=kind, models=models or ["-"], column=node.get("column_name") or "",
                         status=r["status"], failures=r.get("failures"), seconds=r.get("execution_time") or 0.0))
    return rows


def table(header: list[str], body: list[list]) -> str:
    lines = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in body]
    return "\n".join(lines)


def counts(rows: list[dict]) -> list:
    c = Counter(r["status"] for r in rows)
    return [len(rows)] + [c.get(s, 0) for s in STATUSES]


def build_report(run_results: dict, manifest: dict) -> str:
    rows = classify(run_results["results"], manifest)
    meta = run_results.get("metadata", {})
    args = run_results.get("args", {})
    total = counts(rows)
    ok = total[2] == total[3] == total[4] == 0  # no warn, fail or error
    selected = args.get("select") or []
    out = [
        "# dbt test results",
        "",
        f"Recorded from `dbt/target/run_results.json` (generated {meta.get('generated_at', 'unknown')}, "
        f"dbt {meta.get('dbt_version', 'unknown')}). Regenerate with `uv run python -m src.dbt_results --run`.",
        "",
        f"**Result: {'ALL TESTS PASSED' if ok else 'ATTENTION NEEDED'}** - {total[1]} of {total[0]} passed, "
        f"{total[2]} warnings, {total[3]} failures, {total[4]} errors.",
    ]
    if selected:
        out += ["", f"Note: this run used `--select {' '.join(selected)}`, so it covers only part of the project."]
    out += ["", "## By test type", "",
            table(["Test type", "Tests", *STATUSES], [[k, *counts([r for r in rows if r["kind"] == k])]
                                                        for k in TYPE_ORDER if any(r["kind"] == k for r in rows)]
                  + [["**Total**", *total]]),
            "", "What each type protects:", "",
            "- `unique` and `not_null`: keys identify exactly one row and required fields are filled, so joins cannot double or drop rows.",
            "- `relationships`: every customer, order and transaction id points to a row that exists in the table it refers to.",
            "- `accepted_values`: categories (channel group, order status, match status, link rule) stay inside the documented list.",
            "- `singular`: business rules written as SQL that must return no rows, such as order totals tying out between layers.",
            "", "## By model", ""]
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        for m in r["models"]:
            by_model[m].append(r)
    body = []
    for m in sorted(by_model):
        rs = by_model[m]
        per_type = " / ".join(str(sum(1 for r in rs if r["kind"] == k)) for k in TYPE_ORDER)
        c = counts(rs)
        body.append([f"`{m}`", per_type, c[0], c[1], c[2] + c[3] + c[4]])
    out += [table(["Model or source", "unique / not_null / relationships / accepted_values / singular", "Tests", "Passed",
                   "Not passed"], body),
            "", "A singular test that reads several models is counted under each of them.", "",
            "## Singular tests (business rules)", ""]
    sing = sorted((r for r in rows if r["kind"] == "singular"), key=lambda r: r["name"])
    out += [table(["Test", "Models read", "Rows returned", "Status"],
                  [[f"`{r['name']}`", ", ".join(r["models"]), r["failures"] if r["failures"] is not None else "-",
                    r["status"]] for r in sing]), ""]
    bad = [r for r in rows if r["status"] != "pass"]
    out += ["## Warnings and failures", ""]
    if bad:
        out += [table(["Test", "Type", "Model", "Column", "Status", "Rows failing"],
                      [[f"`{r['name']}`", r["kind"], ", ".join(r["models"]), r["column"], r["status"],
                        r["failures"] if r["failures"] is not None else "-"] for r in bad])]
    else:
        out += ["None."]
    out += ["", "A `warn` is a test configured with `severity: warn` (for example the device category list): the build "
                "continues, but the rows should be looked at.", ""]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true", help="run the full dbt test first")
    ap.add_argument("--target-dir", type=Path, default=TARGET)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args(argv)
    if a.run:
        subprocess.run(["dbt", "test", "--project-dir", str(ROOT / "dbt"), "--profiles-dir", str(ROOT / "dbt")], check=False)
    try:
        run_results = json.loads((a.target_dir / "run_results.json").read_text(encoding="utf-8"))
        manifest = json.loads((a.target_dir / "manifest.json").read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        print(f"Cannot find {e.filename}. Run `uv run dbt test --project-dir dbt --profiles-dir dbt` first.", file=sys.stderr)
        return 2
    if run_results.get("args", {}).get("which") not in (None, "test", "build"):
        print("The last dbt command was not a test run; run dbt test first.", file=sys.stderr)
        return 2
    report = build_report(run_results, manifest)
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(report, encoding="utf-8")
    bad = [r for r in classify(run_results["results"], manifest) if r["status"] != "pass"]
    print(f"Wrote {a.out.relative_to(ROOT) if a.out.is_relative_to(ROOT) else a.out}: "
          f"{len(classify(run_results['results'], manifest))} tests, {len(bad)} not passed")
    return 1 if any(r["status"] in ("fail", "error") for r in bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())

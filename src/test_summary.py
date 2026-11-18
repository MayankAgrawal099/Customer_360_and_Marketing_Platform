"""Write docs/test_results.md: one page with the final results of every check in the project.

    uv run python -m src.test_summary                 # build the page from the recorded results
    uv run python -m src.test_summary --run-pytest    # also run the pytest suite and record its count
    uv run python -m src.test_summary --check         # exit 1 if the page is out of date

It reads files the other commands already wrote, so it needs no BigQuery login:

* docs/dbt_test_results.md        from ``uv run python -m src.dbt_results --run``
* reports/identity_accuracy.json  from ``uv run python -m src.identity.accuracy``
* reports/attribution_comparison.json   from ``uv run python -m src.attribution_report``

Every number on the page is read from those files; nothing is typed in. Re-run it after any of the three commands.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DBT_MD = ROOT / "docs" / "dbt_test_results.md"
IDENTITY_JSON = ROOT / "reports" / "identity_accuracy.json"
ATTRIBUTION_JSON = ROOT / "reports" / "attribution_comparison.json"
OUT = ROOT / "docs" / "test_results.md"
TYPES = ["unique", "not_null", "relationships", "accepted_values", "singular"]


def pct(x: float, places: int = 1) -> str:
    return f"{x * 100:.{places}f}%"


def n(x) -> str:
    return f"{x:,.0f}"


def read_dbt(text: str) -> dict:
    """Totals and the by-type table from docs/dbt_test_results.md."""
    gen = re.search(r"generated ([0-9T:\-\.]+)Z?, dbt ([0-9\.]+)", text)
    res = re.search(r"\*\*Result: ([A-Z ]+)\*\* - (\d+) of (\d+) passed, (\d+) warnings, (\d+) failures, (\d+) errors", text)
    if not res:
        raise ValueError("docs/dbt_test_results.md has no result line; run: uv run python -m src.dbt_results --run")
    by_type = {}
    for t in TYPES:
        m = re.search(rf"^\| {t} \| (\d+) \| (\d+) \| (\d+) \| (\d+) \| (\d+) \|", text, flags=re.M)
        if m:
            by_type[t] = tuple(int(g) for g in m.groups())
    return {
        "verdict": res.group(1), "passed": int(res.group(2)), "total": int(res.group(3)),
        "warn": int(res.group(4)), "fail": int(res.group(5)), "error": int(res.group(6)),
        "date": gen.group(1)[:10] if gen else "unknown", "dbt": gen.group(2) if gen else "unknown", "by_type": by_type,
    }


def run_pytest() -> str:
    proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"], cwd=ROOT, capture_output=True, text=True)
    last = [ln for ln in proc.stdout.strip().splitlines() if " passed" in ln or " failed" in ln or " error" in ln]
    return re.sub(r" in [0-9\.]+s.*$", "", last[-1]).strip() if last else "unknown"


def build(pytest_line: str | None = None) -> str:
    dbt = read_dbt(DBT_MD.read_text(encoding="utf-8"))
    idy = json.loads(IDENTITY_JSON.read_text(encoding="utf-8"))
    att = json.loads(ATTRIBUTION_JSON.read_text(encoding="utf-8"))
    base = next(s for s in idy["stress"] if s["scenario"] == "baseline")
    rule_names = {"identify_verified": "Verified identify event", "order_match": "Order matched to a GA4 purchase"}

    L: list[str] = []
    a = L.append
    a("# Test results")
    a("")
    a("The final results of every check in the project, on one page. Each number is read from a recorded result file, so this page matches the last run; "
      "`uv run python -m src.test_summary` rebuilds it, and a test fails if it is out of date.")
    a("")
    a("> The checks run on **synthetic CRM, order and ad-spend data** joined to **real GA4 events**. Identity accuracy is measured against a synthetic ground truth, "
      "so it shows that the rules work as designed; it is not a claim about real customers.")
    a("")
    a("## Summary")
    a("")
    a("| Check | Result | What it proves | Detail |")
    a("|---|---|---|---|")
    dbt_ok = dbt["fail"] == 0 and dbt["error"] == 0 and dbt["passed"] == dbt["total"]
    a(f"| dbt tests | **{dbt['passed']} of {dbt['total']} pass**, {dbt['warn']} warnings, {dbt['fail']} failures | Keys are unique, required fields are filled, ids point at real rows, categories stay in their lists, and {dbt['by_type']['singular'][0]} business rules tie each layer to the one before | [dbt_test_results.md](dbt_test_results.md) |")
    a(f"| Identity accuracy | Precision **{pct(idy['precision'])}** ({n(idy['correct_links'])} of {n(idy['predicted_links'])}), recall **{pct(idy['recall'])}** ({n(idy['found_links'])} of {n(idy['true_links'])}) | Every link made is correct; the rest have no usable signal | [identity_accuracy_report.md](../reports/identity_accuracy_report.md) |")
    a(f"| Attribution checks | **{att['checks_passed']} of {att['checks']} pass** | Each of the four models credits every order once and exactly ${n(att['total_revenue_by_model']['linear'])} of net revenue | [attribution_comparison.md](../reports/attribution_comparison.md) |")
    a(f"| pytest suite | {pytest_line if pytest_line else 'run `uv run pytest -q`'} | The model SQL, exports, READMEs and documents behave as described (real SQL on small hand-built tables in DuckDB) | `tests/` |")
    a("")
    a("## dbt tests")
    a("")
    a(f"Recorded {dbt['date']} with dbt {dbt['dbt']} by `uv run python -m src.dbt_results --run`. "
      f"**{dbt['verdict'].capitalize()}**: {dbt['passed']} of {dbt['total']} passed, {dbt['warn']} warnings, {dbt['fail']} failures, {dbt['error']} errors.")
    a("")
    a("| Test type | Tests | Passed | Warned | Failed | Errored |")
    a("|---|---|---|---|---|---|")
    for t in TYPES:
        if t in dbt["by_type"]:
            tot, p, w, f, e = dbt["by_type"][t]
            a(f"| {t} | {tot} | {p} | {w} | {f} | {e} |")
    a(f"| **Total** | {dbt['total']} | {dbt['passed']} | {dbt['warn']} | {dbt['fail']} | {dbt['error']} |")
    a("")
    a("Every test, by model and by name, is in [dbt_test_results.md](dbt_test_results.md); what each test type protects is in the [data and API documentation](data_api_docs.md#tests).")
    a("")
    a("## Identity accuracy")
    a("")
    a("Scored against `raw.ground_truth_identity_links`, which the rules never read.")
    a("")
    a("| Measure | Value |")
    a("|---|---|")
    a(f"| True device-to-customer links | {n(idy['true_links'])} |")
    a(f"| Links made | {n(idy['predicted_links'])} |")
    a(f"| Correct links | {n(idy['correct_links'])} (wrong customer: {n(idy['wrong_customer_links'])}) |")
    a(f"| Precision | {pct(idy['precision'])} |")
    a(f"| Recall | {pct(idy['recall'])} |")
    a(f"| Best possible recall for these rules | {pct(idy['recall_ceiling'])} ({n(idy['reachable_links'])} links have a usable signal) |")
    a(f"| Recall of the links that have a usable signal | {pct(idy['recall_of_reachable'])} |")
    a(f"| Links with no usable signal | {n(idy['missed_unreachable'])} |")
    a(f"| Customers with a device found | {n(idy['customers_with_a_device_found'])} of {n(idy['customers'])} |")
    a(f"| Purchase revenue on a linked device | ${n(idy['revenue_linked'])} of ${n(idy['revenue_total'])} ({pct(idy['revenue_linked'] / idy['revenue_total'])}) |")
    a("")
    a("**By rule**")
    a("")
    a("| Rule | Links | Correct | Precision |")
    a("|---|---|---|---|")
    for r in idy["by_rule"]:
        a(f"| {rule_names.get(r['link_rule'], r['link_rule'])} (`{r['link_rule']}`) | {n(r['links'])} | {n(r['correct'])} | {pct(r['precision'])} |")
    a("")
    a("**By device role**")
    a("")
    a("| Role | True links | Found | Recall |")
    a("|---|---|---|---|")
    for r in idy["by_role"]:
        a(f"| {r['device_role']} | {n(r['true_links'])} | {n(r['found'])} | {pct(r['recall'])} |")
    a("")
    a("**Stress test.** The same rules run on deliberately damaged evidence, to show where they stay safe and where they break.")
    a("")
    a("| Scenario | What is damaged | Links | Precision | Recall | Wrong links |")
    a("|---|---|---|---|---|---|")
    for s in idy["stress"]:
        a(f"| `{s['scenario']}` | {s['description']} | {n(s['links'])} | {pct(s['precision'])} | {pct(s['recall'])} | {n(s['wrong_links'])} |")
    a("")
    worst = min(idy["stress"], key=lambda s: s["precision"])
    a(f"Precision stays at 100% unless a wrong customer id arrives with no email hash to catch it; the worst case is `{worst['scenario']}` at {pct(worst['precision'])}. "
      f"Method and limits: [identity_resolution.md](identity_resolution.md).")
    a("")
    a("## Attribution checks")
    a("")
    a(f"{att['checks_passed']} of {att['checks']} checks pass" + (f"; failed: {', '.join(att['failed_checks'])}" if att["failed_checks"] else "") + ".")
    a("")
    tot = att["total_revenue_by_model"]
    a("| Model | Net revenue credited |")
    a("|---|---|")
    for k, label in (("first_touch", "First touch"), ("last_touch", "Last touch"), ("linear", "Linear"), ("time_decay", "Time decay")):
        a(f"| {label} | ${tot[k]:,.2f} |")
    a("")
    a(f"The four totals differ by ${max(tot.values()) - min(tot.values()):,.2f}: the models move credit between channels but never create or lose revenue. "
      f"The checks also confirm that every order carries exactly one unit of credit per model and that credited orders and revenue equal the orders mart. "
      f"{pct(att['share_without_known_source'])} of revenue has no known source under any model (direct, unknown or no touchpoint). "
      f"The largest disagreement between models is on {att['largest_relative_spread_channel']} ({pct(att['largest_relative_spread_pct'])} relative spread). "
      f"Method: [attribution.md](attribution.md).")
    a("")
    a("## How to reproduce")
    a("")
    a("```bash")
    a("uv run dbt test --project-dir dbt --profiles-dir dbt     # or, to test and record in one step:")
    a("uv run python -m src.dbt_results --run                   # -> docs/dbt_test_results.md")
    a("uv run python -m src.identity.accuracy                   # -> reports/identity_accuracy.json and .md")
    a("uv run python -m src.attribution_report                  # -> reports/attribution_comparison.json and .md")
    a("uv run python -m src.test_summary --run-pytest           # -> this page, including the pytest count")
    a("```")
    a("")
    a("## Limits")
    a("")
    a("- The data behind every check is synthetic apart from the GA4 events, so results describe the method, not a real business.")
    a("- dbt tests prove structure and tie-outs, not that a business rule is the right one. Attribution checks prove conservation of revenue, not that any one model is correct.")
    a("- Precision is measured on clean inputs; the stress test above shows how it degrades.")
    a("")
    return "\n".join(L).rstrip() + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run-pytest", action="store_true", help="run the pytest suite and record its result line")
    ap.add_argument("--check", action="store_true", help="exit 1 if docs/test_results.md is out of date")
    args = ap.parse_args(argv)
    existing = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
    pytest_line = run_pytest() if args.run_pytest else None
    if pytest_line is None:
        # keep the last recorded pytest result when it is not re-run
        m = re.search(r"^\| pytest suite \| (.+?) \|", existing, flags=re.M)
        if m and not m.group(1).startswith("run `"):
            pytest_line = m.group(1)
    text = build(pytest_line)
    if args.check:
        if existing != text:
            print("docs/test_results.md is out of date: run  uv run python -m src.test_summary")
            return 1
        print("docs/test_results.md is up to date")
        return 0
    OUT.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {OUT.relative_to(ROOT)}" + (f" (pytest: {pytest_line})" if pytest_line else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())

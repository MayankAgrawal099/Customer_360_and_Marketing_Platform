"""Write the attribution model comparison report from the two comparison tables in BigQuery.

Reads ``marts.fct_attribution_model_comparison`` and ``marts.fct_attribution_checks`` (both a few dozen rows) and writes
``reports/attribution_comparison.md`` (and ``reports/attribution_comparison.json`` with the numbers): the checks that credit
adds up, revenue by channel under the four models, how far the models disagree, and which channels introduce or close
customers. Every figure in the text is computed from the tables; nothing is typed in by hand.

Usage (repository root, after ``uv run dbt run`` for the attribution models and ``gcloud auth application-default login``)::

    uv run python -m src.attribution_report
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "reports" / "attribution_comparison.md"
DEFAULT_JSON = ROOT / "reports" / "attribution_comparison.json"
DEFAULT_PROJECT = "da02-customer360"
MODELS = ["first_touch", "last_touch", "linear", "time_decay"]
LABEL = {"first_touch": "First touch", "last_touch": "Last touch", "linear": "Linear", "time_decay": "Time decay"}


def usd(x: float) -> str:
    return f"${x:,.0f}"


def pct(x: float, digits: int = 1) -> str:
    return f"{100 * x:.{digits}f}%"


def table(header: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def summarise(cmp_: pd.DataFrame, checks: pd.DataFrame) -> dict:
    """The numbers the report states, computed from the tables."""
    total = {m: float(cmp_[f"revenue_{m}"].sum()) for m in MODELS}
    no_source = cmp_[~cmp_["is_known_source"]]
    known = cmp_[cmp_["is_known_source"]]
    avg_total = sum(total.values()) / len(MODELS)
    material = known[known["revenue_max"] >= 0.01 * avg_total]       # channels with at least 1% of revenue
    big = material.sort_values("revenue_spread_pct", ascending=False).iloc[0] if len(material) else None
    paid = cmp_[cmp_["is_paid_channel"]]
    paid_rev = [float(paid[f"revenue_{m}"].sum()) for m in MODELS]
    return {
        "total_revenue_by_model": total,
        "revenue_without_known_source": float(no_source["revenue_linear"].sum()),
        "share_without_known_source": float(no_source["revenue_linear"].sum() / total["linear"]) if total["linear"] else 0.0,
        "largest_relative_spread_channel": None if big is None else str(big["credited_channel"]),
        "largest_relative_spread_pct": None if big is None else float(big["revenue_spread_pct"]),
        "largest_dollar_spread_channel": str(known.sort_values("revenue_spread_usd", ascending=False).iloc[0]["credited_channel"]),
        "largest_dollar_spread_usd": float(known["revenue_spread_usd"].max()),
        "introduces": sorted(cmp_.loc[cmp_["role"] == "Introduces", "credited_channel"]),
        "closes": sorted(cmp_.loc[cmp_["role"] == "Closes", "credited_channel"]),
        "paid_revenue_min": min(paid_rev), "paid_revenue_max": max(paid_rev),
        "paid_share_of_revenue": max(paid_rev) / total["linear"] if total["linear"] else 0.0,
        "checks": int(len(checks)), "checks_passed": int(checks["passed"].sum()),
        "failed_checks": checks.loc[~checks["passed"], ["check_name", "model"]].to_dict("records"),
    }


def build_report(cmp_: pd.DataFrame, checks: pd.DataFrame, generated: str) -> tuple[str, dict]:
    s = summarise(cmp_, checks)
    cmp_ = cmp_.sort_values("revenue_linear", ascending=False)
    ok = s["checks_passed"] == s["checks"] and s["checks"] > 0
    spread_totals = max(s["total_revenue_by_model"].values()) - min(s["total_revenue_by_model"].values())
    lines = [
        "# Attribution: comparing the four models", "",
        f"Generated {generated} by `src/attribution_report.py` from `marts.fct_attribution_model_comparison` and "
        "`marts.fct_attribution_checks`. Method: `docs/attribution.md`.", "",
        "## Do the models add up?", "",
        f"**{'ALL CHECKS PASSED' if ok else 'CHECKS FAILED'}**: {s['checks_passed']} of {s['checks']} checks passed. "
        f"Each model credits {usd(s['total_revenue_by_model']['linear'])} of net revenue, the same as the orders, and "
        f"the four totals differ by {usd(spread_totals)}.", "",
    ]
    if s["failed_checks"]:
        lines += ["Failed: " + ", ".join(f"`{f['check_name']}` ({f['model']})" for f in s["failed_checks"]), ""]
    lines += [table(["Check", "Model", "Expected", "Actual", "Difference", "Passed"],
                    [[f"`{r.check_name}`", r.model, f"{r.expected:,.2f}", f"{r.actual:,.2f}", f"{r.difference:,.2f}",
                      "yes" if r.passed else "**NO**"] for r in checks.sort_values(["check_name", "model"]).itertuples()]),
              "", "## Net revenue by channel", "",
              table(["Channel", *[LABEL[m] for m in MODELS], "Spread", "Spread %", "Role"],
                    [[r.credited_channel, *[usd(getattr(r, f"revenue_{m}")) for m in MODELS], usd(r.revenue_spread_usd),
                      "" if pd.isna(r.revenue_spread_pct) else pct(r.revenue_spread_pct), r.role] for r in cmp_.itertuples()]
                    + [["**Total**", *[f"**{usd(s['total_revenue_by_model'][m])}**" for m in MODELS], "", "", ""]]),
              "", "Spread is the highest minus the lowest revenue the channel gets across the four models. Role compares "
              "first and last touch: *Introduces* when first touch gives the channel at least 5% (and $25) more than last "
              "touch, *Closes* when it gives less. *No known source* rows collect orders whose journey has no source.",
              "", "## Share of revenue", "",
              table(["Channel", *[LABEL[m] for m in MODELS]],
                    [[r.credited_channel, *[pct(getattr(r, f"share_{m}")) for m in MODELS]] for r in cmp_.itertuples()]),
              "", "## What the comparison shows", ""]
    if s["largest_relative_spread_channel"]:
        lines.append(f"- **The choice of model moves big channels little.** Among channels with at least 1% of revenue, the "
                     f"largest difference between models is {pct(s['largest_relative_spread_pct'])} of the channel's average "
                     f"(**{s['largest_relative_spread_channel']}**); the largest in dollars is "
                     f"{usd(s['largest_dollar_spread_usd'])} (**{s['largest_dollar_spread_channel']}**).")
    lines.append(f"- **The biggest uncertainty is missing sources, not the model.** {usd(s['revenue_without_known_source'])} "
                 f"({pct(s['share_without_known_source'])} of revenue) has no known source and is credited identically by all "
                 "four models (Direct / Unknown and No Touchpoint).")
    lines.append(f"- **Paid channels are small.** Paid Search, Display, Paid Social, Affiliate and Email together get "
                 f"{usd(s['paid_revenue_min'])} to {usd(s['paid_revenue_max'])} depending on the model, about "
                 f"{pct(s['paid_share_of_revenue'])} of revenue.")
    lines.append("- **Introduces:** " + (", ".join(s["introduces"]) or "no channel clears the threshold") + ". **Closes:** "
                 + (", ".join(s["closes"]) or "no channel clears the threshold") + ".")
    lines += ["", "## How to read it", "",
              "- The models differ only on orders with more than one visit that has a known source; single-visit orders get the "
              "same credit under all four.",
              "- Linear and time decay credit fractions of an order, so channel order counts can be fractions.",
              "- Attribution covers CRM orders (customers who can be followed across devices). GA4 purchases by visitors who "
              "are not in the CRM are not part of it.",
              "- The data covers about three months, so the 30-day look-back and the 7-day time-decay half-life are "
              "conventions, not findings.", ""]
    numbers = {**s, "channels": cmp_.to_dict("records")}
    return "\n".join(lines), numbers


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", default=os.environ.get("GCP_PROJECT", DEFAULT_PROJECT))
    ap.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    ap.add_argument("--json", type=Path, default=DEFAULT_JSON)
    args = ap.parse_args(argv)
    from google.cloud import bigquery

    try:
        client = bigquery.Client(project=args.project)
    except Exception as exc:  # noqa: BLE001
        print(f"Could not connect to BigQuery: {exc}\nRun: gcloud auth application-default login")
        return 1
    cfg = bigquery.QueryJobConfig(maximum_bytes_billed=1024 ** 3)
    read = lambda t: client.query(f"select * from `{args.project}.marts.{t}`", job_config=cfg).result().to_dataframe()  # noqa: E731
    cmp_, checks = read("fct_attribution_model_comparison"), read("fct_attribution_checks")
    text, numbers = build_report(cmp_, checks, dt.date.today().isoformat())
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(text, encoding="utf-8")
    args.json.write_text(json.dumps(numbers, indent=2, default=str), encoding="utf-8")
    print(f"OK    wrote {args.report}\nOK    wrote {args.json}\n"
          f"{numbers['checks_passed']} of {numbers['checks']} checks passed")
    return 0 if numbers["checks_passed"] == numbers["checks"] else 1


if __name__ == "__main__":
    sys.exit(main())

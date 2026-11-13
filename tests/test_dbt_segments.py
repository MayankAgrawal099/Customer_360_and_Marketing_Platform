"""Tests for the segment models (dim_customer_segments, fct_customer_segments) and their dbt tests.

Every one of the 125 possible (R, F, M) score combinations is run through the real model SQL in DuckDB and
must land in exactly the segment the written rules give; the definitions page, the definitions table and the
model must agree; and the singular dbt tests pass on good data and catch damaged data.
"""

import itertools
import re
import sys
from pathlib import Path

import pandas as pd
import pytest
import yaml

pytest.importorskip("duckdb")
sqlglot = pytest.importorskip("sqlglot")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tests.test_dbt_sessions import DBT, SINGULAR, render, run  # noqa: E402
from tests.test_dbt_staging import output_columns  # noqa: E402

SEG_SQL = (DBT / "models" / "marts" / "fct_customer_segments.sql").read_text(encoding="utf-8")
DEF_SQL = (DBT / "models" / "marts" / "dim_customer_segments.sql").read_text(encoding="utf-8")
DOC = (ROOT / "docs" / "customer_segments.md").read_text(encoding="utf-8")
ORDER = ["Champions", "Loyal", "At Risk", "Big Spenders", "New Customers", "Promising", "Needs Attention", "Lost",
         "No Purchase Yet"]


def expected(r: int, f: int, m: int) -> str:
    """The rules exactly as the definitions page words them, written independently of the SQL."""
    if r >= 4 and f >= 3:
        return "Champions"
    if f >= 2:
        return "Loyal" if r >= 3 else "At Risk"
    if r >= 3 and m >= 4:
        return "Big Spenders"
    return {5: "New Customers", 4: "New Customers", 3: "Promising", 2: "Needs Attention", 1: "Lost"}[r]


COMBOS = list(itertools.product(range(1, 6), range(1, 6), range(1, 6)))


def definitions() -> pd.DataFrame:
    return run(DEF_SQL)


def inputs():
    buyers = [f"B{i:03d}" for i in range(len(COMBOS))]
    dim = pd.DataFrame([dict(customer_id=c, country="US", marketing_opt_in=True, is_buyer=True, has_linked_device=False,
                             first_order_channel_group=None, first_session_channel_group=None,
                             orders=f, net_revenue_usd=10.0 * m) for c, (r, f, m) in zip(buyers, COMBOS)]
                       + [dict(customer_id=c, country="IN", marketing_opt_in=False, is_buyer=False, has_linked_device=True,
                               first_order_channel_group=None, first_session_channel_group="Direct", orders=0,
                               net_revenue_usd=0.0) for c in ("N1", "N2")])
    rfm = pd.DataFrame([dict(customer_id=c, recency_days=100 - 10 * r, frequency=f, monetary_usd=10.0 * m, r_score=r,
                             f_score=f, m_score=m, rfm_code=f"{r}{f}{m}", rfm_total=r + f + m)
                        for c, (r, f, m) in zip(buyers, COMBOS)])
    clv = pd.DataFrame([dict(customer_id=c, predicted_revenue_90d_usd=5.0, predicted_revenue_12m_usd=20.0,
                             clv_12m_usd=10.0 * m + 20.0) for c, (r, f, m) in zip(buyers, COMBOS)])
    return dim, rfm, clv


@pytest.fixture(scope="module")
def seg() -> pd.DataFrame:
    dim, rfm, clv = inputs()
    return run(SEG_SQL, dim_customers=dim, fct_customer_rfm=rfm, fct_customer_clv=clv,
               dim_customer_segments=definitions()).set_index("customer_id")


def test_every_score_combination_lands_in_exactly_the_documented_segment(seg):
    for i, (r, f, m) in enumerate(COMBOS):
        assert seg.loc[f"B{i:03d}", "segment"] == expected(r, f, m), (r, f, m)


def test_all_nine_segments_are_used_and_customers_are_neither_lost_nor_doubled(seg):
    assert len(seg) == len(COMBOS) + 2 and seg.index.is_unique
    assert set(seg["segment"]) == set(ORDER)


def test_customers_without_orders_are_no_purchase_yet_with_zero_value(seg):
    for c in ("N1", "N2"):
        r = seg.loc[c]
        assert r["segment"] == "No Purchase Yet" and not r["is_buyer"] and pd.isna(r["r_score"])
        assert (r["orders"], r["historical_net_revenue_usd"], r["clv_12m_usd"]) == (0, 0.0, 0.0)


def test_segment_order_follows_the_definitions(seg):
    order = {s: i + 1 for i, s in enumerate(ORDER)}
    assert (seg["segment_order"] == seg["segment"].map(order)).all()


def test_money_is_carried_through(seg):
    assert seg.loc["B000", "clv_12m_usd"] == 30.0 and seg.loc["B000", "predicted_revenue_90d_usd"] == 5.0


# ----------------------------------------------------------------------------- definitions, docs, schema
def test_definitions_table_has_nine_ordered_unique_segments():
    d = definitions().sort_values("segment_order")
    assert list(d["segment"]) == ORDER and list(d["segment_order"]) == list(range(1, 10))
    assert d[["definition", "rule", "action"]].notna().all().all()


def test_the_docs_page_matches_the_definitions_table_exactly():
    rows = {}
    for line in DOC.splitlines():
        m = re.match(r"\| (\d) \| \*\*(.+?)\*\* \| (.+?) \| (.+?) \| (.+?) \|$", line)
        if m:
            rows[m.group(2)] = m.groups()
    d = definitions().set_index("segment")
    assert set(rows) == set(d.index)
    for name, (order, _, definition, rule, action) in rows.items():
        assert (int(order), definition, rule, action) == (d.loc[name, "segment_order"], d.loc[name, "definition"],
                                                          d.loc[name, "rule"], d.loc[name, "action"]), name


def test_the_model_case_statement_names_only_defined_segments():
    names = set(re.findall(r"then '([^']+)'", SEG_SQL)) | {"Lost"}
    assert names == set(ORDER)


@pytest.mark.parametrize("model,sql", [("fct_customer_segments", SEG_SQL), ("dim_customer_segments", DEF_SQL)])
def test_models_return_exactly_the_documented_columns(model, sql):
    models = yaml.safe_load((DBT / "models" / "marts" / "_marts.yml").read_text(encoding="utf-8"))["models"]
    doc = next(m for m in models if m["name"] == model)
    if model == "dim_customer_segments":        # a UNION: the columns are the ones the rows come back with
        got = list(definitions().columns)
    else:
        got = output_columns(sqlglot.parse_one(render(sql), read="bigquery"))
    want = [c["name"] for c in doc["columns"]]
    assert sorted(got) == sorted(want), set(got) ^ set(want)
    assert all(c.get("description") for c in doc["columns"])


def test_the_models_never_read_the_ground_truth():
    assert "ground_truth" not in "\n".join(l for l in (SEG_SQL + DEF_SQL).splitlines() if not l.strip().startswith("--"))


# ----------------------------------------------------------------------------- singular dbt tests
NAMES = ["assert_segments_cover_every_customer", "assert_segment_rules_hold"]


def singular(name: str, seg: pd.DataFrame) -> pd.DataFrame:
    dim, _, _ = inputs()
    return run(SINGULAR[name], fct_customer_segments=seg.reset_index(), dim_customers=dim)


@pytest.mark.parametrize("name", NAMES)
def test_singular_tests_pass_on_good_data(name, seg):
    assert singular(name, seg).empty


def test_catches_a_missing_customer_a_wrong_bucket_or_changed_money(seg):
    t = "assert_segments_cover_every_customer"
    assert not singular(t, seg.drop("B000")).empty
    broken = seg.copy()
    broken.loc["N1", "segment"] = "Lost"
    assert not singular(t, broken).empty
    broken = seg.copy()
    broken.loc["B000", "segment"] = "No Purchase Yet"
    assert not singular(t, broken).empty
    broken = seg.copy()
    broken.loc["B000", "historical_net_revenue_usd"] = 999.0
    assert not singular(t, broken).empty
    broken = seg.copy()
    broken.loc["B000", "segment_order"] = None
    assert not singular(t, broken).empty


def test_catches_a_customer_in_the_wrong_segment(seg):
    t = "assert_segment_rules_hold"
    for cust, wrong in (("B000", "Champions"), ("B124", "Lost"), ("B061", "At Risk")):
        broken = seg.copy()
        broken.loc[cust, "segment"] = wrong
        assert cust in list(singular(t, broken)["customer_id"]), (cust, wrong)
    broken = seg.copy()
    broken.loc["N1", "segment"] = "Loyal"
    assert "N1" in list(singular(t, broken)["customer_id"])

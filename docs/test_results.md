# Test results

The final results of every check in the project, on one page. Each number is read from a recorded result file, so this page matches the last run; `uv run python -m src.test_summary` rebuilds it, and a test fails if it is out of date.

> The checks run on **synthetic CRM, order and ad-spend data** joined to **real GA4 events**. Identity accuracy is measured against a synthetic ground truth, so it shows that the rules work as designed; it is not a claim about real customers.

## Summary

| Check | Result | What it proves | Detail |
|---|---|---|---|
| dbt tests | **334 of 334 pass**, 0 warnings, 0 failures | Keys are unique, required fields are filled, ids point at real rows, categories stay in their lists, and 30 business rules tie each layer to the one before | [dbt_test_results.md](dbt_test_results.md) |
| Identity accuracy | Precision **100.0%** (5,931 of 5,931), recall **90.8%** (5,931 of 6,529) | Every link made is correct; the rest have no usable signal | [identity_accuracy_report.md](../reports/identity_accuracy_report.md) |
| Attribution checks | **30 of 30 pass** | Each of the four models credits every order once and exactly $344,692 of net revenue | [attribution_comparison.md](../reports/attribution_comparison.md) |
| pytest suite | 582 passed | The model SQL, exports, READMEs and documents behave as described (real SQL on small hand-built tables in DuckDB) | `tests/` |

## dbt tests

Recorded 2026-11-18 with dbt 1.12.6 by `uv run python -m src.dbt_results --run`. **All tests passed**: 334 of 334 passed, 0 warnings, 0 failures, 0 errors.

| Test type | Tests | Passed | Warned | Failed | Errored |
|---|---|---|---|---|---|
| unique | 19 | 19 | 0 | 0 | 0 |
| not_null | 224 | 224 | 0 | 0 | 0 |
| relationships | 18 | 18 | 0 | 0 | 0 |
| accepted_values | 43 | 43 | 0 | 0 | 0 |
| singular | 30 | 30 | 0 | 0 | 0 |
| **Total** | 334 | 334 | 0 | 0 | 0 |

Every test, by model and by name, is in [dbt_test_results.md](dbt_test_results.md); what each test type protects is in the [data and API documentation](data_api_docs.md#tests).

## Identity accuracy

Scored against `raw.ground_truth_identity_links`, which the rules never read.

| Measure | Value |
|---|---|
| True device-to-customer links | 6,529 |
| Links made | 5,931 |
| Correct links | 5,931 (wrong customer: 0) |
| Precision | 100.0% |
| Recall | 90.8% |
| Best possible recall for these rules | 90.8% (5,931 links have a usable signal) |
| Recall of the links that have a usable signal | 100.0% |
| Links with no usable signal | 598 |
| Customers with a device found | 5,582 of 6,003 |
| Purchase revenue on a linked device | $263,576 of $308,830 (85.3%) |

**By rule**

| Rule | Links | Correct | Precision |
|---|---|---|---|
| Verified identify event (`identify_verified`) | 5,498 | 5,498 | 100.0% |
| Order matched to a GA4 purchase (`order_match`) | 433 | 433 | 100.0% |

**By device role**

| Role | True links | Found | Recall |
|---|---|---|---|
| primary | 6,003 | 5,561 | 92.6% |
| second | 526 | 370 | 70.3% |

**Stress test.** The same rules run on deliberately damaged evidence, to show where they stay safe and where they break.

| Scenario | What is damaged | Links | Precision | Recall | Wrong links |
|---|---|---|---|---|---|
| `baseline` | Inputs as generated | 5,931 | 100.0% | 90.8% | 0 |
| `drop_30pct_identifies` | 30% of identify events lost | 5,068 | 100.0% | 77.6% | 0 |
| `strip_all_hashes` | No identify event has an email hash | 5,931 | 100.0% | 90.8% | 0 |
| `no_order_transaction_ids` | No order carries a GA4 transaction id | 5,498 | 100.0% | 84.2% | 0 |
| `wrong_userid_with_hash_5` | 5% of identify events name the wrong customer; hash still correct | 5,801 | 100.0% | 88.8% | 0 |
| `wrong_userid_no_hash_5` | 5% name the wrong customer and carry no hash | 5,931 | 97.8% | 88.8% | 130 |
| `wrong_userid_no_hash_5_no_orders` | Same as above, with no order evidence to outvote them | 5,498 | 95.0% | 80.0% | 275 |
| `shared_device_5` | 5% of devices are also claimed, a day later, by a second customer | 5,931 | 100.0% | 90.8% | 0 |
| `shared_device_5_claimant_first` | Same, but the second customer's claim comes a day before the owner's | 5,931 | 97.8% | 88.8% | 130 |

Precision stays at 100% unless a wrong customer id arrives with no email hash to catch it; the worst case is `wrong_userid_no_hash_5_no_orders` at 95.0%. Method and limits: [identity_resolution.md](identity_resolution.md).

## Attribution checks

30 of 30 checks pass.

| Model | Net revenue credited |
|---|---|
| First touch | $344,691.89 |
| Last touch | $344,691.89 |
| Linear | $344,691.89 |
| Time decay | $344,691.89 |

The four totals differ by $0.00: the models move credit between channels but never create or lose revenue. The checks also confirm that every order carries exactly one unit of credit per model and that credited orders and revenue equal the orders mart. 29.3% of revenue has no known source under any model (direct, unknown or no touchpoint). The largest disagreement between models is on Paid Search (5.5% relative spread). Method: [attribution.md](attribution.md).

## How to reproduce

```bash
uv run dbt test --project-dir dbt --profiles-dir dbt     # or, to test and record in one step:
uv run python -m src.dbt_results --run                   # -> docs/dbt_test_results.md
uv run python -m src.identity.accuracy                   # -> reports/identity_accuracy.json and .md
uv run python -m src.attribution_report                  # -> reports/attribution_comparison.json and .md
uv run python -m src.test_summary --run-pytest           # -> this page, including the pytest count
```

## Limits

- The data behind every check is synthetic apart from the GA4 events, so results describe the method, not a real business.
- dbt tests prove structure and tie-outs, not that a business rule is the right one. Attribution checks prove conservation of revenue, not that any one model is correct.
- Precision is measured on clean inputs; the stress test above shows how it degrades.

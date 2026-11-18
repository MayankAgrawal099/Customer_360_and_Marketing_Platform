# Documentation

| Folder or file | What it covers |
|---|---|
| `architecture/` | Architecture diagram (PNG and SVG) and the script that draws it, see [architecture/README.md](architecture/README.md) |
| `screenshots/` | Evidence screenshots used in the READMEs: BigQuery tables, dbt results, and the two Tableau dashboards |
| `data_api_docs.md` | The reference for every dataset, dbt model and column, output file and command (generated; rebuild with `uv run python -m src.build_data_api_docs`) |
| `data_dictionary.md` | Every table and column, raw to marts |
| `metric_dictionary.md` | RFM, CLV, attribution, ROI and CPA definitions |
| `synthetic_data.md` | Which data is real (GA4) and which is synthetic (CRM, orders, ad spend, Segment events), and every assumption |
| `identity_resolution.md` | The matching rules, conflicts and limits |
| `customer_segments.md` | The nine segments |
| `attribution.md` | The four attribution models |
| `campaign_roi.md`, `cpa.md` | Return on ad spend and cost per acquisition |
| `budget_recommendations.md` | How a budget recommendation is decided |
| `dbt_test_results.md` | The recorded result of `dbt test` (regenerate with `uv run python -m src.dbt_results --run`) |
| `ga4_exploration.md`, `ga4_exploration_sessions.md` | What the GA4 sample contains and how sessions are defined |

Generated reports with measured results are in [`../reports/`](../reports/).

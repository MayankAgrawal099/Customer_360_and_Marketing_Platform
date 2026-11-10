# Customer 360 and Marketing Attribution Platform

Combines website, CRM and ad-spend data into one customer view and shows which marketing channels actually bring revenue. Built with BigQuery, dbt, Python and Tableau for internship project DA-02.

> Work in progress. This README is rewritten with full results and setup steps when the project is finished.

## About the data

- **Website sessions and purchases:** the GA4 obfuscated sample e-commerce dataset (`bigquery-public-data.ga4_obfuscated_sample_ecommerce`), real data from the Google Merchandise Store.
- **CRM customers, orders and ad spend:** synthetic, generated with Faker using a fixed seed and linked to real GA4 users and dates.
- Segment is not used as a live service. The synthetic CRM events follow Segment's `identify` and `track` format.

## Planned structure

```
Customer_360_and_Marketing_Platform/
├── dbt/          # dbt project: staging, intermediate and mart models, tests
├── src/          # Python: synthetic data, identity resolution, attribution
├── sql/          # standalone SQL (for example attribution queries)
├── data/         # synthetic CSVs (raw downloads are git-ignored)
├── tableau/      # workbook and exports
├── docs/         # architecture, dictionaries, screenshots
├── tests/        # pytest suite
├── reports/      # test results
├── pyproject.toml
└── README.md
```

## Setup

You need Python 3.12, [uv](https://docs.astral.sh/uv/), the [Google Cloud CLI](https://cloud.google.com/sdk/docs/install) and a Google Cloud project (the free BigQuery sandbox is enough).

```bash
git clone https://github.com/MayankAgrawal099/Customer_360_and_Marketing_Platform.git
cd Customer_360_and_Marketing_Platform
uv sync
gcloud auth application-default login
gcloud config set project da02-customer360
uv run dbt debug --project-dir dbt --profiles-dir dbt
```

If your project ID is not `da02-customer360`, set it first: `set GCP_PROJECT=your-project-id` (Windows) or `export GCP_PROJECT=your-project-id`.

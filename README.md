# Product Analytics Deep-Dive

> End-to-end product analytics case studies: funnels, retention, engagement segmentation, and north-star metric design. SQL-first, memo-driven.

![CI](https://github.com/wavde/product-analytics-deepdive/actions/workflows/ci.yml/badge.svg)

## Why this repo

At senior analytics levels, the hard part isn't running the query — it's framing the question, defining the metric, and writing the memo that drives the decision. Every case study here includes:

1. A **business question** framed like a real PM/DS partnership
2. A **metric definition** with tradeoffs made explicit
3. **SQL** (Postgres / Spark SQL / DuckDB) as the workhorse
4. **Python** for anything SQL can't express cleanly (bootstrap CIs, visual exploration)
5. A **memo** that would survive an interview take-home review

## Case Studies

| # | Case Study | Primary concepts | Status |
|---|-----------|------------------|--------|
| 01 | [Funnel + retention on simulated e-commerce](case-studies/01-funnel-and-retention/) | Conversion funnel, cohort retention, north-star metric | ✅ Complete |
| 02 | [Cohort engagement & segmentation](case-studies/02-engagement-segmentation/) | RFM, power-user (L-28) curve, k-means | ✅ Complete |
| 03 | [North-star metric design memo](case-studies/03-north-star-metric/) | Metric tradeoffs, WAU × conversion decomposition, gaming risk | ✅ Complete |

## Stack

- **DuckDB** for portable SQL (runs anywhere, includes window functions)
- **Spark SQL** for scale demonstrations (syntax notes called out where different)
- **Python**: pandas, numpy, matplotlib for analysis + charts

## How to run

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
pytest                          # smoke tests — regenerates data and validates queries
```

Each case study has its own README + reproducer.

## License

MIT — see [LICENSE](LICENSE).

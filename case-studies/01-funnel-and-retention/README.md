# Case Study 01 — Funnel Conversion + Cohort Retention

**Dataset:** Simulated 3-month e-commerce event log (20,000 users, ~hundreds of thousands of events), generated locally.
**Tools:** DuckDB (portable SQL with window functions), Python (pandas).

## TL;DR

With `seed=7` (default):
- Overall view → purchase conversion is **~13.5%**, dominated by the 65% drop-off between "view" and "add to cart".
- **Mobile converts ~35% worse than desktop** at the cart step — the biggest addressable opportunity.
- Weekly retention follows a power-law decay: **~40% at W+1, ~15% at W+4, ~8% by W+11**, with heavy-tailed "power user" cohorts accounting for most long-term revenue.

## Business framing

If you were a DS partnered with a PM running this storefront, the two natural questions are:

1. **"Where in the funnel should we focus product investment?"** — answered by the funnel + device split.
2. **"Is our product growing or just refilling a leaky bucket?"** — answered by cohort retention curves.

This case study is the 2-hour version of what you'd expect to turn in on day 1 of a new role.

## How to reproduce

```bash
cd case-studies/01-funnel-and-retention
python src/generate_data.py        # writes data/ecommerce.db
python src/run_analysis.py         # executes all 3 SQL queries and prints results
```

Everything is deterministic (seed=7). CI runs both steps end-to-end.

## Queries

| File | Question |
|------|----------|
| [`sql/01_funnel_overall.sql`](sql/01_funnel_overall.sql) | Overall 4-step conversion rates |
| [`sql/02_retention_weekly.sql`](sql/02_retention_weekly.sql) | Weekly cohort retention for 12 weeks |
| [`sql/03_funnel_by_device.sql`](sql/03_funnel_by_device.sql) | Funnel broken out by device type |

Each query uses:
- Conditional aggregation (`COUNT(*) FILTER (WHERE ...)`)
- The "ordering constraint" pattern — step N's timestamp must exceed step N-1's — which is the most common interview-pitfall in funnel SQL.

## Methodology notes

- **First-session funnel.** We anchor to each user's first `view_product` and ask whether subsequent stages happened within 24 hours. This avoids inflating conversion rate via repeat sessions.
- **Window for retention.** Weeks are defined via `DATE_TRUNC('week', ...)` so W+0 is the signup week itself (expected to be ~100%, used as sanity check).
- **Right-censoring.** For cohorts near the end of the data window, late weeks (W+10, W+11) are mechanically zero. A real memo would either drop those cohort-weeks or use a hazard-model framing.
- **DuckDB vs Spark SQL.** Syntax is 99% identical. The main differences:
  - DuckDB: `INTERVAL 24 HOUR` ; Spark: `INTERVAL '24' HOUR`
  - DuckDB supports `FILTER (WHERE ...)` ; Spark needs `SUM(CASE WHEN ... THEN 1 END)`.

## What I'd do next

1. **Metric decomposition.** Express conversion rate as a product of stage conversion rates and track each as a leading indicator.
2. **North-star candidate.** Propose "weekly active purchasers" as a north-star and quantify its correlation with revenue. (This is [Case Study 03](../03-north-star-metric/).)
3. **Causal mobile-funnel investigation.** Is mobile worse because of UX, or because mobile users are a structurally different population? A natural next project for the [causal-inference-playbook](https://github.com/wavde/causal-inference-playbook).

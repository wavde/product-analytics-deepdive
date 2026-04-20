# Case Study 02 — Cohort Engagement & Segmentation

**Question:** *We have 20K e-commerce users — who are our power users, who's about to churn, and who deserves a re-engagement push?*

## TL;DR

Combine **RFM** (interpretable, ops-friendly) with **k-means on engagement features** (data-driven, captures non-linear groupings) for a defensible segmentation. Top revenue decile drives ~55% of total revenue; the L-28 power-user curve has a clear bimodal shape (one-time visitors vs. weekly returners), and k=4 cleanly separates *casual visitors / active browsers / engaged buyers / power users*.

## Why two methods, not one

| | RFM | K-means |
|---|---|---|
| Interpretability | ✅ Each digit is a quintile rank | ⚠️ Cluster centroids need translation |
| Operationalizable | ✅ "Champions = R≥4 & F≥4 & M≥4" is a SQL filter | ⚠️ Need to ship cluster IDs |
| Captures non-linear structure | ❌ Hard cuts on margins | ✅ Picks up joint structure |
| Scales to many features | ⚠️ 3 dims is the practical limit | ✅ Easily 10+ |
| Stable across re-runs | ✅ Deterministic | ⚠️ k-means initialization noise |

**Use both.** RFM is the segment definition you ship to lifecycle marketing tomorrow. K-means is the validation layer — if your "champions" RFM segment splits cleanly into one k-means cluster, you have a real segment. If it splits across 3 clusters, your RFM thresholds are wrong.

## Method

### 1. RFM (`sql/01_rfm_scores.sql`)
For each purchaser:
- **R**ecency: days since last purchase (anchored to panel end)
- **F**requency: total purchases
- **M**onetary: total revenue

Each scored into quintiles (NTILE 1–5) → 3-digit segment code (`555` = champion, `111` = lost).

### 2. Power-user curve (`sql/02_power_user_curve.sql`)
For each active user, count distinct active days in the trailing 28-day window. The histogram is the **product's heartbeat** — the standard "L7/L28" Sean Ellis chart. We want a tail at L ≥ 20.

### 3. Revenue concentration (`sql/03_revenue_concentration.sql`)
Decile users by lifetime revenue; compute each decile's share + cumulative %. Drives the strategic question: *do we optimize for top-decile retention, or expand the funnel?*

### 4. K-means engagement (`src/segment.py`)
Four standardized features per active user:
`views_28d, active_days_28d, purchase_count, revenue_cents`

Fit k=4 with `random_state=0`. Centroids are translated to business names heuristically:
- `power_users`: highest-revenue cluster
- `engaged_buyers`: ≥1 purchase
- `active_browsers`: ≥5 active days, no purchase
- `casual_visitors`: everyone else

## How to reproduce

```bash
cd case-studies/02-engagement-segmentation
# regenerate data if needed:
python ../01-funnel-and-retention/src/generate_data.py
python src/run_analysis.py
```

With `seed=7` (default), the output has the shape below. Exact decile rows are in the SQL output; the qualitative pattern is:

```
=== 03_revenue_concentration.sql ===
Top decile contributes ~30-35% of revenue.
Top three deciles contribute ~65-75% cumulative.
Bottom five deciles combined contribute <15%.

=== K-means engagement segmentation (k=4) ===
Four clusters separate cleanly into:
  power_users      — top-revenue cluster, 5-10% of users, most purchases
  engaged_buyers   — >=1 purchase, moderate activity
  active_browsers  — >=5 active days, no purchase
  casual_visitors  — light single-session users, majority of the base
```

## Limitations & what I'd do next

1. **K-means assumes spherical clusters in standardized space.** Engagement data is heavy-tailed; **Gaussian Mixture** or **HDBSCAN** often produce more interpretable groups, especially for the long tail of power users.
2. **No time dimension.** RFM-T (adding tenure) or recency-trajectory features (e.g., "is recency improving or worsening?") capture lifecycle stage better than a snapshot.
3. **No churn prediction.** The natural follow-up: predict 28-day churn per cluster, then run a retention experiment targeting the highest-risk-yet-recoverable cluster (causal_inference_playbook case 01 stack: variance-reduce with CUPED).
4. **Validate k.** A real shipped segmentation would justify k via silhouette score + business stakeholder review, not just `k=4` for narrative convenience.
5. **LTV instead of M.** Total revenue confounds tenure. CLV (Pareto/NBD or BG/NBD model) is the clean monetary signal.

## References

- Hughes, A. (1994). *Strategic Database Marketing.* — original RFM
- Fader, P., Hardie, B. (2009). *Probability Models for Customer-Base Analysis.* — BG/NBD CLV
- Ellis, S. — "Power User Curve" (Substack/posts)
- Reichheld, F. — *The Loyalty Effect*

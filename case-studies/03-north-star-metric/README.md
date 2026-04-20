# Case Study 03 — North-Star Metric Design Memo

**Audience:** Cross-functional leadership (Product, Eng, Marketing, Finance)
**Author:** Senior Data Scientist, Analytics
**Status:** Recommendation — for review

## Question

> *We need one metric we'll all align on for the next 6 months. It has to be honest about whether the product is working — not vanity, not gameable, and tied to revenue without being revenue itself.*

## TL;DR — Recommendation

**Adopt Weekly Purchasing Active Users (WPAU)** as the company north-star metric.

> *WPAU = number of distinct users who completed ≥1 purchase in the trailing 7 days.*

It captures the **only thing the product exists to do** (move users through the funnel to purchase) at the **right time granularity** (a week filters out daily noise but moves fast enough to action), and it has a **clean two-factor decomposition** that gives every team a lever:

$$\text{WPAU} = \text{WAU} \;\times\; \text{Purchase Conversion}$$

WAU is the marketing/growth lever; conversion is the product/UX lever. Each function knows whether they're winning.

## Method — what I considered

I evaluated 5 candidates against a fixed rubric:

| Candidate | What it is | Vanity risk | Gaming risk | Decomposes? | Tracks revenue? | Verdict |
|---|---|---|---|---|---|---|
| **DAU** | Distinct users active in 1 day | High — opening the app counts | Low | ✅ | Loosely | ❌ Doesn't reflect product success |
| **Revenue / Day** | $ booked | Low | Medium (discount-stuffing) | ✅ | ✅ Trivially | ❌ Lagging, volatile, no UX accountability |
| **Avg Order Value (AOV)** | $/purchase | Medium | High — drop discounts to inflate | ❌ | Loosely | ❌ Inverse correlation with volume |
| **Daily Active Buyers** | Daily WPAU | Low | Low | ✅ | ✅ | ⚠️ Too noisy day-to-day; weekly is the right cadence |
| **WPAU** ✅ | Weekly active buyers | Low | Low | ✅ via WAU × conv | ✅ Strongly | **Recommended** |

### Why WPAU passes all four tests

1. **It's not vanity.** Opening the app doesn't count. Browsing doesn't count. Only completed purchases.
2. **It's hard to game.** Unlike revenue, you can't lift it via pricing or discounting *without* moving the underlying user behavior (fake purchases would be visible in finance reconciliation).
3. **It decomposes cleanly.** Two factors map to two org functions. If WPAU is flat, you can immediately tell whether it's a top-of-funnel problem (WAU) or a conversion problem (% of WAU who purchase).
4. **It correlates with revenue without being revenue.** This avoids the "Goodhart's Law" failure of metrics that *are* the goal — but it tracks revenue closely enough that finance and product look at the same chart.

### Why not revenue directly?

Revenue is the **outcome**, not the **leading indicator**. It moves with WPAU but lags it by ~7–14 days because of refund cycles, gift-card delay, and FX. WPAU moves first, which is what a north-star is for. Revenue is the right *board metric* — WPAU is the right *operational* metric.

### Why weekly, not daily?

- Day-of-week seasonality dwarfs real signal at daily cadence.
- Weekly trims that out without losing responsiveness — most teams ship weekly.
- 7-day rolling window means every team can check it on any day with a stable comparison.

### Why not monthly?

- Too slow to action — a 4-week feedback loop is a death sentence for experiments.
- Monthly metrics encourage end-of-month sandbagging.

## Decomposition — how teams use it

```
                          WPAU
                           │
            ┌──────────────┴──────────────┐
            │                             │
           WAU                  Purchase Conversion
       (top of funnel)         (% of WAU who buy)
            │                             │
   ┌────────┴────────┐           ┌────────┴────────┐
   │                 │           │                 │
 New users      Returning     Cart starts      Cart→Pay
 (Marketing)     (Lifecycle)    (Product/UX)   (Payments)
```

Each leaf is a team's KPI. Each parent is a CEO-readable rollup. Goodhart's Law mitigation: any single team gaming their leaf metric will be visible in the parent — if Marketing inflates new-user signups with low-intent traffic, conversion drops, WPAU stays flat.

## Gaming risk — concrete failure modes & detections

| If the team... | They could try to... | We catch it via... |
|---|---|---|
| Marketing | Buy low-intent traffic to spike WAU | Conversion rate drops; WPAU flat |
| Product | Force a paywall to push conversion | WAU drops (users bounce); WPAU flat |
| Payments | Auto-retry failed cards as "purchase" | Refund rate spike; finance reconciliation |
| Lifecycle | Spammy notifications to reactivate | Active-days-per-user *and* WPAU diverge |

## Limitations & explicit choices

1. **WPAU treats $1 and $1,000 buyers the same.** A revenue-weighted version (`Σ revenue from each weekly buyer`) would weight whales more. I'd add this as a **secondary** metric, not replace WPAU — single-buyer counts are democratic and discourage chasing whales.
2. **Doesn't reward retention beyond the 7-day window.** Pair with a retention rate (e.g., W4 retention) as a guardrail.
3. **A user who upgrades to subscription doesn't "purchase" weekly** under this definition. If we launch subscriptions at scale, the metric needs to evolve to "Weekly Paying Users" (subscribers + one-time purchasers).
4. **Refunds.** WPAU is based on *purchase events*, not net revenue. A 95% refund rate would not move WPAU. Pair with a guardrail on refund rate.
5. **Cross-device deduplication assumes user_id is reliable.** If logged-out browsing is a meaningful share of activity, we'll double-count.

## How to track it

```bash
cd case-studies/03-north-star-metric
python ../01-funnel-and-retention/src/generate_data.py    # if needed
python src/run_analysis.py
```

`sql/01_north_star_daily.sql` produces the daily WPAU time series.
`sql/02_decomposition.sql` produces the WAU × conversion decomposition with WoW comparison.

## Decision asks

1. **Approve WPAU as the company north-star** for the next 6 months.
2. **Approve the team-level decomposition** (Marketing → WAU; Product → conversion).
3. **Approve guardrails:** refund rate < 3%, W4 retention ≥ baseline, NPS unchanged.
4. **Schedule the 6-month review** to test whether the metric still reflects product reality.

## References

- Sean Ellis — *Hacking Growth*, Ch. 3 (north-star principles)
- Lenny Rachitsky — "What is a north star metric?" (lennysnewsletter.com)
- Goodhart, C. (1975) — "When a measure becomes a target, it ceases to be a good measure."
- Amplitude — *Mastering Retention* (decomposition framing)
- Kohavi, Tang, Xu — *Trustworthy Online Controlled Experiments*, Ch. 7 (OEC design)

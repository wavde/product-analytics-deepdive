-- Case Study 02 -- Query 3: Revenue concentration by user decile.
--
-- Sort purchasers by total revenue, bucket into deciles, and report each
-- decile's share of total revenue. The classic "top 10% drives 50%+" check.
--
-- This single query is one of the most asked-for slides in any analytics
-- review: shows lifetime-value skew and informs whether to optimize
-- top-of-funnel volume vs. high-value cohorts.

WITH user_revenue AS (
    SELECT
        user_id,
        SUM(revenue_cents) AS revenue_cents
    FROM events
    WHERE event_name = 'purchase'
    GROUP BY user_id
),
decile_assigned AS (
    SELECT
        user_id,
        revenue_cents,
        NTILE(10) OVER (ORDER BY revenue_cents DESC) AS revenue_decile
    FROM user_revenue
)
SELECT
    revenue_decile,
    COUNT(*)                                                                AS n_users,
    SUM(revenue_cents) / 100.0                                              AS decile_revenue_dollars,
    ROUND(100.0 * SUM(revenue_cents) / SUM(SUM(revenue_cents)) OVER (), 2)  AS pct_of_total_revenue,
    ROUND(
        100.0 * SUM(SUM(revenue_cents)) OVER (
            ORDER BY revenue_decile
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) / SUM(SUM(revenue_cents)) OVER (),
        2
    )                                                                       AS cumulative_pct
FROM decile_assigned
GROUP BY revenue_decile
ORDER BY revenue_decile;

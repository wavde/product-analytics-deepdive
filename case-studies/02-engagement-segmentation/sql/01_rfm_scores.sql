-- Case Study 02 -- Query 1: RFM scores per user.
--
-- Recency  : days since last purchase (lower = better)
-- Frequency: count of purchase events
-- Monetary : total revenue (cents)
--
-- We score each dimension into quintiles (1=worst, 5=best) using NTILE,
-- then concatenate into a 3-digit RFM segment code (e.g. '555' = champions).

WITH purchase_data AS (
    SELECT
        user_id,
        MAX(event_time)                                  AS last_purchase_at,
        COUNT(*)                                         AS purchase_count,
        SUM(revenue_cents)                               AS total_revenue_cents
    FROM events
    WHERE event_name = 'purchase'
    GROUP BY user_id
),
analysis_anchor AS (
    SELECT MAX(event_time) AS anchor_time FROM events
),
rfm_raw AS (
    SELECT
        p.user_id,
        DATE_DIFF('day', p.last_purchase_at, a.anchor_time)  AS recency_days,
        p.purchase_count                                      AS frequency,
        p.total_revenue_cents                                 AS monetary_cents
    FROM purchase_data p
    CROSS JOIN analysis_anchor a
)
SELECT
    user_id,
    recency_days,
    frequency,
    monetary_cents,
    -- NTILE(5) ASC for recency: smaller days = top quintile = score 5
    6 - NTILE(5) OVER (ORDER BY recency_days)                AS r_score,
    NTILE(5) OVER (ORDER BY frequency)                       AS f_score,
    NTILE(5) OVER (ORDER BY monetary_cents)                  AS m_score,
    CONCAT(
        CAST(6 - NTILE(5) OVER (ORDER BY recency_days)   AS VARCHAR),
        CAST(    NTILE(5) OVER (ORDER BY frequency)      AS VARCHAR),
        CAST(    NTILE(5) OVER (ORDER BY monetary_cents) AS VARCHAR)
    )                                                         AS rfm_segment
FROM rfm_raw
ORDER BY r_score DESC, f_score DESC, m_score DESC
LIMIT 100;

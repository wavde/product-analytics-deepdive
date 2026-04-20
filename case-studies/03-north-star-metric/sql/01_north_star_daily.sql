-- Case Study 03 -- Daily north-star metric: Weekly Purchasing Active Users (WPAU).
--
-- Definition: number of distinct users who made >=1 purchase in the trailing
-- 7 days, computed at each calendar day.
--
-- Why this metric? See README.md. TL;DR: it captures the *intent* of the
-- product (people pay for things), is robust to trial-and-bounce noise,
-- and can be decomposed into clean input drivers.

WITH days AS (
    SELECT DISTINCT DATE_TRUNC('day', event_time)::DATE AS d
    FROM events
),
purchases AS (
    SELECT user_id, DATE_TRUNC('day', event_time)::DATE AS purchase_day
    FROM events
    WHERE event_name = 'purchase'
)
SELECT
    d.d                                                         AS report_date,
    COUNT(DISTINCT p.user_id)                                   AS wpau
FROM days d
LEFT JOIN purchases p
  ON p.purchase_day BETWEEN d.d - INTERVAL 6 DAY AND d.d
GROUP BY d.d
ORDER BY d.d;

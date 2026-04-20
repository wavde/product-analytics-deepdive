-- Case Study 03 -- North-star decomposition.
--
-- WPAU = Weekly Active Users (WAU)
--      x conversion (% of WAU who purchased)
--
-- For the latest reportable day, decompose WPAU into its two drivers so we
-- can trace which one is moving WPAU week-over-week.
--
-- WoW comparison: latest 7-day window vs. the 7-day window ending 7 days earlier.

WITH bounds AS (
    SELECT
        MAX(event_time)::DATE                                AS today,
        (MAX(event_time) - INTERVAL 6 DAY)::DATE             AS this_window_start,
        (MAX(event_time) - INTERVAL 7 DAY)::DATE             AS prev_window_end,
        (MAX(event_time) - INTERVAL 13 DAY)::DATE            AS prev_window_start
    FROM events
),
this_week AS (
    SELECT
        COUNT(DISTINCT e.user_id)                                              AS wau,
        COUNT(DISTINCT CASE WHEN e.event_name = 'purchase' THEN e.user_id END) AS wpau
    FROM events e, bounds b
    WHERE e.event_time::DATE BETWEEN b.this_window_start AND b.today
),
prev_week AS (
    SELECT
        COUNT(DISTINCT e.user_id)                                              AS wau,
        COUNT(DISTINCT CASE WHEN e.event_name = 'purchase' THEN e.user_id END) AS wpau
    FROM events e, bounds b
    WHERE e.event_time::DATE BETWEEN b.prev_window_start AND b.prev_window_end
)
SELECT
    'this_week' AS period,
    wau,
    wpau,
    ROUND(100.0 * wpau / NULLIF(wau, 0), 2) AS purchase_conversion_pct
FROM this_week
UNION ALL
SELECT
    'prev_week' AS period,
    wau,
    wpau,
    ROUND(100.0 * wpau / NULLIF(wau, 0), 2) AS purchase_conversion_pct
FROM prev_week;

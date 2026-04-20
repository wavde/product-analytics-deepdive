-- Case Study 02 -- Query 2: Power-user curve (L-of-N).
--
-- For each active user, count distinct active days in the last 28 days
-- of the panel. The histogram of this count tells you whether your
-- product has a "power user" tail (Sean Ellis L7/L28 framing).
--
-- Healthy retention products usually show a U-shape:
--   spike at L=1 (one-time visitors) AND a meaningful tail at L>=20 (daily users).
-- A product with no power-user tail is one users *try* but don't *return* to.

WITH window_bounds AS (
    SELECT
        MAX(event_time)                              AS panel_end,
        MAX(event_time) - INTERVAL 28 DAY            AS window_start
    FROM events
),
active_days_per_user AS (
    SELECT
        e.user_id,
        COUNT(DISTINCT DATE_TRUNC('day', e.event_time)) AS active_days_in_28
    FROM events e
    CROSS JOIN window_bounds w
    WHERE e.event_time >= w.window_start
    GROUP BY e.user_id
)
SELECT
    active_days_in_28          AS L_value,
    COUNT(*)                   AS users,
    ROUND(
        100.0 * COUNT(*) / SUM(COUNT(*)) OVER (),
        2
    )                          AS pct_of_active_users
FROM active_days_per_user
GROUP BY active_days_in_28
ORDER BY active_days_in_28;

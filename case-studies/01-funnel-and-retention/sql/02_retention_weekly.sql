-- Weekly cohort retention: for users who signed up in week W,
-- what fraction returned (had any event) in week W+k for k = 0..11
-- (a 12-week retention curve, indexed from the sign-up week).

WITH cohorts AS (
    SELECT
        user_id,
        DATE_TRUNC('week', signup_date) AS cohort_week
    FROM users
),
cohort_size AS (
    SELECT cohort_week, COUNT(DISTINCT user_id) AS size
    FROM cohorts
    GROUP BY cohort_week
),
offsets AS (
    SELECT range AS week_offset
    FROM range(12)
),
cohort_spine AS (
    SELECT
        cs.cohort_week,
        o.week_offset,
        cs.size
    FROM cohort_size cs
    CROSS JOIN offsets o
),
activity AS (
    SELECT DISTINCT
        user_id,
        DATE_TRUNC('week', event_time) AS active_week
    FROM events
),
cohort_activity AS (
    SELECT
        c.cohort_week,
        CAST(DATE_DIFF('day', c.cohort_week, a.active_week) / 7 AS INTEGER) AS week_offset,
        COUNT(DISTINCT a.user_id) AS active_users
    FROM cohorts c
    JOIN activity a USING (user_id)
    WHERE a.active_week >= c.cohort_week
      AND a.active_week <  c.cohort_week + INTERVAL 12 WEEK
    GROUP BY 1, 2
)
SELECT
    spine.cohort_week,
    spine.week_offset,
    ROUND(100.0 * COALESCE(ca.active_users, 0) / spine.size, 2) AS retention_pct,
    COALESCE(ca.active_users, 0) AS active_users,
    spine.size AS cohort_size
FROM cohort_spine spine
LEFT JOIN cohort_activity ca
  ON ca.cohort_week = spine.cohort_week
 AND ca.week_offset = spine.week_offset
ORDER BY spine.cohort_week, spine.week_offset;

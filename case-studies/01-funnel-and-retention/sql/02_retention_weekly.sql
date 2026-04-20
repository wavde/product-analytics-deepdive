-- Weekly cohort retention: for users who signed up in week W,
-- what fraction returned (had any event) in week W+k for k = 0..11
-- (a 12-week retention curve, indexed from the sign-up week).

WITH cohorts AS (
    SELECT
        user_id,
        DATE_TRUNC('week', signup_date) AS cohort_week
    FROM users
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
        a.active_week,
        -- integer weeks since cohort start
        CAST(DATE_DIFF('day', c.cohort_week, a.active_week) / 7 AS INTEGER) AS week_offset,
        COUNT(DISTINCT a.user_id) AS active_users
    FROM cohorts c
    JOIN activity a USING (user_id)
    WHERE a.active_week >= c.cohort_week
      AND a.active_week <  c.cohort_week + INTERVAL 12 WEEK
    GROUP BY 1, 2
),
cohort_size AS (
    SELECT cohort_week, COUNT(DISTINCT user_id) AS size
    FROM cohorts
    GROUP BY cohort_week
)
SELECT
    ca.cohort_week,
    ca.week_offset,
    ROUND(100.0 * ca.active_users / cs.size, 2) AS retention_pct,
    ca.active_users,
    cs.size AS cohort_size
FROM cohort_activity ca
JOIN cohort_size cs USING (cohort_week)
ORDER BY ca.cohort_week, ca.week_offset;

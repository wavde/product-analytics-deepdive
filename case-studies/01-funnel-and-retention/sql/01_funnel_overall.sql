-- Overall 4-step conversion funnel.
-- For each user's first session, count whether they progressed through each
-- stage (each stage must occur AFTER the previous one).

WITH first_sessions AS (
    SELECT
        user_id,
        MIN(event_time) AS viewed_at
    FROM events
    WHERE event_name = 'view_product'
    GROUP BY user_id
),
user_stages AS (
    SELECT
        fs.user_id,
        fs.viewed_at,
        MIN(CASE WHEN e.event_name = 'add_to_cart' THEN e.event_time END) AS carted_at,
        MIN(CASE WHEN e.event_name = 'checkout'    THEN e.event_time END) AS checkout_at,
        MIN(CASE WHEN e.event_name = 'purchase'    THEN e.event_time END) AS purchased_at
    FROM first_sessions fs
    LEFT JOIN events e
      ON e.user_id = fs.user_id
     AND e.event_time >= fs.viewed_at
     AND e.event_time <  fs.viewed_at + INTERVAL 24 HOUR
    GROUP BY fs.user_id, fs.viewed_at
)
SELECT
    COUNT(*)                                                                  AS viewed,
    COUNT(*) FILTER (WHERE carted_at    > viewed_at)                          AS carted,
    COUNT(*) FILTER (WHERE checkout_at  > carted_at)                          AS checkout,
    COUNT(*) FILTER (WHERE purchased_at > checkout_at)                        AS purchased,

    ROUND(100.0 * COUNT(*) FILTER (WHERE carted_at    > viewed_at)    / COUNT(*), 2) AS pct_view_to_cart,
    ROUND(100.0 * COUNT(*) FILTER (WHERE checkout_at  > carted_at)    /
                  NULLIF(COUNT(*) FILTER (WHERE carted_at > viewed_at), 0), 2)       AS pct_cart_to_checkout,
    ROUND(100.0 * COUNT(*) FILTER (WHERE purchased_at > checkout_at)  /
                  NULLIF(COUNT(*) FILTER (WHERE checkout_at > carted_at), 0), 2)     AS pct_checkout_to_purchase
FROM user_stages;

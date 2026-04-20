-- Funnel broken out by device to surface the biggest drop-off opportunity.

WITH first_sessions AS (
    SELECT e.user_id, u.device, MIN(e.event_time) AS viewed_at
    FROM events e
    JOIN users u USING (user_id)
    WHERE e.event_name = 'view_product'
    GROUP BY e.user_id, u.device
),
user_stages AS (
    SELECT
        fs.user_id,
        fs.device,
        fs.viewed_at,
        MIN(CASE WHEN e.event_name = 'add_to_cart' THEN e.event_time END) AS carted_at,
        MIN(CASE WHEN e.event_name = 'checkout'    THEN e.event_time END) AS checkout_at,
        MIN(CASE WHEN e.event_name = 'purchase'    THEN e.event_time END) AS purchased_at
    FROM first_sessions fs
    LEFT JOIN events e
      ON e.user_id = fs.user_id
     AND e.event_time >= fs.viewed_at
     AND e.event_time <  fs.viewed_at + INTERVAL 24 HOUR
    GROUP BY fs.user_id, fs.device, fs.viewed_at
)
SELECT
    device,
    COUNT(*)                                                              AS viewed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE carted_at    > viewed_at)  / COUNT(*), 2)                       AS pct_view_to_cart,
    ROUND(100.0 * COUNT(*) FILTER (WHERE checkout_at  > carted_at)  /
          NULLIF(COUNT(*) FILTER (WHERE carted_at > viewed_at), 0), 2)                                   AS pct_cart_to_checkout,
    ROUND(100.0 * COUNT(*) FILTER (WHERE purchased_at > checkout_at) /
          NULLIF(COUNT(*) FILTER (WHERE checkout_at > carted_at), 0), 2)                                 AS pct_checkout_to_purchase,
    ROUND(100.0 * COUNT(*) FILTER (WHERE purchased_at > checkout_at)  / COUNT(*), 2)                     AS pct_view_to_purchase
FROM user_stages
GROUP BY device
ORDER BY viewed DESC;

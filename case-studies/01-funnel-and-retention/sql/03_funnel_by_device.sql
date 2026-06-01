-- Funnel broken out by device to surface the biggest drop-off opportunity.

WITH first_sessions AS (
    SELECT e.user_id, u.device, MIN(e.event_time) AS viewed_at
    FROM events e
    JOIN users u USING (user_id)
    WHERE e.event_name = 'view_product'
    GROUP BY e.user_id, u.device
),
cart_steps AS (
    SELECT
        fs.user_id,
        fs.device,
        fs.viewed_at,
        MIN(e.event_time) AS carted_at
    FROM first_sessions fs
    LEFT JOIN events e
      ON e.user_id = fs.user_id
     AND e.event_name = 'add_to_cart'
     AND e.event_time > fs.viewed_at
     AND e.event_time < fs.viewed_at + INTERVAL 24 HOUR
    GROUP BY fs.user_id, fs.device, fs.viewed_at
),
checkout_steps AS (
    SELECT
        cs.user_id,
        cs.device,
        cs.viewed_at,
        cs.carted_at,
        MIN(e.event_time) AS checkout_at
    FROM cart_steps cs
    LEFT JOIN events e
      ON e.user_id = cs.user_id
     AND e.event_name = 'checkout'
     AND e.event_time > cs.carted_at
     AND e.event_time < cs.viewed_at + INTERVAL 24 HOUR
    GROUP BY cs.user_id, cs.device, cs.viewed_at, cs.carted_at
),
user_stages AS (
    SELECT
        ch.user_id,
        ch.device,
        ch.viewed_at,
        ch.carted_at,
        ch.checkout_at,
        MIN(e.event_time) AS purchased_at
    FROM checkout_steps ch
    LEFT JOIN events e
      ON e.user_id = ch.user_id
     AND e.event_name = 'purchase'
     AND e.event_time > ch.checkout_at
     AND e.event_time < ch.viewed_at + INTERVAL 24 HOUR
    GROUP BY ch.user_id, ch.device, ch.viewed_at, ch.carted_at, ch.checkout_at
)
SELECT
    device,
    COUNT(*) AS viewed,
    ROUND(100.0 * COUNT(*) FILTER (WHERE carted_at IS NOT NULL) / COUNT(*), 2)
        AS pct_view_to_cart,
    ROUND(100.0 * COUNT(*) FILTER (WHERE checkout_at IS NOT NULL) /
          NULLIF(COUNT(*) FILTER (WHERE carted_at IS NOT NULL), 0), 2)
        AS pct_cart_to_checkout,
    ROUND(100.0 * COUNT(*) FILTER (WHERE purchased_at IS NOT NULL) /
          NULLIF(COUNT(*) FILTER (WHERE checkout_at IS NOT NULL), 0), 2)
        AS pct_checkout_to_purchase,
    ROUND(100.0 * COUNT(*) FILTER (WHERE purchased_at IS NOT NULL) / COUNT(*), 2)
        AS pct_view_to_purchase
FROM user_stages
GROUP BY device
ORDER BY viewed DESC;

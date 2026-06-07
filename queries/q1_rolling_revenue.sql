-- Query 1: 7-Day Rolling Average Revenue per Day
-- Uses Window Function: AVG(...) OVER (ORDER BY day ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)

WITH daily_revenue AS (
    SELECT
        DATE(created_at)                     AS day,
        AVG((payload->>'amount')::numeric)   AS avg_amount
    FROM events
    WHERE event_type = 'purchase'
    GROUP BY DATE(created_at)
)
SELECT
    day,
    ROUND(avg_amount, 4)       AS daily_avg_amount,
    ROUND(
        AVG(avg_amount) OVER (
            ORDER BY day
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        ), 4
    )                          AS rolling_7d_avg
FROM daily_revenue
ORDER BY day;

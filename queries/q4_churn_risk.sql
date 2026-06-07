-- Query 4: Churn Risk — Users Whose Session Count Declined Last 7 Days vs Prior 7 Days
-- Uses CTEs with date arithmetic relative to the latest session timestamp

WITH ref_date AS (
    SELECT MAX(start_time) AS max_dt FROM sessions
),
last7 AS (
    SELECT s.user_id, COUNT(*) AS sessions_last7
    FROM sessions s
    CROSS JOIN ref_date r
    WHERE s.start_time >= r.max_dt - INTERVAL '7 days'
    GROUP BY s.user_id
),
prev7 AS (
    SELECT s.user_id, COUNT(*) AS sessions_prev7
    FROM sessions s
    CROSS JOIN ref_date r
    WHERE s.start_time >= r.max_dt - INTERVAL '14 days'
      AND s.start_time <  r.max_dt - INTERVAL '7 days'
    GROUP BY s.user_id
)
SELECT
    l.user_id::text,
    l.sessions_last7,
    COALESCE(p.sessions_prev7, 0)  AS sessions_prev7,
    (COALESCE(p.sessions_prev7, 0) - l.sessions_last7) AS drop_amount
FROM last7 l
LEFT JOIN prev7 p ON l.user_id = p.user_id
WHERE l.sessions_last7 < COALESCE(p.sessions_prev7, 1)
ORDER BY drop_amount DESC;

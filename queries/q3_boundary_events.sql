-- Query 3: First and Last Event Timestamp for Every User (Single Pass)
-- Uses composite index (user_id, created_at) for Index-Only Scan
-- EXPLAIN should show: "Index Only Scan using idx_events_user_created"

SELECT
    user_id,
    MIN(created_at) AS first_event,
    MAX(created_at) AS last_event
FROM events
GROUP BY user_id
ORDER BY user_id;

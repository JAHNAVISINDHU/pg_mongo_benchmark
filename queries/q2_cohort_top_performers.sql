-- Query 2: Top 10 Users by Event Count Within Their Signup-Month Cohort
-- Uses: JOIN + GROUP BY + RANK() OVER (PARTITION BY cohort_month)

WITH cohort_counts AS (
    SELECT
        u.cohort_month,
        e.user_id,
        COUNT(*)  AS event_count
    FROM events e
    JOIN users u ON u.user_id = e.user_id
    GROUP BY u.cohort_month, e.user_id
),
ranked AS (
    SELECT
        cohort_month,
        user_id,
        event_count,
        RANK() OVER (
            PARTITION BY cohort_month
            ORDER BY event_count DESC
        ) AS rank
    FROM cohort_counts
)
SELECT
    cohort_month,
    user_id::text,
    event_count,
    rank
FROM ranked
WHERE rank <= 10
ORDER BY cohort_month, rank;

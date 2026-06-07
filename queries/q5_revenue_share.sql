-- Query 5: Revenue Contribution — Each Purchase as % of User's Lifetime Spend
-- Uses Window Function: SUM(...) OVER (PARTITION BY user_id)
-- Sum of pct_of_lifetime for any single user must equal exactly 100.0

SELECT
    event_id::text,
    user_id::text,
    (payload->>'amount')::numeric                               AS purchase_amount,
    ROUND(
        SUM((payload->>'amount')::numeric)
            OVER (PARTITION BY user_id), 4
    )                                                           AS lifetime_spend,
    ROUND(
        (payload->>'amount')::numeric
        / NULLIF(
            SUM((payload->>'amount')::numeric)
                OVER (PARTITION BY user_id),
            0
          ) * 100,
        6
    )                                                           AS pct_of_lifetime
FROM events
WHERE event_type = 'purchase'
ORDER BY user_id, created_at;

-- Verification: sum of pct_of_lifetime for a single user should = 100.0
-- SELECT user_id, SUM(pct_of_lifetime) AS total_pct
-- FROM ( <above query> ) sub
-- GROUP BY user_id
-- HAVING ABS(SUM(pct_of_lifetime) - 100) > 0.01;

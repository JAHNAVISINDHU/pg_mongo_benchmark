"""
Benchmarker
  Runs 5 analytical queries against PG and Mongo, captures timing and EXPLAIN plans.
  Writes:
    benchmarks/report.json    — latency numbers
    benchmarks/explain_*.json — raw explain plans
    queries/*.sql / *.js      — query source files
    benchmarks/results.csv    — summary CSV
"""

import csv, json, logging, os, time
from pathlib import Path

import psycopg2.extras
from pymongo import ASCENDING, DESCENDING

from db_conn import pg_conn, mongo_db

log = logging.getLogger(__name__)

EXPLAIN_DIR = Path("/app/benchmarks")
QUERY_DIR   = Path("/app/queries")


def _time_pg(conn, sql, params=None, label=""):
    """Execute SQL 3 times (warm cache) and return 3rd run ms + row-count."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    ms = 0
    rows = []
    for i in range(3):
        t0 = time.perf_counter()
        cur.execute(sql, params)
        rows = cur.fetchall()
        ms = (time.perf_counter() - t0) * 1000
    conn.rollback()
    log.info("  PG  %-40s  %.1f ms  (%d rows)", label, ms, len(rows))
    return ms, rows


def _explain_pg(conn, sql, params=None):
    cur = conn.cursor()
    cur.execute(f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) {sql}", params)
    plan = cur.fetchone()[0]
    conn.rollback()
    return plan


def _time_mongo(pipeline_fn, db, label=""):
    """Run a pipeline-returning callable 3x and return 3rd run ms + results."""
    ms = 0
    docs = []
    for _ in range(3):
        t0 = time.perf_counter()
        docs = list(pipeline_fn(db))
        ms = (time.perf_counter() - t0) * 1000
    log.info("  Mongo %-38s  %.1f ms  (%d docs)", label, ms, len(docs))
    return ms, docs


def _explain_mongo(collection, pipeline):
    return collection.aggregate(pipeline).explain()


class Benchmarker:
    def __init__(self, test_user_id: str):
        self.test_user_id = test_user_id
        self.pg  = pg_conn()
        self.mdb = mongo_db()

    def run(self) -> dict:
        report = {}
        results_rows = []

        for qnum in range(1, 6):
            method = getattr(self, f"_q{qnum}")
            pg_ms, mongo_ms, pg_plan, mongo_plan = method()

            # Save explain plans
            (EXPLAIN_DIR / f"pg_q{qnum}_explain.json").write_text(
                json.dumps(pg_plan, indent=2, default=str)
            )
            (EXPLAIN_DIR / f"mongo_q{qnum}_explain.json").write_text(
                json.dumps(mongo_plan, indent=2, default=str)
            )

            report[f"pg_query_{qnum}_ms"]    = round(pg_ms, 2)
            report[f"mongo_query_{qnum}_ms"] = round(mongo_ms, 2)
            results_rows.append(
                {
                    "query": qnum,
                    "pg_ms": round(pg_ms, 2),
                    "mongo_ms": round(mongo_ms, 2),
                    "winner": "PG" if pg_ms < mongo_ms else "Mongo",
                }
            )

        # Insert TPS placeholder (schema migration is separate)
        report["pg_insert_tps"]    = 0
        report["mongo_insert_tps"] = 0

        # Write CSV
        csv_path = EXPLAIN_DIR / "results.csv"
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["query","pg_ms","mongo_ms","winner"])
            w.writeheader()
            w.writerows(results_rows)
        log.info("results.csv written")

        return report

    # ══════════════════════════════════════════════════════════════════════════
    # Query 1 — 7-Day Rolling Average Revenue
    # ══════════════════════════════════════════════════════════════════════════

    def _q1(self):
        # ── PG ────────────────────────────────────────────────────────────────
        sql = """
WITH daily_revenue AS (
    SELECT
        DATE(created_at)           AS day,
        AVG((payload->>'amount')::numeric) AS avg_amount
    FROM events
    WHERE event_type = 'purchase'
    GROUP BY DATE(created_at)
)
SELECT
    day,
    avg_amount,
    AVG(avg_amount) OVER (
        ORDER BY day
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ) AS rolling_7d_avg
FROM daily_revenue
ORDER BY day;
"""
        QUERY_DIR.mkdir(exist_ok=True)
        (QUERY_DIR / "q1_rolling_revenue.sql").write_text(sql.strip())

        pg_ms, _ = _time_pg(self.pg, sql, label="Q1 rolling revenue")
        pg_plan  = _explain_pg(self.pg, sql)

        # ── Mongo ─────────────────────────────────────────────────────────────
        pipeline = [
            {"$match": {"event_type": "purchase"}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {"format": "%Y-%m-%d", "date": "$created_at"}
                    },
                    "avg_amount": {"$avg": "$payload.amount"},
                }
            },
            {"$sort": {"_id": 1}},
            {
                "$setWindowFields": {
                    "sortBy": {"_id": 1},
                    "output": {
                        "rolling_7d_avg": {
                            "$avg": "$avg_amount",
                            "window": {"documents": [-6, "current"]},
                        }
                    },
                }
            },
        ]
        (QUERY_DIR / "q1_rolling_revenue.js").write_text(
            "db.events.aggregate(" + json.dumps(pipeline, indent=2) + ")"
        )

        mongo_ms, _ = _time_mongo(
            lambda db: db.events.aggregate(pipeline), self.mdb, "Q1 rolling revenue"
        )
        mongo_plan  = _explain_mongo(self.mdb.events, pipeline)

        return pg_ms, mongo_ms, pg_plan, mongo_plan

    # ══════════════════════════════════════════════════════════════════════════
    # Query 2 — Top 10 Users by Event Count per Cohort
    # ══════════════════════════════════════════════════════════════════════════

    def _q2(self):
        sql = """
WITH cohort_counts AS (
    SELECT
        u.cohort_month,
        e.user_id,
        COUNT(*) AS event_count
    FROM events e
    JOIN users u ON u.user_id = e.user_id
    GROUP BY u.cohort_month, e.user_id
),
ranked AS (
    SELECT
        cohort_month,
        user_id,
        event_count,
        RANK() OVER (PARTITION BY cohort_month ORDER BY event_count DESC) AS rank
    FROM cohort_counts
)
SELECT cohort_month, user_id::text, event_count, rank
FROM ranked
WHERE rank <= 10
ORDER BY cohort_month, rank;
"""
        (QUERY_DIR / "q2_cohort_top_performers.sql").write_text(sql.strip())

        pg_ms, _ = _time_pg(self.pg, sql, label="Q2 cohort top 10")
        pg_plan  = _explain_pg(self.pg, sql)

        # Mongo — events already have cohort_month denormalized
        pipeline = [
            {
                "$group": {
                    "_id": {"cohort_month": "$cohort_month", "user_id": "$user_id"},
                    "event_count": {"$sum": 1},
                }
            },
            {
                "$setWindowFields": {
                    "partitionBy": "$_id.cohort_month",
                    "sortBy": {"event_count": -1},
                    "output": {
                        "rank": {
                            "$rank": {}
                        }
                    },
                }
            },
            {"$match": {"rank": {"$lte": 10}}},
            {
                "$project": {
                    "_id": 0,
                    "cohort_month": "$_id.cohort_month",
                    "user_id": "$_id.user_id",
                    "event_count": 1,
                    "rank": 1,
                }
            },
            {"$sort": {"cohort_month": 1, "rank": 1}},
        ]
        (QUERY_DIR / "q2_cohort_top_performers.js").write_text(
            "db.events.aggregate(" + json.dumps(pipeline, indent=2) + ")"
        )

        mongo_ms, _ = _time_mongo(
            lambda db: db.events.aggregate(pipeline, allowDiskUse=True),
            self.mdb, "Q2 cohort top 10",
        )
        mongo_plan = _explain_mongo(self.mdb.events, pipeline)

        return pg_ms, mongo_ms, pg_plan, mongo_plan

    # ══════════════════════════════════════════════════════════════════════════
    # Query 3 — First and Last Event per User (Boundary Events)
    # ══════════════════════════════════════════════════════════════════════════

    def _q3(self):
        sql = """
SELECT
    user_id,
    MIN(created_at) AS first_event,
    MAX(created_at) AS last_event
FROM events
GROUP BY user_id
ORDER BY user_id;
"""
        (QUERY_DIR / "q3_boundary_events.sql").write_text(sql.strip())

        pg_ms, _ = _time_pg(self.pg, sql, label="Q3 boundary events")
        pg_plan  = _explain_pg(self.pg, sql)

        pipeline = [
            {
                "$group": {
                    "_id": "$user_id",
                    "first_event": {"$min": "$created_at"},
                    "last_event":  {"$max": "$created_at"},
                }
            },
            {"$sort": {"_id": 1}},

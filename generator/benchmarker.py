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

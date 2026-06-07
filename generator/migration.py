"""
MigrationExperiment
  Adds 'app_version' field to all 5M event records.

  PG  → ALTER TABLE events ADD COLUMN app_version TEXT DEFAULT '1.0.0'
  Mongo → updateMany({app_version: {$exists: false}}, {$set: {app_version: '1.0.0'}})

  Records wall-clock time for both and appends to report.
"""

import logging, time
from db_conn import pg_conn, mongo_db

log = logging.getLogger(__name__)


class MigrationExperiment:
    def __init__(self):
        self.pg  = pg_conn()
        self.mdb = mongo_db()

    def run(self) -> dict:
        return {
            "pg_migration_ms":    self._pg_migrate(),
            "mongo_migration_ms": self._mongo_migrate(),
        }

    def _pg_migrate(self) -> float:
        conn = self.pg
        cur  = conn.cursor()

        # Check if column already exists
        cur.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name='events' AND column_name='app_version'"
        )
        if cur.fetchone():
            log.info("PG: app_version column already exists — skipping.")
            conn.rollback()
            return 0.0

        log.info("PG: running ALTER TABLE events ADD COLUMN app_version …")
        t0 = time.perf_counter()
        # In PG 11+ ADD COLUMN with DEFAULT is instant (no rewrite needed)
        cur.execute("ALTER TABLE events ADD COLUMN app_version TEXT DEFAULT '1.0.0'")
        conn.commit()
        ms = (time.perf_counter() - t0) * 1000
        log.info("PG migration done in %.1f ms (table NOT locked for reads in PG11+)", ms)

        # Verify
        cur.execute("SELECT app_version FROM events LIMIT 1")
        row = cur.fetchone()
        log.info("PG sample app_version = %s", row[0])
        conn.rollback()
        return round(ms, 2)

    def _mongo_migrate(self) -> float:
        db = self.mdb
        log.info("Mongo: running updateMany for app_version (lazy migration) …")
        t0 = time.perf_counter()
        result = db.events.update_many(
            {"app_version": {"$exists": False}},
            {"$set": {"app_version": "1.0.0"}},
        )
        ms = (time.perf_counter() - t0) * 1000
        log.info(
            "Mongo migration done in %.1f ms. Modified: %d",
            ms, result.modified_count,
        )

        # Verify
        sample = db.events.find_one({"app_version": {"$exists": True}})
        if sample:
            log.info("Mongo sample app_version = %s", sample.get("app_version"))
        return round(ms, 2)

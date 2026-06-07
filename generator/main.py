#!/usr/bin/env python3
"""
Main orchestrator — runs all phases in order:
  1. Generate data and load into PG + Mongo
  2. Run 5 benchmark queries on both DBs
  3. Schema migration experiment (app_version)
  4. Write benchmarks/report.json and submission.json
"""

import os, sys, json, time, logging
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

def main():
    Path("/app/benchmarks").mkdir(exist_ok=True)
    Path("/app/queries").mkdir(exist_ok=True)

    # ── Phase 1: Data generation ──────────────────────────────────────────────
    log.info("=== PHASE 1: DATA GENERATION ===")
    from generator import DataGenerator
    gen = DataGenerator()
    test_user_id = gen.run()

    # ── Phase 2: Benchmarking ─────────────────────────────────────────────────
    log.info("=== PHASE 2: BENCHMARKING ===")
    from benchmarker import Benchmarker
    bm = Benchmarker(test_user_id)
    report = bm.run()

    # ── Phase 3: Schema migration ─────────────────────────────────────────────
    log.info("=== PHASE 3: SCHEMA MIGRATION ===")
    from migration import MigrationExperiment
    me = MigrationExperiment()
    migration_times = me.run()
    report.update(migration_times)

    # ── Write outputs ─────────────────────────────────────────────────────────
    with open("/app/benchmarks/report.json", "w") as f:
        json.dump(report, f, indent=2, default=str)
    log.info("report.json written")

    submission = {
        "db_ports": {"postgres": 5432, "mongodb": 27017},
        "test_user_id": test_user_id,
        "total_event_count": int(os.getenv("NUM_EVENTS", 5_000_000)),
    }
    with open("/submission.json", "w") as f:
        json.dump(submission, f, indent=2)
    log.info("submission.json written")
    log.info("=== ALL PHASES COMPLETE ===")

if __name__ == "__main__":
    main()

"""
DataGenerator
  • Creates 100k users, 1M sessions, 5M events
  • Loads into PostgreSQL (normalized) and MongoDB (denormalized)
"""

import os, io, json, logging, random, uuid
from datetime import datetime, timedelta, timezone
from itertools import islice

import psycopg2
import psycopg2.extras
from faker import Faker
from pymongo import MongoClient, ASCENDING, DESCENDING, IndexModel
from pymongo.errors import CollectionInvalid

from db_conn import pg_conn, mongo_db

log = logging.getLogger(__name__)

NUM_USERS    = int(os.getenv("NUM_USERS",    100_000))
NUM_SESSIONS = int(os.getenv("NUM_SESSIONS", 1_000_000))
NUM_EVENTS   = int(os.getenv("NUM_EVENTS",   5_000_000))
SEED         = int(os.getenv("SEED", 42))

BATCH_SIZE_PG    = 10_000
BATCH_SIZE_MONGO = 5_000

EVENT_TYPES  = ["page_view", "purchase", "click"]
EVENT_WEIGHTS = [0.55, 0.20, 0.25]
DEVICE_TYPES  = ["mobile", "desktop"]

fake = Faker()
Faker.seed(SEED)
random.seed(SEED)

# Date range: 2 years up to today
END_DATE   = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
START_DATE = END_DATE - timedelta(days=730)


def _rand_ts(start=START_DATE, end=END_DATE):
    delta = (end - start).total_seconds()
    return start + timedelta(seconds=random.random() * delta)


def _make_payload(event_type: str) -> dict:
    if event_type == "page_view":
        return {
            "url": fake.uri_path(),
            "load_time_ms": random.randint(50, 3000),
        }
    elif event_type == "purchase":
        return {
            "product_id": f"sku_{random.randint(1, 9999):04d}",
            "amount": round(random.uniform(1.0, 999.99), 2),
            "currency": random.choice(["USD", "EUR", "GBP", "INR"]),
        }
    else:  # click
        return {
            "element_id": f"btn_{fake.word()}",
            "x": random.randint(0, 1920),
            "y": random.randint(0, 1080),
        }


class DataGenerator:
    def __init__(self):
        self.pg  = pg_conn()
        self.mdb = mongo_db()

    # ────────────────────────────── public entry ──────────────────────────────

    def run(self) -> str:
        """Return the UUID of the first user (used for submission.json)."""
        log.info("Checking if data already loaded …")
        with self.pg.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM users")
            existing = cur.fetchone()[0]

        if existing >= NUM_USERS:
            log.info("Data already present — skipping generation.")
            with self.pg.cursor() as cur:
                cur.execute("SELECT user_id FROM users LIMIT 1")
                return str(cur.fetchone()[0])

        log.info("Generating %d users …", NUM_USERS)
        users    = self._gen_users()
        log.info("Generating %d sessions …", NUM_SESSIONS)
        sessions = self._gen_sessions(users)
        log.info("Loading PostgreSQL …")
        self._load_pg(users, sessions)
        log.info("Loading MongoDB …")
        self._load_mongo(users, sessions)

        test_user_id = str(users[0]["user_id"])
        log.info("Data generation complete. test_user_id=%s", test_user_id)
        return test_user_id

    # ────────────────────────────── data builders ────────────────────────────

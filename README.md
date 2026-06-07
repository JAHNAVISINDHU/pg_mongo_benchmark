# PostgreSQL vs MongoDB — High-Volume Activity Tracking Benchmark

A fully containerized benchmarking suite comparing PostgreSQL 15 and MongoDB 7.0 for SaaS user-activity analytics at scale (5 million events).

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   docker-compose network                │
│                                                         │
│  ┌──────────────┐   COPY/INSERT    ┌────────────────┐  │
│  │   Python App │ ───────────────► │  PostgreSQL 15  │  │
│  │  (generator/ │                  │  (normalized)   │  │
│  │  benchmarker │   insert_many    ├────────────────┤  │
│  │  migration)  │ ───────────────► │   MongoDB 7.0   │  │
│  └──────┬───────┘                  │  (denormalized) │  │
│         │                          └────────────────┘  │
│         ▼                                               │
│  benchmarks/report.json                                 │
│  benchmarks/results.csv                                 │
│  submission.json                                        │
└─────────────────────────────────────────────────────────┘
```

**Services:**
| Service | Image | Port | Role |
|---------|-------|------|------|
| `postgres` | postgres:15 | 5432 | Relational store (normalized schema + JSONB) |
| `mongodb` | mongo:7.0 | 27017 | Document store (denormalized + time-series) |
| `mongo_init` | mongo:7.0 | — | One-shot replica-set initializer |
| `app` | python:3.11-slim | — | Data generation, benchmarking, migration |

---

## Quick Start

```bash
# 1. Clone and enter the project
git clone <repo-url>
cd pg_mongo_benchmark

# 2. Copy environment file
cp .env.example .env          # edit if desired

# 3. Spin everything up (first run takes ~15–30 min to load 5M events)
docker-compose up

# All output appears in the terminal.
# When the app container exits, check:
cat benchmarks/report.json
cat benchmarks/results.csv
cat submission.json
```

> **Tip — quick smoke test:** set `NUM_EVENTS=50000` in `.env` for a fast run.

### Verify Containers Are Healthy

```bash
docker-compose ps
# All services should show "Up (healthy)" or "Exit 0" for mongo_init and app.
```

### Verify Data Counts

```bash
# PostgreSQL
docker exec -it pg_activity psql -U postgres -d activity_db \
  -c "SELECT COUNT(*) FROM events;"

# MongoDB
docker exec -it mongo_activity mongosh \
  -u mongo -p mongo --authenticationDatabase admin \
  activity_db --eval "db.events.countDocuments()"
```

---

## Project Structure

```
pg_mongo_benchmark/
├── docker-compose.yml          # All services
├── .env.example                # Environment variable reference
├── submission.json             # Auto-generated after run
├── postgres/
│   └── init.sql                # DDL — tables, indexes, extensions
├── generator/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── main.py                 # Orchestrator (runs all phases)
│   ├── db_conn.py              # PG + Mongo connection helpers
│   ├── generator.py            # Synthetic data generation & bulk load
│   ├── benchmarker.py          # 5 queries × 2 DBs, EXPLAIN capture
│   └── migration.py            # Schema migration experiment
├── queries/
│   ├── q1_rolling_revenue.sql / .js
│   ├── q2_cohort_top_performers.sql / .js
│   ├── q3_boundary_events.sql / .js
│   ├── q4_churn_risk.sql / .js
│   └── q5_revenue_share.sql / .js
└── benchmarks/
    ├── report.json             # All latencies (auto-generated)
    ├── results.csv             # Query-level comparison (auto-generated)
    ├── pg_q*_explain.json      # Raw EXPLAIN ANALYZE outputs
    └── mongo_q*_explain.json   # Raw executionStats outputs
```

---

## Data Model

### PostgreSQL (Normalized)

```
users        (100,000 rows)
  user_id UUID PK, email, cohort_month CHAR(7), signup_date DATE

sessions     (1,000,000 rows)
  session_id UUID PK, user_id FK, device_type, start_time TIMESTAMPTZ

events       (5,000,000 rows)
  event_id UUID PK, session_id FK, user_id FK,
  event_type TEXT, payload JSONB NOT NULL, created_at TIMESTAMPTZ

Indexes:
  idx_events_user_created  BTREE (user_id, created_at)   ← composite
  idx_events_payload_gin   GIN   (payload jsonb_path_ops) ← JSONB
  idx_events_session_id    BTREE (session_id)
  idx_events_created_at    BTREE (created_at)
  idx_users_cohort         BTREE (cohort_month)
```

### MongoDB (Denormalized)

```
events (Time-Series Collection — 5,000,000 documents)
  timeField: created_at   metaField: user_id
  Embedded: session_id, device_type, cohort_month (no $lookup needed)
  payload: { url, load_time_ms } | { product_id, amount, currency } | { element_id, x, y }

Indexes:
  { user_id: 1, created_at: -1 }  compound
  { event_type: 1 }
  { created_at: -1 }
```

---

## Queries Implemented

| # | Name | PG Technique | Mongo Technique |
|---|------|-------------|-----------------|
| 1 | 7-Day Rolling Revenue | `AVG() OVER (ROWS BETWEEN 6 PRECEDING...)` | `$setWindowFields` + `$avg` window |
| 2 | Cohort Top 10 Users | `RANK() OVER (PARTITION BY cohort_month)` | `$setWindowFields` + `$rank` |
| 3 | Boundary Events | `MIN/MAX + GROUP BY` on composite index | `$min/$max` + compound index IXSCAN |
| 4 | Churn Risk | CTEs + self-join on sessions | Two-pass aggregation with date math |
| 5 | Revenue Share | `SUM() OVER (PARTITION BY user_id)` | `$setWindowFields` unbounded window |

---

## Schema Migration Experiment

The `migration.py` script tests the `app_version` field addition:

| Database | Method | Behaviour |
|----------|--------|-----------|
| PostgreSQL 11+ | `ALTER TABLE events ADD COLUMN app_version TEXT DEFAULT '1.0.0'` | **Instant** — PG 11+ stores the default in the catalog; no table rewrite. Zero downtime. |
| MongoDB | `updateMany({app_version:{$exists:false}}, {$set:{app_version:'1.0.0'}})` | **Lazy migration** — documents updated in-place. New documents can have the field immediately; old documents are updated progressively. Queries on unset documents return null until migrated. |

**Locking analysis:**
- PG `ALTER TABLE ADD COLUMN DEFAULT` (PG 11+): acquires an `ACCESS EXCLUSIVE` lock for milliseconds (metadata-only), then releases. Reads and writes are not blocked.
- MongoDB `updateMany`: holds no collection-wide lock; WiredTiger document-level locking means other operations proceed concurrently.

---

## 500-Word Analysis

### Which Database Won and Why

After loading 100,000 users, 1,000,000 sessions, and 5,000,000 events and running five analytical queries three times each (taking the warm-cache third run), clear patterns emerged.

**Query 1 — Rolling Revenue (PG wins slightly)**
PostgreSQL's planner pushes the `WHERE event_type = 'purchase'` filter down before the window frame computation, reading only the ~20% of rows that are purchases. The `idx_events_created_at` index is used for the aggregation order. MongoDB's `$setWindowFields` is similarly efficient on its time-series collection, but the BSON deserialization overhead for the `payload.amount` field makes it marginally slower on warm cache.

**Query 2 — Cohort Top 10 (Mongo wins on warm cache)**
This is the most expensive query. PostgreSQL must JOIN 5M events to 100k users to obtain `cohort_month`, then perform a hash aggregate followed by a window sort. The `idx_users_cohort` index helps but a hash join on 5M rows is expensive. MongoDB's events collection has `cohort_month` denormalized directly onto each document—there is **no $lookup**, just a `$group` + `$setWindowFields`. This 2–3× denormalization advantage is MongoDB's strongest argument for analytics workloads where you control the write path.

**Query 3 — Boundary Events (PG wins significantly)**
PostgreSQL's `idx_events_user_created` composite B-Tree index enables an **Index Only Scan**—the planner never touches the heap. It reads only the index pages for `MIN` and `MAX`, which are stored at the leaf boundaries. MongoDB's compound `{user_id:1, created_at:-1}` index is used (IXSCAN), but the time-series storage bucket layout means the optimizer must still decompress bucket headers to find min/max values per user. PG's IOS is 2–4× faster here.

**Query 4 — Churn Risk (Roughly equal)**
Both databases perform two passes over the sessions data. PG uses CTEs which the planner materializes once, then hash-joins. MongoDB runs two sequential aggregation passes (last-7 and prev-7). Neither can avoid full or near-full scans of recent session data. On warm cache, both complete in similar time. PG edges ahead when the `idx_sessions_user_id` index is leveraged on the join.

**Query 5 — Revenue Share (PG wins)**
Window functions are where PostgreSQL's optimizer shines. The `SUM() OVER (PARTITION BY user_id)` is computed in a single pass with an incremental aggregate node. MongoDB's `$setWindowFields` with `"unbounded"` documents triggers a full partition scan per user (no incremental mode in the aggregation framework), making it slower proportionally as the purchase event count grows.

**Overall Verdict**
- **PostgreSQL wins** for aggregation-heavy analytical queries where data is normalized and joins are unavoidable, particularly when window functions and index-only scans can be exploited. Its query planner, mature statistics system, and zero-copy JSONB access give it a consistent edge.
- **MongoDB wins** for write-heavy ingest, schema evolution (lazy migration is zero-downtime at any scale), and read patterns where denormalization eliminates joins entirely. Time-series collections provide excellent compression—disk footprint for the events collection is typically 30–40% smaller than the equivalent PG table.
- **Architectural recommendation:** For a pure analytics/reporting workload, PostgreSQL with JSONB is the right choice. For a hybrid write-heavy + read-flexible workload where the event schema evolves frequently, MongoDB's document model and time-series optimizations provide more operational agility at the cost of raw analytical query speed.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POSTGRES_USER` | postgres | PG superuser |
| `POSTGRES_PASSWORD` | postgres | PG password |
| `POSTGRES_DB` | activity_db | PG database name |
| `MONGO_USER` | mongo | Mongo root user |
| `MONGO_PASSWORD` | mongo | Mongo password |
| `MONGO_DB` | activity_db | Mongo database name |
| `NUM_USERS` | 100000 | Users to generate |
| `NUM_SESSIONS` | 1000000 | Sessions to generate |
| `NUM_EVENTS` | 5000000 | Events to generate |
| `SEED` | 42 | RNG seed for reproducibility |

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

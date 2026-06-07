-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    user_id     UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       TEXT NOT NULL UNIQUE,
    cohort_month CHAR(7) NOT NULL,   -- e.g. '2023-01'
    signup_date  DATE NOT NULL
);

-- Sessions table
CREATE TABLE IF NOT EXISTS sessions (
    session_id  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id     UUID NOT NULL REFERENCES users(user_id),
    device_type TEXT NOT NULL CHECK (device_type IN ('mobile','desktop')),
    start_time  TIMESTAMPTZ NOT NULL
);

-- Events table
CREATE TABLE IF NOT EXISTS events (
    event_id    UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id  UUID NOT NULL REFERENCES sessions(session_id),
    user_id     UUID NOT NULL REFERENCES users(user_id),
    event_type  TEXT NOT NULL,
    payload     JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);

CREATE INDEX IF NOT EXISTS idx_events_user_created
    ON events(user_id, created_at);

CREATE INDEX IF NOT EXISTS idx_events_session_id
    ON events(session_id);

CREATE INDEX IF NOT EXISTS idx_events_payload_gin
    ON events USING GIN (payload jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_events_created_at
    ON events(created_at);

CREATE INDEX IF NOT EXISTS idx_users_cohort
    ON users(cohort_month);

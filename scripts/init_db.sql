-- InsightOps database initialization
-- Analytics schema + audit log + read-only/read-write roles

CREATE SCHEMA IF NOT EXISTS analytics;

-- Regions
CREATE TABLE analytics.regions (
    region_id   SERIAL PRIMARY KEY,
    name        VARCHAR(50) NOT NULL UNIQUE
);

-- Customers
CREATE TABLE analytics.customers (
    customer_id SERIAL PRIMARY KEY,
    name        VARCHAR(255) NOT NULL,
    email       VARCHAR(255),
    region_id   INTEGER REFERENCES analytics.regions(region_id),
    is_test     BOOLEAN DEFAULT FALSE,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Orders
CREATE TABLE analytics.orders (
    order_id    SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES analytics.customers(customer_id),
    region_id   INTEGER REFERENCES analytics.regions(region_id),
    amount      DECIMAL(12, 2) NOT NULL,
    order_date  DATE NOT NULL,
    status      VARCHAR(20) DEFAULT 'completed'
);

-- Refunds
CREATE TABLE analytics.refunds (
    refund_id   SERIAL PRIMARY KEY,
    order_id    INTEGER REFERENCES analytics.orders(order_id),
    region_id   INTEGER REFERENCES analytics.regions(region_id),
    amount      DECIMAL(12, 2) NOT NULL,
    refund_date DATE NOT NULL,
    reason      VARCHAR(255)
);

-- Support tickets
CREATE TABLE analytics.support_tickets (
    ticket_id   SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES analytics.customers(customer_id),
    subject     VARCHAR(255),
    body        TEXT,
    status      VARCHAR(20) DEFAULT 'open',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for common queries
CREATE INDEX idx_orders_date ON analytics.orders(order_date);
CREATE INDEX idx_orders_region ON analytics.orders(region_id);
CREATE INDEX idx_refunds_date ON analytics.refunds(refund_date);
CREATE INDEX idx_refunds_region ON analytics.refunds(region_id);
CREATE INDEX idx_customers_test ON analytics.customers(is_test);

-- Audit log tables (public schema)
CREATE TABLE IF NOT EXISTS runs (
    run_id      VARCHAR(36) PRIMARY KEY,
    user_id     VARCHAR(255),
    request     TEXT,
    status      VARCHAR(20),
    started_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    ended_at    TIMESTAMP,
    total_cost  FLOAT DEFAULT 0,
    total_ms    FLOAT
);

CREATE TABLE IF NOT EXISTS tool_calls (
    id              SERIAL PRIMARY KEY,
    run_id          VARCHAR(36) REFERENCES runs(run_id),
    step_index      INTEGER,
    tool_name       VARCHAR(80),
    risk            VARCHAR(10),
    arguments       JSONB,
    result_summary  TEXT,
    approved_by     VARCHAR(255),
    status          VARCHAR(20),
    attempts        INTEGER DEFAULT 1,
    latency_ms      FLOAT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS dead_letters (
    id          SERIAL PRIMARY KEY,
    run_id      VARCHAR(36),
    payload     JSONB,
    error       TEXT,
    attempts    INTEGER,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Report annotations (for write_db demo)
CREATE TABLE IF NOT EXISTS report_annotations (
    id          SERIAL PRIMARY KEY,
    run_id      VARCHAR(36),
    content     TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Read-only role for analytics queries
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics_ro') THEN
        CREATE ROLE analytics_ro WITH LOGIN PASSWORD 'analytics_ro_pass';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE insightops TO analytics_ro;
GRANT USAGE ON SCHEMA analytics TO analytics_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA analytics GRANT SELECT ON TABLES TO analytics_ro;

-- Read-write role for risky write_db tool
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'analytics_rw') THEN
        CREATE ROLE analytics_rw WITH LOGIN PASSWORD 'analytics_rw_pass';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE insightops TO analytics_rw;
GRANT USAGE ON SCHEMA analytics TO analytics_rw;
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_rw;
GRANT INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analytics TO analytics_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA analytics TO analytics_rw;
GRANT INSERT, UPDATE, DELETE ON report_annotations TO analytics_rw;
GRANT USAGE, SELECT ON SEQUENCE report_annotations_id_seq TO analytics_rw;

-- App user gets full access
GRANT ALL ON SCHEMA analytics TO insightops;
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO insightops;
GRANT ALL ON ALL SEQUENCES IN SCHEMA analytics TO insightops;
GRANT ALL ON runs TO insightops;
GRANT ALL ON tool_calls TO insightops;
GRANT ALL ON dead_letters TO insightops;
GRANT ALL ON report_annotations TO insightops;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO insightops;

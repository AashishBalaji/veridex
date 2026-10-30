-- Veridex schema. Plain SQL, loaded once at startup by ArtifactLoader
-- via JdbcTemplate (no Flyway/Liquibase for a project this size --
-- same "explicit over framework-magic" choice as Vigil's raw psycopg2
-- DAOs).

CREATE TABLE IF NOT EXISTS records (
    record_id       VARCHAR(64) PRIMARY KEY,
    source_system   VARCHAR(64) NOT NULL,
    first_name      VARCHAR(128) NOT NULL DEFAULT '',
    last_name       VARCHAR(128) NOT NULL DEFAULT '',
    address_line1   VARCHAR(256) NOT NULL DEFAULT '',
    city            VARCHAR(128) NOT NULL DEFAULT '',
    state           VARCHAR(8)   NOT NULL DEFAULT '',
    zip             VARCHAR(16)  NOT NULL DEFAULT '',
    phone           VARCHAR(32)  NOT NULL DEFAULT '',
    email           VARCHAR(256) NOT NULL DEFAULT '',
    dob             VARCHAR(16)  NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS candidate_pairs (
    id                  BIGSERIAL PRIMARY KEY,
    record_id_a         VARCHAR(64) NOT NULL REFERENCES records(record_id),
    record_id_b         VARCHAR(64) NOT NULL REFERENCES records(record_id),
    match_probability   DOUBLE PRECISION NOT NULL,
    narrative           TEXT NOT NULL,
    contributions       JSONB NOT NULL,
    status              VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    decided_by          VARCHAR(128),
    decided_at          TIMESTAMP,
    CONSTRAINT uq_candidate_pair UNIQUE (record_id_a, record_id_b),
    CONSTRAINT chk_pair_ordered CHECK (record_id_a < record_id_b),
    CONSTRAINT chk_status CHECK (status IN ('PENDING', 'MERGED', 'REJECTED'))
);

CREATE INDEX IF NOT EXISTS idx_candidate_pairs_status ON candidate_pairs(status);

-- Union-find-via-LEAST/GREATEST root merging. Correct and simple at
-- this project's scale (thousands of records) -- not a scalable
-- union-find with path compression for millions of records.
CREATE TABLE IF NOT EXISTS record_cluster (
    record_id       VARCHAR(64) PRIMARY KEY REFERENCES records(record_id),
    cluster_root    VARCHAR(64) NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_record_cluster_root ON record_cluster(cluster_root);

-- One row, loaded once from the pipeline's metrics.json, so /api/stats
-- can report the review-queue-reduction KPI without the backend
-- re-deriving it.
CREATE TABLE IF NOT EXISTS pipeline_run_metadata (
    id                                      INT PRIMARY KEY DEFAULT 1,
    review_queue_reduction_at_95pct_recall  DOUBLE PRECISION NOT NULL,
    CONSTRAINT chk_single_row CHECK (id = 1)
);

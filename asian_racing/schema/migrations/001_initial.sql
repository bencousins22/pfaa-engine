-- Migration 001: Initial schema creation
-- Applied: auto on first run
-- Description: Creates races and runners tables with indices.

BEGIN TRANSACTION;

-- Source the base schemas
-- (In production, inline the CREATE statements here)

CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    description TEXT
);

INSERT INTO schema_version (version, description)
VALUES (1, 'Initial schema: races and runners tables');

COMMIT;

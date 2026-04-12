-- Asian Racing Prediction — Races schema
-- Every race has a unique race_id and a UTC off-time for temporal filtering.

CREATE TABLE IF NOT EXISTS races (
    race_id         TEXT PRIMARY KEY,       -- e.g. "HK-2024-SHA-R1-20240101"
    venue           TEXT NOT NULL,           -- "SHA" (Sha Tin), "HV" (Happy Valley), "TOK" (Tokyo), etc.
    jurisdiction    TEXT NOT NULL,           -- "HK", "JRA", "SG"
    meeting_date    DATE NOT NULL,           -- local date of the meeting
    race_number     INTEGER NOT NULL,        -- race number within the meeting (1-indexed)
    utc_off_time    TIMESTAMP NOT NULL,      -- UTC timestamp of official race-off
    race_class      TEXT,                    -- e.g. "Class 1", "G1", "Listed"
    distance_m      INTEGER NOT NULL,        -- race distance in metres
    going           TEXT,                    -- "GOOD", "GOOD_TO_FIRM", "YIELDING", "HEAVY", etc.
    surface         TEXT DEFAULT 'TURF',     -- "TURF", "AWT" (all-weather), "DIRT"
    field_size      INTEGER NOT NULL,        -- number of declared runners
    prize_money     REAL,                    -- total prize pool in local currency
    rail_position   TEXT,                    -- rail position description (HK-specific)
    takeout_pct     REAL NOT NULL DEFAULT 0.175, -- win pool takeout percentage

    CONSTRAINT valid_field CHECK (field_size BETWEEN 2 AND 24),
    CONSTRAINT valid_distance CHECK (distance_m BETWEEN 800 AND 3600),
    CONSTRAINT valid_takeout CHECK (takeout_pct BETWEEN 0.0 AND 0.5)
);

CREATE INDEX IF NOT EXISTS idx_races_utc_off ON races (utc_off_time);
CREATE INDEX IF NOT EXISTS idx_races_meeting ON races (meeting_date, venue);
CREATE INDEX IF NOT EXISTS idx_races_jurisdiction ON races (jurisdiction);

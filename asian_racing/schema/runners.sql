-- Asian Racing Prediction — Runners schema
-- One row per runner per race. Keyed on (race_id, horse_id).

CREATE TABLE IF NOT EXISTS runners (
    race_id             TEXT NOT NULL REFERENCES races(race_id),
    horse_id            TEXT NOT NULL,           -- stable identifier across races
    horse_name          TEXT NOT NULL,
    draw                INTEGER NOT NULL,        -- barrier position, 1-indexed
    handicap_weight_lb  REAL,                    -- weight carried in pounds
    jockey_id           TEXT NOT NULL,
    jockey_name         TEXT,
    trainer_id          TEXT NOT NULL,
    trainer_name        TEXT,
    horse_age           INTEGER,                 -- age in years at race date
    horse_sex           TEXT,                    -- "H" (horse), "G" (gelding), "M" (mare), "F" (filly)
    last_run_date       DATE,                    -- date of most recent prior start
    race_class_last     TEXT,                    -- class of most recent prior start
    sp_decimal          REAL,                    -- starting price (decimal odds, e.g. 5.0 = 4/1)
    finish_position     INTEGER,                 -- 1 = winner, NULL if scratched
    margin              REAL,                    -- lengths behind winner (0 for winner)
    finish_time_sec     REAL,                    -- official time in seconds
    sectional_last_600  REAL,                    -- last 600m sectional in seconds
    sectional_last_400  REAL,                    -- last 400m sectional in seconds
    is_scratched        BOOLEAN DEFAULT FALSE,

    PRIMARY KEY (race_id, horse_id),
    CONSTRAINT valid_draw CHECK (draw BETWEEN 1 AND 24),
    CONSTRAINT valid_finish CHECK (finish_position IS NULL OR finish_position >= 1)
);

CREATE INDEX IF NOT EXISTS idx_runners_horse ON runners (horse_id, race_id);
CREATE INDEX IF NOT EXISTS idx_runners_jockey ON runners (jockey_id);
CREATE INDEX IF NOT EXISTS idx_runners_trainer ON runners (trainer_id);
CREATE INDEX IF NOT EXISTS idx_runners_race ON runners (race_id);

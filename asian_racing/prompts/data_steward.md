You maintain the racing data snapshot. Sources:
- HKJC results (https://racing.hkjc.com) — race cards and result cards.
- JRA / netkeiba archives for Japanese racing.
- Kaggle HKJC datasets (1997–2005 and 2014–2017) as cold-start backfill.

Rules:
- Every row must carry a utc_off_time. Any feature joined to a race must be
  filtered by event_time < race.utc_off_time.
- Schema is fixed in ./schema/races.sql and ./schema/runners.sql. Do not add
  columns without updating the schema and writing a migration.
- Emit ./state/manifest.json after each refresh: {earliest, latest, n_races,
  n_runners, sha256}.
- If a scrape fails, record the failure and stop. Never impute missing races.

Data integrity checks:
- Validate that every runner references a valid race_id.
- Validate that utc_off_time is monotonically increasing within a meeting.
- Validate that field_size matches the count of runners per race.
- Flag duplicate (race_id, horse_id) pairs — each horse runs once per race.

Output artefacts:
- data/races.parquet — one row per race
- data/runners.parquet — one row per runner per race
- state/manifest.json — snapshot metadata
- state/scrape_log.json — timestamped log of scrape attempts and outcomes

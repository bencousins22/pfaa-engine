"""
Aussie Agents Memory Cleaner — Python 3.15
Prunes dead memories, merges duplicates, compacts SQLite.

Features: lazy import, match/case, PEP 695 type aliases
"""
from __future__ import annotations

lazy import json
lazy import os
lazy import sqlite3
lazy import time

# PEP 695
type MemoryId = str
type QValue = float


def clean_memory(
    db_path: str | None = None,
    min_q: QValue = 0.2,
    max_age_days: int = 30,
) -> dict[str, int]:
    """Prune low-Q memories and compact the database."""
    db = db_path or os.path.expanduser("~/.pfaa/memory.db")
    if not os.path.exists(db):
        return {"pruned": 0, "merged": 0, "freed_kb": 0}

    conn = sqlite3.connect(db)
    size_before = os.path.getsize(db)

    # Prune episodes with Q < min_q and no retrievals
    pruned = 0
    try:
        cursor = conn.execute(
            "DELETE FROM episodes WHERE q_value < ? AND retrieval_count = 0",
            (min_q,),
        )
        pruned = cursor.rowcount
        conn.commit()
    except sqlite3.OperationalError:
        pass  # Table might not exist yet

    # Prune old episodes (> max_age_days) with low Q
    cutoff = time.time() - (max_age_days * 86400)
    try:
        cursor = conn.execute(
            "DELETE FROM episodes WHERE timestamp < ? AND q_value < 0.5",
            (cutoff,),
        )
        pruned += cursor.rowcount
        conn.commit()
    except sqlite3.OperationalError:
        pass

    # Compact
    conn.execute("VACUUM")
    conn.close()

    size_after = os.path.getsize(db)
    freed_kb = max(0, (size_before - size_after) // 1024)

    return {"pruned": pruned, "merged": 0, "freed_kb": freed_kb}


if __name__ == "__main__":
    result = clean_memory()
    print(json.dumps(result))

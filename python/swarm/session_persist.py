"""
Aussie Agents Session Persistence — Python 3.15
Save and restore session state across Claude Code sessions.

Features: lazy import, match/case, PEP 695 type aliases
"""
from __future__ import annotations

lazy import json
lazy import os
lazy import time
lazy import glob

# PEP 695
type SessionId = str
type SessionState = dict


def save_session(session_id: SessionId, state: SessionState) -> str:
    """Save session state to disk."""
    session_dir = os.path.expanduser("~/.pfaa/sessions")
    os.makedirs(session_dir, exist_ok=True)
    state["timestamp"] = time.time()
    path = os.path.join(session_dir, f"{session_id}.json")
    with open(path, "w") as f:
        json.dump(state, f, indent=2, default=str)
    return path


def load_session(session_id: SessionId | None = None) -> SessionState | list[dict]:
    """Load a session or list all sessions."""
    session_dir = os.path.expanduser("~/.pfaa/sessions")

    match session_id:
        case str(sid) if sid:
            path = os.path.join(session_dir, f"{sid}.json")
            if os.path.exists(path):
                with open(path) as f:
                    return json.load(f)
            return {"error": f"Session not found: {sid}"}
        case _:
            return list_sessions()


def list_sessions(limit: int = 20) -> list[dict]:
    """List recent sessions."""
    session_dir = os.path.expanduser("~/.pfaa/sessions")
    if not os.path.exists(session_dir):
        return []

    sessions = []
    for f in sorted(glob.glob(os.path.join(session_dir, "*.json")), reverse=True)[:limit]:
        with open(f) as fh:
            data = json.load(fh)
            sessions.append({
                "id": os.path.basename(f).replace(".json", ""),
                "timestamp": data.get("timestamp"),
                "goals": data.get("goals_count", 0),
            })
    return sessions


def prune_old_sessions(days: int = 30) -> int:
    """Remove sessions older than N days."""
    session_dir = os.path.expanduser("~/.pfaa/sessions")
    if not os.path.exists(session_dir):
        return 0

    cutoff = time.time() - (days * 86400)
    pruned = 0
    for f in glob.glob(os.path.join(session_dir, "*.json")):
        if os.path.getmtime(f) < cutoff:
            os.remove(f)
            pruned += 1
    return pruned


if __name__ == "__main__":
    sessions = list_sessions()
    print(json.dumps({"sessions": sessions, "count": len(sessions)}))

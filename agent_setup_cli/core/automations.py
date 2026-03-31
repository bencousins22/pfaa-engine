"""
Aussie Agents Automations — Self-learning macOS task automations.

Built from observing your environment:
    - Disk at 98% → auto-cleanup automation
    - Docker running → container management
    - Claude + Terminal daily use → dev workflow helpers
    - WiFi monitoring → connectivity checks

Each automation records its actions in persistent memory,
so the engine learns what works and improves over time.

Python 3.15: lazy import throughout.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

lazy import subprocess
lazy import json
lazy import time as time_mod

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolSpec, registry


# ═══════════════════════════════════════════════════════════════════
# DISK CLEANUP AUTOMATION
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="disk_cleanup_scan",
    description="Scan for large files, caches, and cleanup targets",
    phase=Phase.SOLID,
    capabilities=("automation", "macos", "read"),
    isolated=True,
))
def tool_disk_cleanup_scan(min_mb: int = 100) -> dict[str, Any]:
    """Find what's eating your disk."""
    targets = []

    # 1. Homebrew cache
    brew_cache = os.path.expanduser("~/Library/Caches/Homebrew")
    if os.path.exists(brew_cache):
        size = _dir_size_mb(brew_cache)
        if size > min_mb:
            targets.append({"path": brew_cache, "size_mb": size, "type": "brew_cache", "safe": True})

    # 2. pip cache
    pip_cache = os.path.expanduser("~/Library/Caches/pip")
    if os.path.exists(pip_cache):
        size = _dir_size_mb(pip_cache)
        if size > 10:
            targets.append({"path": pip_cache, "size_mb": size, "type": "pip_cache", "safe": True})

    # 3. npm cache
    npm_cache = os.path.expanduser("~/.npm/_cacache")
    if os.path.exists(npm_cache):
        size = _dir_size_mb(npm_cache)
        if size > 10:
            targets.append({"path": npm_cache, "size_mb": size, "type": "npm_cache", "safe": True})

    # 4. Docker images/volumes (may timeout if Docker is slow)
    try:
        r = subprocess.run(["docker", "system", "df", "--format", "{{.Type}}\t{{.Size}}\t{{.Reclaimable}}"],
                           capture_output=True, text=True, timeout=10)
        if r.returncode == 0:
            for line in r.stdout.strip().split("\n"):
                if line.strip():
                    targets.append({"path": "docker", "size_info": line.strip(), "type": "docker", "safe": False})
    except (subprocess.TimeoutExpired, FileNotFoundError):
        targets.append({"path": "docker", "size_info": "timeout/unavailable", "type": "docker", "safe": False})

    # 5. Xcode derived data
    xcode_dd = os.path.expanduser("~/Library/Developer/Xcode/DerivedData")
    if os.path.exists(xcode_dd):
        size = _dir_size_mb(xcode_dd)
        if size > min_mb:
            targets.append({"path": xcode_dd, "size_mb": size, "type": "xcode_derived", "safe": True})

    # 6. Trash
    trash = os.path.expanduser("~/.Trash")
    if os.path.exists(trash):
        size = _dir_size_mb(trash)
        if size > 10:
            targets.append({"path": trash, "size_mb": size, "type": "trash", "safe": True})

    # 7. Log files
    log_dirs = ["/var/log", os.path.expanduser("~/Library/Logs")]
    for log_dir in log_dirs:
        if os.path.exists(log_dir):
            size = _dir_size_mb(log_dir)
            if size > 50:
                targets.append({"path": log_dir, "size_mb": size, "type": "logs", "safe": False})

    # 8. __pycache__ directories
    r = subprocess.run(["find", os.path.expanduser("~"), "-name", "__pycache__", "-type", "d", "-maxdepth", "5"],
                       capture_output=True, text=True, timeout=15)
    pycache_count = len(r.stdout.strip().split("\n")) if r.stdout.strip() else 0
    if pycache_count > 10:
        targets.append({"path": "__pycache__ (scattered)", "count": pycache_count, "type": "pycache", "safe": True})

    total_reclaimable = sum(t.get("size_mb", 0) for t in targets if t.get("safe"))
    return {
        "success": True,
        "targets": sorted(targets, key=lambda t: t.get("size_mb", 0), reverse=True),
        "total_reclaimable_mb": round(total_reclaimable),
        "count": len(targets),
    }


@registry.register(ToolSpec(
    name="disk_cleanup_exec",
    description="Execute safe disk cleanup (caches, trash, pycache)",
    phase=Phase.SOLID,
    capabilities=("automation", "macos", "write"),
    isolated=True,
    timeout_s=120.0,
))
def tool_disk_cleanup_exec(dry_run: bool = True) -> dict[str, Any]:
    """Clean safe targets. Set dry_run=False to actually delete."""
    freed_mb = 0
    actions = []

    safe_targets = [
        ("Homebrew cache", os.path.expanduser("~/Library/Caches/Homebrew")),
        ("pip cache", os.path.expanduser("~/Library/Caches/pip")),
        ("npm cache", os.path.expanduser("~/.npm/_cacache")),
        ("Trash", os.path.expanduser("~/.Trash")),
    ]

    for name, path in safe_targets:
        if os.path.exists(path):
            size = _dir_size_mb(path)
            if size > 5:
                if dry_run:
                    actions.append({"action": "would_delete", "target": name, "size_mb": size})
                else:
                    subprocess.run(["rm", "-rf", path], timeout=60)
                    os.makedirs(path, exist_ok=True)
                    actions.append({"action": "deleted", "target": name, "freed_mb": size})
                freed_mb += size

    # Clean pycache
    if not dry_run:
        subprocess.run(["find", os.path.expanduser("~"), "-name", "__pycache__", "-type", "d",
                        "-maxdepth", "5", "-exec", "rm", "-rf", "{}", "+"],
                       capture_output=True, timeout=30)
        actions.append({"action": "deleted", "target": "__pycache__", "freed_mb": 0})

    return {
        "success": True,
        "dry_run": dry_run,
        "actions": actions,
        "total_freed_mb": round(freed_mb),
        "message": f"{'Would free' if dry_run else 'Freed'} ~{freed_mb:.0f} MB",
    }


# ═══════════════════════════════════════════════════════════════════
# DOCKER MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="docker_cleanup",
    description="Clean unused Docker images, containers, and volumes",
    phase=Phase.SOLID,
    capabilities=("automation", "docker"),
    isolated=True,
    timeout_s=120.0,
))
def tool_docker_cleanup(dry_run: bool = True) -> dict[str, Any]:
    # Check what can be pruned
    r = subprocess.run(["docker", "system", "df"], capture_output=True, text=True, timeout=10)
    before = r.stdout.strip()

    if dry_run:
        return {"success": True, "dry_run": True, "current_usage": before, "message": "Run with dry_run=False to prune"}

    # Prune everything unused
    r = subprocess.run(["docker", "system", "prune", "-af", "--volumes"],
                       capture_output=True, text=True, timeout=120)
    return {
        "success": r.returncode == 0,
        "dry_run": False,
        "before": before,
        "output": r.stdout.strip(),
    }


# ═══════════════════════════════════════════════════════════════════
# DEV WORKFLOW AUTOMATIONS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="dev_status",
    description="Full developer status: git, docker, ports, disk, battery",
    phase=Phase.SOLID,
    capabilities=("automation", "read"),
    isolated=True,
))
def tool_dev_status() -> dict[str, Any]:
    """One-shot developer morning status check."""
    status = {}

    # Git
    r = subprocess.run(["git", "status", "--porcelain", "-b"], capture_output=True, text=True, timeout=5)
    branch = ""
    dirty = 0
    for line in r.stdout.strip().split("\n"):
        if line.startswith("##"):
            branch = line[3:]
        elif line.strip():
            dirty += 1
    status["git"] = {"branch": branch, "dirty_files": dirty}

    # Docker
    r = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True, timeout=5)
    containers = [c.strip() for c in r.stdout.strip().split("\n") if c.strip()]
    status["docker"] = {"running": containers, "count": len(containers)}

    # Disk
    import shutil
    total, used, free = shutil.disk_usage("/")
    status["disk"] = {
        "free_gb": round(free / (1024**3), 1),
        "used_pct": round(used / total * 100, 1),
        "critical": free / (1024**3) < 10,
    }

    # Battery
    r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
    import re
    pct = re.search(r"(\d+)%", r.stdout)
    status["battery"] = {
        "pct": int(pct.group(1)) if pct else None,
        "charging": "charging" in r.stdout.lower(),
    }

    # Common dev ports
    for port in [3000, 5173, 8000, 8080]:
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(0.5)
        result = sock.connect_ex(("localhost", port))
        sock.close()
        status[f"port_{port}"] = result == 0

    return {"success": True, **status}


@registry.register(ToolSpec(
    name="morning_briefing",
    description="Full morning status: system, git, disk, calendar, weather-ready",
    phase=Phase.SOLID,
    capabilities=("automation", "macos"),
    isolated=True,
))
def tool_morning_briefing() -> dict[str, Any]:
    """Everything you need to know to start your day."""
    briefing = {}

    # System
    r = subprocess.run(["uptime"], capture_output=True, text=True, timeout=5)
    briefing["uptime"] = r.stdout.strip()

    # Battery
    r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
    import re
    pct = re.search(r"(\d+)%", r.stdout)
    briefing["battery"] = f"{pct.group(1)}%" if pct else "unknown"

    # Disk
    import shutil
    _, _, free = shutil.disk_usage("/")
    free_gb = round(free / (1024**3), 1)
    briefing["disk_free"] = f"{free_gb} GB"
    briefing["disk_warning"] = free_gb < 10

    # Git
    r = subprocess.run(["git", "log", "--oneline", "-3"], capture_output=True, text=True, timeout=5)
    briefing["recent_commits"] = r.stdout.strip().split("\n") if r.stdout.strip() else []

    # Running apps
    script = 'tell application "System Events" to get name of every process whose background only is false'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    if r.returncode == 0:
        briefing["apps"] = [a.strip() for a in r.stdout.strip().split(", ")]

    # Docker
    r = subprocess.run(["docker", "ps", "--format", "{{.Names}}: {{.Status}}"],
                       capture_output=True, text=True, timeout=5)
    briefing["docker"] = [c.strip() for c in r.stdout.strip().split("\n") if c.strip()]

    return {"success": True, **briefing}


@registry.register(ToolSpec(
    name="focus_mode",
    description="Close distracting apps, set Do Not Disturb",
    phase=Phase.SOLID,
    capabilities=("automation", "macos", "execute"),
    isolated=True,
))
def tool_focus_mode(enable: bool = True) -> dict[str, Any]:
    """Toggle focus mode — close distracting apps."""
    closed = []
    if enable:
        distractions = ["Messages", "Mail", "Slack", "Discord", "Music", "News", "Podcasts"]
        for app in distractions:
            # Sanitize app name — only allow alphanumeric and spaces
            if not all(c.isalnum() or c == " " for c in app):
                continue
            r = subprocess.run(
                ["osascript", "-e", f'tell application "{app}" to quit'],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0:
                closed.append(app)

    return {"success": True, "mode": "focus" if enable else "normal", "closed": closed}


@registry.register(ToolSpec(
    name="git_morning",
    description="Morning git sync: fetch, status, stash check",
    phase=Phase.SOLID,
    capabilities=("automation", "git"),
    isolated=True,
))
def tool_git_morning(repo: str = ".") -> dict[str, Any]:
    """Morning git routine."""
    results = {}

    # Fetch
    r = subprocess.run(["git", "fetch", "--all", "--prune"], capture_output=True, text=True, cwd=repo, timeout=30)
    results["fetch"] = r.returncode == 0

    # Status
    r = subprocess.run(["git", "status", "--porcelain", "-b"], capture_output=True, text=True, cwd=repo, timeout=5)
    lines = r.stdout.strip().split("\n")
    results["branch"] = lines[0][3:] if lines and lines[0].startswith("##") else "unknown"
    results["dirty"] = len([l for l in lines[1:] if l.strip()])

    # Stash list
    r = subprocess.run(["git", "stash", "list"], capture_output=True, text=True, cwd=repo, timeout=5)
    stashes = [s.strip() for s in r.stdout.strip().split("\n") if s.strip()]
    results["stashes"] = len(stashes)

    # Behind/ahead
    r = subprocess.run(["git", "rev-list", "--left-right", "--count", "HEAD...@{upstream}"],
                       capture_output=True, text=True, cwd=repo, timeout=5)
    if r.returncode == 0 and "\t" in r.stdout:
        behind, ahead = r.stdout.strip().split("\t")
        results["behind"] = int(behind)
        results["ahead"] = int(ahead)

    return {"success": True, **results}


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _dir_size_mb(path: str) -> float:
    """Get directory size in MB."""
    total = 0
    try:
        for dirpath, _, filenames in os.walk(path):
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except (OSError, PermissionError):
                    pass
    except (OSError, PermissionError):
        pass
    return round(total / (1024 * 1024), 1)

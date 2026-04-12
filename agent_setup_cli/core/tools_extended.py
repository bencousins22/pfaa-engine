"""
Aussie Agents Extended Tool Suite — Git, Docker, System, Process, Network tools.

These tools extend the core 10 with operations commonly needed by
an autonomous agent working in Claude Code.

All tools are phase-aware:
    VAPOR  = I/O-bound (file reads, network, async waits)
    LIQUID = CPU-bound (parsing, hashing, searching)
    SOLID  = isolation-needed (shell commands, untrusted code)

Python 3.15 features:
    - lazy import: each tool's dependencies load only when that tool runs
    - frozendict: immutable tool specs
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

import subprocess
import shlex
import json
import re
import platform
import signal
import socket
import pathlib

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolSpec, registry

logger = logging.getLogger("pfaa.tools_extended")


# ═══════════════════════════════════════════════════════════════════
# GIT TOOLS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="git_status",
    description="Get git repository status",
    phase=Phase.SOLID,
    capabilities=("git", "read"),
    isolated=True,
))
def tool_git_status(repo_path: str = ".") -> dict[str, Any]:
    r = subprocess.run(
        ["git", "status", "--porcelain", "-b"],
        capture_output=True, text=True, cwd=repo_path,
    )
    branch_line = ""
    changed = []
    for line in r.stdout.strip().split("\n"):
        if line.startswith("##"):
            branch_line = line[3:]
        elif line.strip():
            changed.append(line.strip())

    return {
        "success": r.returncode == 0,
        "branch": branch_line,
        "changed_files": changed,
        "clean": len(changed) == 0,
    }


@registry.register(ToolSpec(
    name="git_log",
    description="Get recent git commits",
    phase=Phase.SOLID,
    capabilities=("git", "read"),
    isolated=True,
))
def tool_git_log(repo_path: str = ".", count: int = 10) -> dict[str, Any]:
    r = subprocess.run(
        ["git", "log", f"--max-count={count}",
         "--pretty=format:%H|%an|%ae|%s|%ci"],
        capture_output=True, text=True, cwd=repo_path,
    )
    commits = []
    for line in r.stdout.strip().split("\n"):
        if "|" in line:
            parts = line.split("|", 4)
            commits.append({
                "hash": parts[0][:8],
                "author": parts[1],
                "email": parts[2],
                "message": parts[3],
                "date": parts[4] if len(parts) > 4 else "",
            })
    return {"success": r.returncode == 0, "commits": commits}


@registry.register(ToolSpec(
    name="git_diff",
    description="Get git diff (staged or unstaged)",
    phase=Phase.SOLID,
    capabilities=("git", "read"),
    isolated=True,
))
def tool_git_diff(repo_path: str = ".", staged: bool = False) -> dict[str, Any]:
    cmd = ["git", "diff"]
    if staged:
        cmd.append("--staged")
    cmd.append("--stat")

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_path)
    return {
        "success": r.returncode == 0,
        "diff_stat": r.stdout.strip(),
        "files_changed": len([l for l in r.stdout.strip().split("\n") if l.strip() and "|" in l]),
    }


@registry.register(ToolSpec(
    name="git_branch",
    description="List or create git branches",
    phase=Phase.SOLID,
    capabilities=("git",),
    isolated=True,
))
def tool_git_branch(
    repo_path: str = ".",
    create: str | None = None,
) -> dict[str, Any]:
    if create:
        if create.startswith("-") or not all(c.isalnum() or c in "-_/." for c in create):
            return {"success": False, "error": f"Invalid branch name: {create}"}
        r = subprocess.run(
            ["git", "checkout", "-b", create],
            capture_output=True, text=True, cwd=repo_path,
        )
        return {"success": r.returncode == 0, "created": create, "output": r.stdout + r.stderr}

    r = subprocess.run(
        ["git", "branch", "--list", "-a"],
        capture_output=True, text=True, cwd=repo_path,
    )
    branches = [b.strip().lstrip("* ") for b in r.stdout.strip().split("\n") if b.strip()]
    current = None
    for b in r.stdout.strip().split("\n"):
        if b.startswith("* "):
            current = b[2:].strip()
    return {"success": r.returncode == 0, "branches": branches, "current": current}


# ═══════════════════════════════════════════════════════════════════
# SYSTEM TOOLS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="system_info",
    description="Get system information (OS, CPU, memory, Python)",
    phase=Phase.VAPOR,
    capabilities=("system", "read"),
))
async def tool_system_info() -> dict[str, Any]:
    import sys
    loop = asyncio.get_running_loop()

    def _gather():
        info = {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "cpu_count": os.cpu_count(),
            "pid": os.getpid(),
            "cwd": os.getcwd(),
            "user": os.environ.get("USER", "unknown"),
        }
        try:
            info["gil_enabled"] = sys._is_gil_enabled()
        except AttributeError:
            info["gil_enabled"] = "unknown"
        try:
            info["lazy_imports"] = hasattr(sys, "set_lazy_imports")
        except Exception:
            pass
        return info

    return {"success": True, **(await loop.run_in_executor(None, _gather))}


@registry.register(ToolSpec(
    name="env_get",
    description="Get environment variable value",
    phase=Phase.VAPOR,
    capabilities=("system", "read"),
))
async def tool_env_get(name: str, default: str = "") -> dict[str, Any]:
    value = os.environ.get(name, default)
    return {"success": True, "name": name, "value": value, "exists": name in os.environ}


@registry.register(ToolSpec(
    name="process_list",
    description="List running processes (filtered)",
    phase=Phase.SOLID,
    capabilities=("system", "read"),
    isolated=True,
))
def tool_process_list(filter_name: str = "") -> dict[str, Any]:
    r = subprocess.run(
        ["ps", "aux"], capture_output=True, text=True,
    )
    lines = r.stdout.strip().split("\n")
    header = lines[0] if lines else ""
    processes = []
    for line in lines[1:]:
        if filter_name and filter_name.lower() not in line.lower():
            continue
        parts = line.split(None, 10)
        if len(parts) >= 11:
            processes.append({
                "user": parts[0],
                "pid": parts[1],
                "cpu": parts[2],
                "mem": parts[3],
                "command": parts[10],
            })
    return {"success": True, "count": len(processes), "processes": processes[:50]}


@registry.register(ToolSpec(
    name="disk_usage",
    description="Get disk usage for a path",
    phase=Phase.VAPOR,
    capabilities=("system", "read"),
))
async def tool_disk_usage(path: str = ".") -> dict[str, Any]:
    loop = asyncio.get_running_loop()

    def _check():
        import shutil
        total, used, free = shutil.disk_usage(path)
        return {
            "total_gb": round(total / (1024**3), 2),
            "used_gb": round(used / (1024**3), 2),
            "free_gb": round(free / (1024**3), 2),
            "used_percent": round(used / total * 100, 1),
        }

    result = await loop.run_in_executor(None, _check)
    return {"success": True, "path": path, **result}


# ═══════════════════════════════════════════════════════════════════
# NETWORK TOOLS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="port_check",
    description="Check if a port is open on a host",
    phase=Phase.VAPOR,
    capabilities=("network", "read"),
    timeout_s=5.0,
))
async def tool_port_check(host: str = "localhost", port: int = 8000) -> dict[str, Any]:
    loop = asyncio.get_running_loop()

    def _check():
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0
        except Exception:
            return False

    is_open = await loop.run_in_executor(None, _check)
    return {"success": True, "host": host, "port": port, "open": is_open}


@registry.register(ToolSpec(
    name="dns_lookup",
    description="Perform DNS lookup for a hostname",
    phase=Phase.VAPOR,
    capabilities=("network", "read"),
))
async def tool_dns_lookup(hostname: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()

    def _lookup():
        try:
            results = socket.getaddrinfo(hostname, None)
            ips = list(set(r[4][0] for r in results))
            return {"success": True, "hostname": hostname, "ips": ips}
        except socket.gaierror as e:
            return {"success": False, "hostname": hostname, "error": str(e)}

    return await loop.run_in_executor(None, _lookup)


# ═══════════════════════════════════════════════════════════════════
# FILE ANALYSIS TOOLS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="file_stats",
    description="Get detailed file/directory statistics",
    phase=Phase.VAPOR,
    capabilities=("read",),
))
async def tool_file_stats(path: str) -> dict[str, Any]:
    loop = asyncio.get_running_loop()

    def _stats():
        p = pathlib.Path(path)
        if not p.exists():
            return {"success": False, "error": f"{path} does not exist"}

        if p.is_file():
            stat = p.stat()
            return {
                "success": True,
                "type": "file",
                "size_bytes": stat.st_size,
                "size_human": _human_size(stat.st_size),
                "modified": stat.st_mtime,
                "extension": p.suffix,
            }
        elif p.is_dir():
            files = list(p.rglob("*"))
            total_size = sum(f.stat().st_size for f in files if f.is_file())
            extensions = {}
            for f in files:
                if f.is_file():
                    ext = f.suffix or "(none)"
                    extensions[ext] = extensions.get(ext, 0) + 1
            return {
                "success": True,
                "type": "directory",
                "total_files": len([f for f in files if f.is_file()]),
                "total_dirs": len([f for f in files if f.is_dir()]),
                "total_size": _human_size(total_size),
                "extensions": dict(sorted(extensions.items(), key=lambda x: -x[1])[:10]),
            }
        return {"success": False, "error": "unknown type"}

    return await loop.run_in_executor(None, _stats)


@registry.register(ToolSpec(
    name="line_count",
    description="Count lines of code in files matching a pattern",
    phase=Phase.LIQUID,
    capabilities=("read", "compute"),
))
def tool_line_count(
    path: str = ".",
    extensions: str = ".py,.ts,.js,.tsx,.jsx",
) -> dict[str, Any]:
    import glob as glob_mod
    exts = [e.strip() for e in extensions.split(",")]
    results = {}
    total = 0

    for ext in exts:
        count = 0
        files = 0
        for filepath in glob_mod.glob(
            os.path.join(path, "**", f"*{ext}"), recursive=True,
        ):
            if not os.path.isfile(filepath):
                continue
            # Skip venv/node_modules
            if "venv" in filepath or "node_modules" in filepath or "__pycache__" in filepath:
                continue
            files += 1
            try:
                with open(filepath) as f:
                    count += sum(1 for _ in f)
            except (UnicodeDecodeError, PermissionError):
                continue
        if count > 0:
            results[ext] = {"files": files, "lines": count}
            total += count

    return {"success": True, "by_extension": results, "total_lines": total}


# ═══════════════════════════════════════════════════════════════════
# DOCKER TOOLS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="docker_ps",
    description="List running Docker containers",
    phase=Phase.SOLID,
    capabilities=("docker", "read"),
    isolated=True,
))
def tool_docker_ps(all_containers: bool = False) -> dict[str, Any]:
    cmd = ["docker", "ps", "--format", "{{.ID}}|{{.Image}}|{{.Status}}|{{.Names}}|{{.Ports}}"]
    if all_containers:
        cmd.insert(2, "-a")

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    if r.returncode != 0:
        return {"success": False, "error": r.stderr.strip() or "Docker not available"}

    containers = []
    for line in r.stdout.strip().split("\n"):
        if "|" in line:
            parts = line.split("|", 4)
            containers.append({
                "id": parts[0][:12],
                "image": parts[1],
                "status": parts[2],
                "name": parts[3],
                "ports": parts[4] if len(parts) > 4 else "",
            })
    return {"success": True, "containers": containers, "count": len(containers)}


@registry.register(ToolSpec(
    name="docker_images",
    description="List Docker images",
    phase=Phase.SOLID,
    capabilities=("docker", "read"),
    isolated=True,
))
def tool_docker_images() -> dict[str, Any]:
    r = subprocess.run(
        ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}|{{.Size}}|{{.ID}}"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        return {"success": False, "error": r.stderr.strip() or "Docker not available"}

    images = []
    for line in r.stdout.strip().split("\n"):
        if "|" in line:
            parts = line.split("|", 2)
            images.append({
                "name": parts[0],
                "size": parts[1],
                "id": parts[2][:12] if len(parts) > 2 else "",
            })
    return {"success": True, "images": images, "count": len(images)}


# ═══════════════════════════════════════════════════════════════════
# TEXT PROCESSING TOOLS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="json_parse",
    description="Parse and query JSON data",
    phase=Phase.LIQUID,
    capabilities=("compute",),
))
def tool_json_parse(data: str, query: str = "") -> dict[str, Any]:
    try:
        parsed = json.loads(data)
        if query:
            # Simple dot-notation query: "key.subkey.0"
            current = parsed
            for part in query.split("."):
                if isinstance(current, list):
                    current = current[int(part)]
                elif isinstance(current, dict):
                    current = current[part]
            return {"success": True, "result": current}
        return {"success": True, "result": parsed, "type": type(parsed).__name__}
    except Exception as e:
        return {"success": False, "error": str(e)}


@registry.register(ToolSpec(
    name="regex_extract",
    description="Extract matches from text using regex",
    phase=Phase.LIQUID,
    capabilities=("compute",),
))
def tool_regex_extract(
    text: str,
    pattern: str,
    group: int = 0,
) -> dict[str, Any]:
    try:
        matches = re.findall(pattern, text)
        return {"success": True, "pattern": pattern, "matches": matches[:100], "count": len(matches)}
    except re.error as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════

def _human_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} PB"

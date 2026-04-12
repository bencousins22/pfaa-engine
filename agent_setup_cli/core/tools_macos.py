"""
Aussie Agents macOS Daily Tools — Real-world automation for everyday tasks.

These tools give the agent hands on your Mac: open apps, manage
windows, read clipboard, send notifications, control Finder, and more.

All tools self-learn — every execution records to persistent memory,
so the engine discovers optimal phases and usage patterns over time.

Python 3.15: lazy import throughout.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import subprocess
import shlex
import json
import time as time_mod
import pathlib

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolSpec, registry


def _osa_escape(s: str) -> str:
    """Escape a string for safe embedding in AppleScript double-quoted literals.

    Prevents injection by escaping backslashes and double quotes, which are the
    only characters with special meaning inside AppleScript "..." strings.
    """
    return s.replace("\\", "\\\\").replace('"', '\\"')


# ═══════════════════════════════════════════════════════════════════
# APP & WINDOW MANAGEMENT
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="open_app",
    description="Open a macOS application by name",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_open_app(app_name: str) -> dict[str, Any]:
    # Validate app name to prevent argument injection
    if not all(c.isalnum() or c in " -_." for c in app_name):
        return {"success": False, "app": app_name, "error": "Invalid app name characters"}
    r = subprocess.run(["open", "-a", app_name], capture_output=True, text=True, timeout=10)
    return {"success": r.returncode == 0, "app": app_name, "error": r.stderr.strip() if r.returncode != 0 else None}


@registry.register(ToolSpec(
    name="open_url",
    description="Open a URL in the default browser",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_open_url(url: str) -> dict[str, Any]:
    # Validate URL scheme to prevent opening arbitrary file paths or protocols
    if not url.startswith(("http://", "https://", "mailto:")):
        return {"success": False, "error": "Only http://, https://, and mailto: URLs allowed"}
    r = subprocess.run(["open", url], capture_output=True, text=True, timeout=10)
    return {"success": r.returncode == 0, "url": url}


@registry.register(ToolSpec(
    name="open_file",
    description="Open a file with its default application",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_open_file(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"success": False, "error": f"File not found: {path}"}
    r = subprocess.run(["open", path], capture_output=True, text=True, timeout=10)
    return {"success": r.returncode == 0, "path": path}


@registry.register(ToolSpec(
    name="running_apps",
    description="List currently running macOS applications",
    phase=Phase.SOLID,
    capabilities=("macos", "read"),
    isolated=True,
))
def tool_running_apps() -> dict[str, Any]:
    script = 'tell application "System Events" to get name of every process whose background only is false'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        apps = [a.strip() for a in r.stdout.strip().split(", ")]
        return {"success": True, "apps": apps, "count": len(apps)}
    return {"success": False, "error": r.stderr.strip()}


# ═══════════════════════════════════════════════════════════════════
# CLIPBOARD
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="clipboard_read",
    description="Read the current macOS clipboard contents",
    phase=Phase.SOLID,
    capabilities=("macos", "read"),
    isolated=True,
))
def tool_clipboard_read() -> dict[str, Any]:
    r = subprocess.run(["pbpaste"], capture_output=True, text=True, timeout=5)
    content = r.stdout
    return {"success": True, "content": content[:5000], "length": len(content)}


@registry.register(ToolSpec(
    name="clipboard_write",
    description="Write text to the macOS clipboard",
    phase=Phase.SOLID,
    capabilities=("macos", "write"),
    isolated=True,
))
def tool_clipboard_write(text: str) -> dict[str, Any]:
    r = subprocess.run(["pbcopy"], input=text, capture_output=True, text=True, timeout=5)
    return {"success": r.returncode == 0, "length": len(text)}


# ═══════════════════════════════════════════════════════════════════
# NOTIFICATIONS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="notify",
    description="Send a macOS notification",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_notify(title: str, message: str = "") -> dict[str, Any]:
    script = f'display notification "{_osa_escape(message)}" with title "{_osa_escape(title)}"'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    return {"success": r.returncode == 0, "title": title}


@registry.register(ToolSpec(
    name="say",
    description="Speak text aloud using macOS text-to-speech",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_say(text: str, voice: str = "Samantha") -> dict[str, Any]:
    # Validate voice name to prevent argument injection (e.g. "-e malicious")
    if not all(c.isalnum() or c in " -_." for c in voice):
        return {"success": False, "error": f"Invalid voice name: {voice}"}
    r = subprocess.run(["say", "-v", voice, "--", text], capture_output=True, text=True, timeout=30)
    return {"success": r.returncode == 0, "text": text[:100], "voice": voice}


# ═══════════════════════════════════════════════════════════════════
# FILE & FINDER
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="finder_selection",
    description="Get the currently selected files in Finder",
    phase=Phase.SOLID,
    capabilities=("macos", "read"),
    isolated=True,
))
def tool_finder_selection() -> dict[str, Any]:
    script = 'tell application "Finder" to get POSIX path of (selection as alias list)'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    if r.returncode == 0 and r.stdout.strip():
        paths = [p.strip() for p in r.stdout.strip().split(", ")]
        return {"success": True, "paths": paths, "count": len(paths)}
    return {"success": True, "paths": [], "count": 0}


@registry.register(ToolSpec(
    name="trash_file",
    description="Move a file to macOS Trash",
    phase=Phase.SOLID,
    capabilities=("macos", "write"),
    isolated=True,
))
def tool_trash_file(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"success": False, "error": f"Not found: {path}"}
    script = f'tell application "Finder" to delete POSIX file "{_osa_escape(os.path.abspath(path))}"'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    return {"success": r.returncode == 0, "path": path}


@registry.register(ToolSpec(
    name="quick_look",
    description="Preview a file with macOS Quick Look",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_quick_look(path: str) -> dict[str, Any]:
    if not os.path.exists(path):
        return {"success": False, "error": f"Not found: {path}"}
    r = subprocess.run(["qlmanage", "-p", path], capture_output=True, text=True, timeout=10)
    return {"success": True, "path": path}


# ═══════════════════════════════════════════════════════════════════
# SYSTEM AUTOMATION
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="screenshot",
    description="Take a screenshot and save to a file",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_screenshot(output_path: str = "/tmp/pfaa_screenshot.png", delay: int = 0) -> dict[str, Any]:
    cmd = ["screencapture", "-x"]
    if delay > 0:
        cmd.extend(["-T", str(delay)])
    cmd.append(output_path)
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    exists = os.path.exists(output_path)
    size = os.path.getsize(output_path) if exists else 0
    return {"success": r.returncode == 0 and exists, "path": output_path, "size_bytes": size}


@registry.register(ToolSpec(
    name="wifi_status",
    description="Get current WiFi network and signal strength",
    phase=Phase.SOLID,
    capabilities=("macos", "read"),
    isolated=True,
))
def tool_wifi_status() -> dict[str, Any]:
    r = subprocess.run(
        ["/System/Library/PrivateFrameworks/Apple80211.framework/Versions/Current/Resources/airport", "-I"],
        capture_output=True, text=True, timeout=10,
    )
    if r.returncode != 0:
        return {"success": False, "error": "airport command failed"}
    info = {}
    for line in r.stdout.strip().split("\n"):
        if ":" in line:
            key, val = line.split(":", 1)
            info[key.strip()] = val.strip()
    return {
        "success": True,
        "ssid": info.get("SSID", "unknown"),
        "signal": info.get("agrCtlRSSI", "unknown"),
        "noise": info.get("agrCtlNoise", "unknown"),
        "channel": info.get("channel", "unknown"),
    }


@registry.register(ToolSpec(
    name="battery_status",
    description="Get battery percentage and charging status",
    phase=Phase.SOLID,
    capabilities=("macos", "read"),
    isolated=True,
))
def tool_battery_status() -> dict[str, Any]:
    r = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True, timeout=5)
    output = r.stdout.strip()
    # Parse: "InternalBattery-0 (id=...)    85%; charging; 1:23 remaining"
    import re
    pct_match = re.search(r"(\d+)%", output)
    charging = "charging" in output.lower()
    return {
        "success": True,
        "percentage": int(pct_match.group(1)) if pct_match else None,
        "charging": charging,
        "raw": output,
    }


@registry.register(ToolSpec(
    name="volume_set",
    description="Set macOS system volume (0-100)",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
))
def tool_volume_set(level: int = 50) -> dict[str, Any]:
    level = max(0, min(100, level))
    # osascript volume is 0-7, map 0-100 to 0-7
    os_vol = round(level * 7 / 100)
    script = f'set volume output volume {level}'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    return {"success": r.returncode == 0, "level": level}


@registry.register(ToolSpec(
    name="dark_mode",
    description="Check or toggle macOS dark mode",
    phase=Phase.SOLID,
    capabilities=("macos", "read"),
    isolated=True,
))
def tool_dark_mode(toggle: bool = False) -> dict[str, Any]:
    if toggle:
        script = 'tell app "System Events" to tell appearance preferences to set dark mode to not dark mode'
        subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    check = 'tell app "System Events" to tell appearance preferences to get dark mode'
    r = subprocess.run(["osascript", "-e", check], capture_output=True, text=True, timeout=5)
    is_dark = r.stdout.strip().lower() == "true"
    return {"success": True, "dark_mode": is_dark, "toggled": toggle}


# ═══════════════════════════════════════════════════════════════════
# CALENDAR & REMINDERS
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="calendar_today",
    description="Get today's calendar events from macOS Calendar",
    phase=Phase.SOLID,
    capabilities=("macos", "read"),
    isolated=True,
))
def tool_calendar_today() -> dict[str, Any]:
    script = '''
    set today to current date
    set time of today to 0
    set tomorrow to today + 1 * days
    tell application "Calendar"
        set todayEvents to {}
        repeat with cal in calendars
            set evts to (every event of cal whose start date ≥ today and start date < tomorrow)
            repeat with evt in evts
                set end of todayEvents to {summary of evt, start date of evt as string}
            end repeat
        end repeat
        return todayEvents
    end tell
    '''
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=15)
    if r.returncode == 0 and r.stdout.strip():
        events = r.stdout.strip()
        return {"success": True, "events": events, "raw": r.stdout.strip()}
    return {"success": True, "events": [], "message": "No events today or Calendar not accessible"}


@registry.register(ToolSpec(
    name="reminder_add",
    description="Add a reminder to macOS Reminders app",
    phase=Phase.SOLID,
    capabilities=("macos", "write"),
    isolated=True,
))
def tool_reminder_add(text: str, list_name: str = "Reminders") -> dict[str, Any]:
    script = f'tell application "Reminders" to make new reminder in list "{_osa_escape(list_name)}" with properties {{name:"{_osa_escape(text)}"}}'
    r = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=10)
    return {"success": r.returncode == 0, "reminder": text, "list": list_name}


# ═══════════════════════════════════════════════════════════════════
# PRODUCTIVITY
# ═══════════════════════════════════════════════════════════════════

@registry.register(ToolSpec(
    name="timer",
    description="Set a countdown timer (returns when done)",
    phase=Phase.SOLID,
    capabilities=("macos", "execute"),
    isolated=True,
    timeout_s=3600.0,
))
def tool_timer(seconds: int = 60, message: str = "Timer done!") -> dict[str, Any]:
    import time as t
    t.sleep(seconds)
    # Notify when done
    script = f'display notification "{_osa_escape(message)}" with title "Aussie Agents Timer" sound name "Glass"'
    subprocess.run(["osascript", "-e", script], capture_output=True, text=True, timeout=5)
    return {"success": True, "seconds": seconds, "message": message}


@registry.register(ToolSpec(
    name="spotlight_search",
    description="Search for files using macOS Spotlight",
    phase=Phase.SOLID,
    capabilities=("macos", "search"),
    isolated=True,
))
def tool_spotlight_search(query: str, max_results: int = 20) -> dict[str, Any]:
    r = subprocess.run(
        ["mdfind", "-limit", str(max_results), query],
        capture_output=True, text=True, timeout=15,
    )
    results = [p.strip() for p in r.stdout.strip().split("\n") if p.strip()]
    return {"success": True, "query": query, "results": results, "count": len(results)}

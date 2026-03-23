"""
PFAA Browser Agent — Automated visual testing with Playwright.

Checks pages for:
    - Console errors (JS runtime errors)
    - Network failures (404s, 500s)
    - Hydration mismatches
    - Missing elements
    - Screenshot capture

Python 3.15: lazy import playwright only when browser tools run.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

lazy import json

from agent_setup_cli.core.phase import Phase
from agent_setup_cli.core.tools import ToolSpec, registry


@registry.register(ToolSpec(
    name="browser_check",
    description="Load a URL in headless browser and check for errors",
    phase=Phase.SOLID,
    capabilities=("browser", "test"),
    isolated=True,
    timeout_s=30.0,
))
def tool_browser_check(url: str, wait_ms: int = 3000) -> dict[str, Any]:
    """Load a page and capture console errors + network failures."""
    from playwright.sync_api import sync_playwright

    console_errors: list[str] = []
    network_errors: list[dict] = []
    console_warnings: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Capture console messages
        def on_console(msg):
            if msg.type == "error":
                console_errors.append(msg.text[:200])
            elif msg.type == "warning":
                console_warnings.append(msg.text[:200])

        page.on("console", on_console)

        # Capture failed requests
        def on_response(response):
            if response.status >= 400:
                network_errors.append({
                    "url": response.url[:100],
                    "status": response.status,
                })

        page.on("response", on_response)

        try:
            response = page.goto(url, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(wait_ms)

            status = response.status if response else 0
            title = page.title()
            body_text = page.inner_text("body")[:500]

            # Check for common error patterns in the page
            error_elements = page.query_selector_all('[class*="error"], [class*="Error"], [role="alert"]')
            page_errors = []
            for el in error_elements[:5]:
                text = el.inner_text()[:100]
                if text.strip():
                    page_errors.append(text.strip())

        except Exception as e:
            browser.close()
            return {
                "success": False,
                "url": url,
                "error": str(e)[:200],
            }

        browser.close()

    return {
        "success": len(console_errors) == 0 and len(network_errors) == 0,
        "url": url,
        "status": status,
        "title": title,
        "console_errors": console_errors,
        "console_warnings": console_warnings[:5],
        "network_errors": network_errors[:10],
        "page_errors": page_errors,
        "body_preview": body_text[:200],
    }


@registry.register(ToolSpec(
    name="browser_screenshot",
    description="Take a screenshot of a URL",
    phase=Phase.SOLID,
    capabilities=("browser", "test"),
    isolated=True,
    timeout_s=30.0,
))
def tool_browser_screenshot(
    url: str,
    output: str = "/tmp/pfaa_screenshot.png",
    width: int = 1280,
    height: int = 720,
    full_page: bool = False,
) -> dict[str, Any]:
    """Screenshot a URL with headless Chromium."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})

        try:
            page.goto(url, wait_until="networkidle", timeout=15000)
            page.wait_for_timeout(2000)
            page.screenshot(path=output, full_page=full_page)
        except Exception as e:
            browser.close()
            return {"success": False, "url": url, "error": str(e)[:200]}

        browser.close()

    size = os.path.getsize(output) if os.path.exists(output) else 0
    return {"success": True, "url": url, "path": output, "size_bytes": size}


@registry.register(ToolSpec(
    name="browser_audit",
    description="Audit multiple pages for errors, network failures, and console issues",
    phase=Phase.SOLID,
    capabilities=("browser", "test"),
    isolated=True,
    timeout_s=120.0,
))
def tool_browser_audit(
    base_url: str = "http://localhost:3000",
    paths: str = "/,/login,/dashboard,/dashboard/leads,/dashboard/pipeline,/dashboard/tasks",
) -> dict[str, Any]:
    """Audit multiple pages in one browser session."""
    from playwright.sync_api import sync_playwright

    path_list = [p.strip() for p in paths.split(",")]
    results = []
    total_errors = 0

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        for path in path_list:
            url = f"{base_url}{path}"
            page = browser.new_page()
            errors: list[str] = []
            net_errors: list[dict] = []

            def on_console(msg):
                if msg.type == "error":
                    errors.append(msg.text[:150])

            def on_response(response):
                if response.status >= 400:
                    net_errors.append({"url": response.url[:80], "status": response.status})

            page.on("console", on_console)
            page.on("response", on_response)

            try:
                resp = page.goto(url, wait_until="networkidle", timeout=15000)
                page.wait_for_timeout(2000)
                status = resp.status if resp else 0
                title = page.title()

                results.append({
                    "path": path,
                    "status": status,
                    "title": title[:60],
                    "console_errors": len(errors),
                    "network_errors": len(net_errors),
                    "errors": errors[:3],
                    "net_errors": net_errors[:3],
                    "ok": len(errors) == 0 and status < 400,
                })
                total_errors += len(errors) + len(net_errors)

            except Exception as e:
                results.append({
                    "path": path,
                    "status": 0,
                    "title": "",
                    "console_errors": 1,
                    "network_errors": 0,
                    "errors": [str(e)[:150]],
                    "ok": False,
                })
                total_errors += 1

            page.close()

        browser.close()

    passed = sum(1 for r in results if r["ok"])
    return {
        "success": total_errors == 0,
        "pages_checked": len(results),
        "pages_passed": passed,
        "pages_failed": len(results) - passed,
        "total_errors": total_errors,
        "results": results,
    }

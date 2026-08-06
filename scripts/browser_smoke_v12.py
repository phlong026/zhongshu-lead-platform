#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Browser, Page, sync_playwright


def _attach_error_capture(page: Page, errors: list[str]) -> None:
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.on(
        "console",
        lambda message: errors.append(f"console-error: {message.text}")
        if message.type == "error"
        else None,
    )


def _assert_no_visible_error(page: Page, selectors: tuple[str, ...]) -> None:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() and locator.first.is_visible():
            text = locator.first.inner_text().strip()
            raise AssertionError(f"visible error {selector}: {text}")


def _admin_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    try:
        page = context.new_page()
        _attach_error_capture(page, errors)
        page.goto(f"{base_url}/admin/", wait_until="networkidle")
        page.locator("#username").fill("admin")
        page.locator("#password").fill("Admin123!")
        page.locator("#login-btn").click()
        page.wait_for_selector(".layout", timeout=15000)
        page.goto(f"{base_url}/admin/v12-operations.html?view=overview", wait_until="networkidle")
        page.wait_for_selector(".ops-shell", timeout=15000)
        page.wait_for_selector(".ops-kpi", timeout=15000)
        _assert_no_visible_error(page, (".ops-error",))
        title = page.title()
        if "V1.2" not in title:
            raise AssertionError(f"unexpected admin title: {title}")
        screenshot = output / "v12-admin-overview.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "valid": True,
            "title": title,
            "kpi_count": page.locator(".ops-kpi").count(),
            "screenshot": str(screenshot),
        }
    finally:
        context.close()


def _h5_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        locale="zh-CN",
    )
    try:
        response = context.request.post(
            f"{base_url}/api/v1/auth/login",
            data={"username": "franchise_demo", "password": "Franchise123!"},
        )
        if not response.ok:
            raise AssertionError(f"franchise login failed: {response.status} {response.text()}")
        page = context.new_page()
        _attach_error_capture(page, errors)
        page.goto(f"{base_url}/h5/v12-workbench.html?view=home", wait_until="networkidle")
        page.wait_for_selector(".wb-header", timeout=15000)
        page.wait_for_selector(".wb-hero", timeout=15000)
        _assert_no_visible_error(page, (".wb-error",))
        title = page.title()
        if "全链路工作台" not in title:
            raise AssertionError(f"unexpected H5 title: {title}")
        screenshot = output / "v12-h5-home-mobile.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "valid": True,
            "title": title,
            "nav_count": page.locator(".wb-nav").count(),
            "screenshot": str(screenshot),
        }
    finally:
        context.close()


def _run_scenario(
    name: str,
    action: Callable[[], dict[str, object]],
    errors: list[str],
) -> dict[str, object]:
    before = len(errors)
    try:
        result = action()
    except Exception as exc:  # CI evidence must survive an individual scenario failure.
        message = f"{name}: {type(exc).__name__}: {exc}"
        errors.append(message)
        return {"valid": False, "error": message}
    scenario_errors = errors[before:]
    if scenario_errors:
        return {**result, "valid": False, "errors": scenario_errors}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.2 Chromium visual and interaction smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("dist/browser-smoke"))
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    results: dict[str, Any] = {}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            base_url = args.base_url.rstrip("/")
            results["admin"] = _run_scenario(
                "admin",
                lambda: _admin_smoke(browser, base_url, args.output_dir, errors),
                errors,
            )
            results["h5"] = _run_scenario(
                "h5",
                lambda: _h5_smoke(browser, base_url, args.output_dir, errors),
                errors,
            )
        finally:
            browser.close()
    payload = {**results, "errors": errors, "valid": not errors}
    report_path = args.output_dir / "browser-smoke-report.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

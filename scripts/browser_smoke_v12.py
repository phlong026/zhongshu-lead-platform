#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Browser, Page, sync_playwright


def _attach_pageerror_capture(page: Page, errors: list[str]) -> None:
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))


def _attach_console_error_capture(page: Page, errors: list[str]) -> None:
    page.on(
        "console",
        lambda message: errors.append(f"console-error: {message.text}")
        if message.type == "error"
        else None,
    )


def _attach_error_capture(page: Page, errors: list[str]) -> None:
    _attach_pageerror_capture(page, errors)
    _attach_console_error_capture(page, errors)


def _assert_no_visible_error(page: Page, selectors: tuple[str, ...]) -> None:
    for selector in selectors:
        locator = page.locator(selector)
        if locator.count() and locator.first.is_visible():
            text = locator.first.inner_text().strip()
            raise AssertionError(f"visible error {selector}: {text}")


def _assert_safe_html_boundary(page: Page) -> dict[str, bool]:
    result = page.evaluate(
        """() => {
            if (typeof window.zsSetSafeHtml !== 'function') {
                throw new Error('safe HTML boundary is not installed');
            }
            const target = document.createElement('div');
            document.body.appendChild(target);
            window.zsSetSafeHtml(target, `
              <form id="kept-form" action="javascript:alert(1)" onsubmit="alert(1)">
                <input name="reason" value="ok">
                <button formaction="data:text/html,bad">Submit</button>
              </form>
              <table><tbody><tr><td id="kept-cell">cell</td></tr></tbody></table>
              <select><option id="kept-option">choice</option></select>
              <svg id="kept-svg"><path id="kept-path" d="M0 0h1"></path>
                <animate id="blocked-animate" attributeName="href" values="javascript:alert(1)"></animate>
                <foreignObject id="blocked-foreign"><div>foreign</div></foreignObject>
                <use id="blocked-use" href="https://example.invalid/icon.svg#x"></use>
              </svg>
              <template id="blocked-template"><img onerror="alert(1)"></template>
              <math id="blocked-math"><mtext>math</mtext></math>
              <a id="safe-link" href="/relative" target="_blank">safe</a>
              <a id="unsafe-link" href="javascript:alert(1)">unsafe</a>
              <div id="unsafe-style" style="background:url(javascript:alert(1))">styled</div>
              <script id="blocked-script">alert(1)<\\/script>
              <iframe id="blocked-frame"></iframe>
            `);
            const checks = {
                formPreserved: Boolean(target.querySelector('#kept-form')),
                tablePreserved: Boolean(target.querySelector('#kept-cell')),
                selectPreserved: Boolean(target.querySelector('#kept-option')),
                svgPathPreserved: Boolean(target.querySelector('#kept-path')),
                unsafeActionRemoved: !target.querySelector('#kept-form').hasAttribute('action'),
                eventHandlerRemoved: !target.querySelector('#kept-form').hasAttribute('onsubmit'),
                unsafeFormactionRemoved: !target.querySelector('button').hasAttribute('formaction'),
                unsafeHrefRemoved: !target.querySelector('#unsafe-link').hasAttribute('href'),
                unsafeStyleRemoved: !target.querySelector('#unsafe-style').hasAttribute('style'),
                activeSvgRemoved: !target.querySelector('#blocked-animate, #blocked-foreign, #blocked-use'),
                templateRemoved: !target.querySelector('#blocked-template'),
                mathRemoved: !target.querySelector('#blocked-math'),
                scriptRemoved: !target.querySelector('#blocked-script'),
                iframeRemoved: !target.querySelector('#blocked-frame'),
                blankRelHardened:
                    target.querySelector('#safe-link').getAttribute('rel') === 'noopener noreferrer',
            };
            target.remove();
            return checks;
        }"""
    )
    failed = sorted(name for name, passed in result.items() if not passed)
    if failed:
        raise AssertionError(f"safe HTML boundary failed: {', '.join(failed)}")
    return result


def _admin_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    try:
        page = context.new_page()
        # The admin app intentionally probes /auth/me on first load. An unauthenticated
        # 401 is therefore expected before the login form appears. Capture page-level
        # JavaScript errors from the first byte, but start console-error capture only
        # after the login form has rendered so real post-login console failures remain
        # release blockers without treating the expected pre-auth 401 as a defect.
        _attach_pageerror_capture(page, errors)
        page.goto(f"{base_url}/admin/", wait_until="networkidle")
        page.wait_for_selector("#username", timeout=15000)
        page.locator("#username").fill("admin")
        page.locator("#password").fill("Admin123!")
        _attach_console_error_capture(page, errors)
        page.locator("#login-btn").click()
        page.wait_for_selector(".layout", timeout=15000)
        page.goto(f"{base_url}/admin/index.html#/users", wait_until="networkidle")
        page.wait_for_selector("#new-user", timeout=15000)
        internal_user_rows = page.locator("main.page table tbody tr").count()
        page.locator("#new-user").click()
        page.wait_for_selector("#save-user", timeout=15000)
        internal_role_count = page.locator('input[name="u-role"]').count()
        if internal_role_count != 7:
            raise AssertionError(f"unexpected internal role count: {internal_role_count}")
        if page.locator('input[value="FRANCHISE_OWNER"]').count():
            raise AssertionError("franchise role leaked into internal account modal")
        page.locator("#modal-root [data-close]").first.click()
        page.locator("[data-edit-user]").first.click()
        page.wait_for_selector("#save-user-roles", timeout=15000)
        page.locator("#modal-root [data-close]").first.click()
        page.locator("[data-reset-user]").first.click()
        page.wait_for_selector("#reset-user-password", timeout=15000)
        page.locator("#modal-root [data-close]").first.click()
        internal_user_screenshot = output / "v12-admin-internal-users.png"
        page.screenshot(path=str(internal_user_screenshot), full_page=True)
        page.goto(f"{base_url}/admin/v12-operations.html?view=overview", wait_until="networkidle")
        page.wait_for_selector(".ops-shell", timeout=15000)
        page.wait_for_selector(".ops-kpi", timeout=15000)
        _assert_no_visible_error(page, (".ops-error",))
        title = page.title()
        if "客资运营台" not in title:
            raise AssertionError(f"unexpected admin title: {title}")
        screenshot = output / "v12-admin-overview.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "valid": True,
            "title": title,
            "kpi_count": page.locator(".ops-kpi").count(),
            "internal_user_rows": internal_user_rows,
            "internal_role_count": internal_role_count,
            "internal_user_screenshot": str(internal_user_screenshot),
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
        safe_html_boundary = _assert_safe_html_boundary(page)
        title = page.title()
        if "客资工作台" not in title:
            raise AssertionError(f"unexpected H5 title: {title}")
        screenshot = output / "v12-h5-home-mobile.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "valid": True,
            "title": title,
            "nav_count": page.locator(".wb-nav").count(),
            "safe_html_boundary": safe_html_boundary,
            "screenshot": str(screenshot),
        }
    finally:
        context.close()


def _call_smoke(
    browser: Browser,
    base_url: str,
    output: Path,
    errors: list[str],
) -> dict[str, object]:
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
            data={"username": "telesales", "password": "Telesales123!"},
        )
        if not response.ok:
            raise AssertionError(
                f"telesales login failed: {response.status} {response.text()}"
            )
        page = context.new_page()
        _attach_error_capture(page, errors)
        page.goto(f"{base_url}/call/", wait_until="networkidle")
        page.wait_for_selector(".shell", timeout=15000)
        page.wait_for_selector(".top", timeout=15000)
        page.wait_for_selector(".content", timeout=15000)
        _assert_no_visible_error(page, (".toast.show.error",))
        title = page.title()
        if "电销核验台" not in title:
            raise AssertionError(f"unexpected call title: {title}")
        task_count = page.locator("[data-task]").count()
        empty_state = None
        if task_count == 0:
            empty_state = page.locator(".empty").inner_text()
            if "暂无待办任务" not in empty_state:
                raise AssertionError(f"unexpected call empty state: {empty_state}")
        screenshot = output / "v12-call-home-mobile.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "valid": True,
            "title": title,
            "task_count": task_count,
            "empty_state": empty_state,
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
            results["call"] = _run_scenario(
                "call",
                lambda: _call_smoke(browser, base_url, args.output_dir, errors),
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

#!/usr/bin/env python3
"""Chromium smoke checks for the five formal V1.2 workbenches."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from playwright.sync_api import Browser, Page, sync_playwright


MOBILE_WIDTHS = (320, 375, 390, 414)


def _attach_errors(page: Page, errors: list[str]) -> None:
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
            raise AssertionError(f"visible error {selector}: {locator.first.inner_text().strip()}")


def _assert_responsive_widths(page: Page, selectors: tuple[str, ...]) -> dict[str, dict[str, int]]:
    results: dict[str, dict[str, int]] = {}
    for width in MOBILE_WIDTHS:
        page.set_viewport_size({"width": width, "height": 844})
        page.wait_for_timeout(80)
        for selector in selectors:
            if not page.locator(selector).count() or not page.locator(selector).first.is_visible():
                raise AssertionError(f"responsive element missing at {width}px: {selector}")
        layout = page.evaluate(
            """() => ({viewportWidth: window.innerWidth, documentWidth: document.documentElement.scrollWidth})"""
        )
        if layout["documentWidth"] > layout["viewportWidth"] + 1:
            raise AssertionError(
                f"horizontal overflow at {width}px: document={layout['documentWidth']} viewport={layout['viewportWidth']}"
            )
        results[str(width)] = layout
    return results


def _assert_safe_html_boundary(page: Page) -> dict[str, bool]:
    result = page.evaluate(
        """() => {
          if (typeof window.zsSetSafeHtml !== 'function') throw new Error('safe HTML boundary is not installed');
          const target = document.createElement('div'); document.body.appendChild(target);
          window.zsSetSafeHtml(target, '<form id="form" action="javascript:alert(1)" onsubmit="alert(1)"><button formaction="data:text/html,bad">ok</button></form><a id="unsafe" href="javascript:alert(1)">bad</a><script id="script">alert(1)<\\/script>');
          const checks = {
            formPreserved: Boolean(target.querySelector('#form')),
            unsafeActionRemoved: !target.querySelector('#form').hasAttribute('action'),
            eventHandlerRemoved: !target.querySelector('#form').hasAttribute('onsubmit'),
            unsafeFormactionRemoved: !target.querySelector('button').hasAttribute('formaction'),
            unsafeHrefRemoved: !target.querySelector('#unsafe').hasAttribute('href'),
            scriptRemoved: !target.querySelector('#script'),
          };
          target.remove(); return checks;
        }"""
    )
    failed = sorted(name for name, passed in result.items() if not passed)
    if failed:
        raise AssertionError(f"safe HTML boundary failed: {', '.join(failed)}")
    return result


def _login(context, base_url: str, username: str, password: str) -> None:
    response = context.request.post(
        f"{base_url}/api/v1/auth/login",
        data={"username": username, "password": password},
    )
    if not response.ok:
        raise AssertionError(f"{username} login failed: {response.status} {response.text()}")


def _admin_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    try:
        page = context.new_page()
        page.goto(f"{base_url}/admin/", wait_until="networkidle")
        page.wait_for_selector("#platform-login-form", timeout=15000)
        page.locator("#username").fill("admin")
        page.locator("#password").fill("Admin123!")
        page.locator("#login-btn").click()
        page.wait_for_selector(".ops-shell", timeout=15000)
        _attach_errors(page, errors)
        _assert_no_visible_error(page, (".ops-error",))
        for view in ("overview", "leads", "telesales", "dispatch", "companies", "returns", "finance", "audit"):
            if page.locator(f'.ops-menu [data-view="{view}"]').count() != 1:
                raise AssertionError(f"super admin is missing {view} navigation")
        overview_screenshot = output / "v12-admin-overview.png"
        page.screenshot(path=str(overview_screenshot), full_page=True)
        created = page.evaluate(
            """async () => {
              const response = await fetch('/api/v1/v1.2/platform/leads', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                credentials: 'include',
                body: JSON.stringify({
                  customer_name: '浏览器验收客户',
                  phone: '13900001234',
                  province: '广东省',
                  city: '广州市',
                  district: '天河区',
                  need_summary: '用于确认客资详情页面的客户信息和处理进度。',
                  consent_confirmed: true
                })
              });
              return {status: response.status, payload: await response.json()};
            }"""
        )
        if created["status"] != 200 or created["payload"].get("code") != "OK":
            raise AssertionError(f"unable to create isolated V1.2 lead: {created}")
        lead_id = created["payload"]["data"]["id"]
        page.locator('.ops-menu [data-view="leads"]').click()
        page.wait_for_url(f"{base_url}/admin/v12-operations.html?view=leads")
        detail_button = page.locator(f'[data-platform-detail="{lead_id}"]')
        detail_button.wait_for(timeout=15000)
        detail_button.click()
        page.wait_for_selector("#trace", timeout=15000)
        page.locator("#trace").click()
        page.wait_for_selector(".ops-trace-layout", timeout=15000)
        _assert_no_visible_error(page, (".ops-error",))
        trace_screenshot = output / "v12-full-process-detail.png"
        page.screenshot(path=str(trace_screenshot), full_page=True)
        page.locator('.ops-menu [data-view="companies"]').click()
        page.wait_for_url(f"{base_url}/admin/v12-operations.html?view=companies")
        page.wait_for_selector(".company-review", timeout=15000)
        account_button = page.locator("[data-company-accounts]").first
        if account_button.count():
            account_button.click()
            page.wait_for_selector("#company-account-create", timeout=15000)
            page.locator("#modal-close").click()
        page.evaluate("history.back()")
        page.wait_for_url(f"{base_url}/admin/v12-operations.html?view=trace&id={lead_id}")
        page.wait_for_selector(".ops-trace-layout", timeout=15000)
        page.evaluate("history.forward()")
        page.wait_for_url(f"{base_url}/admin/v12-operations.html?view=companies")
        page.locator('.ops-menu [data-view="finance"]').click()
        page.wait_for_url(f"{base_url}/admin/v12-operations.html?view=finance")
        page.wait_for_selector(".ops-card", timeout=15000)
        page.locator('.ops-menu [data-view="audit"]').click()
        page.wait_for_url(f"{base_url}/admin/v12-operations.html?view=audit")
        page.get_by_text("通知发送异常", exact=True).wait_for(timeout=15000)
        return {
            "valid": True,
            "title": page.title(),
            "navigation_count": page.locator(".ops-menu [data-view]").count(),
            "overview_screenshot": str(overview_screenshot),
            "trace_screenshot": str(trace_screenshot),
            "browser_history_valid": True,
        }
    finally:
        context.close()


def _operation_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 1440, "height": 900}, locale="zh-CN")
    try:
        _login(context, base_url, "operation", "Operation123!")
        page = context.new_page()
        _attach_errors(page, errors)
        page.goto(f"{base_url}/admin/v12-operations.html?view=overview", wait_until="networkidle")
        page.wait_for_selector(".ops-shell", timeout=15000)
        _assert_no_visible_error(page, (".ops-error",))
        if page.locator('.ops-menu [data-view="finance"]').count():
            raise AssertionError("operation user can see finance navigation")
        page.locator('.ops-menu [data-view="telesales"]').click()
        page.wait_for_url(f"{base_url}/admin/v12-operations.html?view=telesales")
        page.wait_for_selector(".ops-card", timeout=15000)
        screenshot = output / "v12-operation-telesales.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {"valid": True, "screenshot": str(screenshot)}
    finally:
        context.close()


def _platform_h5_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
        locale="zh-CN",
    )
    try:
        _login(context, base_url, "operation", "Operation123!")
        page = context.new_page()
        _attach_errors(page, errors)
        page.goto(f"{base_url}/h5/admin/", wait_until="networkidle")
        page.wait_for_selector(".platform-shell", timeout=15000)
        page.wait_for_selector(".platformHomeHero", timeout=15000)
        page.wait_for_selector(".platformHomeMetrics", timeout=15000)
        _assert_no_visible_error(page, (".error",))
        if page.locator('[data-go="funds"]').count():
            raise AssertionError("operation H5 can see finance navigation")
        operation_nav_count = page.locator(".nav").count()
        if operation_nav_count != 5:
            raise AssertionError("operation H5 must keep five focused bottom tabs")
        responsive_widths = _assert_responsive_widths(page, (".platform-top", ".platform-bottom"))
        safe_html_boundary = _assert_safe_html_boundary(page)
        page.set_viewport_size({"width": 390, "height": 844})
        screenshot = output / "v12-platform-h5-home-mobile.png"
        page.screenshot(path=str(screenshot), full_page=True)
        context.request.post(f"{base_url}/api/v1/auth/logout")
        _login(context, base_url, "admin", "Admin123!")
        page.goto(f"{base_url}/h5/admin/?role=superadmin#/home", wait_until="networkidle")
        page.wait_for_selector(".platform-shell", timeout=15000)
        page.wait_for_selector(".platformHomeHero", timeout=15000)
        if not page.get_by_text("风险待办", exact=True).count():
            raise AssertionError("super admin H5 must prioritize risk work on the home screen")
        _assert_no_visible_error(page, (".error",))
        if page.locator(".nav").count() != 4:
            raise AssertionError("super admin H5 must keep four focused bottom tabs")
        superadmin_home_screenshot = output / "v12-platform-h5-superadmin-home-mobile.png"
        page.screenshot(path=str(superadmin_home_screenshot), full_page=True)
        page.locator('[data-go="funds"]').click()
        page.wait_for_url(f"{base_url}/h5/admin/?role=superadmin#/funds")
        page.wait_for_selector('[data-go="funds"].active', timeout=15000)
        page.get_by_role("heading", name="资金").wait_for(timeout=15000)
        if not page.get_by_role("heading", name="资金").count():
            raise AssertionError("super admin H5 fund workbench is missing")
        return {
            "valid": True,
            "nav_count": operation_nav_count,
            "superadmin_nav_count": page.locator(".nav").count(),
            "responsive_widths": responsive_widths,
            "safe_html_boundary": safe_html_boundary,
            "screenshot": str(screenshot),
            "superadmin_home_screenshot": str(superadmin_home_screenshot),
        }
    finally:
        context.close()


def _h5_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="zh-CN")
    try:
        _login(context, base_url, "franchise_demo", "Franchise123!")
        page = context.new_page()
        _attach_errors(page, errors)
        page.goto(f"{base_url}/h5/v12-workbench.html?view=home", wait_until="networkidle")
        page.wait_for_selector(".wb-header", timeout=15000)
        page.wait_for_selector(".wb-hero", timeout=15000)
        page.wait_for_selector(".franchiseHomeHero", timeout=15000)
        _assert_no_visible_error(page, (".wb-error",))
        owner_nav_count = page.locator(".wb-nav").count()
        if owner_nav_count != 5:
            raise AssertionError("franchise owner H5 must keep five focused bottom tabs")
        if page.locator(".wb-nav").evaluate_all("nodes => new Set(nodes.map(node => Math.round(node.getBoundingClientRect().top))).size") != 1:
            raise AssertionError("franchise owner H5 bottom navigation must stay on one row")
        if not page.locator('[data-nav="assignments"]').count() or not page.locator('[data-nav="followups"]').count():
            raise AssertionError("franchise owner H5 must expose receive and follow-up entries")
        responsive_widths = _assert_responsive_widths(page, (".wb-header", ".wb-bottom"))
        safe_html_boundary = _assert_safe_html_boundary(page)
        page.set_viewport_size({"width": 390, "height": 844})
        screenshot = output / "v12-h5-home-mobile.png"
        page.screenshot(path=str(screenshot), full_page=True)
        context.request.post(f"{base_url}/api/v1/auth/logout")
        _login(context, base_url, "franchise_employee_demo", "Employee123!")
        page.goto(f"{base_url}/h5/v12-workbench.html?view=home", wait_until="networkidle")
        page.wait_for_selector(".wb-header", timeout=15000)
        page.wait_for_selector(".franchiseHomeHero", timeout=15000)
        _assert_no_visible_error(page, (".wb-error",))
        employee_nav_count = page.locator(".wb-nav").count()
        if employee_nav_count != 4:
            raise AssertionError("franchise employee H5 must keep four focused bottom tabs")
        if page.locator(".wb-nav").evaluate_all("nodes => new Set(nodes.map(node => Math.round(node.getBoundingClientRect().top))).size") != 1:
            raise AssertionError("franchise employee H5 bottom navigation must stay on one row")
        if page.locator('[data-nav="assignments"]').count() or page.locator('[data-nav="points"]').count():
            raise AssertionError("franchise employee H5 can see an owner-only entry")
        if not page.locator('[data-nav="followups"]').count() or not page.locator('[data-nav="leads"]').count():
            raise AssertionError("franchise employee H5 is missing follow-up or supply entry")
        employee_screenshot = output / "v12-h5-employee-home-mobile.png"
        page.screenshot(path=str(employee_screenshot), full_page=True)
        return {"valid": True, "title": page.title(), "owner_nav_count": owner_nav_count, "employee_nav_count": employee_nav_count, "responsive_widths": responsive_widths, "safe_html_boundary": safe_html_boundary, "screenshot": str(screenshot), "employee_screenshot": str(employee_screenshot)}
    finally:
        context.close()


def _call_smoke(browser: Browser, base_url: str, output: Path, errors: list[str]) -> dict[str, object]:
    context = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, locale="zh-CN")
    try:
        _login(context, base_url, "telesales", "Telesales123!")
        page = context.new_page()
        _attach_errors(page, errors)
        page.goto(f"{base_url}/h5/call/", wait_until="networkidle")
        page.wait_for_selector(".shell", timeout=15000)
        page.wait_for_selector(".callHomeHero", timeout=15000)
        page.wait_for_selector(".callHomeMetrics", timeout=15000)
        _assert_no_visible_error(page, (".toast.show.error",))
        if page.locator(".nav").count() != 4:
            raise AssertionError("telesales H5 must keep four focused bottom tabs")
        if page.locator(".nav").evaluate_all("nodes => new Set(nodes.map(node => Math.round(node.getBoundingClientRect().top))).size") != 1:
            raise AssertionError("telesales H5 bottom navigation must stay on one row")
        primary_action_color = page.locator(".callHomeHero .btn span").evaluate("node => getComputedStyle(node).color")
        if primary_action_color != "rgb(99, 68, 45)":
            raise AssertionError("telesales primary action must keep contrast")
        responsive_widths = _assert_responsive_widths(page, (".top", ".bottom"))
        page.set_viewport_size({"width": 390, "height": 844})
        screenshot = output / "v12-call-home-mobile.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {"valid": True, "title": page.title(), "task_count": page.locator("[data-task]").count(), "responsive_widths": responsive_widths, "screenshot": str(screenshot)}
    finally:
        context.close()


def _run_scenario(name: str, action: Callable[[], dict[str, object]], errors: list[str]) -> dict[str, object]:
    before = len(errors)
    try:
        result = action()
    except Exception as exc:
        message = f"{name}: {type(exc).__name__}: {exc}"
        errors.append(message)
        return {"valid": False, "error": message}
    scenario_errors = errors[before:]
    return {**result, "valid": not scenario_errors, **({"errors": scenario_errors} if scenario_errors else {})}


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.2 formal-workbench Chromium smoke")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", type=Path, default=Path("dist/browser-smoke"))
    parser.add_argument("--browser-executable", type=Path, default=None)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True, executable_path=str(args.browser_executable) if args.browser_executable else None)
        try:
            base_url = args.base_url.rstrip("/")
            results: dict[str, Any] = {
                "admin": _run_scenario("admin", lambda: _admin_smoke(browser, base_url, args.output_dir, errors), errors),
                "operation": _run_scenario("operation", lambda: _operation_smoke(browser, base_url, args.output_dir, errors), errors),
                "platform_h5": _run_scenario("platform_h5", lambda: _platform_h5_smoke(browser, base_url, args.output_dir, errors), errors),
                "h5": _run_scenario("h5", lambda: _h5_smoke(browser, base_url, args.output_dir, errors), errors),
                "call": _run_scenario("call", lambda: _call_smoke(browser, base_url, args.output_dir, errors), errors),
            }
        finally:
            browser.close()
    payload = {**results, "errors": errors, "valid": not errors}
    report_path = args.output_dir / "browser-smoke-report.json"
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())

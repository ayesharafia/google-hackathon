"""Exercise atmosphere browser journeys against a caller-owned disposable fixture."""

import argparse
import datetime as dt
import ipaddress
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit

from playwright.sync_api import Error, expect, sync_playwright

TIMEOUT_MS = 30_000
CAUGHT_ERRORS = (Error, RuntimeError, AssertionError, ValueError, KeyError, OSError)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, help="Existing loopback fixture URL")
    parser.add_argument("--mode", required=True, choices=("local", "hosted"))
    parser.add_argument(
        "--token",
        default=os.environ.get("PHYSIMESH_API_TOKEN"),
        help="Synthetic local fixture token; defaults to PHYSIMESH_API_TOKEN",
    )
    parser.add_argument("--project", help="Hosted synthetic viewer project ID")
    parser.add_argument("--evidence", required=True, type=Path)
    args = parser.parse_args()

    if os.environ.get("PHYSIMESH_BROWSER_DISPOSABLE") != "1":
        parser.error("PHYSIMESH_BROWSER_DISPOSABLE=1 is required")

    try:
        parsed = urlsplit(args.base)
        port = parsed.port
        host = parsed.hostname
        loopback = host == "localhost" or (
            host is not None and ipaddress.ip_address(host).is_loopback
        )
    except ValueError:
        loopback = False
        port = None

    if (
        not loopback
        or parsed.scheme not in ("http", "https")
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
        or port == 0
    ):
        parser.error("--base must be an HTTP(S) loopback origin without credentials")

    args.base = args.base.rstrip("/")
    if args.mode == "local":
        if not args.token:
            parser.error("local mode requires --token or PHYSIMESH_API_TOKEN")
        if args.project:
            parser.error("local mode creates a fresh synthetic example; --project is hosted-only")
    if args.mode == "hosted":
        if not args.project:
            parser.error("hosted mode requires --project")
        if not os.environ.get("PHYSIMESH_BROWSER_FIXTURE_PASSWORD"):
            parser.error("hosted mode requires PHYSIMESH_BROWSER_FIXTURE_PASSWORD")
    return args


def idle(page, mode):
    selector = "#token" if mode == "local" else "#projects"
    expect(page.locator(selector)).to_be_enabled(timeout=TIMEOUT_MS)


def open_project(page, project, mode):
    page.locator("#projects").select_option(project)
    page.locator("#open").click()
    page.wait_for_function(
        """() => document.querySelector('#input-editors').textContent.length > 100"""
    )
    idle(page, mode)


def cases_group(page):
    group = page.locator("[data-readiness-group=cases]")
    if group.get_attribute("open") is None:
        group.locator("summary").click()
    return group


def screenshot(page, directory, name):
    page.screenshot(path=str(directory / name), full_page=True)


def mobile_preview(page, group, directory):
    page.set_viewport_size({"width": 390, "height": 844})
    try:
        group.scroll_into_view_if_needed()
        group.get_by_role(
            "button", name="Preview reference atmosphere", exact=True
        ).locator("..").screenshot(path=str(directory / "mobile-preview.png"))
    finally:
        page.set_viewport_size({"width": 1280, "height": 900})


def local_journey(page, context, args, receipt):
    def api(path):
        response = context.request.get(
            args.base + "/api/drone" + path,
            headers={"Authorization": "Bearer " + args.token},
            timeout=TIMEOUT_MS,
        )
        try:
            require(response.ok, "Fixture API read failed: " + str(response.status))
            return response.json()
        finally:
            response.dispose()

    page.locator("#token").fill(args.token)
    page.locator("#connection button").click()
    idle(page, "local")

    with page.expect_response(
        lambda response: response.request.method == "POST"
        and "/api/drone/projects" in response.url
    ) as created:
        page.locator("#realistic-example").click()
    require(created.value.ok, "Realistic example creation failed")
    page.wait_for_function("() => document.querySelector('#projects').value !== ''")
    idle(page, "local")
    project = page.locator("#projects").input_value()
    receipt["project"] = project
    prefix = "/projects/" + quote(project, safe="")

    page.locator("#freeze").click()
    idle(page, "local")
    page.locator("#calculate").click()
    page.wait_for_function(
        "() => document.querySelector('#study-report').textContent.length > 100"
    )
    idle(page, "local")

    before = api(prefix)
    raw = page.locator("#snapshot").input_value()
    require(before.get("studies"), "Calculation did not retain a study")
    require(before.get("revisions"), "Initial freeze did not retain a revision")
    retained = before["studies"][0]
    old_revision = before["revisions"][0]
    study_path = prefix + "/studies/" + quote(retained["study_sha256"], safe="")
    retained_raw = api(study_path)

    group = cases_group(page)
    altitude = group.get_by_label("Reference altitude, m", exact=True)
    convention = group.get_by_label("Altitude convention", exact=True)
    preview = group.get_by_role(
        "button", name="Preview reference atmosphere", exact=True
    )
    apply = group.get_by_role("button", name="Apply preview to unsaved draft")

    def evaluate_preview():
        with page.expect_response(
            lambda response: urlsplit(response.url).path
            == "/api/drone/atmosphere/evaluate"
        ) as evaluated:
            preview.click()
        require(evaluated.value.ok, "Atmosphere preview request failed")
        expect(apply).to_be_enabled()
        idle(page, "local")

    def unchanged():
        require(
            page.locator("#snapshot").input_value() == raw,
            "Preview unexpectedly changed the draft",
        )
        require(
            api(prefix)["draft_version"] == before["draft_version"],
            "Preview unexpectedly changed the saved draft version",
        )

    altitude.fill("20000")
    convention.select_option("geometric")
    evaluate_preview()
    unchanged()
    group.locator("fieldset").first.screenshot(
        path=str(args.evidence / "atmosphere-fields.png")
    )
    preview.locator("..").screenshot(
        path=str(args.evidence / "atmosphere-preview.png")
    )

    altitude.fill("21000")
    expect(apply).to_be_disabled()
    unchanged()

    delivered = {"value": False}

    def late_response(route):
        response = route.fetch(timeout=TIMEOUT_MS)
        try:
            page.evaluate(
                """() => {
                    const select = document.querySelector(
                        '[aria-label="Altitude convention"]'
                    );
                    select.value = 'geopotential';
                    select.dispatchEvent(new Event('change', {bubbles: true}));
                }"""
            )
            route.fulfill(response=response)
            delivered["value"] = True
        finally:
            response.dispose()

    pattern = "**/api/drone/atmosphere/evaluate"
    page.route(pattern, late_response, times=1)
    try:
        with page.expect_response(
            lambda response: urlsplit(response.url).path
            == "/api/drone/atmosphere/evaluate"
        ) as late:
            preview.click()
        require(late.value.ok, "Intercepted atmosphere request failed")
        expect(convention).to_have_value("geopotential")
        idle(page, "local")
        require(delivered["value"], "Late response was not delivered")
        expect(apply).to_be_disabled()
        unchanged()
    finally:
        page.unroute(pattern, late_response)

    altitude.fill("20000")
    convention.select_option("geometric")
    evaluate_preview()
    mobile_preview(page, group, args.evidence)
    apply.click()

    draft = json.loads(page.locator("#snapshot").input_value())
    require(draft["atmosphere"]["altitude_m"] == 20000, "Apply failed")
    expect(page.locator("#freeze")).to_be_disabled()
    expect(page.locator("#calculate")).to_be_disabled()
    expect(page.locator("#review-pack-binding")).to_contain_text(
        "Unsaved draft edits are excluded."
    )
    expect(page.locator("#study-report .study-binding")).to_contain_text(
        "earlier revision", ignore_case=True
    )
    require(
        api(prefix)["draft_version"] == before["draft_version"],
        "Apply unexpectedly saved the draft",
    )
    require(api(study_path) == retained_raw, "Retained study changed")
    require(old_revision in api(prefix)["revisions"], "Prior revision disappeared")
    screenshot(page, args.evidence, "retained-study-unsaved.png")

    page.locator("#save").click()
    idle(page, "local")
    after = api(prefix)
    require(
        after["draft_version"] == before["draft_version"] + 1,
        "Explicit save did not increment draft version once",
    )
    page.locator("#freeze").click()
    idle(page, "local")
    frozen = api(prefix)
    require(
        any(
            revision["draft_version"] == after["draft_version"]
            for revision in frozen["revisions"]
        ),
        "Explicit freeze did not retain the saved version",
    )
    require(old_revision in frozen["revisions"], "Prior revision disappeared")
    require(api(study_path) == retained_raw, "Retained study changed after save")
    screenshot(page, args.evidence, "saved-and-frozen.png")
    receipt["checks"] = [
        "token login and realistic example",
        "initial freeze and retained calculation",
        "preview leaves draft and version unchanged",
        "input change invalidates apply",
        "late API response cannot enable stale apply",
        "filled mobile preview",
        "apply changes only unsaved draft",
        "unsaved calculation and freeze disabled",
        "retained study and prior revision preserved",
        "explicit save increments version",
        "explicit freeze retains saved version",
    ]


def hosted_journey(page, args, receipt):
    page.locator("#login-email").fill("viewer@example.test")
    page.locator("#login-password").fill(
        os.environ["PHYSIMESH_BROWSER_FIXTURE_PASSWORD"]
    )
    page.locator("#individual-login button").click()
    page.wait_for_function(
        "project => [...document.querySelector('#projects').options].some(o => o.value === project)",
        arg=args.project,
    )
    idle(page, "hosted")
    open_project(page, args.project, "hosted")
    expect(page.locator("#save")).to_be_disabled()

    group = cases_group(page)
    for control in (
        group.get_by_label("Reference altitude, m", exact=True),
        group.get_by_label("Altitude convention", exact=True),
        group.get_by_role(
            "button", name="Preview reference atmosphere", exact=True
        ),
        group.get_by_role("button", name="Apply preview to unsaved draft"),
    ):
        expect(control).to_be_disabled()

    snapshot = page.locator("#snapshot")
    require(
        snapshot.get_attribute("readonly") is not None or snapshot.is_disabled(),
        "Viewer snapshot is editable",
    )
    for control_id in ("save", "freeze", "calculate"):
        expect(page.locator("#" + control_id)).to_be_disabled()

    group.screenshot(path=str(args.evidence / "hosted-viewer.png"))
    mobile_preview(page, group, args.evidence)
    receipt["project"] = args.project
    receipt["checks"] = [
        "synthetic fixture viewer login",
        "requested synthetic project opened",
        "atmosphere controls disabled",
        "snapshot readonly",
        "save, freeze and calculate disabled",
        "mobile preview with existing fixture values",
    ]


def main():
    args = parse_args()
    args.evidence.mkdir(parents=True, exist_ok=True)
    receipt = {
        "mode": args.mode,
        "status": "failed",
        "started_at": dt.datetime.now(dt.UTC).isoformat(),
        "scope": "Disposable fixture browser checks; no scientific acceptance or full CI claim.",
        "fixture_cleanup": "Caller owns fixture lifecycle and disposable data cleanup.",
        "page_errors": [],
    }
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            try:
                context = browser.new_context(
                    viewport={"width": 1280, "height": 900}
                )
                try:
                    context.set_default_timeout(TIMEOUT_MS)
                    context.set_default_navigation_timeout(TIMEOUT_MS)
                    page = context.new_page()
                    page.on(
                        "pageerror",
                        lambda error: receipt["page_errors"].append(str(error)),
                    )
                    try:
                        page.goto(
                            args.base + "/web/workbench.html",
                            wait_until="domcontentloaded",
                        )
                        if args.mode == "local":
                            local_journey(page, context, args, receipt)
                        else:
                            hosted_journey(page, args, receipt)
                        require(not receipt["page_errors"], "Browser page errors occurred")
                        receipt["status"] = "passed"
                    except CAUGHT_ERRORS:
                        try:
                            screenshot(page, args.evidence, "failure.png")
                        except CAUGHT_ERRORS as screenshot_error:
                            receipt["failure_screenshot_error"] = {
                                "error_type": type(screenshot_error).__name__,
                                "message": str(screenshot_error),
                            }
                        raise
                finally:
                    context.close()
            finally:
                browser.close()
    except KeyboardInterrupt:
        receipt["status"] = "failed"
        receipt["error_type"] = "KeyboardInterrupt"
        return 130
    except CAUGHT_ERRORS as error:
        receipt["status"] = "failed"
        receipt["error_type"] = type(error).__name__
        receipt["error"] = str(error)
        print("Atmosphere browser checks failed; see receipt.json.", file=sys.stderr)
        return 1
    finally:
        receipt["finished_at"] = dt.datetime.now(dt.UTC).isoformat()
        (args.evidence / "receipt.json").write_text(
            json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
        )
    print("Atmosphere browser checks passed; see receipt.json.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

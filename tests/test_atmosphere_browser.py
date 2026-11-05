import importlib.util
import json
import sys
import types
from pathlib import Path
from unittest.mock import Mock

import pytest


@pytest.fixture
def browser_module(monkeypatch):
    playwright = types.ModuleType("playwright")
    api = types.ModuleType("playwright.sync_api")
    api.Error = type("Error", (Exception,), {})
    api.expect = Mock()
    api.sync_playwright = Mock(side_effect=AssertionError("Browser access forbidden"))
    playwright.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)

    roots = [Path.cwd(), *Path(__file__).resolve().parents]
    source = next(
        root / "scripts/qa/atmosphere_browser.py"
        for root in roots
        if (root / "scripts/qa/atmosphere_browser.py").is_file()
    )
    spec = importlib.util.spec_from_file_location("atmosphere_browser_under_test", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def cli(monkeypatch, tmp_path):
    monkeypatch.setenv("PHYSIMESH_BROWSER_DISPOSABLE", "1")
    monkeypatch.delenv("PHYSIMESH_API_TOKEN", raising=False)
    monkeypatch.delenv("PHYSIMESH_BROWSER_FIXTURE_PASSWORD", raising=False)

    def configure(base="http://localhost", mode="local", extra=("--token", "synthetic")):
        monkeypatch.setattr(
            sys,
            "argv",
            [
                "atmosphere_browser.py",
                "--base", base,
                "--mode", mode,
                "--evidence", str(tmp_path / "evidence"),
                *extra,
            ],
        )

    configure()
    return configure


def assert_refused(module):
    with pytest.raises(SystemExit) as error:
        module.parse_args()
    assert error.value.code == 2


@pytest.mark.parametrize("value", [None, "", "0", "true"])
def test_requires_disposable_marker(browser_module, cli, monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PHYSIMESH_BROWSER_DISPOSABLE")
    else:
        monkeypatch.setenv("PHYSIMESH_BROWSER_DISPOSABLE", value)
    assert_refused(browser_module)


@pytest.mark.parametrize(
    "base",
    [
        "https://production.example.com",
        "http://user@localhost",
        "http://user:password@localhost",
        "http://localhost/nonroot",
        "http://localhost/?query=value",
        "http://localhost/#fragment",
        "http://localhost:0",
        "http://localhost:invalid",
        "http://localhost:65536",
        "http://localhost.example.com",
        "http://localhostevil",
        "ftp://localhost",
    ],
)
def test_rejects_unsafe_origins(browser_module, cli, base):
    cli(base=base)
    assert_refused(browser_module)


@pytest.mark.parametrize(
    "base",
    [
        "http://localhost",
        "https://localhost:8443/",
        "http://127.0.0.1:8080/",
        "http://[::1]:8080/",
    ],
)
def test_accepts_loopback_with_local_token(browser_module, cli, base):
    cli(base=base)
    args = browser_module.parse_args()
    assert args.base == base.rstrip("/")
    assert args.token == "synthetic"
    assert args.mode == "local"


def test_local_accepts_environment_token(browser_module, cli, monkeypatch):
    cli(extra=())
    monkeypatch.setenv("PHYSIMESH_API_TOKEN", "synthetic-env")
    assert browser_module.parse_args().token == "synthetic-env"


def test_local_requires_token(browser_module, cli):
    cli(extra=())
    assert_refused(browser_module)


def test_local_refuses_project(browser_module, cli):
    cli(extra=("--token", "synthetic", "--project", "fixture-project"))
    assert_refused(browser_module)


@pytest.mark.parametrize("missing", ["project", "password"])
def test_hosted_requires_project_and_password(
    browser_module, cli, monkeypatch, missing
):
    extra = () if missing == "project" else ("--project", "fixture-project")
    cli(mode="hosted", extra=extra)
    if missing == "project":
        monkeypatch.setenv("PHYSIMESH_BROWSER_FIXTURE_PASSWORD", "synthetic-password")
    assert_refused(browser_module)


@pytest.fixture
def fake_browser(browser_module, monkeypatch):
    page = Mock()
    context = Mock()
    context.new_page.return_value = page
    browser = Mock()
    browser.new_context.return_value = context
    playwright = Mock()
    playwright.chromium.launch.return_value = browser
    manager = Mock()
    manager.__enter__ = Mock(return_value=playwright)
    manager.__exit__ = Mock(return_value=False)
    start = Mock(return_value=manager)
    monkeypatch.setattr(browser_module, "sync_playwright", start)
    monkeypatch.setattr(browser_module, "local_journey", Mock())
    monkeypatch.setattr(browser_module, "hosted_journey", Mock())
    monkeypatch.setattr(browser_module, "screenshot", Mock())
    return types.SimpleNamespace(
        page=page, context=context, browser=browser, start=start
    )


def read_receipt(tmp_path):
    return json.loads((tmp_path / "evidence/receipt.json").read_text())


def test_main_fails_closed_before_browser(
    browser_module, cli, fake_browser, monkeypatch, tmp_path
):
    monkeypatch.delenv("PHYSIMESH_BROWSER_DISPOSABLE")
    with pytest.raises(SystemExit) as error:
        browser_module.main()
    assert error.value.code == 2
    fake_browser.start.assert_not_called()
    assert not (tmp_path / "evidence").exists()


def test_main_success(browser_module, cli, fake_browser, tmp_path):
    assert browser_module.main() == 0
    receipt = read_receipt(tmp_path)
    assert receipt["status"] == "passed"
    assert receipt["page_errors"] == []
    assert receipt["started_at"]
    assert receipt["finished_at"]
    fake_browser.context.close.assert_called_once()
    fake_browser.browser.close.assert_called_once()


def test_main_catches_failure_and_screenshot_failure(
    browser_module, cli, fake_browser, tmp_path
):
    browser_module.local_journey.side_effect = RuntimeError("journey failed")
    browser_module.screenshot.side_effect = OSError("screenshot failed")
    assert browser_module.main() == 1
    receipt = read_receipt(tmp_path)
    assert receipt["status"] == "failed"
    assert receipt["error_type"] == "RuntimeError"
    assert receipt["error"] == "journey failed"
    assert receipt["failure_screenshot_error"] == {
        "error_type": "OSError",
        "message": "screenshot failed",
    }
    assert receipt["finished_at"]
    fake_browser.context.close.assert_called_once()
    fake_browser.browser.close.assert_called_once()


def test_page_errors_fail_closed(browser_module, cli, fake_browser, tmp_path):
    def journey(page, context, args, receipt):
        callback = fake_browser.page.on.call_args.args[1]
        callback(RuntimeError("page exploded"))

    browser_module.local_journey.side_effect = journey
    assert browser_module.main() == 1
    receipt = read_receipt(tmp_path)
    assert receipt["status"] == "failed"
    assert receipt["page_errors"] == ["page exploded"]
    assert receipt["error_type"] == "RuntimeError"


@pytest.mark.parametrize("interrupt_at", ["journey", "context_cleanup"])
def test_keyboard_interrupt_writes_failed_receipt_and_returns_130(
    browser_module, cli, fake_browser, tmp_path, interrupt_at
):
    observed_status = []

    def journey(page, context, args, receipt):
        observed_status.append(receipt)
        if interrupt_at == "journey":
            raise KeyboardInterrupt()

    def close():
        if interrupt_at == "context_cleanup":
            assert observed_status[0]["status"] == "passed"
            raise KeyboardInterrupt()

    browser_module.local_journey.side_effect = journey
    fake_browser.context.close.side_effect = close

    assert browser_module.main() == 130
    receipt = read_receipt(tmp_path)
    assert receipt["status"] == "failed"
    assert receipt["error_type"] == "KeyboardInterrupt"
    assert receipt["started_at"]
    assert receipt["finished_at"]
    fake_browser.context.close.assert_called_once()
    fake_browser.browser.close.assert_called_once()

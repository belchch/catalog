from __future__ import annotations

from unittest.mock import MagicMock

import catalog.cli as cli


def test_cli_main_binds_localhost_and_opens_browser(monkeypatch) -> None:
    run = MagicMock()
    open_browser = MagicMock()
    monkeypatch.setattr(cli.uvicorn, "run", run)
    monkeypatch.setattr(cli.webbrowser, "open", open_browser)

    timers: list = []

    class _Timer:
        def __init__(self, _interval, function) -> None:
            timers.append(function)

        def start(self) -> None:
            return None

    monkeypatch.setattr(cli.threading, "Timer", _Timer)

    cli.main(["--port", "8123"])

    run.assert_called_once()
    kwargs = run.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1"
    assert kwargs["port"] == 8123
    assert run.call_args.args[0] == "catalog.main:app"
    assert timers
    timers[0]()
    open_browser.assert_called_once_with("http://127.0.0.1:8123/")


def test_cli_rejects_wildcard_host(monkeypatch) -> None:
    run = MagicMock()
    monkeypatch.setattr(cli.uvicorn, "run", run)
    monkeypatch.setattr(cli.threading, "Timer", lambda *_a, **_k: MagicMock(start=lambda: None))
    monkeypatch.setattr(cli.webbrowser, "open", MagicMock())

    cli.main(["--host", "0.0.0.0", "--no-browser"])

    assert run.call_args.kwargs["host"] == "127.0.0.1"


def test_cli_no_browser(monkeypatch) -> None:
    run = MagicMock()
    timer = MagicMock()
    monkeypatch.setattr(cli.uvicorn, "run", run)
    monkeypatch.setattr(cli.threading, "Timer", timer)
    monkeypatch.setattr(cli.webbrowser, "open", MagicMock())

    cli.main(["--no-browser"])

    timer.assert_not_called()
    run.assert_called_once()

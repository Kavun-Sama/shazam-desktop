from __future__ import annotations

from pathlib import Path

import pytest

from shazam_desktop.__main__ import build_parser, main
from shazam_desktop.selfcheck import CheckResult, default_checks, run_checks, run_self_check


def passing() -> str:
    return "fine"


def failing() -> str:
    raise RuntimeError("boom")


def test_every_check_is_reported_and_a_failure_does_not_stop_the_rest() -> None:
    results = run_checks([("a", failing), ("b", passing)])
    assert results == [
        CheckResult("a", False, "RuntimeError: boom"),
        CheckResult("b", True, "fine"),
    ]


def test_exit_code_is_zero_only_when_everything_passes(capsys: pytest.CaptureFixture[str]) -> None:
    assert run_self_check(checks=[("b", passing)]) == 0
    assert "self-check passed" in capsys.readouterr().out
    assert run_self_check(checks=[("a", failing), ("b", passing)]) == 1
    assert "FAIL a: RuntimeError: boom" in capsys.readouterr().out


def test_report_file_gets_the_same_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report = tmp_path / "report.txt"
    run_self_check(report, checks=[("b", passing)])
    assert report.read_text(encoding="utf-8") == capsys.readouterr().out


def test_report_is_written_even_without_stdout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A windowed Windows build has sys.stdout set to None.
    monkeypatch.setattr("sys.stdout", None)
    report = tmp_path / "report.txt"
    assert run_self_check(report, checks=[("b", passing)]) == 0
    assert "self-check passed" in report.read_text(encoding="utf-8")


def test_default_checks_cover_the_bundle_contents() -> None:
    assert [name for name, _ in default_checks()] == [
        "qt imports",
        "shazam imports",
        "platform imports",
        "ffmpeg tools",
        "audio decode",
        "qt offscreen",
    ]


def test_qt_and_import_checks_pass_in_a_development_environment() -> None:
    checks = dict(default_checks())
    for name in ("qt imports", "shazam imports", "platform imports", "qt offscreen"):
        assert checks[name]()


def test_cli_parses_self_check_and_report(tmp_path: Path) -> None:
    args = build_parser().parse_args(["--self-check", "--report", str(tmp_path / "r.txt")])
    assert args.self_check
    assert args.report == tmp_path / "r.txt"


def test_main_runs_the_self_check_without_starting_the_app(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[Path | None] = []

    def fake_run_self_check(report: Path | None) -> int:
        seen.append(report)
        return 7

    monkeypatch.setattr("shazam_desktop.selfcheck.run_self_check", fake_run_self_check)
    assert main(["--self-check"]) == 7
    assert seen == [None]

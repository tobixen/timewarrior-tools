"""Tests for aw-report.py."""

import datetime
import io
import json
from unittest import mock

import pytest
from dateutil import tz

# Import the module under test
import importlib
aw_report = importlib.import_module("aw-report")


SAMPLE_HEADER = (
    "temp.report.start: 20250115T070000Z\n"
    "temp.report.end: 20250115T160000Z\n"
    "color: off\n"
    "\n"
)


def make_input(intervals):
    """Build a timew-style input stream (header + JSON body)."""
    return io.StringIO(SAMPLE_HEADER + json.dumps(intervals))


class TestParseTimewInput:
    def test_parses_header_and_body(self):
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
        ]
        config, result = aw_report.parse_timew_input(make_input(intervals))
        assert config["temp.report.start"] == "20250115T070000Z"
        assert config["temp.report.end"] == "20250115T160000Z"
        assert len(result) == 1
        assert result[0]["tags"] == ["work"]

    def test_empty_body(self):
        stream = io.StringIO(SAMPLE_HEADER + "[]")
        config, result = aw_report.parse_timew_input(stream)
        assert result == []
        assert "temp.report.start" in config


class TestUtcToLocalIso:
    def test_returns_iso_format(self):
        result = aw_report.utc_to_local_iso("20250115T120000Z")
        # Should be a valid ISO 8601 string with timezone info
        dt = datetime.datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_preserves_instant(self):
        result = aw_report.utc_to_local_iso("20250115T120000Z")
        dt = datetime.datetime.fromisoformat(result)
        expected_utc = datetime.datetime(2025, 1, 15, 12, 0, 0, tzinfo=tz.tzutc())
        assert dt == expected_utc


class TestFormatLocalTime:
    def test_returns_date_and_time(self):
        result = aw_report.format_local_time("20250115T120000Z")
        # Should be %FT%H:%M:%S format, e.g. 2025-01-15T13:00:00
        assert "T" in result
        assert result.count(":") == 2
        assert result.startswith("2025-01-15")


class TestGetOption:
    def test_prefers_args(self):
        args = mock.Mock(aw_args="--format=json")
        result = aw_report.get_option("AW_ARGS", args, {"AW_ARGS": "--all-columns"})
        assert result == "--format=json"

    def test_falls_back_to_env(self):
        args = mock.Mock(aw_args=None)
        with mock.patch.dict("os.environ", {"AW_ARGS": "--all-columns"}):
            result = aw_report.get_option("AW_ARGS", args, {})
        assert result == "--all-columns"

    def test_falls_back_to_config(self):
        args = mock.Mock(aw_args=None)
        result = aw_report.get_option("AW_ARGS", args, {"AW_ARGS": "--no-truncate"})
        assert result == "--no-truncate"

    def test_returns_none_when_unset(self):
        args = mock.Mock(aw_args=None)
        result = aw_report.get_option("AW_ARGS", args, {})
        assert result is None


class TestRunAwReport:
    @mock.patch("subprocess.run")
    def test_success(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="report output", stderr="")
        result = aw_report.run_aw_report("20250115T080000Z", "20250115T090000Z", None)
        assert result == "report output"
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "aw-export-timewarrior"
        assert cmd[1] == "report"
        assert cmd[2].startswith("--from=")
        assert cmd[3].startswith("--to=")

    @mock.patch("subprocess.run")
    def test_with_extra_args(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=0, stdout="output", stderr="")
        aw_report.run_aw_report("20250115T080000Z", "20250115T090000Z",
                                "--format=json --all-columns")
        cmd = mock_run.call_args[0][0]
        assert "--format=json" in cmd
        assert "--all-columns" in cmd

    @mock.patch("subprocess.run")
    def test_error_returncode(self, mock_run):
        mock_run.return_value = mock.Mock(returncode=1, stdout="", stderr="something failed")
        result = aw_report.run_aw_report("20250115T080000Z", "20250115T090000Z", None)
        assert "[error" in result
        assert "something failed" in result

    @mock.patch("subprocess.run", side_effect=FileNotFoundError)
    def test_not_found(self, mock_run):
        result = aw_report.run_aw_report("20250115T080000Z", "20250115T090000Z", None)
        assert "not found" in result


class TestMain:
    @mock.patch.object(aw_report, "run_aw_report", return_value="activity data")
    def test_prints_intervals(self, mock_aw, capsys):
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
            {"start": "20250115T100000Z", "end": "20250115T110000Z", "tags": ["meeting", "proj"]},
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "work" in captured
        assert "meeting, proj" in captured
        assert "activity data" in captured
        assert mock_aw.call_count == 2

    @mock.patch.object(aw_report, "run_aw_report")
    def test_no_intervals(self, mock_aw, capsys):
        with mock.patch("sys.stdin", make_input([])):
            with mock.patch("sys.argv", ["aw-report.py"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "No intervals" in captured
        mock_aw.assert_not_called()

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_no_tags(self, mock_aw, capsys):
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z"},
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "(no tags)" in captured

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_track_hint_with_color(self, mock_aw, capsys):
        """When color is on, print a timew track hint for each interval."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
        ]
        color_header = (
            "temp.report.start: 20250115T070000Z\n"
            "temp.report.end: 20250115T160000Z\n"
            "color: on\n"
            "\n"
        )
        stream = io.StringIO(color_header + json.dumps(intervals))
        with mock.patch("sys.stdin", stream):
            with mock.patch("sys.argv", ["aw-report.py"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "To overwrite this interval, do:" in captured
        assert "timew track :adjust" in captured
        assert "work" in captured

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_no_track_hint_with_color_off(self, mock_aw, capsys):
        """When color is off, no track hint is printed."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "timew track" not in captured

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_open_interval(self, mock_aw, capsys):
        """An interval without 'end' should use current time."""
        intervals = [
            {"start": "20250115T080000Z", "tags": ["work"]},
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "work" in captured
        mock_aw.assert_called_once()

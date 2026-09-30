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


class TestParseDuration:
    def test_seconds(self):
        assert aw_report.parse_duration("30s") == 30
        assert aw_report.parse_duration("30") == 30  # default unit is seconds

    def test_minutes(self):
        assert aw_report.parse_duration("5m") == 300
        assert aw_report.parse_duration("1.5m") == 90

    def test_hours(self):
        assert aw_report.parse_duration("1h") == 3600
        assert aw_report.parse_duration("2h") == 7200

    def test_case_insensitive(self):
        assert aw_report.parse_duration("5M") == 300
        assert aw_report.parse_duration("1H") == 3600

    def test_invalid(self):
        assert aw_report.parse_duration("abc") is None
        assert aw_report.parse_duration("5x") is None
        assert aw_report.parse_duration("") is None


class TestFormatDuration:
    def test_seconds_only(self):
        assert aw_report.format_duration(45) == "45s"
        assert aw_report.format_duration(0) == "0s"

    def test_minutes_and_seconds(self):
        assert aw_report.format_duration(90) == "1m 30s"
        assert aw_report.format_duration(300) == "5m"

    def test_hours_minutes_seconds(self):
        assert aw_report.format_duration(3661) == "1h 1m 1s"
        assert aw_report.format_duration(3600) == "1h"

    def test_negative(self):
        assert aw_report.format_duration(-10) == "0s"


class TestComputeDuration:
    def test_one_hour(self):
        result = aw_report.compute_duration("20250115T080000Z", "20250115T090000Z")
        assert result == 3600

    def test_partial(self):
        result = aw_report.compute_duration("20250115T080000Z", "20250115T081530Z")
        assert result == 15 * 60 + 30


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

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_duration_displayed(self, mock_aw, capsys):
        """Duration should be shown in the header."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "(1h)" in captured

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_min_duration_filters_short_intervals(self, mock_aw, capsys):
        """Short intervals should be skipped with --min-duration."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["long"]},  # 1h
            {"start": "20250115T100000Z", "end": "20250115T100200Z", "tags": ["short"]},  # 2m
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py", "--min-duration=5m"]):
                aw_report.main()

        captured = capsys.readouterr().out
        assert "=== long" in captured
        assert "=== short" not in captured
        assert "1 interval(s) shorter than 5m skipped" in captured
        assert mock_aw.call_count == 1

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_min_duration_via_env(self, mock_aw, capsys):
        """MIN_DURATION env var should filter intervals."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["long"]},
            {"start": "20250115T100000Z", "end": "20250115T100100Z", "tags": ["short"]},  # 1m
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                with mock.patch.dict("os.environ", {"MIN_DURATION": "30m"}):
                    aw_report.main()

        captured = capsys.readouterr().out
        assert "=== long" in captured
        assert "=== short" not in captured


class TestEditMode:
    @mock.patch.object(aw_report, "run_aw_report", return_value="activity data")
    @mock.patch.object(aw_report, "run_editor_and_execute")
    def test_edit_mode_generates_script(self, mock_editor, mock_aw):
        """In edit mode, a script should be generated and passed to the editor."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                with mock.patch.dict("os.environ", {"EDIT_MODE": "1"}):
                    aw_report.main()

        mock_editor.assert_called_once()
        script = mock_editor.call_args[0][0]
        assert "#!/bin/bash" in script
        assert "timew track :adjust" in script
        assert "# === work" in script
        assert "# activity data" in script

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    @mock.patch.object(aw_report, "run_editor_and_execute")
    def test_edit_mode_comments_output(self, mock_editor, mock_aw):
        """AW report output should be commented in edit mode script."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
        ]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                with mock.patch.dict("os.environ", {"EDIT_MODE": "1"}):
                    aw_report.main()

        script = mock_editor.call_args[0][0]
        lines = script.splitlines()
        # timew track command should NOT be commented
        track_lines = [l for l in lines if l.startswith("timew track")]
        assert len(track_lines) == 1
        # activity output should be commented
        data_lines = [l for l in lines if "data" in l]
        assert all(l.startswith("#") for l in data_lines)


class TestRunEditorAndExecute:
    @mock.patch("subprocess.run")
    def test_executes_via_bash(self, mock_run):
        """After editing, script should be executed via bash."""
        mock_run.return_value = mock.Mock(returncode=0)
        script = "#!/bin/bash\ntimew track :adjust 2025-01-15T09:00:00 - 2025-01-15T10:00:00 work\n"

        with mock.patch.dict("os.environ", {"EDITOR": "true"}):
            result = aw_report.run_editor_and_execute(script)

        # Should have called editor first, then bash
        assert mock_run.call_count == 2
        # Second call should be bash
        bash_call = mock_run.call_args_list[1]
        assert bash_call[0][0][0] == "bash"

    def test_runs_with_errexit(self, tmp_path):
        """A failing line must not be masked by a later line that succeeds.

        Plain `bash script` only reports the last command's status, so a
        `timew track` that failed halfway down read as success.
        """
        script = "#!/bin/bash\nfalse\ntrue\n"
        with mock.patch.dict("os.environ", {"EDITOR": "true"}):
            assert aw_report.run_editor_and_execute(script) is False

    def test_nothing_to_run_is_not_a_failure(self):
        """All lines commented out is a choice, not an error."""
        script = "#!/bin/bash\n# timew track :adjust x - y work\n"
        with mock.patch.dict("os.environ", {"EDITOR": "true"}):
            assert aw_report.run_editor_and_execute(script) is None


class TestEditModeExitCode:
    intervals = [
        {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["work"]},
    ]

    @pytest.mark.parametrize("outcome, code", [(True, None), (None, None), (False, 1)])
    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    def test_failed_script_exits_nonzero(self, mock_aw, outcome, code):
        """A caller has to be able to tell that the edited commands failed."""
        with mock.patch.object(aw_report, "run_editor_and_execute", return_value=outcome):
            with mock.patch("sys.stdin", make_input(self.intervals)):
                with mock.patch("sys.argv", ["aw-report.py"]):
                    with mock.patch.dict("os.environ", {"EDIT_MODE": "1"}):
                        if code is None:
                            aw_report.main()
                        else:
                            with pytest.raises(SystemExit) as exc:
                                aw_report.main()
                            assert exc.value.code == code


class TestTrackCommandQuoting:
    """The track command is run by bash, so every tag must survive the shell."""

    TAGS = ["plain", "two words", "$(touch pwned)", "it's", 'say "hi"', "a;b&c*"]

    @mock.patch.object(aw_report, "run_aw_report", return_value="data")
    @mock.patch.object(aw_report, "run_editor_and_execute")
    def test_tags_round_trip_through_the_shell(self, mock_editor, mock_aw):
        import shlex

        intervals = [{"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": self.TAGS}]
        with mock.patch("sys.stdin", make_input(intervals)):
            with mock.patch("sys.argv", ["aw-report.py"]):
                with mock.patch.dict("os.environ", {"EDIT_MODE": "1"}):
                    aw_report.main()

        script = mock_editor.call_args[0][0]
        [track] = [l for l in script.splitlines() if l.startswith("timew track")]
        assert shlex.split(track)[-len(self.TAGS):] == self.TAGS


class TestEditorSelection:
    def test_editor_with_arguments(self):
        script = "#!/bin/bash\n# nothing\n"
        with mock.patch.dict("os.environ", {"EDITOR": "true --wait", "VISUAL": ""}):
            assert aw_report.run_editor_and_execute(script) is None

    def test_visual_is_preferred_over_editor(self):
        script = "#!/bin/bash\n# nothing\n"
        with mock.patch.dict("os.environ", {"VISUAL": "true", "EDITOR": "false"}):
            assert aw_report.run_editor_and_execute(script) is None

    def test_missing_editor_is_a_failure_not_a_traceback(self, capsys):
        script = "#!/bin/bash\n# nothing\n"
        with mock.patch.dict("os.environ", {"EDITOR": "no-such-editor-xyz", "VISUAL": ""}):
            assert aw_report.run_editor_and_execute(script) is False
        assert "no-such-editor-xyz" in capsys.readouterr().err

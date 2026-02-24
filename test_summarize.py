"""Tests for summarize.py."""

import argparse
import io
import json

import pytest
import importlib

summarize = importlib.import_module("summarize")


SAMPLE_HEADER = (
    "temp.report.start: 20250115T070000Z\n"
    "temp.report.end: 20250115T160000Z\n"
    "color: off\n"
    "\n"
)


def make_input(intervals):
    """Build a timew-style input stream (header + JSON body)."""
    return io.StringIO(SAMPLE_HEADER + json.dumps(intervals))


def default_args(**kwargs):
    """Return a Namespace with default arg values, overridable via kwargs."""
    defaults = dict(
        tags=None,
        regex=None,
        negregex=None,
        killtags=None,
        ignoretags=None,
        concat=False,
        split=False,
        min_duration=None,
        timew_args=[],
    )
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


class TestParseDuration:
    def test_minutes(self):
        assert summarize.parse_duration("5m") == 300

    def test_hours(self):
        assert summarize.parse_duration("2h") == 7200

    def test_seconds(self):
        assert summarize.parse_duration("90s") == 90

    def test_bare_number_is_seconds(self):
        assert summarize.parse_duration("60") == 60

    def test_decimal(self):
        assert summarize.parse_duration("1.5h") == 5400

    def test_invalid_returns_none(self):
        assert summarize.parse_duration("foobar") is None

    def test_empty_returns_none(self):
        assert summarize.parse_duration("") is None


class TestMinDuration:
    """Tests for --min-duration filtering of output rows."""

    INTERVALS = [
        # "big-project": 2 hours
        {"start": "20250115T080000Z", "end": "20250115T100000Z", "tags": ["big-project"]},
        # "tiny-task": 2 minutes
        {"start": "20250115T100000Z", "end": "20250115T100200Z", "tags": ["tiny-task"]},
        # "medium-work": 30 minutes
        {"start": "20250115T110000Z", "end": "20250115T113000Z", "tags": ["medium-work"]},
        # "also-tiny": 1 minute
        {"start": "20250115T120000Z", "end": "20250115T120100Z", "tags": ["also-tiny"]},
    ]

    def test_no_min_duration_shows_all_tags(self):
        args = default_args()
        output = summarize.calculate_totals(make_input(self.INTERVALS), args)
        text = "\n".join(output)
        assert "big-project" in text
        assert "tiny-task" in text
        assert "medium-work" in text
        assert "also-tiny" in text
        assert "short" not in text.lower()

    def test_min_duration_hides_short_tags(self):
        args = default_args(min_duration="5m")
        output = summarize.calculate_totals(make_input(self.INTERVALS), args)
        text = "\n".join(output)
        assert "big-project" in text
        assert "medium-work" in text
        assert "tiny-task" not in text
        assert "also-tiny" not in text

    def test_min_duration_shows_short_intervals_summary(self):
        args = default_args(min_duration="5m")
        output = summarize.calculate_totals(make_input(self.INTERVALS), args)
        text = "\n".join(output)
        # Should mention something about short/skipped intervals
        assert "short" in text.lower() or "skipped" in text.lower()

    def test_min_duration_short_total_included_in_grand_total(self):
        args = default_args(min_duration="5m")
        output = summarize.calculate_totals(make_input(self.INTERVALS), args)
        # Grand total should be 2h + 30m + 2m + 1m = 2h33m = 9180s
        # Match the summary row "Total  H:MM:SS" but not the header "Total by Tag, for ..."
        total_line = [l for l in output if l.strip().startswith("Total ") and "by Tag" not in l]
        assert len(total_line) == 1
        # 9180s = 2h 33m 0s → "   2:33:00"
        assert "2:33:00" in total_line[0]

    def test_min_duration_all_below_threshold(self):
        """When everything is below threshold, no regular rows, only short summary."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T080100Z", "tags": ["a"]},
            {"start": "20250115T090000Z", "end": "20250115T090100Z", "tags": ["b"]},
        ]
        args = default_args(min_duration="5m")
        output = summarize.calculate_totals(make_input(intervals), args)
        text = "\n".join(output)
        assert "a" not in text or "short" in text.lower()
        # Grand total = 2 minutes
        total_line = [l for l in output if l.strip().startswith("Total ") and "by Tag" not in l]
        assert len(total_line) == 1
        assert "0:02:00" in total_line[0]

    def test_min_duration_nothing_short(self):
        """When everything is above threshold, no short-intervals line."""
        intervals = [
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["big"]},
        ]
        args = default_args(min_duration="5m")
        output = summarize.calculate_totals(make_input(intervals), args)
        text = "\n".join(output)
        assert "big" in text
        assert "short" not in text.lower()

    def test_min_duration_hours(self):
        """Test --min-duration with hours unit."""
        args = default_args(min_duration="1h")
        output = summarize.calculate_totals(make_input(self.INTERVALS), args)
        text = "\n".join(output)
        assert "big-project" in text
        assert "medium-work" not in text
        assert "tiny-task" not in text

    def test_min_duration_folds_short_untagged_intervals(self):
        """Untagged time below threshold is also grouped into short intervals."""
        intervals = [
            # tagged, above threshold
            {"start": "20250115T080000Z", "end": "20250115T090000Z", "tags": ["big"]},
            # untagged, below threshold (1 minute)
            {"start": "20250115T100000Z", "end": "20250115T100100Z", "tags": []},
        ]
        args = default_args(min_duration="5m")
        output = summarize.calculate_totals(make_input(intervals), args)
        text = "\n".join(output)
        # Untagged blank row should NOT appear
        lines_with_blank_tag = [l for l in output if l.startswith("  ") and ":" in l and "short" not in l.lower()]
        assert not any(l.strip().startswith("0:01:00") for l in lines_with_blank_tag)
        # Short intervals row should appear
        assert "short" in text.lower()
        # Grand total should include the untagged minute: 60 + 3600 = 3660s = 1:01:00
        total_line = [l for l in output if l.strip().startswith("Total ") and "by Tag" not in l]
        assert "1:01:00" in total_line[0]

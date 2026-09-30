"""Tests for the small shell helpers, run against a throwaway TIMEWARRIORDB."""

import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REAL_TIMEW = shutil.which("timew")

pytestmark = pytest.mark.skipif(REAL_TIMEW is None, reason="timew not installed")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "db"
    path.mkdir()
    return path


def run(db, *cmd):
    env = dict(os.environ, TIMEWARRIORDB=str(db))
    return subprocess.run(list(cmd), capture_output=True, text=True, env=env)


def start(db, *tags):
    assert run(db, REAL_TIMEW, "start", "2026-01-01T10:00", *tags, ":yes").returncode == 0


def active_tags(db):
    out = run(db, REAL_TIMEW, "export").stdout
    open_intervals = [i for i in json.loads(out) if "end" not in i]
    return [sorted(i.get("tags", [])) for i in open_intervals]


class TestTimewShort:
    SCRIPT = os.path.join(HERE, "timew-short.sh")

    def test_single_tag_shows_no_dom_error(self, db):
        start(db, "work")
        result = run(db, self.SCRIPT)
        assert "DOM reference" not in result.stdout
        assert "work" in result.stdout

    def test_waybar_output_is_valid_json_for_awkward_tags(self, db):
        start(db, 'say "hi"', "back\\slash", "~css_class:busy")
        result = run(db, self.SCRIPT, "waybar")
        data = json.loads(result.stdout)
        assert data["class"] == "busy"
        assert 'say "hi"' in data["tooltip"]
        assert "back\\slash" in data["tooltip"]

    def test_waybar_inactive(self, db):
        assert json.loads(run(db, self.SCRIPT, "waybar").stdout) == {
            "text": "No active tracking"
        }


class TestTimewStartAfk:
    SCRIPT = os.path.join(HERE, "timew-start-afk")

    def test_starts_afk_when_nothing_is_active(self, db):
        result = run(db, self.SCRIPT)
        assert result.returncode == 0, result.stderr
        assert active_tags(db) == [["afk"]]

    def test_starts_afk_over_a_multi_word_tag(self, db):
        start(db, "two words")
        result = run(db, self.SCRIPT)
        assert "too many arguments" not in result.stderr
        assert active_tags(db) == [["afk"]]

    def test_leaves_an_afk_interval_alone(self, db):
        start(db, "a", "b", "c", "afk")
        result = run(db, self.SCRIPT)
        assert result.returncode == 0
        assert active_tags(db) == [["a", "afk", "b", "c"]]

    def test_no_deprecation_warning(self, db):
        start(db, "work")
        assert "deprecated" not in run(db, self.SCRIPT).stdout + run(db, self.SCRIPT).stderr

"""Tests for timew-change-tag.

The interesting scenario is a concurrent writer.  Timewarrior assigns @ids
backwards from the newest interval, so any interval created while timew-change-tag
is working (in real life: the aw-export-timewarrior sync daemon) shifts every id
by one.  An implementation that resolves @ids once up front and then mutates them
silently retags the *neighbouring* intervals instead of the intended ones.

These tests run against a throwaway TIMEWARRIORDB and simulate the concurrent
writer with a `timew` shim placed ahead of the real binary on PATH.
"""

import json
import os
import shutil
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "timew-change-tag")
REAL_TIMEW = shutil.which("timew")

pytestmark = pytest.mark.skipif(REAL_TIMEW is None, reason="timew not installed")


def timew(db, *args):
    """Run the real timew against `db`."""
    env = dict(os.environ, TIMEWARRIORDB=str(db))
    return subprocess.run(
        [REAL_TIMEW, *args], capture_output=True, text=True, env=env
    )


def export(db):
    """Return all intervals in `db`."""
    out = timew(db, "export").stdout
    return json.loads(out) if out.strip() else []


def tags_by_start(db):
    """Map interval start timestamp -> sorted tag list."""
    return {i["start"]: sorted(i.get("tags", [])) for i in export(db)}


@pytest.fixture
def db(tmp_path):
    """A timew database seeded with targets interleaved with innocent neighbours."""
    path = tmp_path / "db"
    path.mkdir()
    seed = [
        ("10:00", "10:10", ["A", "BOGUS"]),
        ("10:10", "10:20", ["A", "innocent1"]),
        ("10:20", "10:30", ["A", "BOGUS"]),
        ("10:30", "10:40", ["A", "innocent2"]),
        ("10:40", "10:50", ["A", "BOGUS"]),
        ("10:50", "11:00", ["A", "innocent3"]),
    ]
    for start, end, tags in seed:
        timew(path, "track", f"2026-01-01T{start}", "-", f"2026-01-01T{end}", *tags)
    assert len(export(path)) == 6
    return path


def _make_shim(tmp_path, trigger):
    """Build a `timew` shim that appends one interval once, on `trigger`.

    The injected interval shifts every @id, reproducing the sync-daemon race
    deterministically.  Returns a PATH prefix directory.
    """
    shim_dir = tmp_path / f"shim-{trigger}"
    shim_dir.mkdir()
    flag = tmp_path / f"injected-{trigger}"
    script = shim_dir / "timew"
    script.write_text(
        f"""#!/bin/bash
inject() {{
  if [ ! -e "{flag}" ]; then
    touch "{flag}"
    "{REAL_TIMEW}" track 2026-06-01T10:00 - 2026-06-01T10:05 CONCURRENT >/dev/null 2>&1
  fi
}}
for a in "$@"; do
  case "$a" in
    {trigger}) inject; break ;;
  esac
done
exec "{REAL_TIMEW}" "$@"
"""
    )
    script.chmod(0o755)
    return shim_dir


@pytest.fixture
def shim(tmp_path):
    """Realistic race: the daemon writes while we hold results of the first export.

    This is the window that actually bit in production - seconds elapse between
    the initial full export and the mutations that follow.
    """
    return _make_shim(tmp_path, "export")


@pytest.fixture
def shim_mid_command(tmp_path):
    """Pathological race: the write lands inside the mutating call itself.

    No external tool can win this window, so the requirement here is only that
    the damage is never silent.
    """
    return _make_shim(tmp_path, "untag")


def run_change_tag(db, *args, path_prefix=None):
    env = dict(os.environ, TIMEWARRIORDB=str(db))
    if path_prefix:
        env["PATH"] = f"{path_prefix}{os.pathsep}{env['PATH']}"
    return subprocess.run(
        [SCRIPT, *args], capture_output=True, text=True, env=env
    )


def assert_expected_result(db):
    """Targets carry GOOD instead of BOGUS; neighbours are untouched."""
    result = tags_by_start(db)
    seeded = sorted(s for s in result if not result[s] == ["CONCURRENT"])
    assert len(seeded) == 6

    expected = [
        ["A", "GOOD"],
        ["A", "innocent1"],
        ["A", "GOOD"],
        ["A", "innocent2"],
        ["A", "GOOD"],
        ["A", "innocent3"],
    ]
    actual = [result[s] for s in seeded]
    assert actual == expected


def test_change_tag_without_concurrent_writer(db):
    """Baseline: the straightforward case must work."""
    run_change_tag(db, "BOGUS", "GOOD")
    assert_expected_result(db)


def test_change_tag_survives_concurrent_append(db, shim):
    """Regression: ids must be re-resolved, not reused across mutations."""
    result = run_change_tag(db, "BOGUS", "GOOD", path_prefix=shim)
    assert_expected_result(db)
    assert result.returncode == 0, result.stderr


def test_mid_command_race_is_never_silent(db, shim_mid_command):
    """An unwinnable race must still be reported, not silently corrupt data."""
    result = run_change_tag(db, "BOGUS", "GOOD", path_prefix=shim_mid_command)
    tags = tags_by_start(db)
    targets_done = all(
        "BOGUS" not in t and "GOOD" in t for t in tags.values() if "BOGUS" in t or "GOOD" in t
    )
    collateral = any(
        "GOOD" in t and any(n in t for n in ("innocent1", "innocent2", "innocent3"))
        for t in tags.values()
    )
    if collateral or not targets_done:
        assert result.returncode != 0, (
            "data was left inconsistent but the tool reported success:\n"
            f"{json.dumps(tags, indent=2)}\nstderr: {result.stderr}"
        )


def test_dry_run_changes_nothing(db, shim):
    def seeded_only(db):
        # The shim's own injected interval is not a change made by the tool.
        return {s: t for s, t in tags_by_start(db).items() if t != ["CONCURRENT"]}

    before = seeded_only(db)
    run_change_tag(db, "BOGUS", "GOOD", "--dry-run", path_prefix=shim)
    assert seeded_only(db) == before


def test_reports_no_matches(db):
    result = run_change_tag(db, "NOSUCHTAG", "WHATEVER")
    assert "no intervals found" in result.stdout.lower()
    assert tags_by_start(db) == tags_by_start(db)


def test_pure_removal(db):
    """An empty replacement just removes the tag."""
    run_change_tag(db, "BOGUS", "")
    result = tags_by_start(db)
    assert sorted(result.values()) == sorted(
        [["A"], ["A"], ["A"], ["A", "innocent1"], ["A", "innocent2"], ["A", "innocent3"]]
    )


def _make_custom_shim(tmp_path, name, body):
    """Build a `timew` shim running `body` (bash) before exec'ing the real one."""
    shim_dir = tmp_path / f"shim-{name}"
    shim_dir.mkdir()
    script = shim_dir / "timew"
    script.write_text(f'#!/bin/bash\nREAL="{REAL_TIMEW}"\n{body}\nexec "$REAL" "$@"\n')
    script.chmod(0o755)
    return shim_dir


def test_diverted_untag_is_never_silent(db, tmp_path):
    """A mis-resolved @id that strips a tag from a neighbour must be reported.

    The first untag is sent to the next-newer interval, as a concurrent append
    landing between resolve and mutate would do.  The retry then fixes the
    target, so only the audit can notice the neighbour lost its tag.
    """
    flag = tmp_path / "diverted"
    shim = _make_custom_shim(
        tmp_path,
        "divert",
        f"""if [ "$1" = untag ] && [ ! -e "{flag}" ]; then
  touch "{flag}"
  id=${{2#@}}
  set -- untag "@$((id - 1))" "${{@:3}}"
fi""",
    )
    result = run_change_tag(db, "BOGUS,A", "BOGUS", path_prefix=shim)
    assert flag.exists()
    lost = [t for t in tags_by_start(db).values() if t and t[0].startswith("innocent")]
    assert lost, "the diversion did not hit a neighbour; the test is not testing anything"
    assert result.returncode != 0, result.stdout + result.stderr
    assert "lost" in result.stderr


def test_failed_tag_leaves_old_tag_in_place(db, tmp_path):
    """If adding the new tag fails, the interval must not end up with neither."""
    shim = _make_custom_shim(
        tmp_path, "failtag", 'if [ "$1" = tag ]; then echo "simulated failure" >&2; exit 1; fi'
    )
    result = run_change_tag(db, "BOGUS", "GOOD", path_prefix=shim)
    assert result.returncode != 0
    values = tags_by_start(db).values()
    assert sorted(values) == sorted(
        [["A", "BOGUS"]] * 3 + [["A", "innocent1"], ["A", "innocent2"], ["A", "innocent3"]]
    )

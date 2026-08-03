"""Tests for timew-undo-check."""

import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

# The script has no .py extension (it is a command, like timew-change-tag),
# so it needs loading by path rather than by module name.
import importlib.util
_spec = importlib.util.spec_from_loader(
    "timew_undo_check",
    importlib.machinery.SourceFileLoader(
        "timew_undo_check", str(pathlib.Path(__file__).with_name("timew-undo-check"))
    ),
)
undo_check = importlib.util.module_from_spec(_spec)
# @dataclass resolves annotations via sys.modules, so register before exec.
sys.modules["timew_undo_check"] = undo_check
_spec.loader.exec_module(undo_check)


def make_txn(start, tags, end=None, ident=1):
    """Build one undo.data transaction: interval gets an end timestamp."""
    before = '{"id":%d,"start":"%s","tags":%s}' % (ident, start, tags)
    after = '{"id":%d,"start":"%s","end":"%s","tags":%s}' % (ident, start, end, tags)
    return (
        "txn:\n"
        "  type: interval\n"
        "  before: %s\n"
        "  after: \n"
        "  type: interval\n"
        "  before: \n"
        "  after: %s\n" % (before, after)
    )


def make_journal(count=5):
    """Build a syntactically valid undo.data with `count` transactions."""
    out = []
    for i in range(count):
        out.append(
            make_txn(
                "202607%02dT050000Z" % (i + 1),
                '["tag%d"]' % i,
                end="202607%02dT060000Z" % (i + 1),
            )
        )
    return "".join(out).encode()


# The real-world corruption: a run of NUL bytes replacing the tail that was
# in flight when the machine went down, with the next `txn:` appended
# directly onto it (no intervening newline).
def corrupt(data, at_txn=2, nuls=205):
    offsets = undo_check.transaction_offsets(data)
    cut = offsets[at_txn]
    return data[:cut] + b"\x00" * nuls + data[cut:]


# The nastier variant: the zero-fill starts in the middle of a line, so the
# bytes it replaced are gone and the next `txn:` lands on the cut-off line.
def corrupt_mid_line(data, at_txn=2):
    offsets = undo_check.transaction_offsets(data)
    cut = offsets[at_txn]
    mid = data.rindex(b'"start"', 0, cut)
    return data[:mid] + b"\x00" * (cut - mid) + data[cut:]


class TestFindNulRuns:
    def test_clean_data_has_no_runs(self):
        assert undo_check.find_nul_runs(make_journal()) == []

    def test_single_run_reports_offset_and_length(self):
        data = corrupt(make_journal(), at_txn=2, nuls=205)
        runs = undo_check.find_nul_runs(data)
        assert len(runs) == 1
        offset, length = runs[0]
        assert length == 205
        assert data[offset : offset + 205] == b"\x00" * 205

    def test_multiple_runs(self):
        data = corrupt(corrupt(make_journal(6), at_txn=4, nuls=7), at_txn=2, nuls=3)
        assert [length for _, length in undo_check.find_nul_runs(data)] == [3, 7]


class TestStripNuls:
    def test_removes_all_nuls(self):
        data = corrupt(make_journal())
        assert undo_check.strip_nuls(data).count(b"\x00") == 0

    def test_restores_original_bytes(self):
        clean = make_journal()
        assert undo_check.strip_nuls(corrupt(clean)) == clean

    def test_clean_data_untouched(self):
        clean = make_journal()
        assert undo_check.strip_nuls(clean) == clean

    def test_mid_line_cut_keeps_next_txn_on_its_own_line(self):
        damaged = corrupt_mid_line(make_journal(5))
        stripped = undo_check.strip_nuls(damaged)
        assert len(undo_check.transaction_offsets(stripped)) == 5


class TestMalformedLines:
    def test_clean_journal_is_clean(self):
        assert undo_check.malformed_lines(make_journal()) == []

    def test_nul_run_before_txn_is_flagged(self):
        bad = undo_check.malformed_lines(corrupt(make_journal()))
        assert len(bad) == 1
        lineno, line = bad[0]
        # This is the line timew itself chokes on.
        assert line.endswith(b"txn:")
        assert line.count(b"\x00") == 205

    def test_garbage_line_is_flagged(self):
        data = make_journal() + b"who put this here\n"
        bad = undo_check.malformed_lines(data)
        assert [line for _, line in bad] == [b"who put this here"]

    def test_truncated_json_value_is_flagged(self):
        data = b'txn:\n  type: interval\n  before: \n  after: {"id":1,"sta\n'
        assert [n for n, _ in undo_check.malformed_lines(data)] == [4]

    def test_mid_line_cut_is_still_malformed_after_strip(self):
        stripped = undo_check.strip_nuls(corrupt_mid_line(make_journal(5)))
        assert undo_check.malformed_lines(stripped) != []

    def test_trailing_newline_is_not_a_malformed_line(self):
        assert undo_check.malformed_lines(b"txn:\n  type: interval\n") == []


class TestTransactionOffsets:
    def test_counts_transactions(self):
        assert len(undo_check.transaction_offsets(make_journal(5))) == 5

    def test_first_offset_is_zero(self):
        assert undo_check.transaction_offsets(make_journal())[0] == 0

    def test_every_offset_starts_a_txn_line(self):
        data = make_journal(4)
        for offset in undo_check.transaction_offsets(data):
            assert data[offset:].startswith(b"txn:\n")

    def test_empty_data(self):
        assert undo_check.transaction_offsets(b"") == []

    def test_txn_inside_a_value_is_not_counted(self):
        # A tag could legitimately be named "txn:" — it must not be mistaken
        # for a transaction marker, because it is not at the start of a line.
        data = b'txn:\n  type: interval\n  after: {"tags":["txn:"]}\n'
        assert undo_check.transaction_offsets(data) == [0]


class TestKeepLastTransactions:
    def test_keeps_requested_number(self):
        data = undo_check.keep_last_transactions(make_journal(10), 3)
        assert len(undo_check.transaction_offsets(data)) == 3

    def test_result_starts_with_txn_marker(self):
        data = undo_check.keep_last_transactions(make_journal(10), 3)
        assert data.startswith(b"txn:\n")

    def test_keeps_the_last_ones_not_the_first(self):
        data = undo_check.keep_last_transactions(make_journal(10), 2)
        assert b"tag9" in data
        assert b"tag8" in data
        assert b"tag7" not in data

    def test_tail_is_byte_identical(self):
        full = make_journal(10)
        kept = undo_check.keep_last_transactions(full, 3)
        assert full.endswith(kept)

    def test_keeping_more_than_exists_is_a_noop(self):
        full = make_journal(3)
        assert undo_check.keep_last_transactions(full, 99) == full

    @pytest.mark.parametrize("keep", [0, -5])
    def test_rejects_non_positive_keep(self, keep):
        with pytest.raises(ValueError):
            undo_check.keep_last_transactions(make_journal(10), keep)

    def test_result_is_still_well_formed(self):
        kept = undo_check.keep_last_transactions(make_journal(10), 4)
        assert undo_check.malformed_lines(kept) == []


class TestAtomicWrite:
    def test_writes_content(self, tmp_path):
        target = tmp_path / "undo.data"
        undo_check.atomic_write(target, b"hello\n")
        assert target.read_bytes() == b"hello\n"

    def test_replaces_existing_content(self, tmp_path):
        target = tmp_path / "undo.data"
        target.write_bytes(b"old content that is longer\n")
        undo_check.atomic_write(target, b"new\n")
        assert target.read_bytes() == b"new\n"

    def test_preserves_mode_of_replaced_file(self, tmp_path):
        target = tmp_path / "undo.data"
        target.write_bytes(b"old\n")
        target.chmod(0o600)
        undo_check.atomic_write(target, b"new\n")
        assert target.stat().st_mode & 0o777 == 0o600

    def test_leaves_no_temp_file_behind(self, tmp_path):
        target = tmp_path / "undo.data"
        undo_check.atomic_write(target, b"x\n")
        assert [p.name for p in tmp_path.iterdir()] == ["undo.data"]


class TestStaleTempFiles:
    def test_finds_old_temp_files(self, tmp_path):
        old = tmp_path / "undo.data.12345-3.tmp"
        old.write_bytes(b"junk")
        os.utime(old, (time.time() - 86400 * 30, time.time() - 86400 * 30))
        assert undo_check.stale_temp_files(tmp_path, max_age=3600) == [old]

    def test_ignores_fresh_temp_files(self, tmp_path):
        fresh = tmp_path / "undo.data.999-1.tmp"
        fresh.write_bytes(b"in flight")
        assert undo_check.stale_temp_files(tmp_path, max_age=3600) == []

    def test_ignores_data_files(self, tmp_path):
        keep = tmp_path / "2026-07.data"
        keep.write_bytes(b"inc 20260701T050000Z\n")
        os.utime(keep, (time.time() - 86400 * 30, time.time() - 86400 * 30))
        assert undo_check.stale_temp_files(tmp_path, max_age=3600) == []


class TestBackupPath:
    def test_never_reuses_an_existing_name(self, tmp_path):
        undo = tmp_path / "data" / "undo.data"
        first = undo_check.backup_path(undo)
        first.write_bytes(b"x")
        assert undo_check.backup_path(undo) != first


class TestVanishingTempFile:
    def test_temp_file_removed_during_scan_is_skipped(self, tmp_path, monkeypatch):
        gone = tmp_path / "undo.data.1-1.tmp"
        gone.write_bytes(b"x")
        real_stat = pathlib.Path.stat

        def stat(self, *args, **kwargs):
            if self == gone:
                raise FileNotFoundError(self)
            return real_stat(self, *args, **kwargs)

        monkeypatch.setattr(pathlib.Path, "stat", stat)
        assert undo_check.stale_temp_files(tmp_path, max_age=0) == []
        assert undo_check.write_in_flight(tmp_path) == []


class TestCheck:
    def test_clean_journal_reports_no_problems(self):
        report = undo_check.check(make_journal(5))
        assert report.ok
        assert report.nul_runs == []
        assert report.malformed == []
        assert report.transactions == 5

    def test_corrupt_journal_is_not_ok(self):
        report = undo_check.check(corrupt(make_journal(5)))
        assert not report.ok
        assert len(report.nul_runs) == 1
        assert len(report.malformed) == 1


class TestFindDatabase:
    def test_honours_timewarriordb(self, tmp_path, monkeypatch):
        data = tmp_path / "mydb" / "data"
        data.mkdir(parents=True)
        monkeypatch.setenv("TIMEWARRIORDB", str(tmp_path / "mydb"))
        assert undo_check.find_database() == data

    def test_falls_back_to_xdg_data_home(self, tmp_path, monkeypatch):
        data = tmp_path / "xdg" / "timewarrior" / "data"
        data.mkdir(parents=True)
        monkeypatch.delenv("TIMEWARRIORDB", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        assert undo_check.find_database() == data

    def test_raises_when_nothing_found(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TIMEWARRIORDB", str(tmp_path / "nope"))
        with pytest.raises(FileNotFoundError):
            undo_check.find_database()


class TestMain:
    """The command itself: exit codes, the write path and its safety checks."""

    def make_db(self, tmp_path, undo_data):
        data = tmp_path / "db" / "data"
        data.mkdir(parents=True)
        (data / "undo.data").write_bytes(undo_data)
        return data

    def run(self, data, *args):
        return undo_check.main(["--db", str(data), *args])

    def test_clean_journal_exits_ok(self, tmp_path):
        assert self.run(self.make_db(tmp_path, make_journal())) == undo_check.EXIT_OK

    def test_damaged_journal_exits_problems(self, tmp_path):
        data = self.make_db(tmp_path, corrupt(make_journal()))
        assert self.run(data) == undo_check.EXIT_PROBLEMS

    def test_dry_run_repair_of_damaged_journal_exits_problems(self, tmp_path):
        damaged = corrupt(make_journal())
        data = self.make_db(tmp_path, damaged)
        assert self.run(data, "--repair", "--dry-run") == undo_check.EXIT_PROBLEMS
        assert (data / "undo.data").read_bytes() == damaged

    def test_repair_writes_clean_journal_and_backup(self, tmp_path):
        clean = make_journal()
        damaged = corrupt(clean)
        data = self.make_db(tmp_path, damaged)
        assert self.run(data, "--repair") == undo_check.EXIT_OK
        assert (data / "undo.data").read_bytes() == clean
        backups = list(data.parent.glob("undo.data.bak-*"))
        assert [b.read_bytes() for b in backups] == [damaged]

    def test_repair_refuses_mid_line_cut(self, tmp_path):
        damaged = corrupt_mid_line(make_journal(5))
        data = self.make_db(tmp_path, damaged)
        assert self.run(data, "--repair") == undo_check.EXIT_ERROR
        assert (data / "undo.data").read_bytes() == damaged

    def test_truncating_past_mid_line_cut_succeeds(self, tmp_path):
        damaged = corrupt_mid_line(make_journal(5), at_txn=2)
        data = self.make_db(tmp_path, damaged)
        assert self.run(data, "--repair", "--truncate", "3") == undo_check.EXIT_OK
        assert undo_check.check((data / "undo.data").read_bytes()).ok

    def test_back_to_back_runs_keep_both_backups(self, tmp_path):
        damaged = corrupt(make_journal(10))
        data = self.make_db(tmp_path, damaged)
        assert self.run(data, "--repair") == undo_check.EXIT_OK
        assert self.run(data, "--truncate", "3") == undo_check.EXIT_OK
        contents = {b.read_bytes() for b in data.parent.glob("undo.data.bak-*")}
        assert damaged in contents
        assert len(contents) == 2

    @pytest.mark.parametrize("keep", ["0", "-5"])
    def test_truncate_rejects_non_positive(self, tmp_path, keep):
        data = self.make_db(tmp_path, make_journal())
        with pytest.raises(SystemExit):
            self.run(data, "--truncate", keep)

    def test_refuses_while_write_in_flight(self, tmp_path):
        damaged = corrupt(make_journal())
        data = self.make_db(tmp_path, damaged)
        (data / "undo.data.4242-1.tmp").write_bytes(b"x")
        assert self.run(data, "--repair") == undo_check.EXIT_ERROR
        assert (data / "undo.data").read_bytes() == damaged

    def test_refuses_when_journal_changed_before_rename(self, tmp_path, monkeypatch):
        damaged = corrupt(make_journal())
        data = self.make_db(tmp_path, damaged)
        undo = data / "undo.data"
        real_write = undo_check.atomic_write

        def write(path, content):
            real_write(path, content)
            if path != undo:  # the backup: timew appends right after it
                undo.write_bytes(damaged + make_txn("20260801T050000Z", '["late"]').encode())

        monkeypatch.setattr(undo_check, "atomic_write", write)
        assert self.run(data, "--repair") == undo_check.EXIT_ERROR
        assert b"late" in undo.read_bytes()

    def test_detects_repair_overwritten_after_rename(self, tmp_path, monkeypatch, capsys):
        damaged = corrupt(make_journal())
        data = self.make_db(tmp_path, damaged)
        undo = data / "undo.data"
        real_write = undo_check.atomic_write

        def write(path, content):
            real_write(path, content)
            if path == undo:  # a timew that copied the old journal renames over ours
                undo.write_bytes(damaged)

        monkeypatch.setattr(undo_check, "atomic_write", write)
        assert self.run(data, "--repair") == undo_check.EXIT_ERROR
        assert "overwritten" in capsys.readouterr().err


@pytest.mark.skipif(shutil.which("timew") is None, reason="timew not installed")
class TestAgainstRealTimew:
    """End-to-end: prove timew rejects the corruption and accepts the repair."""

    def make_db(self, tmp_path, undo_data):
        db = tmp_path / "db"
        (db / "data").mkdir(parents=True)
        (db / "timewarrior.cfg").write_text("")
        (db / "data" / "undo.data").write_bytes(undo_data)
        (db / "data" / "2026-07.data").write_text(
            "".join(
                "inc 202607%02dT050000Z - 202607%02dT060000Z # tag%d\n" % (i + 1, i + 1, i)
                for i in range(5)
            )
        )
        return db

    def run_undo(self, db):
        env = dict(os.environ, TIMEWARRIORDB=str(db))
        return subprocess.run(
            ["timew", "undo"], env=env, capture_output=True, text=True
        )

    def test_timew_rejects_corrupt_journal(self, tmp_path):
        db = self.make_db(tmp_path, corrupt(make_journal(5)))
        result = self.run_undo(db)
        assert "Cannot handle line" in result.stdout + result.stderr

    def test_timew_accepts_repaired_journal(self, tmp_path):
        db = self.make_db(tmp_path, undo_check.strip_nuls(corrupt(make_journal(5))))
        result = self.run_undo(db)
        output = result.stdout + result.stderr
        assert "Cannot handle line" not in output
        assert "Undo" in output

    def test_timew_accepts_truncated_journal(self, tmp_path):
        """Truncating to the last N transactions must stay parseable."""
        db = self.make_db(tmp_path, undo_check.keep_last_transactions(make_journal(5), 2))
        result = self.run_undo(db)
        output = result.stdout + result.stderr
        assert "Cannot handle line" not in output
        assert "Undo" in output

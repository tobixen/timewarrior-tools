# timewarrior-tools

Various scripts and tools for use with [Timewarrior](https://timewarrior.net/).

**In the 0.x release series I can and I will change the behaviour of some of the scripts**.  The options for `summarize` has not been very well tought through, they have just been added "organically" to support my work flow.  I have on my list to refactor this.

Arguably some of the functionality here should be introduced in the core TimeWarrior code.  I'm intending to spend some time looking through the issue tracker and see if it makes sense to make any pull requests.

## Scripts

### summarize.py

A timewarrior report extension that summarizes tracked time by tag.

**Options** (via command-line or environment variables):

| Option | Env Var | Description |
|--------|---------|-------------|
| `--tags` | `TAGS` | Only include these tags (comma-separated, OR logic) |
| `--regex` | `REGEX` | Only include tags matching this regex |
| `--negregex` | `NEGREGEX` | Exclude tags matching this regex |
| `--killtags` | `KILLTAGS` | Skip intervals containing these tags (comma-separated) |
| `--ignoretags` | `IGNORETAGS` | Remove these tags from output (comma-separated) |
| `--concat` | `CONCAT` | Combine all tags on an interval into a single key |
| `--split` | `SPLIT` | Divide time equally among tags on an interval |
| `--min-duration` | `MIN_DURATION` | Fold tags with less total time than this (e.g. `5m`, `1h`) into one "(short intervals)" row |
| `--sort` | `SORT` | Row order: `tag` (default, alphabetical) or `time` (heaviest first) |
| `--unmatched` | `UNMATCHED` | Give in-scope time with no tag matching `--regex` a row under this label instead of dropping it |

**Usage:**

```bash
# Via timew report (traditional)
timew report summarize.py :yesterday
REGEX="^4" timew report summarize.py :week

# Direct invocation (auto re-execs via timew report)
summarize.py --regex="^4" --concat :yesterday
summarize.py --killtags="afk,break" :week
```

### aw-report.py

A timewarrior report extension that shows, for every timewarrior interval, what
[ActivityWatch](https://activitywatch.net/) recorded during it.  It needs
[aw-export-timewarrior](https://github.com/tobixen/aw-export-timewarrior) on the `PATH`.

**Options** (via command-line or environment variables):

| Option | Env Var | Description |
|--------|---------|-------------|
| `--aw-args` | `AW_ARGS` | Extra arguments for `aw-export-timewarrior report` (one quoted string) |
| `--min-duration` | `MIN_DURATION` | Skip intervals shorter than this (e.g. `5m`) |
| `--min-event-duration` | `MIN_EVENT_DURATION` | Hide ActivityWatch events shorter than this (e.g. `2s`) |
| `--edit` | `EDIT_MODE=1` | Open `$VISUAL`/`$EDITOR` on a script of `timew track :adjust` commands, one per interval with the activity as comments, and run it with `bash -e` on save.  Exits 1 if the editor or any command fails |

With colour on, each interval is followed by the `timew track :adjust` command
that would overwrite it.

**Usage:**

```bash
timew report aw-report.py :yesterday
aw-report.py --min-duration=5m --min-event-duration=2s :yesterday
aw-report.py --edit :yesterday
```

### diary.py

A timewarrior report extension for diary-style time summaries. Shows time spent on specified tags, with unmatched time shown as UNACCOUNTED.

**Options** (via command-line or environment variables):

| Option | Env Var | Description |
|--------|---------|-------------|
| `--tags`, `--tags-wanted` | `TAGS_WANTED` | Tags to track (comma-separated), others shown as UNACCOUNTED |
| `--pretty-alias` | `PRETTY_ALIAS` | Map tag to display name (repeatable, format: `tag:Alias`) |

**Usage:**

```bash
# Via timew report (traditional)
TAGS_WANTED="work,personal,exercise" timew report diary.py :yesterday

# Direct invocation (auto re-execs via timew report)
./diary.py --tags="work,personal,exercise" :yesterday

# With pretty aliases
./diary.py --tags="4me-personal-admin,4WORK" \
  --pretty-alias="4me-personal-admin:Personal admin" \
  --pretty-alias="4WORK:Work" :yesterday
```

### timew-change-tag

Change or rename tags across timewarrior intervals. Supports:

- Simple tag renaming: `timew-change-tag oldtag newtag`
- Tag combinations: `timew-change-tag 'tag1,tag2' 'newtag'`
- Tag removal: `timew-change-tag unwanted ''`
- Date filtering: `--from` and `--to` options
- Preview mode: `--dry-run`

### timew-undo-check

Check and repair timewarrior's `undo.data` journal.

Timewarrior writes `undo.data` by copying the whole file to a temp file, appending, and renaming it into place — without ever calling `fsync(2)` ([`AtomicFile.cpp`](https://github.com/GothenburgBitFactory/timewarrior/blob/develop/src/AtomicFile.cpp)). On ext4 an unclean shutdown can therefore bring the freshly written tail back zero-filled, gluing a run of NUL bytes onto the next `txn:` marker. Nothing notices, because only `timew undo` ever parses the journal — every other command copies the bad bytes forward. Weeks later you get:

```
$ timew undo
Cannot handle line '<NUL bytes>txn:'
```

| Option | Description |
|--------|-------------|
| `--repair` | Strip NUL runs left behind by an unclean shutdown.  A line the crash cut off mid-way cannot be repaired and is refused; add `--truncate` with a count that excludes the damaged transaction |
| `--truncate [N]` | Discard all but the last N transactions (default 200) |
| `--clean-tmp` | Delete `*.tmp` leftovers from interrupted timew runs |
| `--dry-run` | Report what would change, without writing |
| `--db DIR` | Data directory (default: `$TIMEWARRIORDB/data` or XDG) |
| `--no-backup` | Skip the timestamped backup copy |
| `--force` | Write even if a timew write looks in flight |

Exit status is 0 when the journal is clean, 1 when it is damaged, 2 on error — so it works as a cron/systemd health check.

Timewarrior takes no lock on `undo.data`.  The tool re-reads the journal right before and after its own write and refuses or complains if timew got in between, but that only narrows the window: run `--repair` and `--truncate` while nothing else (such as the aw-export-timewarrior sync daemon) is running timew.

**Usage:**

```bash
# Health check
timew-undo-check

# Fix corruption after a crash
timew-undo-check --repair

# Keep the journal small: copying a multi-megabyte undo.data on every
# single timew invocation is what makes the corruption likely in the
# first place.  Undo history beyond the last few dozen entries is dead weight.
timew-undo-check --truncate 200 --clean-tmp
```

**Why not just set `journal.size`?** Timewarrior does have an official pruning setting — `journal.size`, the number of transactions to keep, `-1` (the default) meaning unbounded and `0` disabling the journal entirely. It is undocumented; [discussion #593](https://github.com/GothenburgBitFactory/timewarrior/discussions/593) is the only description of it.

Setting it is a real trade-off rather than a straight win. With `journal.size > 1`, `Journal::endTransaction()` re-parses the entire journal on *every* transaction — so while the unbounded growth goes away, a single corrupt byte stops `timew start` and `timew stop` too, not just `timew undo`. Until the missing `fsync` is fixed upstream ([#772](https://github.com/GothenburgBitFactory/timewarrior/issues/772)), leaving `journal.size` at `-1` and truncating out-of-band with this tool keeps the blast radius of the next crash confined to the undo feature.

Backups are written to the parent of the data directory (as `undo.data.bak-<timestamp>`), deliberately not into the data directory itself — timew globs `*.data` there, and it is often a git repository.

### timew-short.sh

Status display script for showing current time tracking. Modes:

- Default: Simple text output with current tag and duration
- `waybar`: JSON output for waybar/swaybar with tooltip and css class support
- `start`: Start new tracking or cycle RETAGME counter

Supports `~css_class:X` tags for styling in status bars.

### timew-start-afk

Simple script to start tracking AFK time if not already tracking it.

## Installation

```bash
# Install (copies files)
make install

# For development (creates symlinks)
make install-dev

# Uninstall
make uninstall
```

This installs:
- `summarize.py`, `diary.py`, `aw-report.py` to `~/.config/timewarrior/extensions/`
- the same three plus `timew-change-tag`, `timew-undo-check`, `timew-short.sh`, `timew-start-afk` to `~/.local/bin/`, for direct invocation

`summarize.py`, `aw-report.py` and `timew-undo-check` support shell tab
completion when [argcomplete](https://github.com/kislyuk/argcomplete) is
installed and activated (`activate-global-python-argcomplete`).

## Related

- [aw-export-timewarrior](https://github.com/tobixen/aw-export-timewarrior) - Export data from ActivityWatch to Timewarrior
- [Blog post: Time tracking in practice](https://www.redpill-linpro.com/techblog/2025/08/21/time-tracking-in-practice.html) - How I use Timewarrior and ActivityWatch

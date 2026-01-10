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
| `--regex` | `REGEX` | Only include tags matching this regex |
| `--negregex` | `NEGREGEX` | Exclude tags matching this regex |
| `--killtags` | `KILLTAGS` | Skip intervals containing these tags (space-separated) |
| `--ignoretags` | `IGNORETAGS` | Remove these tags from output (space-separated) |
| `--concat` | `CONCAT` | Combine all tags on an interval into a single key |
| `--split` | `SPLIT` | Divide time equally among tags on an interval |

**Usage:**

```bash
# Via timew report (traditional)
timew report summarize.py :yesterday
REGEX="^4" timew report summarize.py :week

# Direct invocation (auto re-execs via timew report)
summarize.py --regex="^4" --concat :yesterday
summarize.py --killtags="afk break" :week
```

### timew-change-tag

Change or rename tags across timewarrior intervals. Supports:

- Simple tag renaming: `timew-change-tag oldtag newtag`
- Tag combinations: `timew-change-tag 'tag1,tag2' 'newtag'`
- Tag removal: `timew-change-tag unwanted ''`
- Date filtering: `--from` and `--to` options
- Preview mode: `--dry-run`

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
- `summarize.py` to `~/.config/timewarrior/extensions/`
- `timew-change-tag`, `timew-short.sh`, `timew-start-afk` to `~/.local/bin/`

## Related

- [aw-export-timewarrior](https://github.com/tobixen/aw-export-timewarrior) - Export data from ActivityWatch to Timewarrior
- [Blog post: Time tracking in practice](https://www.redpill-linpro.com/techblog/2025/08/21/time-tracking-in-practice.html) - How I use Timewarrior and ActivityWatch

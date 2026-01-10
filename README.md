# timewarrior-tools

Various scripts and tools for use with [Timewarrior](https://timewarrior.net/).

## Scripts

### summarize.py

A timewarrior report extension that summarizes tracked time by tag. Provides flexible filtering and grouping options via environment variables:

- `REGEX` - Only include tags matching this regex
- `NEGREGEX` - Exclude tags matching this regex
- `KILLTAGS` - Skip intervals containing these tags (space-separated)
- `IGNORETAGS` - Remove these tags from output (space-separated)
- `CONCAT` - Combine all tags on an interval into a single key
- `SPLIT` - Divide time equally among tags on an interval

Usage: `timew report summarize.py [timespan]`

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

## Related

- [aw-export-timewarrior](https://github.com/tobixen/aw-export-timewarrior) - Export data from ActivityWatch to Timewarrior
- [Blog post: Time tracking in practice](https://www.redpill-linpro.com/techblog/2025/08/21/time-tracking-in-practice.html) - How I use Timewarrior and ActivityWatch

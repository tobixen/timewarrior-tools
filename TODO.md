# TODO

## Completed

- [x] Look through work that wasn't committed, and make some good commit messages
- [x] Make a CHANGELOG according to the KeepAChangelog standard
- [x] Brush up the README
- [x] Rename myday.py to summarize.py
- [x] Investigate plugin parameter passing (see findings below)
- [x] Create a Makefile for installation

## Investigation Findings: Plugin Parameter Passing

### How timewarrior passes data to report plugins

Extensions receive all data via **stdin only** - no command line arguments are passed.

Input format:
1. Configuration header: All config values as `key: value` lines
2. Blank line separator
3. JSON data: Array of interval objects

Source: `~/timewarrior/src/commands/CmdReport.cpp` and `~/timewarrior/src/Extensions.cpp`

### GitHub Issue #230 - "Allow extensions to take extra options"

This is an **open enhancement request since 2019**. The maintainer acknowledges it would be useful but has concerns about argument disambiguation.

**Current workaround**: Use `rc.key=value` on the command line:
```bash
timew report summarize.py rc.REGEX="^4" rc.CONCAT=1 :yesterday
```
These appear in the config header and can be read by the extension.

### Solution Implemented

summarize.py now supports both approaches:

1. **Command-line options**: `--regex`, `--negregex`, `--killtags`, `--ignoretags`, `--concat`, `--split`
2. **Direct invocation**: When called from a terminal, it detects missing stdin and re-execs via `timew report`
3. **Config header parsing**: Falls back to reading options from the timew config header

Priority: command-line args > environment variables > config header

Example usage:
```bash
summarize.py --regex="^4" --concat :yesterday
```

## Future Ideas

- [ ] Consider contributing a documentation improvement to timewarrior about the `rc.` workaround

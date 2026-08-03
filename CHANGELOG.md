# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Added
- `timew-undo-check`: New tool to check and repair timewarrior's `undo.data` journal
  - Repairs the `Cannot handle line '<NUL bytes>txn:'` damage an unclean
    shutdown can leave behind, which stops `timew undo` from working at all
  - `--truncate [N]` to keep only recent undo history, `--clean-tmp` to remove
    leftovers from interrupted timew runs, `--dry-run` to preview
  - Exit status 0/1/2 (clean/damaged/error) for use as a health check

## [0.4.0] - 2026-01-26

### Added
- `summarize.py`: `--tags` option for explicit OR filtering without regex
- `diary.py`: New report extension for diary-style time summaries
  - Shows time spent on specified tags, unmatched time as UNACCOUNTED
  - `--tags`/`--tags-wanted` options (comma-separated tag list)
  - `--pretty-alias` option to map tags to display names (can be repeated)
  - Aliased tags are automatically included in wanted tags (no need to repeat in `--tags`)
  - Direct invocation support with auto re-exec via `timew report`
- `diary.py`: Diary update integration (requires diary-md package)
  - `--update-diary` to inject output into markdown diary
  - `--diary-file` to specify custom diary file path
  - `--section` to set diary section name (default: timewarrior)
  - `--dry-run` to preview changes without modifying files
  - `--commit` and `--push` for git operations
  - Lazy loading ensures script works without diary-md installed

### Changed
- `summarize.py`: Tags in `--killtags`, `--ignoretags` now comma-separated (breaking change)
- `diary.py`: `TAGS_WANTED` env var now uses comma-separated format
- `diary.py`: `PRETTY_ALIAS` env var now uses JSON format (allows any characters in aliases)

## [0.3.1] - 2026-01-10

### Fixed
- `summarize.py`: ANSI escape codes now display correctly (ESC character was missing)
- `summarize.py`: Boolean options (`--concat`, `--split`) now correctly fall back to environment variables when not set on command line

### Documentation
- Added links to related timewarrior issues (#209, #339, #64, #230) in summarize.py docstring

## [0.3.0] - 2026-01-10

### Added
- `summarize.py`: Command-line options (`--regex`, `--negregex`, `--killtags`, `--ignoretags`, `--concat`, `--split`)
- `summarize.py`: Direct invocation support - auto re-execs via `timew report` when called from terminal
- `summarize.py`: Configuration header parsing as fallback for options

### Changed
- `summarize.py`: Refactored to use argparse for argument handling

## [0.2.0] - 2026-01-10

### Added
- Makefile with `install`, `install-dev` (symlinks), and `uninstall` targets
- Installation documentation in README

### Documentation
- Investigated timewarrior plugin parameter passing (see TODO.md)
- Documented that environment variables and `rc.key=value` are the supported approaches

## [0.1.0] - 2026-01-10

### Added
- `timew-short.sh`: waybar output mode (`timew-short.sh waybar`) with JSON output
- `timew-short.sh`: Support for `~css_class:X` tags for styling in waybar/swaybar
- `timew-change-tag`: `--dry-run` option to preview changes
- `timew-change-tag`: `--verbose` option for detailed output
- `timew-change-tag`: Support for tag combinations (match intervals with multiple tags)
- `timew-change-tag`: Support for removing tags (empty replacement)

### Changed
- Renamed `myday.py` to `summarize.py` for clarity
- `timew-change-tag`: Rewritten from bash to Python with argparse
- `timew-change-tag`: Now uses `timew export` JSON instead of parsing summary output
- `timew-short.sh`: Handle css_class removal in 'start' mode

### Fixed
- `timew-short.sh`: Fixed tag DOM references (`dom.active.tag` -> `dom.active.tags`)

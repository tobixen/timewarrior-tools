# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

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

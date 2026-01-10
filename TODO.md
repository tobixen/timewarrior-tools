# TODO

## Completed

- [x] Look through work that wasn't committed, and make some good commit messages
- [x] Make a CHANGELOG according to the KeepAChangelog standard
- [x] Brush up the README
- [x] Rename myday.py to summarize.py

## Pending

### Investigate plugin parameter passing

summarize.py takes parameters as environment variables rather than --long-options.

- [ ] The script is intended to be invoked as a plugin via the `timew report` command, and I believe this is the easiest way to pass options to the script - is that correct? It should be investigated. The timewarrior source is available under ~/timewarrior
- [ ] I think the timew command does not take any --long-options (or short options), they have `:hints` instead. Based on this, it should be relatively trivial to pass all options starting with `-` to the report plugin and process everything not starting with `-` (and everything after `--`) by timew. Check the GitHub issues and pull requests if anyone has thought about this or similar ideas earlier.
- [ ] Check the contribution guidelines. If it's trivial to add support for this, then we should do it through a pull request, if not, we'll add a wrapper script for running the summarize report.

### Installation

- [ ] The plugin should be in ~/.config/timewarrior/extensions/ - create a Makefile that can install the file there. For me a symlink would be more appropriate than copy, so make a special development target for installing the symlink.

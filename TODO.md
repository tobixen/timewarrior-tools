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

### Conclusion

Environment variables work fine for now. The `rc.key=value` workaround is the "official" approach.

Options for improvement:
1. **Modify summarize.py** to also read from config header (in addition to env vars)
2. **Create a wrapper script** that parses `--options` and converts to `rc.key=value`
3. **Contribute to timewarrior** - Implement issue #230 (significant effort)

For now, the current environment variable approach is acceptable. A wrapper script like `~/bin/myday.sh` handles the complexity of setting the right variables.

## Future Ideas

- [ ] Consider adding config header parsing to summarize.py as fallback
- [ ] Consider contributing a documentation improvement to timewarrior about the `rc.` workaround

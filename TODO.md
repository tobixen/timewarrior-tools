# TODO

* ~~The aw-report should output the length of each interval~~ (done: shows duration in header, --min-duration to filter)
* ~~It should allow an --edit mode, where the timew commands stays as they are, but everything else is prepended with "# ".  Perhaps automatically throw the client into the editor and execute the file afterwards.~~ (done: --edit opens $EDITOR, executes on save)
* Code review and cleanups.
   * ~~The summarize-script should be able to combine tags by OR (explicitly - without involving regex)~~ (done: `--tags` option)
* Try to get the summarize.py bundled as extension script, or as a replacement for totals.py
* Propose that (some of the) bundled extension(s) should be included in the package and just work
* Follow up on issue #230
* ~~Tags should be comma-separated and not space separated in the summarize-script~~ (done in v0.3.1)
* ~~I have the diary report in the extension directory, it should be moved into this repository, and it should be made to accept options and wrap around timew in the same way as the summarize-report.~~ (done)
* Inevitably, there will be code duplication for the wrapping/reexec.  We should consider some ways to use shared code for this.
* (low priority) for the diary, if the `--tags`-list includes tags with a colon (say, dinner:fish), then `--pretty-alias=dinner:fish:Fish dinner` should do the Right Thing.
* (low priority) for the diary, an `--prettify`-option that will convert underscores to blanks and capitalize the tag
* `diary.py` adds every `--pretty-alias` key to `TAGS_WANTED`, which silently
  defeats `--tags`: pass the full alias table and the filter does nothing.
  Found while building a work-only report in `mydiary.sh`, worked around there
  by withholding aliases (`ONLY_KEYS`).  The two options should be independent
  — aliases are display, `--tags` is selection.

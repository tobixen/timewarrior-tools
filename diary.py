#!/usr/bin/env python3
"""Timewarrior report extension for diary-style time summaries.

Shows time spent on specified tags, with unmatched time shown as UNACCOUNTED.
Useful for personal time tracking where you want to see specific categories.

Can be called in two ways:

1. Via timew report (traditional):
   TAGS_WANTED="work,personal,exercise" timew report diary.py :yesterday

2. Directly with options (will re-exec via timew report):
   ./diary.py --tags="work,personal,exercise" :yesterday

Can also inject the output into a markdown diary (requires diary-md package):
   ./diary.py --tags="work,personal" --update-diary :yesterday
   ./diary.py --tags="work,personal" --update-diary --section=time --dry-run :yesterday
"""

import argparse
import datetime
import json
import os
import sys

from collections import defaultdict
from dateutil import tz

DATEFORMAT = "%Y%m%dT%H%M%SZ"


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Diary-style time summary by tag",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  timew report diary.py :yesterday
  TAGS_WANTED="work,personal" timew report diary.py :week
  ./diary.py --tags="work,personal,exercise" :yesterday

Diary update (requires diary-md package):
  ./diary.py --tags="work,personal" --update-diary :yesterday
  ./diary.py --tags="work" --update-diary --section=time --dry-run :yesterday
  ./diary.py --tags="work" --update-diary --diary-file=~/my-diary.md :yesterday
  ./diary.py --tags="work" --update-diary --commit :yesterday
        """
    )
    parser.add_argument('--tags', '--tags-wanted', metavar='TAGS', dest='tags',
                        help='Tags to track (comma-separated), others shown as UNACCOUNTED')
    parser.add_argument('--pretty-alias', metavar='TAG:ALIAS', action='append', dest='aliases',
                        help='Display alias for a tag (can be repeated)')
    parser.add_argument('--update-diary', action='store_true', dest='update_diary',
                        help='Inject output into diary (requires diary-md package)')
    parser.add_argument('--diary-file', metavar='PATH', dest='diary_file',
                        help='Diary file path (default: ~/solveig/diary-{year}.md)')
    parser.add_argument('--section', '-s',
                        help='Diary section name (default: timewarrior)')
    parser.add_argument('--dry-run', '-n', action='store_true', dest='dry_run',
                        help='Show what would be done without modifying files')
    parser.add_argument('--commit', action='store_true',
                        help='Git commit after updating diary')
    parser.add_argument('--push', action='store_true',
                        help='Git push after committing (implies --commit)')
    parser.add_argument('timew_args', nargs='*', metavar='ARG',
                        help='Arguments to pass to timew (tags, date ranges, etc.)')

    return parser.parse_args()


def get_option(name, args, configuration):
    """Get option value from args, environment, or configuration header.

    Priority: command-line args > environment variables > config header

    For boolean options (store_true), argparse sets False when not specified,
    so we only return the arg value if it's truthy (True), otherwise we fall
    through to check environment and config.
    """
    # Check command-line args (map option names to arg names)
    # Boolean options (store_true) need special handling - only return if True
    if name == 'TAGS_WANTED':
        arg_value = getattr(args, 'tags', None)
        if arg_value is not None:
            return arg_value
    elif name == 'PRETTY_ALIAS':
        arg_value = getattr(args, 'aliases', None)
        # aliases is a list from argparse, convert to JSON
        if arg_value:
            return json.dumps(arg_value)
    elif name == 'DIARY_UPDATE':
        # Boolean option - only return if explicitly True
        if getattr(args, 'update_diary', False):
            return True
    elif name == 'DIARY_FILE':
        arg_value = getattr(args, 'diary_file', None)
        if arg_value is not None:
            return arg_value
    elif name == 'DIARY_SECTION':
        arg_value = getattr(args, 'section', None)
        if arg_value is not None:
            return arg_value
    elif name == 'DIARY_DRY_RUN':
        # Boolean option - only return if explicitly True
        if getattr(args, 'dry_run', False):
            return True
    elif name == 'DIARY_COMMIT':
        # Boolean option - only return if explicitly True
        if getattr(args, 'commit', False):
            return True
    elif name == 'DIARY_PUSH':
        # Boolean option - only return if explicitly True
        if getattr(args, 'push', False):
            return True
    else:
        arg_value = getattr(args, name.lower(), None)
        if arg_value is not None:
            return arg_value

    # Check environment
    env_value = os.environ.get(name)
    if env_value is not None:
        return env_value

    # Check configuration header (from timew)
    return configuration.get(name)


def reexec_via_timew(args):
    """Re-execute this script via 'timew report' with options as env vars."""
    env = os.environ.copy()

    # Convert options to environment variables
    if args.tags:
        env['TAGS_WANTED'] = args.tags
    if args.aliases:
        # Pass as JSON to support any characters in aliases
        env['PRETTY_ALIAS'] = json.dumps(args.aliases)
    if args.update_diary:
        env['DIARY_UPDATE'] = '1'
    if args.diary_file:
        env['DIARY_FILE'] = args.diary_file
    if args.section:
        env['DIARY_SECTION'] = args.section
    if args.dry_run:
        env['DIARY_DRY_RUN'] = '1'
    if args.commit:
        env['DIARY_COMMIT'] = '1'
    if args.push:
        env['DIARY_PUSH'] = '1'

    # Build timew command
    script_name = os.path.basename(sys.argv[0])
    cmd = ['timew', 'report', script_name] + args.timew_args

    # Execute and replace this process
    os.execvpe(cmd[0], cmd, env)


def format_seconds(seconds):
    """Convert seconds to a formatted string.

    Convert seconds: 3961
    To formatted: "      1.1h"
    """
    hours = seconds / 3600
    return "{:9.1f}h".format(hours)


def parse_aliases(alias_str):
    """Parse alias string into a dict mapping tag -> display name.

    Format: JSON array of "tag:alias" strings, e.g. ["tag1:Alias 1", "tag2:Alias, two"]
    Split on first : so aliases can contain colons.
    """
    aliases = {}
    if not alias_str:
        return aliases
    pairs = json.loads(alias_str)
    for pair in pairs:
        if ':' in pair:
            tag, alias = pair.split(':', 1)
            aliases[tag.strip()] = alias.strip()
    return aliases


def calculate_totals(input_stream, args):
    """Calculate totals from timewarrior input.

    Returns a dict with:
        - output: list of output lines
        - diary_lines: list of lines suitable for diary (just the tag rows)
        - report_start: datetime of report start
        - report_end: datetime of report end
        - configuration: parsed timew configuration
    """
    from_zone = tz.tzutc()
    to_zone = tz.tzlocal()

    # Extract the configuration settings from header
    header = True
    configuration = {}
    body = ""

    for line in input_stream:
        if header:
            if line == "\n":
                header = False
            else:
                fields = line.strip().split(": ", 1)
                if len(fields) == 2:
                    configuration[fields[0]] = fields[1]
                else:
                    configuration[fields[0]] = ""
        else:
            body += line

    # Get pretty aliases
    alias_str = get_option('PRETTY_ALIAS', args, configuration)
    aliases = parse_aliases(alias_str)

    # Get tags option - tags with aliases are automatically wanted
    tags_str = get_option('TAGS_WANTED', args, configuration)
    if tags_str:
        TAGS_WANTED = {t.strip() for t in tags_str.split(",")}
    else:
        TAGS_WANTED = set()

    # Add aliased tags to wanted tags
    TAGS_WANTED.update(aliases.keys())

    if not TAGS_WANTED:
        return {
            'output': ["Error: No tags specified. Use --tags or --pretty-alias."],
            'diary_lines': [],
            'report_start': None,
            'report_end': None,
            'configuration': configuration,
        }

    j = json.loads(body)

    if "temp.report.start" in configuration:
        report_start_utc = datetime.datetime.strptime(configuration["temp.report.start"], DATEFORMAT)
        report_start_utc = report_start_utc.replace(tzinfo=from_zone)
        report_start = report_start_utc.astimezone(tz=to_zone)
    else:
        report_start_utc = None
        report_start = None

    if "temp.report.end" in configuration:
        report_end_utc = datetime.datetime.strptime(configuration["temp.report.end"], DATEFORMAT)
        report_end_utc = report_end_utc.replace(tzinfo=from_zone)
        report_end = report_end_utc.astimezone(tz=to_zone)
    else:
        report_end_utc = None
        report_end = None

    if len(j) == 0:
        if report_start is not None and report_end is not None:
            msg = "No data in the range {:%Y-%m-%d %H:%M:%S} - {:%Y-%m-%d %H:%M:%S}".format(report_start, report_end)
        elif report_start is None and report_end is not None:
            msg = "No data in the range until {:%Y-%m-%d %H:%M:%S}".format(report_end)
        elif report_start is not None and report_end is None:
            msg = "No data in the range since {:%Y-%m-%d %H:%M:%S}".format(report_start)
        else:
            msg = "No data to display"
        return {
            'output': [msg],
            'diary_lines': [],
            'report_start': report_start,
            'report_end': report_end,
            'configuration': configuration,
        }

    if "start" in j[0]:
        if report_start_utc is not None:
            j[0]["start"] = max(report_start_utc, datetime.datetime.strptime(j[0]["start"], DATEFORMAT).replace(tzinfo=from_zone)).strftime(DATEFORMAT)
        else:
            report_start_utc = datetime.datetime.strptime(j[0]["start"], DATEFORMAT).replace(tzinfo=from_zone)
            report_start = report_start_utc.astimezone(tz=to_zone)
    else:
        return {
            'output': ["Cannot display an past open range"],
            'diary_lines': [],
            'report_start': report_start,
            'report_end': report_end,
            'configuration': configuration,
        }

    if "end" in j[-1]:
        if report_end_utc is not None:
            j[-1]["end"] = min(report_end_utc, datetime.datetime.strptime(j[-1]["end"], DATEFORMAT).replace(tzinfo=from_zone)).strftime(DATEFORMAT)
        else:
            report_end_utc = datetime.datetime.strptime(j[-1]["end"], DATEFORMAT).replace(tzinfo=from_zone)
            report_end = report_end_utc.astimezone(tz=to_zone)
    else:
        if report_end_utc is not None:
            j[-1]["end"] = min(report_end_utc, datetime.datetime.now(tz=from_zone)).strftime(DATEFORMAT)
        else:
            j[-1]["end"] = datetime.datetime.now(tz=from_zone).strftime(DATEFORMAT)
            report_end = datetime.datetime.now(tz=to_zone)

    # Sum the seconds tracked by tag.
    totals = defaultdict(datetime.timedelta)
    unaccounted = set()

    for obj in j:
        start = datetime.datetime.strptime(obj["start"], DATEFORMAT).replace(tzinfo=from_zone)
        end = datetime.datetime.strptime(obj["end"], DATEFORMAT).replace(tzinfo=from_zone)

        tracked = end - start

        tag_match = set(obj.get("tags", [])).intersection(TAGS_WANTED)
        tag_mismatch = set(obj.get("tags", [])) - TAGS_WANTED
        obj["tags"] = list(tag_match)

        if not tag_match:
            obj["tags"].append("UNACCOUNTED")
            unaccounted = unaccounted.union(tag_mismatch)
        if len(tag_match) > 1:
            obj["tags"].append(",".join(sorted(tag_match)))
            obj["tags"].append("dupes!")

        for tag in obj["tags"]:
            totals[tag] += tracked

    # Determine largest tag width (using aliases where available).
    max_width = len("Total")
    for tag in totals:
        display_name = aliases.get(tag, tag)
        if len(display_name) > max_width:
            max_width = len(display_name)

    # Compose report header.
    output = [
        "",
        "Total by Tag, for {:%Y-%m-%d %H:%M:%S} - {:%Y-%m-%d %H:%M:%S}".format(report_start, report_end),
        ""
    ]

    # Compose table header.
    if configuration.get("color") == "on":
        output.append("\033[4m{:{width}}\033[0m \033[4m{:>10}\033[0m".format("Tag", "Total", width=max_width))
    else:
        output.append("{:{width}} {:>10}".format("Tag", "Total", width=max_width))
        output.append("{} {}".format("-" * max_width, "----------"))

    # Compose table rows (also collect diary lines).
    grand_total = 0
    diary_lines = []
    for tag in sorted(totals, key=lambda x: (int(x=="UNACCOUNTED")<<30)-totals[x].total_seconds()):
        seconds = int(totals[tag].total_seconds())
        formatted = format_seconds(seconds)
        grand_total += seconds
        display_name = aliases.get(tag, tag)
        row = "* {:{width}}   - {:10}".format(display_name, formatted, width=max_width)
        output.append(row)
        diary_lines.append(row)

    # Compose total.
    if configuration.get("color") == "on":
        output.append("{} {}".format(" " * max_width, "\033[4m          \033[0m"))
    else:
        output.append("{} {}".format(" " * max_width, "----------"))

    output.append("{:{width}} {:10}".format("Total", format_seconds(grand_total), width=max_width))
    output.append("")
    output.append(f"UNACCOUNTED had those tags: {unaccounted}")

    return {
        'output': output,
        'diary_lines': diary_lines,
        'report_start': report_start,
        'report_end': report_end,
        'configuration': configuration,
    }


def get_diary_options(args, configuration):
    """Get diary-related options from args or environment."""
    update_diary = get_option('DIARY_UPDATE', args, configuration)
    if isinstance(update_diary, str):
        update_diary = update_diary == '1'

    diary_file = get_option('DIARY_FILE', args, configuration)

    section = get_option('DIARY_SECTION', args, configuration) or 'timewarrior'

    dry_run = get_option('DIARY_DRY_RUN', args, configuration)
    if isinstance(dry_run, str):
        dry_run = dry_run == '1'

    commit = get_option('DIARY_COMMIT', args, configuration)
    if isinstance(commit, str):
        commit = commit == '1'

    push = get_option('DIARY_PUSH', args, configuration)
    if isinstance(push, str):
        push = push == '1'

    return {
        'update_diary': update_diary,
        'diary_file': diary_file,
        'section': section,
        'dry_run': dry_run,
        'commit': commit,
        'push': push,
    }


def update_diary_with_lines(lines, target_date, section, diary_file=None, dry_run=False, commit=False, push=False):
    """Update diary with timewarrior lines using diary-md package.

    Uses lazy loading - diary_md is only imported when this function is called.

    Args:
        lines: List of lines to add to the diary
        target_date: Date for the diary entry
        section: Section name within the date entry
        diary_file: Path to diary file (default: use diary-md's default)
        dry_run: If True, show what would be done without modifying
        commit: If True, git commit after updating
        push: If True, git push after committing
    """
    from pathlib import Path

    try:
        from diary_md.cli.update import update_diary, get_diary_file
        from diary_md.git import git_commit, git_push
    except ImportError:
        print("Error: diary-md package is not installed.", file=sys.stderr)
        print("Install it with: pip install diary-md", file=sys.stderr)
        sys.exit(1)

    if diary_file:
        diary_file = Path(diary_file).expanduser()
    else:
        diary_file = get_diary_file()

    for line in lines:
        update_diary(diary_file, target_date, section, line, dry_run)

    # Git operations
    if dry_run:
        if commit or push:
            print("Would commit changes")
        if push:
            print("Would push to remote")
    else:
        if push:
            commit = True  # --push implies --commit

        if commit:
            message = f"Add {target_date.strftime('%Y-%m-%d')} {section}"
            if git_commit(diary_file.parent, [diary_file], message):
                if push:
                    git_push(diary_file.parent)


def main():
    args = parse_args()

    # If stdin is a terminal, we're being called directly (not via timew report)
    # Re-exec via timew report with options converted to environment variables
    if sys.stdin.isatty():
        reexec_via_timew(args)
        # reexec_via_timew calls os.execvpe, so we never reach here

    # Called via timew report - process the input
    result = calculate_totals(sys.stdin, args)

    # Get diary options
    diary_opts = get_diary_options(args, result['configuration'])

    if diary_opts['update_diary']:
        # Update diary with the lines
        if not result['diary_lines']:
            print("No data to add to diary")
            sys.exit(0)

        # Use the report start date for the diary entry
        if result['report_start'] is None:
            print("Error: Cannot determine date for diary entry", file=sys.stderr)
            sys.exit(1)

        target_date = result['report_start']

        # Check if the report spans multiple days
        if result['report_end'] and result['report_start'].date() != result['report_end'].date():
            print(f"Warning: Report spans multiple days ({result['report_start'].date()} - {result['report_end'].date()})")
            print(f"Using {target_date.date()} for diary entry")

        update_diary_with_lines(
            result['diary_lines'],
            target_date,
            diary_opts['section'],
            diary_opts['diary_file'],
            diary_opts['dry_run'],
            diary_opts['commit'],
            diary_opts['push'],
        )
    else:
        # Just print the output
        for line in result['output']:
            print(line)


if __name__ == "__main__":
    main()

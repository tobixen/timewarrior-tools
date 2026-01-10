#!/usr/bin/env python3
"""Timewarrior report extension for diary-style time summaries.

Shows time spent on specified tags, with unmatched time shown as UNACCOUNTED.
Useful for personal time tracking where you want to see specific categories.

Can be called in two ways:

1. Via timew report (traditional):
   TAGS_WANTED="work,personal,exercise" timew report diary.py :yesterday

2. Directly with options (will re-exec via timew report):
   ./diary.py --tags="work,personal,exercise" :yesterday
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
        """
    )
    parser.add_argument('--tags', '--tags-wanted', metavar='TAGS', dest='tags',
                        help='Tags to track (comma-separated), others shown as UNACCOUNTED')
    parser.add_argument('--pretty-alias', metavar='TAG:ALIAS', action='append', dest='aliases',
                        help='Display alias for a tag (can be repeated)')
    parser.add_argument('timew_args', nargs='*', metavar='ARG',
                        help='Arguments to pass to timew (tags, date ranges, etc.)')

    return parser.parse_args()


def get_option(name, args, configuration):
    """Get option value from args, environment, or configuration header.

    Priority: command-line args > environment variables > config header
    """
    # Check command-line args (map option names to arg names)
    if name == 'TAGS_WANTED':
        arg_value = getattr(args, 'tags', None)
    elif name == 'PRETTY_ALIAS':
        arg_value = getattr(args, 'aliases', None)
        # aliases is a list from argparse, join for consistent string format
        if arg_value:
            return ','.join(arg_value)
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
        # Join multiple aliases with comma (aliases can contain : but not ,)
        env['PRETTY_ALIAS'] = ','.join(args.aliases)

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

    Format: "tag1:Alias 1,tag2:Alias 2"
    Split on first : so aliases can contain colons.
    """
    aliases = {}
    if not alias_str:
        return aliases
    for pair in alias_str.split(','):
        if ':' in pair:
            tag, alias = pair.split(':', 1)
            aliases[tag.strip()] = alias.strip()
    return aliases


def calculate_totals(input_stream, args):
    """Calculate totals from timewarrior input."""
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
        return ["Error: No tags specified. Use --tags or --pretty-alias."]

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
            return ["No data in the range {:%Y-%m-%d %H:%M:%S} - {:%Y-%m-%d %H:%M:%S}".format(report_start, report_end)]
        elif report_start is None and report_end is not None:
            return ["No data in the range until {:%Y-%m-%d %H:%M:%S}".format(report_end)]
        elif report_start is not None and report_end is None:
            return ["No data in the range since {:%Y-%m-%d %H:%M:%S}".format(report_start)]
        else:
            return ["No data to display"]

    if "start" in j[0]:
        if report_start_utc is not None:
            j[0]["start"] = max(report_start_utc, datetime.datetime.strptime(j[0]["start"], DATEFORMAT).replace(tzinfo=from_zone)).strftime(DATEFORMAT)
        else:
            report_start_utc = datetime.datetime.strptime(j[0]["start"], DATEFORMAT).replace(tzinfo=from_zone)
            report_start = report_start_utc.astimezone(tz=to_zone)
    else:
        return ["Cannot display an past open range"]

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

    # Compose table rows.
    grand_total = 0
    for tag in sorted(totals):
        seconds = int(totals[tag].total_seconds())
        formatted = format_seconds(seconds)
        grand_total += seconds
        display_name = aliases.get(tag, tag)
        output.append("* {:{width}}   - {:10}".format(display_name, formatted, width=max_width))

    # Compose total.
    if configuration.get("color") == "on":
        output.append("{} {}".format(" " * max_width, "\033[4m          \033[0m"))
    else:
        output.append("{} {}".format(" " * max_width, "----------"))

    output.append("{:{width}} {:10}".format("Total", format_seconds(grand_total), width=max_width))
    output.append("")
    output.append(f"UNACCOUNTED had those tags: {unaccounted}")

    return output


def main():
    args = parse_args()

    # If stdin is a terminal, we're being called directly (not via timew report)
    # Re-exec via timew report with options converted to environment variables
    if sys.stdin.isatty():
        reexec_via_timew(args)
        # reexec_via_timew calls os.execvpe, so we never reach here

    # Called via timew report - process the input
    for line in calculate_totals(sys.stdin, args):
        print(line)


if __name__ == "__main__":
    main()

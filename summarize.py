#!/usr/bin/env python3
"""Timewarrior report extension that summarizes tracked time by tag.

Can be called in two ways:

1. Via timew report (traditional):
   REGEX="^4" timew report summarize.py :yesterday

2. Directly with options (will re-exec via timew report):
   ./summarize.py --regex="^4" :yesterday
"""

import argparse
import datetime
import json
import os
import re
import subprocess
import sys

from collections import defaultdict
from dateutil import tz

DATEFORMAT = "%Y%m%dT%H%M%SZ"

# Options that can be set via environment variables or command-line
OPTIONS = ['REGEX', 'NEGREGEX', 'KILLTAGS', 'IGNORETAGS', 'CONCAT', 'SPLIT']


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Summarize timewarrior data by tag",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  timew report summarize.py :yesterday
  REGEX="^4" timew report summarize.py :week
  ./summarize.py --regex="^4" --concat :yesterday
  ./summarize.py --killtags="afk break" :week
        """
    )
    parser.add_argument('--regex', metavar='PATTERN',
                        help='Only include tags matching this regex')
    parser.add_argument('--negregex', metavar='PATTERN',
                        help='Exclude tags matching this regex')
    parser.add_argument('--killtags', metavar='TAGS',
                        help='Skip intervals containing these tags (space-separated)')
    parser.add_argument('--ignoretags', metavar='TAGS',
                        help='Remove these tags from output (space-separated)')
    parser.add_argument('--concat', action='store_true',
                        help='Combine all tags on an interval into a single key')
    parser.add_argument('--split', action='store_true',
                        help='Divide time equally among tags on an interval')
    parser.add_argument('timew_args', nargs='*', metavar='ARG',
                        help='Arguments to pass to timew (tags, date ranges, etc.)')

    return parser.parse_args()


def get_option(name, args, configuration):
    """Get option value from args, environment, or configuration header.

    Priority: command-line args > environment variables > config header
    """
    # Check command-line args
    arg_value = getattr(args, name.lower(), None)
    if arg_value is not None:
        if isinstance(arg_value, bool):
            return '1' if arg_value else None
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
    if args.regex:
        env['REGEX'] = args.regex
    if args.negregex:
        env['NEGREGEX'] = args.negregex
    if args.killtags:
        env['KILLTAGS'] = args.killtags
    if args.ignoretags:
        env['IGNORETAGS'] = args.ignoretags
    if args.concat:
        env['CONCAT'] = '1'
    if args.split:
        env['SPLIT'] = '1'

    # Build timew command
    script_name = os.path.basename(sys.argv[0])
    cmd = ['timew', 'report', script_name] + args.timew_args

    # Execute and replace this process
    os.execvpe(cmd[0], cmd, env)


def format_seconds(seconds):
    """Convert seconds to a formatted string.

    Convert seconds: 3661
    To formatted: "   1:01:01"
    """
    hours = seconds // 3600
    minutes = seconds % 3600 // 60
    seconds = seconds % 60
    return "{:4d}:{:02d}:{:02d}".format(hours, minutes, seconds)


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

    # Get options (args > env > config)
    REGEX = get_option('REGEX', args, configuration)
    NEGREGEX = get_option('NEGREGEX', args, configuration)
    KILLTAGS = get_option('KILLTAGS', args, configuration)
    IGNORETAGS = get_option('IGNORETAGS', args, configuration)
    CONCAT = get_option('CONCAT', args, configuration)
    SPLIT = get_option('SPLIT', args, configuration)

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
    untagged = None

    for obj in j:
        start = datetime.datetime.strptime(obj["start"], DATEFORMAT).replace(tzinfo=from_zone)
        end = datetime.datetime.strptime(obj["end"], DATEFORMAT).replace(tzinfo=from_zone)

        tracked = end - start

        if NEGREGEX:
            if any(re.search(NEGREGEX, tag) for tag in obj["tags"]):
                continue

        if REGEX:
            if not any(re.search(REGEX, tag) for tag in obj["tags"]):
                continue

        if KILLTAGS:
            if set(KILLTAGS.split(" ")).intersection(set(obj["tags"])):
                continue

        if IGNORETAGS:
            for tag in IGNORETAGS.split(" "):
                if tag in obj["tags"]:
                    obj["tags"].remove(tag)

        if "tags" not in obj or obj["tags"] == []:
            if untagged:
                untagged += tracked
            else:
                untagged = tracked
        else:
            if CONCAT:
                obj["tags"].sort()
                totals[",".join(obj["tags"])] += tracked
            else:
                if SPLIT:
                    tracked /= len(obj["tags"])
                for tag in obj["tags"]:
                    if REGEX and not re.search(REGEX, tag):
                        continue
                    if NEGREGEX and re.search(NEGREGEX, tag):
                        continue
                    totals[tag] += tracked

    # Determine largest tag width.
    max_width = len("Total")
    for tag in totals:
        if len(tag) > max_width:
            max_width = len(tag)

    # Compose report header.
    output = [
        "",
        "Total by Tag, for {:%Y-%m-%d %H:%M:%S} - {:%Y-%m-%d %H:%M:%S}".format(report_start, report_end),
        ""
    ]

    # Compose table header.
    if configuration.get("color") == "on":
        output.append("[4m{:{width}}[0m [4m{:>10}[0m".format("Tag", "Total", width=max_width))
    else:
        output.append("{:{width}} {:>10}".format("Tag", "Total", width=max_width))
        output.append("{} {}".format("-" * max_width, "----------"))

    # Compose table rows.
    grand_total = 0
    for tag in sorted(totals):
        seconds = int(totals[tag].total_seconds())
        formatted = format_seconds(seconds)
        grand_total += seconds
        output.append("{:{width}} {:10}".format(tag, formatted, width=max_width))

    if untagged is not None:
        seconds = int(untagged.total_seconds())
        formatted = format_seconds(seconds)
        grand_total += seconds
        output.append("{:{width}} {:10}".format("", formatted, width=max_width))

    # Compose total.
    if configuration.get("color") == "on":
        output.append("{} {}".format(" " * max_width, "[4m          [0m"))
    else:
        output.append("{} {}".format(" " * max_width, "----------"))

    output.append("{:{width}} {:10}".format("Total", format_seconds(grand_total), width=max_width))
    output.append("")

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

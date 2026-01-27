#!/usr/bin/env python3
"""Timewarrior report extension that shows ActivityWatch activity per interval.

For each timewarrior interval, runs `aw-export-timewarrior report` and prints
the output with a header showing tags and time range.

Can be called in two ways:

1. Via timew report (traditional):
   timew report aw-report.py :yesterday

2. Directly with options (will re-exec via timew report):
   ./aw-report.py :yesterday
   ./aw-report.py --aw-args="--format=json --all-columns" :yesterday
"""

import argparse
import datetime
import json
import os
import subprocess
import sys

from dateutil import tz

DATEFORMAT = "%Y%m%dT%H%M%SZ"


def parse_args():
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Show ActivityWatch activity per timewarrior interval",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  timew report aw-report.py :yesterday
  ./aw-report.py :yesterday
  ./aw-report.py --aw-args="--format=json --all-columns" :yesterday
  ./aw-report.py --aw-args="--no-truncate" :week
        """
    )
    parser.add_argument('--aw-args', metavar='ARGS', dest='aw_args',
                        help='Extra arguments to pass to aw-export-timewarrior report (quoted string)')
    parser.add_argument('timew_args', nargs='*', metavar='ARG',
                        help='Arguments to pass to timew (tags, date ranges, etc.)')

    return parser.parse_args()


def get_option(name, args, configuration):
    """Get option value from args, environment, or configuration header.

    Priority: command-line args > environment variables > config header
    """
    arg_value = getattr(args, name.lower(), None)
    if arg_value is not None:
        return arg_value

    env_value = os.environ.get(name)
    if env_value is not None:
        return env_value

    return configuration.get(name)


def reexec_via_timew(args):
    """Re-execute this script via 'timew report' with options as env vars."""
    env = os.environ.copy()

    if args.aw_args:
        env['AW_ARGS'] = args.aw_args

    script_name = os.path.basename(sys.argv[0])
    cmd = ['timew', 'report', script_name] + args.timew_args

    os.execvpe(cmd[0], cmd, env)


def parse_timew_input(input_stream):
    """Parse timewarrior header and JSON body from stdin.

    Returns (configuration dict, list of interval dicts).
    """
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

    intervals = json.loads(body) if body.strip() else []
    return configuration, intervals


def utc_to_local_iso(utc_str):
    """Convert a timewarrior UTC timestamp to local ISO 8601 string.

    Input:  '20250115T083000Z'
    Output: '2025-01-15T09:30:00+01:00' (depending on local timezone)
    """
    dt = datetime.datetime.strptime(utc_str, DATEFORMAT)
    dt = dt.replace(tzinfo=tz.tzutc())
    local_dt = dt.astimezone(tz.tzlocal())
    return local_dt.isoformat()


def format_local_time(utc_str):
    """Convert a timewarrior UTC timestamp to a short local time string.

    Input:  '20250115T083000Z'
    Output: '09:30' (depending on local timezone)
    """
    dt = datetime.datetime.strptime(utc_str, DATEFORMAT)
    dt = dt.replace(tzinfo=tz.tzutc())
    local_dt = dt.astimezone(tz.tzlocal())
    return local_dt.strftime("%H:%M")


def run_aw_report(start_utc, end_utc, extra_args):
    """Run aw-export-timewarrior report for a given time range.

    Returns the command's stdout as a string, or an error message.
    """
    from_iso = utc_to_local_iso(start_utc)
    to_iso = utc_to_local_iso(end_utc)

    cmd = ['aw-export-timewarrior', 'report',
           f'--from={from_iso}', f'--to={to_iso}']

    if extra_args:
        import shlex
        cmd.extend(shlex.split(extra_args))

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            stderr = result.stderr.strip()
            return f"[error running aw-export-timewarrior: {stderr}]"
        return result.stdout.rstrip('\n')
    except FileNotFoundError:
        return "[error: aw-export-timewarrior not found in PATH]"
    except subprocess.TimeoutExpired:
        return "[error: aw-export-timewarrior timed out]"


def main():
    args = parse_args()

    if sys.stdin.isatty():
        reexec_via_timew(args)

    configuration, intervals = parse_timew_input(sys.stdin)

    aw_args = get_option('AW_ARGS', args, configuration)

    if not intervals:
        print("No intervals found.")
        return

    for i, interval in enumerate(intervals):
        start = interval.get("start")
        end = interval.get("end")
        tags = interval.get("tags", [])

        if not start:
            print(f"[interval {i}: missing start timestamp, skipping]")
            continue

        if not end:
            end = datetime.datetime.now(tz=tz.tzutc()).strftime(DATEFORMAT)

        tags_str = ", ".join(tags) if tags else "(no tags)"
        time_str = f"{format_local_time(start)}–{format_local_time(end)}"

        print(f"=== {tags_str}  [{time_str}] ===")
        output = run_aw_report(start, end, aw_args)
        if output:
            print(output)
        print()


if __name__ == "__main__":
    main()

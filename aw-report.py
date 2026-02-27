#!/usr/bin/env python3
# PYTHON_ARGCOMPLETE_OK
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

try:
    import argcomplete
    HAS_ARGCOMPLETE = True
except ImportError:
    HAS_ARGCOMPLETE = False

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
  ./aw-report.py --min-duration=5m :yesterday
  ./aw-report.py --min-event-duration=2s :yesterday
  ./aw-report.py --edit :yesterday
        """
    )
    parser.add_argument('--aw-args', metavar='ARGS', dest='aw_args',
                        help='Extra arguments to pass to aw-export-timewarrior report (quoted string)')
    parser.add_argument('--min-duration', metavar='DURATION', dest='min_duration',
                        help='Skip intervals shorter than this (e.g., 5m, 1h, 30s)')
    parser.add_argument('--min-event-duration', metavar='DURATION', dest='min_event_duration',
                        help='Hide AW window events shorter than this (e.g., 2s, 1m) — passed to aw-export-timewarrior report --min-duration')
    parser.add_argument('--edit', action='store_true', dest='edit',
                        help='Open editor with timew track commands, then execute on save')
    parser.add_argument('timew_args', nargs='*', metavar='ARG',
                        help='Arguments to pass to timew (tags, date ranges, etc.)')

    if HAS_ARGCOMPLETE:
        argcomplete.autocomplete(parser)
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
    if args.min_duration:
        env['MIN_DURATION'] = args.min_duration
    if args.min_event_duration:
        env['MIN_EVENT_DURATION'] = args.min_event_duration

    script_name = os.path.basename(sys.argv[0])
    cmd = ['timew', 'report', script_name] + args.timew_args

    os.execvpe(cmd[0], cmd, env)


def fetch_intervals_via_export(timew_args):
    """Fetch intervals directly via 'timew export' instead of 'timew report'.

    This avoids the piped I/O that breaks interactive editors.
    Returns list of interval dicts, or exits on error.
    """
    cmd = ['timew', 'export'] + timew_args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"timew export failed: {result.stderr.strip()}", file=sys.stderr)
            sys.exit(1)
        return json.loads(result.stdout) if result.stdout.strip() else []
    except FileNotFoundError:
        print("Error: timew not found in PATH", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing timew export output: {e}", file=sys.stderr)
        sys.exit(1)


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


def parse_duration(duration_str):
    """Parse a duration string like '5m', '1h', '30s' into seconds.

    Returns None if the string is invalid.
    """
    import re
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([smh]?)$', duration_str.strip().lower())
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2) or 's'
    multipliers = {'s': 1, 'm': 60, 'h': 3600}
    return value * multipliers[unit]


def format_duration(seconds):
    """Format a duration in seconds as a human-readable string.

    Examples: '5m 30s', '1h 15m', '45s'
    """
    if seconds < 0:
        return "0s"
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    if secs or not parts:
        parts.append(f"{secs}s")
    return " ".join(parts)


def compute_duration(start_utc, end_utc):
    """Compute duration in seconds between two UTC timestamp strings."""
    start_dt = datetime.datetime.strptime(start_utc, DATEFORMAT)
    end_dt = datetime.datetime.strptime(end_utc, DATEFORMAT)
    return (end_dt - start_dt).total_seconds()


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
    """Convert a timewarrior UTC timestamp to a local datetime string.

    Input:  '20250115T083000Z'
    Output: '2025-01-15T09:30:00' (depending on local timezone)
    """
    dt = datetime.datetime.strptime(utc_str, DATEFORMAT)
    dt = dt.replace(tzinfo=tz.tzutc())
    local_dt = dt.astimezone(tz.tzlocal())
    return local_dt.strftime("%FT%H:%M:%S")


def run_editor_and_execute(script_content):
    """Write script to temp file, open editor, execute on save.

    Returns True if the script was executed, False if aborted.
    """
    import tempfile

    editor = os.environ.get('EDITOR', os.environ.get('VISUAL', 'vi'))

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.sh', prefix='aw-report-', delete=False
    ) as f:
        f.write(script_content)
        temp_path = f.name

    try:
        result = subprocess.run([editor, temp_path])
        if result.returncode != 0:
            print(f"Editor exited with code {result.returncode}, aborting.", file=sys.stderr)
            return False

        with open(temp_path) as f:
            edited_content = f.read()

        if not edited_content.strip():
            print("Script is empty, nothing to execute.")
            return False

        # Count uncommented timew commands
        cmd_count = sum(1 for line in edited_content.splitlines()
                       if line.strip() and not line.strip().startswith('#'))
        if cmd_count == 0:
            print("No commands to execute (all lines commented out).")
            return False

        print(f"Executing {cmd_count} command(s)...")
        result = subprocess.run(['bash', temp_path])
        return result.returncode == 0
    finally:
        os.unlink(temp_path)


def run_aw_report(start_utc, end_utc, extra_args, min_event_duration_secs=None):
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

    if min_event_duration_secs is not None:
        cmd.append(f'--min-duration={min_event_duration_secs}')

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
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

    # When called directly with --edit, fetch intervals via 'timew export'
    # instead of re-exec'ing via 'timew report'. This keeps stdin/stdout
    # connected to the terminal so the editor works properly.
    if sys.stdin.isatty() and args.edit:
        intervals = fetch_intervals_via_export(args.timew_args)
        configuration = {}
        edit_mode = True
    elif sys.stdin.isatty():
        reexec_via_timew(args)
        return  # unreachable, but makes flow clear
    else:
        configuration, intervals = parse_timew_input(sys.stdin)
        edit_mode = get_option('EDIT_MODE', args, configuration) == '1'

    aw_args = get_option('AW_ARGS', args, configuration)
    use_color = configuration.get("color", "on") != "off"

    min_duration_str = get_option('MIN_DURATION', args, configuration)
    min_duration_secs = None
    if min_duration_str:
        min_duration_secs = parse_duration(min_duration_str)
        if min_duration_secs is None:
            print(f"Invalid --min-duration value: {min_duration_str}", file=sys.stderr)
            sys.exit(1)

    min_event_duration_str = get_option('MIN_EVENT_DURATION', args, configuration)
    min_event_duration_secs = None
    if min_event_duration_str:
        min_event_duration_secs = parse_duration(min_event_duration_str)
        if min_event_duration_secs is None:
            print(f"Invalid --min-event-duration value: {min_event_duration_str}", file=sys.stderr)
            sys.exit(1)

    if not intervals:
        print("No intervals found.")
        return

    # Collect output: either print directly or build script for edit mode
    script_lines = []
    if edit_mode:
        script_lines.append("#!/bin/bash")
        script_lines.append("# Edit the timew track commands below, then save and exit.")
        script_lines.append("# Uncommented lines will be executed.")
        script_lines.append("")

    skipped_count = 0
    for i, interval in enumerate(intervals):
        start = interval.get("start")
        end = interval.get("end")
        tags = interval.get("tags", [])

        if not start:
            if edit_mode:
                script_lines.append(f"# [interval {i}: missing start timestamp, skipped]")
            else:
                print(f"[interval {i}: missing start timestamp, skipping]")
            continue

        if not end:
            end = datetime.datetime.now(tz=tz.tzutc()).strftime(DATEFORMAT)

        duration_secs = compute_duration(start, end)

        if min_duration_secs is not None and duration_secs < min_duration_secs:
            skipped_count += 1
            continue

        tags_str = ", ".join(tags) if tags else "(no tags)"
        time_str = f"{format_local_time(start)} - {format_local_time(end)}"
        duration_str = format_duration(duration_secs)
        tags_arg = " ".join(f'"{t}"' if " " in t else t for t in tags)
        track_cmd = f"timew track :adjust {time_str} {tags_arg}".rstrip()

        if edit_mode:
            script_lines.append(f"# === {tags_str}  [{time_str}]  ({duration_str}) ===")
            output = run_aw_report(start, end, aw_args, min_event_duration_secs)
            if output:
                for line in output.splitlines():
                    script_lines.append(f"# {line}")
            script_lines.append(track_cmd)
            script_lines.append("")
        else:
            print(f"=== {tags_str}  [{time_str}]  ({duration_str}) ===")
            output = run_aw_report(start, end, aw_args, min_event_duration_secs)
            if output:
                print(output)
            if use_color:
                print(f"To overwrite this interval, do:")
                print(f"\033[36m{track_cmd}\033[0m")
            print()

    if edit_mode:
        if skipped_count:
            script_lines.append(f"# ({skipped_count} interval(s) shorter than {min_duration_str} skipped)")
        script_content = "\n".join(script_lines) + "\n"
        run_editor_and_execute(script_content)
    else:
        if skipped_count:
            print(f"({skipped_count} interval(s) shorter than {min_duration_str} skipped)")


if __name__ == "__main__":
    main()

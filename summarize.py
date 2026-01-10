#!/usr/bin/env python3

import datetime
import json
import sys
import os
import re

from dateutil import tz
from collections import defaultdict

DATEFORMAT = "%Y%m%dT%H%M%SZ"


def format_seconds(seconds):
    """Convert seconds to a formatted string

    Convert seconds: 3661
    To formatted: "   1:01:01"
    """
    hours = seconds // 3600
    minutes = seconds % 3600 // 60
    seconds = seconds % 60
    return "{:4d}:{:02d}:{:02d}".format(hours, minutes, seconds)

def calculate_totals(input_stream):
    from_zone = tz.tzutc()
    to_zone = tz.tzlocal()

    # Environment
    REGEX = os.environ.get('REGEX')
    NEGREGEX = os.environ.get('NEGREGEX')
    KILLTAGS = os.environ.get('KILLTAGS')
    IGNORETAGS = os.environ.get('IGNORETAGS')
    CONCAT = os.environ.get('CONCAT')
    SPLIT = os.environ.get('SPLIT')

    # Extract the configuration settings.
    header = 1
    configuration = dict()
    body = ""

    for line in input_stream:
        if header:
            if line == "\n":
                header = 0
            else:
                fields = line.strip().split(": ", 2)
                if len(fields) == 2:
                    configuration[fields[0]] = fields[1]
                else:
                    configuration[fields[0]] = ""
        else:
            body += line

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

    for object in j:
        start = datetime.datetime.strptime(object["start"], DATEFORMAT).replace(tzinfo=from_zone)
        end = datetime.datetime.strptime(object["end"], DATEFORMAT).replace(tzinfo=from_zone)

        tracked = end - start

        if NEGREGEX:
            if any(re.search(NEGREGEX, tag) for tag in object["tags"]):
                continue

        if REGEX:
            if not any(re.search(REGEX, tag) for tag in object["tags"]):
                continue
            
        if KILLTAGS:
            if set(KILLTAGS.split(" ")).intersection(set(object["tags"])):
                continue

        if IGNORETAGS:
            for tag in IGNORETAGS.split(" "):
                if tag in object["tags"]:
                    object["tags"].remove(tag)
                
        if "tags" not in object or object["tags"] == []:
            if untagged:
                untagged += tracked
            else:
                untagged = tracked
        else:
            if CONCAT:
                object["tags"].sort()
                totals[",".join(object["tags"])] += tracked
            else:
                if SPLIT:
                    tracked /= len(object["tags"])
                for tag in object["tags"]:
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
    if configuration["color"] == "on":
        output.append("[4m{:{width}}[0m [4m{:>10}[0m".format("Tag", "Total", width=max_width))
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
    if configuration["color"] == "on":
        output.append("{} {}".format(" " * max_width, "[4m          [0m"))
    else:
        output.append("{} {}".format(" " * max_width, "----------"))

    output.append("{:{width}} {:10}".format("Total", format_seconds(grand_total), width=max_width))
    output.append("")

    return output


if __name__ == "__main__":
    for line in calculate_totals(sys.stdin):
        print(line)

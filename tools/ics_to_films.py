#!/usr/bin/env python3
"""Turn a venue's iCalendar export into screening entries for /calendar.

    python3 tools/ics_to_films.py arkadin.ics --venue Arkadin > entries.js
    python3 tools/ics_to_films.py arkadin.ics --venue Arkadin --splice

--splice rewrites calendar/index.html in place, replacing everything between
the FILMS:BEGIN and FILMS:END markers. Nothing outside those markers is
touched, so the generated block can be regenerated as often as the venue
updates without disturbing the rest of the page.

Titles: venues write long summaries carrying pre-shows, Q&As, series names and
sponsors. The automatic trim below handles the common shapes, but it will never
be right every time, so tools/film-titles.json maps URL slug to a final title
and always wins. Keying on slug rather than position means a hand-written title
survives the event moving, and a slug with no entry falls back to the trim.

Runs on the standard library alone, so it works in any environment that has the
repo checked out.
"""

import argparse
import json
import pathlib
import re
import sys
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PAGE = REPO / "calendar" / "index.html"
TITLES = HERE / "film-titles.json"

BEGIN = "/* FILMS:BEGIN"
END = "/* FILMS:END"

# Trailing clauses venues bolt onto a film's name. Applied to the summary in
# order, each cutting from the marker to the end of the string.
TRAILING = [
    r"\s+--\s.*$",
    r"\s+presented by\s.*$",
    r"\s+w/\s.*$",
    r"\s+\+\s+virtual\s.*$",
    r"\s+sponsored by\s.*$",
    r"\s+featuring\s.*$",
]


def unfold(raw: str) -> str:
    """Undo RFC 5545 line folding and normalise line endings."""
    return re.sub(r"\n[ \t]", "", raw.replace("\r\n", "\n"))


def unescape(value: str) -> str:
    return (value.replace("\\n", "\n").replace("\\,", ",")
                 .replace("\\;", ";").replace("\\\\", "\\"))


def parse_events(raw: str):
    """Yield {property: value} dicts, one per VEVENT. First value wins."""
    for block in re.findall(r"BEGIN:VEVENT\n(.*?)\nEND:VEVENT", raw, re.S):
        event = {}
        for line in block.split("\n"):
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            event.setdefault(key.split(";")[0], unescape(value))
        yield event


def trim_title(summary: str) -> str:
    title = summary
    for pattern in TRAILING:
        title = re.sub(pattern, "", title, flags=re.I)
    return title.strip(" .!-") or summary.strip()


def js_string(value: str) -> str:
    return value.replace("\\", "\\\\").replace("'", "\\'")


def build(ics_path: pathlib.Path, venue: str, overrides: dict):
    raw = unfold(ics_path.read_text(encoding="utf-8", errors="replace"))
    lines, unmatched = [], []
    for event in sorted(parse_events(raw), key=lambda e: e.get("DTSTART", "")):
        if not {"DTSTART", "DTEND", "SUMMARY", "URL"} <= event.keys():
            continue
        start = datetime.strptime(event["DTSTART"], "%Y%m%dT%H%M%S")
        end = datetime.strptime(event["DTEND"], "%Y%m%dT%H%M%S")
        runtime = int((end - start).total_seconds() // 60)
        slug = event["URL"].rstrip("/").split("/")[-1]
        if slug in overrides:
            title = overrides[slug]
        else:
            title = trim_title(event["SUMMARY"])
            unmatched.append((slug, event["SUMMARY"], title))
        lines.append(
            f"  {{date:ldt({start.year},{start.month},{start.day},"
            f"{start.hour},{start.minute}), runtime:{runtime}, "
            f"title:'{js_string(title)}', url:'{event['URL']}'}},")
    return lines, unmatched


def existing_entries() -> list[str]:
    """The entries already spliced into the page, for --merge."""
    page = PAGE.read_text()
    begin, end = page.find(BEGIN), page.find(END)
    if begin == -1 or end == -1:
        return []
    body = page[page.index("\n", begin) + 1:page.rindex("\n", 0, end)]
    return [line for line in body.split("\n") if line.strip()]


def entry_url(line: str) -> str:
    match = re.search(r"url:'([^']+)'", line)
    return match.group(1) if match else line


def entry_sort_key(line: str):
    match = re.search(r"ldt\((\d+),(\d+),(\d+),(\d+),(\d+)\)", line)
    return tuple(int(n) for n in match.groups()) if match else (0, 0, 0, 0, 0)


def merge(old: list[str], new: list[str]) -> list[str]:
    """Union by event URL, newest wins, back into date order.

    A venue exports one month at a time and consecutive months overlap at the
    boundary, so merging rather than replacing is what lets each export simply
    add to the run.
    """
    combined = {entry_url(line): line for line in old}
    combined.update({entry_url(line): line for line in new})
    return sorted(combined.values(), key=entry_sort_key)


def splice(entries: list[str]) -> None:
    page = PAGE.read_text()
    begin, end = page.find(BEGIN), page.find(END)
    if begin == -1 or end == -1:
        sys.exit(f"markers not found in {PAGE}")
    head = page[:page.index("\n", begin) + 1]
    tail = page[page.rindex("\n", 0, end) + 1:]
    PAGE.write_text(head + "\n".join(entries) + "\n" + tail)
    print(f"spliced {len(entries)} entries into {PAGE.relative_to(REPO)}",
          file=sys.stderr)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("ics", type=pathlib.Path)
    ap.add_argument("--venue", required=True, help="shown on the card, e.g. Arkadin")
    ap.add_argument("--splice", action="store_true",
                    help="rewrite calendar/index.html between the FILMS markers")
    ap.add_argument("--merge", action="store_true",
                    help="union with the entries already in the page instead of "
                         "replacing them, so each month's export adds to the run")
    args = ap.parse_args()

    overrides = json.loads(TITLES.read_text()) if TITLES.exists() else {}
    entries, unmatched = build(args.ics, args.venue, overrides)

    if not entries:
        sys.exit("no usable events: every VEVENT needs DTSTART, DTEND, SUMMARY and URL")

    if unmatched:
        print(f"{len(unmatched)} screening(s) had no entry in "
              f"{TITLES.name}, so the automatic trim was used. Check these and "
              f"add any that read badly:", file=sys.stderr)
        for slug, summary, title in unmatched:
            print(f"  {slug}\n    {summary}\n    -> {title}", file=sys.stderr)

    if args.merge:
        before = len(existing_entries())
        entries = merge(existing_entries(), entries)
        print(f"merged: {before} already in the page, {len(entries)} after union",
              file=sys.stderr)

    if args.splice:
        splice(entries)
    else:
        print("\n".join(entries))


if __name__ == "__main__":
    main()

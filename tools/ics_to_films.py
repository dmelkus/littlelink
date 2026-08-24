#!/usr/bin/env python3
"""Turn a venue's iCalendar export into screening entries for /calendar.

    python3 tools/ics_to_films.py arkadin.ics --venue Arkadin > entries.js
    python3 tools/ics_to_films.py arkadin.ics --venue Arkadin --splice

    curl -s https://events.webster.edu/film-series/calendar.ics -o webster.ics
    python3 tools/ics_to_films.py webster.ics --venue "Webster U." \
        --marker WEBSTER --tz America/Chicago --runtime-from-description --splice

--splice rewrites calendar/index.html in place, replacing everything between
the <marker>:BEGIN and <marker>:END comments (FILMS by default, one pair per
venue). Nothing outside those markers is touched, so the generated block can be
regenerated as often as the venue updates without disturbing the rest of the
page.

Two things vary between venues and are why the flags exist:

--tz, because an export may write UTC. Arkadin writes floating local times that
mean what they say, but Localist (Webster) writes everything as ...Z, and a
7:30 PM screening arrives as 00:30 the next day. Read that literally and every
film lands on the wrong date. Passing --tz converts into the venue's own zone;
without it, times are taken as given.

--runtime-from-description, because an export may not carry a real runtime.
Localist ends every event exactly one hour after it starts, a placeholder
rather than a measurement, but the description opens with the film's own
credit block -- "(Maciej Drygas, 2024, Poland, 81 minutes)" -- which is the
real figure. DTEND stays the fallback when no such figure is there.

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
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PAGE = REPO / "calendar" / "index.html"
TITLES = HERE / "film-titles.json"

def markers(marker: str) -> tuple[str, str]:
    return f"/* {marker}:BEGIN", f"/* {marker}:END"


# Venues state a runtime in the film's credit block at the head of the
# description: "(Director, Year, Country, 81 minutes)". Bounded to two or three
# digits so a stray year cannot match.
RUNTIME_IN_DESC = re.compile(r"(\d{2,3})\s*(?:minutes|mins?)\b", re.I)

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


def parse_dt(value: str, tz: ZoneInfo | None) -> datetime:
    """An iCalendar date-time as a naive local wall clock.

    A trailing Z means UTC, which is only meaningful with a zone to land it in;
    anything else is a floating time that already reads as local. Either way the
    result is naive, because that is what ldt() in the page takes.
    """
    if value.endswith("Z"):
        stamp = datetime.strptime(value, "%Y%m%dT%H%M%SZ")
        if tz is None:
            return stamp
        return stamp.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)
    return datetime.strptime(value, "%Y%m%dT%H%M%S")


def build(ics_path: pathlib.Path, venue: str, overrides: dict,
          tz: ZoneInfo | None = None, runtime_from_desc: bool = False):
    raw = unfold(ics_path.read_text(encoding="utf-8", errors="replace"))
    lines, unmatched, no_runtime = [], [], []
    for event in sorted(parse_events(raw), key=lambda e: e.get("DTSTART", "")):
        if not {"DTSTART", "DTEND", "SUMMARY", "URL"} <= event.keys():
            continue
        start = parse_dt(event["DTSTART"], tz)
        end = parse_dt(event["DTEND"], tz)
        runtime = int((end - start).total_seconds() // 60)
        slug = event["URL"].rstrip("/").split("/")[-1]
        if runtime_from_desc:
            found = RUNTIME_IN_DESC.search(event.get("DESCRIPTION", ""))
            if found:
                runtime = int(found.group(1))
            else:
                no_runtime.append((slug, runtime))
        if slug in overrides:
            title = overrides[slug]
        else:
            title = trim_title(event["SUMMARY"])
            unmatched.append((slug, event["SUMMARY"], title))
        lines.append(
            f"  {{date:ldt({start.year},{start.month},{start.day},"
            f"{start.hour},{start.minute}), runtime:{runtime}, "
            f"title:'{js_string(title)}', url:'{event['URL']}'}},")
    return lines, unmatched, no_runtime


def existing_entries(marker: str) -> list[str]:
    """The entries already spliced into the page, for --merge."""
    BEGIN, END = markers(marker)
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


def entry_key(line: str):
    """Identity of a screening, for the --merge union.

    Start time as well as URL, because the two are only interchangeable at some
    venues. Arkadin gives every screening its own listing, so the URL alone is
    unique there. Localist reuses one listing across a run, so all three nights
    of a film share a URL and keying on it drops two of them.
    """
    return (entry_sort_key(line), entry_url(line))


def merge(old: list[str], new: list[str]) -> list[str]:
    """Union by screening, newest wins, back into date order.

    A venue exports one month at a time and consecutive months overlap at the
    boundary, so merging rather than replacing is what lets each export simply
    add to the run.
    """
    combined = {entry_key(line): line for line in old}
    combined.update({entry_key(line): line for line in new})
    return sorted(combined.values(), key=entry_sort_key)


def splice(entries: list[str], marker: str) -> None:
    BEGIN, END = markers(marker)
    page = PAGE.read_text()
    begin, end = page.find(BEGIN), page.find(END)
    if begin == -1 or end == -1:
        sys.exit(f"{marker} markers not found in {PAGE}")
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
    ap.add_argument("--marker", default="FILMS",
                    help="which marker pair to write, e.g. WEBSTER (default: FILMS)")
    ap.add_argument("--tz", help="IANA zone the venue is in, e.g. America/Chicago. "
                                 "Only affects UTC (...Z) times; floating times "
                                 "are already local and are left alone.")
    ap.add_argument("--runtime-from-description", action="store_true",
                    help="take the runtime from the film's credit block in the "
                         "description, falling back to DTEND. For exports whose "
                         "DTEND is a fixed placeholder rather than a real end.")
    ap.add_argument("--splice", action="store_true",
                    help="rewrite calendar/index.html between the marker pair")
    ap.add_argument("--merge", action="store_true",
                    help="union with the entries already in the page instead of "
                         "replacing them, so each month's export adds to the run")
    args = ap.parse_args()

    tz = ZoneInfo(args.tz) if args.tz else None
    overrides = json.loads(TITLES.read_text()) if TITLES.exists() else {}
    entries, unmatched, no_runtime = build(
        args.ics, args.venue, overrides, tz, args.runtime_from_description)

    if not entries:
        sys.exit("no usable events: every VEVENT needs DTSTART, DTEND, SUMMARY and URL")

    if unmatched:
        print(f"{len(unmatched)} screening(s) had no entry in "
              f"{TITLES.name}, so the automatic trim was used. Check these and "
              f"add any that read badly:", file=sys.stderr)
        for slug, summary, title in unmatched:
            print(f"  {slug}\n    {summary}\n    -> {title}", file=sys.stderr)

    if no_runtime:
        print(f"{len(no_runtime)} screening(s) stated no runtime in the "
              f"description, so DTEND was used. Check these against the venue, "
              f"since DTEND is what --runtime-from-description distrusts:",
              file=sys.stderr)
        for slug, fallback in no_runtime:
            print(f"  {slug} -> {fallback}m", file=sys.stderr)

    if args.merge:
        before = len(existing_entries(args.marker))
        entries = merge(existing_entries(args.marker), entries)
        print(f"merged: {before} already in the page, {len(entries)} after union",
              file=sys.stderr)

    if args.splice:
        splice(entries, args.marker)
        print(f"{args.venue}: {len(entries)} screening(s) in the "
              f"{args.marker} block", file=sys.stderr)
    else:
        print("\n".join(entries))


if __name__ == "__main__":
    main()

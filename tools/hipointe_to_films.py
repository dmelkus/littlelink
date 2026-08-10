#!/usr/bin/env python3
"""Turn the Hi-Pointe showtimes API into screening entries for /calendar.

    # from a file you already have (no network)
    python3 tools/hipointe_to_films.py listings.json --until 2026-10-31

    # fetch once, then write it into the page
    python3 tools/hipointe_to_films.py --fetch --until 2026-10-31 --splice

Reads a local file by default and only touches the network when asked. The
venue is a small nonprofit cinema, so this should hit their server once per
refresh and never in a loop.

The site is WordPress and exposes showtimes at

    /wp-json/nj/v1/showtime/listings

as two lists joined on movie_id: `movies` carries name, runtime and release
year, `showtimes` carries the datetime and a per-screening purchase URL. That
covers every field a card needs, so unlike the Arkadin path there is no
iCalendar step and no title cleanup to guess at.

Runs on the standard library alone.
"""

import argparse
import json
import pathlib
import sys
import urllib.request
from datetime import datetime

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parent
PAGE = REPO / "calendar" / "index.html"

ENDPOINT = "https://hipointetheatre.org/wp-json/nj/v1/showtime/listings"
BEGIN = "/* HIPOINTE:BEGIN"
END = "/* HIPOINTE:END"


def fetch() -> dict:
    req = urllib.request.Request(ENDPOINT, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=40) as r:
        return json.load(r)


def as_int(value):
    """The feed uses strings, and release_year is sometimes null."""
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def card_title(movie: dict, shown: datetime) -> str:
    """Name, plus the release year when the film predates the screening.

    Repertory titles read better dated, new releases read worse. Names already
    carrying a format note keep it: '(35MM)', '(4K Restoration)'.
    """
    name = str(movie.get("movie_name", "")).strip()
    year = as_int(movie.get("release_year"))
    if year and year < shown.year and f"({year})" not in name:
        return f"{name} ({year})"
    return name


def build(data: dict, until: datetime | None):
    movies = {m["movie_id"]: m for m in data.get("movies", [])}
    entries, skipped = [], []
    for show in sorted(data.get("showtimes", []), key=lambda s: s.get("datetime", "")):
        movie = movies.get(show.get("movie_id"))
        if not movie:
            skipped.append((show.get("movie_id"), "no matching film"))
            continue
        try:
            when = datetime.strptime(show["datetime"], "%Y%m%d%H%M%S")
        except (KeyError, ValueError):
            skipped.append((show.get("movie_id"), "unreadable datetime"))
            continue
        if until and when > until:
            continue
        runtime = as_int(movie.get("runtime"))
        if not runtime:
            skipped.append((movie.get("movie_name"), "no runtime"))
            continue
        url = show.get("purchase_url", "")
        title = card_title(movie, when).replace("\\", "\\\\").replace("'", "\\'")
        entries.append(
            f"  {{date:ldt({when.year},{when.month},{when.day},"
            f"{when.hour},{when.minute}), runtime:{runtime}, "
            f"title:'{title}', url:'{url}'}},")
    return entries, skipped


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
    ap.add_argument("listings", nargs="?", type=pathlib.Path,
                    help="saved JSON from the endpoint; omit with --fetch")
    ap.add_argument("--fetch", action="store_true",
                    help="pull once from the live endpoint instead of reading a file")
    ap.add_argument("--until", help="drop screenings after this date, YYYY-MM-DD")
    ap.add_argument("--splice", action="store_true",
                    help="rewrite calendar/index.html between the HIPOINTE markers")
    args = ap.parse_args()

    if args.fetch:
        data = fetch()
    elif args.listings:
        data = json.loads(args.listings.read_text())
    else:
        ap.error("give a saved JSON file, or --fetch to pull one")

    until = datetime.strptime(args.until + " 23:59", "%Y-%m-%d %H:%M") if args.until else None
    entries, skipped = build(data, until)

    if not entries:
        sys.exit("no usable screenings")
    if skipped:
        print(f"skipped {len(skipped)}:", file=sys.stderr)
        for what, why in skipped:
            print(f"  {what}: {why}", file=sys.stderr)

    if args.splice:
        splice(entries)
    else:
        print("\n".join(entries))


if __name__ == "__main__":
    main()

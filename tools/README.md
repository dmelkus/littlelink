# tools

Scripts for maintaining `/calendar`. Standard library only, no install step, so
they run in any environment with the repo checked out.

## ics_to_films.py

Turns a venue's iCalendar export into screening entries for the timeline.

```sh
# preview
python3 tools/ics_to_films.py arkadin.ics --venue Arkadin

# write it into the page
python3 tools/ics_to_films.py arkadin.ics --venue Arkadin --splice
```

`--splice` replaces everything between the `FILMS:BEGIN` and `FILMS:END`
markers in `calendar/index.html` and touches nothing else, so it is safe to
re-run as often as a venue updates. Running it twice with the same input leaves
the file unchanged.

### Titles

Venues write long summaries carrying pre-shows, Q&As, series names and
sponsors:

    ANACONDA (1997) w/ scary snakes pre-show @ 6 pm

The cards want the film. The script trims the common trailing shapes
automatically, but that will never be right every time, so `film-titles.json`
maps URL slug to a final title and always wins. Anything with no entry falls
back to the trim and is reported on stderr for review:

    1 screening(s) had no entry in film-titles.json, so the automatic trim was used.
      the-thing-1982-friday-night-wtf
        THE THING (1982) -- Friday Night WTF!
        -> THE THING (1982)

Keying on slug rather than position means a hand-written title survives the
event moving in the calendar.

### Monthly refresh

Venues export one month at a time, and consecutive months overlap at the
boundary. `--merge` unions the new export with what is already in the page,
keyed on event URL, so each month adds rather than replaces:

```sh
python3 tools/ics_to_films.py september.ics --venue Arkadin --merge --splice
```

Without `--merge` the block is replaced outright, which is what you want only
when regenerating the whole run from a single export.

## hipointe_to_films.py

The Hi-Pointe runs WordPress and publishes showtimes as JSON at
`/wp-json/nj/v1/showtime/listings`: two lists joined on `movie_id`, one
carrying name, runtime and release year, the other the datetime and a
per-screening ticket link. Every field a card needs is already there, so there
is no iCalendar step and no title cleanup to guess at.

```sh
# from a file you already have, no network at all
python3 tools/hipointe_to_films.py listings.json --until 2026-10-31 --splice

# fetch once, then write it in
python3 tools/hipointe_to_films.py --fetch --until 2026-10-31 --splice
```

It reads a local file by default and only touches the network when asked.
These are small venues; hit them once per refresh, never in a loop.

`--until` drops screenings past a date. The feed currently runs to December
while the page ends at Halloween, so the run is capped rather than trailing
cards past its own ending.

Titles come through clean, so there is no overrides file. The release year is
appended only when the film predates the screening, which dates the repertory
without dating this year's releases, and format notes like `(35MM)` or
`(4K Restoration)` are kept as the venue wrote them.

### Adding a venue

Cards read `venue` from the object and filter on `group`, so a third venue is
another array with its own `venue`, `group` and `nodeClass`, concatenated into
`events` the same way, plus an entry in `GROUPS` for its legend chip.

## Refreshing

Arkadin publishes through Events Calendar Pro with `REFRESH-INTERVAL:PT1H`, so
the feed is live and the page holds a snapshot. Their iCalendar endpoint sits
behind Mod_Security and refuses scripted requests, so the export has to come
from a browser: use Export Events on their calendar page, then run with
`--merge --splice`.

Hi-Pointe's JSON endpoint answers scripted requests, so `--fetch` works there.

## Verification

The generator was checked by round-tripping: an `.ics` rebuilt in the venue's
exact shape (RFC 5545 folding, `TZID` parameters, escaped commas, unmodified
shouty summaries) regenerates the committed block byte for byte.

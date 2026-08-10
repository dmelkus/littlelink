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

### Adding a venue

Cards read `venue` from the object, so a second venue is a second `films`-style
array with its own `venue` value, concatenated into `events` the same way. The
`.map` that stamps `type`, `tag` and `venue` is where that happens.

## Refreshing

Arkadin publishes through Events Calendar Pro with `REFRESH-INTERVAL:PT1H`, so
the feed is live and the page holds a snapshot. Re-export, re-run with
`--splice`, and commit.

## Verification

The generator was checked by round-tripping: an `.ics` rebuilt in the venue's
exact shape (RFC 5545 folding, `TZID` parameters, escaped commas, unmodified
shouty summaries) regenerates the committed block byte for byte.

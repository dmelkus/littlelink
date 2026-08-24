# Working in this repo

Solo project. One person, one reviewer, no team. Process that exists to
coordinate strangers is pure overhead here, and it costs real tokens.

## No pull requests

**Commit and push straight to `main`.** Do not open a pull request, do not
create a working branch, and do not ask whether one is wanted.

`main` is what Cloudflare Workers deploys to `degs.chat`, so a push to `main`
is the publish step. There is no staging branch and nothing to stage for.

Branch-and-PR on this repo has actively cost time rather than saved it: a PR
against a stale side branch looked merged and green while production served
the old page, and reconciling that branch generated a second empty PR that had
to be closed. Nobody reviews these, so the ceremony buys nothing and hides
what is actually deployed.

If you genuinely need to isolate risky work, use a local branch and merge it
yourself before pushing. Do not surface it as a PR.

## Verifying front-end changes

The pages are static HTML with inline JS and no build step or test suite, so
"it looks right" has to be earned some other way. Drive the real page in a
browser before claiming a change works.

Chromium is preinstalled at `/opt/pw-browsers/chromium-1194/chrome-linux/chrome`;
`npm install playwright-core` in a scratch directory is enough to drive it.

Two things that will mislead you:

- **Serve the page, do not open it over `file://`.** Fonts and images use
  absolute paths (`/fonts/...`), which only resolve from the site root.
  `python3 -m http.server` from the repo root works.
- **Anything date-dependent needs the clock pinned.** `/calendar` renders
  entirely from the current time. Use `page.clock.setFixedTime()` with an
  explicit UTC offset in the timestamp and set `timezoneId` on the context to
  match, or the two disagree by hours and you will misread the result as a bug.

## Deploys

Pushing to `main` triggers a Cloudflare Workers build; it takes a minute or
two. A green build is not proof the bytes you expect are being served, so
confirm it by fetching the live page.

**Diff the whole file, do not grep for a marker, and fetch more than once.**
Cloudflare propagates to its edge nodes unevenly: one request can hit a node
that already has the update while the next hits a stale one. A single
successful `grep` has already reported a deploy as live while the page most
requests were getting was still the old version.

    for i in $(seq 1 6); do
      curl -s https://degs.chat/calendar/ -o /tmp/live.html
      diff -q /tmp/live.html calendar/index.html >/dev/null \
        && echo "$i: identical" || echo "$i: STALE $(wc -c < /tmp/live.html)"
      sleep 3
    done

Byte-identical on every fetch is the check that holds. Anything less can be a
stale edge answering.

# Working in this repo

Solo project. One person, one reviewer, no team. Process that exists to
coordinate strangers is pure overhead here, and it costs real tokens.

## No pull requests

**Commit and push straight to `main`.** Do not open a pull request, do not
create a working branch, and do not ask whether one is wanted.

`main` is what Cloudflare Workers deploys to `degs.skin`, so a push to `main`
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
two. Confirm it actually shipped by fetching the live page and grepping for
the change, rather than trusting the build status:

    curl -s https://degs.skin/calendar/ | grep -c "<a marker from your change>"

A green build is not proof the bytes you expect are being served.

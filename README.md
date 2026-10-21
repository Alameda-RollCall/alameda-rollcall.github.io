# Alameda Roll Call

Live site: https://alameda-rollcall.github.io/

An independent, static voting record for the Alameda City Council: how each
member voted on every recorded roll call since August 2013 (the start of
Alameda's Legistar archive), searchable by member, topic and outcome, with each
vote linked to the City's official meeting record. One HTML file, one JSON data
file, no framework, no backend.

It is **not affiliated with the City of Alameda**. Including someone in the
record (including November 2026 candidates and former members) is not an
endorsement or a comment on any race.

## How it works

Alameda's Legistar instance never populates the electronic vote-tally fields
(`/eventitems/{id}/votes`, `EventItemPassedFlag`, etc. are empty for every
meeting). The only machine-readable vote record is the *text* of the City
Clerk's minutes, filed as a "Minutes of ..." matter. The pipeline:

1. **`refresh_cache.py`**: fetches any newly filed "Minutes of ..." matters
   from the Legistar Web API (`webapi.legistar.com/v1/alameda`, council
   `BodyId` 138) into `minutes_cache/`.
2. **`rescrape_from_cache.py`**: parses every cached minutes document with the
   logic in **`scrape_votes.py`** (roll call, "carried by unanimous voice vote
   - N", "Ayes: ...; Noes: ...", absence/recusal notes, clerk corrections) and
   writes the raw `votes.scraped.historical.json`. No network access.
3. **`annotate_pipeline/annotate.py`**: assigns categories and a one-line,
   neutral, plain-English summary to each vote, using the full agenda title
   (`scrape_votes.py` keeps it as `title_full` because `title` is clipped at
   300 characters for the hand-written overrides).
   - **Summaries** come from title templates plus `summary_text.py`, which
     rewrites legal phrasing into a verb-led "what a yes vote does" sentence of
     25 words or fewer; it only rearranges and trims the title's own words.
     When a summary is cut it ends in "…" and the complete sentence is kept in
     `summary_full`, which the site shows on hover or tap.
   - **Main category** (`category`, used for counts) comes from regex rules in
     precedence order: hand-written overrides; strong subjects (appointments
     and city operations, business-improvement areas, land use, leases and real
     property, finance, housing); then contract-form items (an agreement,
     amendment, purchase or bid) become "Contracts & Purchasing" unless the
     contract's subject is plainly a topic; then the first-pass keyword rules.
     Measured on blind hand-labelled samples, this is about 82-85% exact and
     95%+ acceptable, against 55% / 70% for the first version.
   - **`also` tags** (up to four) mark a vote that spans topics: other
     categories plus 13 cross-cutting topic tags (Labor & Workforce, Policing &
     Civil Liberties, Homelessness & Social Services, Climate & Energy,
     Elections & Open Government, Utilities & Infrastructure, Schools, Youth &
     Libraries, Tenant Protections & Rent, Arts, Culture & History, COVID-19 &
     Public Health, Technology & Data, Real Property & Leases, Recreation
     Facilities) that are never a main category. "Alameda Point" is a place
     tag in the same row (listed first on any vote about the former Naval Air
     Station); the vote keeps its topical main category.
   - Hand-written overrides live in `manual2_titles.json` and
     `reso_ord_overrides.py`. **No LLM API call**, so it is free to re-run and
     auditable; every vote carries `"summary_source": "rules"`. Emails quoted
     in agenda titles are redacted. Also writes `draft_minutes_dates`: meetings after the
     latest one named in a minutes-approval vote, whose minutes are still unapproved drafts (the
     site labels their votes "draft minutes"). Writes `votes.json`.
4. **`post_coverage.py`** (optional): uses the Alameda Post's WordPress API to
   find *News* articles published from 4 days before to 10 days after each
   meeting and fetches the full text of those about the council.
   - It attaches an article to a vote (`coverage`) when its headline, tags or
     body share distinctive words and phrases with the agenda item (closed-
     session items and non-council stories are skipped; a match needs at least
     two rare words, such as names or specific programs). About 160 votes match.
   - For every other vote from 2022 on, the site shows an expandable list of the
     Post's "City Council" stories around that meeting (`post_council_stories`:
     tagged "City Council" or with a Council headline, up to 5 days before and
     7 days after; the tag is on about 90% of its council coverage). These cover
     the meeting generally, not necessarily the item. When a meeting has none,
     the site falls back to a keyword search built from `post_query` (the three
     most distinctive words of the item title; this finds the known article in
     the top 10 for about a third of items, against one in ten for the old
     first-60-characters query).
   - The Post's archive is nearly empty before 2022, so `post_archive_start`
     makes the site show no Post link for earlier votes.
   - Fetched articles are cached in `post_cache.json` / `post_articles.json`
     (git-ignored; re-fetch takes a few minutes). Matches are best-effort, so
     review a sample after changing the thresholds.
5. **`index.html`**: the entire site. It fetches `./votes.json` and shows a
   clear error if the file can't be loaded. The illustrative sample data is
   only shown with `?sample=1`.

6. **Videos and transcripts** (optional; run after steps 3 and 4, since `annotate.py` rewrites `votes.json`):
   - **`fetch_videos.py`** adds `meeting_videos` (date to Granicus clip ids) from
     Legistar's events API in one request. The site's "watch video" link opens the
     whole meeting; 308 of 309 meeting dates have a recording and two have two clips.
   - **`fetch_granicus_index.py`** + **`match_video_items.py`**: Granicus clip pages
     list the agenda items with start times for about 2013 to early 2021 (178
     meetings; none after that, except a few). A vote is matched to an entry by the
     words its title shares with the entry's text, rejecting near-duplicates that
     differ by a name (the Park Street and Webster Street business improvement
     areas). That gives `video_at` for about 580 votes, shown as "watch item" and
     opened with `?entrytime=`. Consent items that were not pulled have no entry.
     In a hand check of about 55 matches against Legistar's own titles, one was wrong.
   - **`fetch_youtube.py`** finds each council meeting on the City of Alameda YouTube
     channel (`meeting_youtube`) and downloads its auto-captions with `yt-dlp`, cached
     in `yt_cache/` (git-ignored). The channel has council meetings from 2025 (one
     from 2024); earlier meetings have only the Granicus video.
   - **`match_youtube_items.py`** matches each vote to an agenda item number and title from
     Legistar's event items, finds where the captions name that item ("item 7B"),
     and keeps the mention followed by the most title words (`yt_at`). A consent item
     never named aloud gets the time the consent calendar was taken up (`["id", sec,
     "c"]`). About 450 of 594 votes in captioned meetings are linked. These land
     within a minute or two of the item, and the site says so.
   - **`build_transcripts.py`** writes `transcripts/<date>.html`: the captions
     paragraphed at speaker changes with "um"/"uh" removed, each paragraph timestamped
     with a link into the YouTube video. These are machine captions, not a record.
`scrape_votes.py` can also be run directly (`python scrape_votes.py --since
YYYY-MM-DD --out file.json`) for a quick, small export straight from the API.

## Updating after a council meeting

Minutes are filed a few weeks after each meeting.

```bash
python3 -m venv venv && venv/bin/pip install requests   # first time only

venv/bin/python refresh_cache.py                        # pull new minutes
venv/bin/python rescrape_from_cache.py                  # parse everything
venv/bin/python annotate_pipeline/annotate.py           # categories + summaries -> votes.json
venv/bin/python post_coverage.py                        # optional: press links
venv/bin/python fetch_videos.py                         # meeting video links
venv/bin/python fetch_granicus_index.py                 # agenda item times (older meetings)
venv/bin/python match_video_items.py                    # link votes to those times
venv/bin/python fetch_youtube.py                        # YouTube videos + captions (needs yt-dlp)
venv/bin/python match_youtube_items.py                  # link votes to times in the captions
venv/bin/python build_transcripts.py                    # transcripts/<date>.html
```

Then **spot-check** a few new votes against the meeting record before
committing `votes.json`.

Things to watch for:

- **`annotate.py` stops with an `AssertionError`** naming a title its templates
  can't categorize. Add an entry to `annotate_pipeline/manual2_titles.json`
  (`"exact title": ["Category", "Neutral summary of what a YES vote does."]`).
  Don't skip it.
- **`tally mismatch` / `multi-motion segment` warnings** from
  `rescrape_from_cache.py` flag votes where the clerk's stated tally doesn't
  reconcile with the parsed roll call, or where one agenda item holds several
  differing motions (the last vote in an item wins). A handful are genuine
  inconsistencies in the City's own minutes. A jump in the count after a code
  change usually means a regression.
- **`roll-call typo`, `clerk name swap`, `outside tenure` warnings** mean the
  clerk named someone who could not have been seated (see below).
- After each election (December swearing-in), update `MEMBERS`, `TENURE` and
  `MEMBER_META` in `scrape_votes.py`.

### Run locally

`fetch()` doesn't work over `file://`, so serve the folder:

```bash
python3 -m http.server 8080     # then open http://localhost:8080
```

## Data notes

- **Terms** are not hand-entered. Each member's `start`, `end` and service
  `spans` come from their own roll-call appearances. A vote held before a
  member's start or after their end is never counted as an absence for them.
- **Clerk errors.** The minutes are typed by hand and sometimes name the wrong
  person. `TENURE` in `scrape_votes.py` records who could be seated when, and
  the parser uses it to correct unambiguous mistakes: for example, minutes from
  July 2017 to January 2018 list Daysog in the roll call where Vella sat (every
  motion in those meetings is Vella's), and some 2021-22 roll calls list Oddie
  for Herrera Spencer. Each correction is logged to stderr.
  `CLERK_VOTE_FIXES` holds the few one-off cases where the clerk's own stated
  tally ("Ayes: 4. Noes: 1.") contradicts the names and surrounding evidence
  says which name is the typo; the parser also logs every roll call whose stated
  tally disagrees with its names ("tally conflict") and leaves those as written.
- **The site is automated.** `index.html` carries a banner, a footer line and an
  About section saying the record is machine-parsed and may contain errors.
- **Absent vs. recused.** "Absent" means not recorded as present for that vote;
  "recused" means the minutes note the member stepped out for a conflict of
  interest. Absences can also be unrecorded recusals, so treat an absence as a
  prompt to check the record.
- **Meeting-record links** use `gateway.aspx?M=L&ID=<MatterId>`. (The file
  number, e.g. `2025-4829`, does *not* work: Legistar reads it as the number
  2025 and lands on an unrelated item.)
- **2026 candidates:** Mayor: Jensen, Daysog, Vella. Council candidates with no
  council record are listed on the About page. Source: the City Clerk's
  Elections page and the Alameda Post election page, 2026-10-20.

## Reporting errors

Every vote on the site has a "Report an error" link that opens a pre-filled
GitHub issue (vote id, title, meeting-record link). Create a `data-error` label
in the repository so those issues are tagged automatically. Corrections are made in the
parser's rules (`scrape_votes.py`, `annotate_pipeline/`) so one fix repairs every
vote with the same pattern; individual overrides go in `CLERK_VOTE_FIXES` or the
hand-written override files.

## Repository layout

| Path | What it is |
|---|---|
| `index.html`, `votes.json` | The site and its data |
| `refresh_cache.py`, `rescrape_from_cache.py`, `scrape_votes.py` | Fetch and parse the minutes |
| `annotate_pipeline/` | Categories, tags and summaries (`annotate.py`, `summary_text.py`, override tables) |
| `post_coverage.py` | Alameda Post links |
| `fetch_videos.py`, `fetch_granicus_index.py`, `match_video_items.py` | Meeting video links and item start times (Granicus) |
| `fetch_youtube.py`, `ytcaptions.py`, `match_youtube_items.py`, `build_transcripts.py` | YouTube captions: item times and `transcripts/` |
| `transcripts/` | Generated transcript pages, one per captioned meeting (about 8 MB) |
| `fonts/` | The site's typefaces (Public Sans, Zilla Slab; Latin subset, about 78 KB) with their license texts, hosted here so visitors make no request to Google |
| `.nojekyll` | Tells GitHub Pages to serve the folders as they are |
| `jsonio.py` | Compact, diff-friendly JSON writer |
| `tests/` | Category-accuracy samples and browser checks (see `tests/README.md`) |

Local-only (git-ignored): `minutes_cache/`, `post_cache.json`, `post_articles.json`, `venv/`.

## Data sources

| What | Where it comes from | Kept in this repo? |
|---|---|---|
| Votes, titles, dates, minutes links | City Clerk's minutes on Legistar (`webapi.legistar.com/v1/alameda`) | Yes, in `votes.json` (the parsed result; the raw minutes are not) |
| Agenda item numbers and titles, meeting video ids | Legistar events API | Video ids in `votes.json`; item lists are cached locally only |
| Meeting video | The City's Granicus archive (`alameda.granicus.com`), linked, not copied | Only clip ids and item start times |
| Agenda item start times, 2013 to early 2021 | Granicus clip pages | Start times only |
| Transcripts, 2025 on | YouTube's automatic captions on the City of Alameda channel, fetched with `yt-dlp` | Yes, as `transcripts/` pages, labelled as unofficial machine captions |
| Alameda Post article links | The Post's public WordPress API | Titles, dates and links only; article text stays in the git-ignored local cache |
| Council roster and tenure dates | Roll calls in the minutes, checked against City and news sources | Yes, in `votes.json` (`members`) |

Categories, tags, summaries and the draft-minutes label are computed by the
rules in `annotate_pipeline/`. The only hand-entered data are the override
tables, the clerk-typo corrections in `scrape_votes.py` (`CLERK_VOTE_FIXES`,
`TENURE`) and a few hand-written summaries for titles the rules handle poorly.

## License and data

The code is MIT-licensed (see `LICENSE`). The fonts in `fonts/` are under the SIL
Open Font License 1.1 (`fonts/OFL-*.txt`): Public Sans (The Public Sans Project
Authors) and Zilla Slab (The Mozilla Foundation). The votes are facts extracted from
the City of Alameda's public meeting minutes (published through Legistar), and
the "Official title" shown on each vote is the City's own agenda wording.
Alameda Post article titles and links are shown as links to the Post's
reporting, with credit; their text is not republished. This is an independent
project, not affiliated with or endorsed by the City of Alameda or the Alameda
Post.

## Accuracy and fairness

- Every vote links to the official meeting record.
- Summaries are neutral: what a YES vote does, not whether it was wise.
- Spot-checks so far compared parsed votes with the minutes text and caught
  several classes of parser error (recusals mislabelled as absences, a
  per-item abstention leaking onto other consent items, the clerk typos
  above). The minutes text itself is the source of truth, and the parser has
  not been audited against the live Legistar pages vote by vote, so report
  errors.

## Hosting

Any static host works; the site is plain files. Published with GitHub Pages
under the Alameda-RollCall organization.

Page views are counted with Cloudflare Web Analytics (a script tag at the end of
`index.html` and in the template in `build_transcripts.py`). To remove it, delete
those two snippets and rebuild the transcripts.

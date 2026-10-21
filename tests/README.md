# Tests

Three kinds of checks, all run from the repository root.

## Category accuracy (`tests/category_accuracy/`)

Four random samples of votes, hand-labelled from the agenda title alone
(before looking at the scheme's answer). Each label has a primary category and
acceptable alternates (a vendor contract whose subject is plainly a topic may be
filed under either).

```bash
python3 tests/category_accuracy/eval_categories.py 4     # samples 1-4
```

Results when this was written (original scheme -> current):

| Sample | Original (exact / acceptable) | Current (exact / acceptable) |
|---|---|---|
| 1 (100 votes; used while tuning) | 54% / 64% | 80% / 88% |
| 2 (100; partly tuned) | 54% / 65% | 86% / 96% |
| 3 (100; first read untuned) | 54% / 67% | 85% / 93% |
| 4 (80; never tuned on) | 55% / 71% | 85% / 98% |

Sampled votes that a later parser fix removed as duplicates are skipped. Samples 1-3 were used while adjusting the rules, so treat them as optimistic.
Sample 4 is the cleanest estimate. Labels are one person's judgment, and vote
ids only stay valid while the Legistar cache they were built from is unchanged.

## Data audit (`tests/data_audit/`)

Re-reads every cached minutes document with a different extraction (word-bounded
member names, cue words) than the parser uses, and compares it with `votes.json`.
It needs `minutes_cache/` (not committed), so it is a maintainer tool.

```bash
venv/bin/python tests/data_audit/audit.py     # agenda items whose text has a vote clause but no recorded vote
venv/bin/python tests/data_audit/audit_b.py   # each vote's last clause vs recorded positions (names, recusals, absences)
venv/bin/python tests/data_audit/audit_c.py   # roll calls vs tenure, results vs counts, duplicate ids
```

Each prints a count per check and writes `audit_*.json` (to `$AUDIT_OUT`, default the
temp dir). Some flags are expected and benign: items with several motions (the site
records the last), a member listed absent in the clerk's bracket but recused in the
prose (recorded as recused), and tenure start dates at a swearing-in.

## Browser checks (`tests/ui/`)

Plain HTML pages that load the site in an iframe, exercise it, and print
PASS/FAIL. Serve the repo and open them in Chrome:

```bash
python3 -m http.server 8080
# http://localhost:8080/tests/ui/ui-regression.html   (31 checks: filters, URL state, video and transcript links, draft-minutes label, CSV, ...)
# http://localhost:8080/tests/ui/tap-targets.html     (smallest tap target per element type, 380px wide)
# http://localhost:8080/tests/ui/search-highlight.html
```

Headless: `chrome --headless=new --virtual-time-budget=60000 --dump-dom <url>`.

# Tests

Two kinds of checks, both run from the repository root.

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

Samples 1-3 were used while adjusting the rules, so treat them as optimistic.
Sample 4 is the cleanest estimate. Labels are one person's judgment, and vote
ids only stay valid while the Legistar cache they were built from is unchanged.

## Browser checks (`tests/ui/`)

Plain HTML pages that load the site in an iframe, exercise it, and print
PASS/FAIL. Serve the repo and open them in Chrome:

```bash
python3 -m http.server 8080
# http://localhost:8080/tests/ui/ui-regression.html   (30 checks: filters, URL state, video and transcript links, draft-minutes label, CSV, ...)
# http://localhost:8080/tests/ui/tap-targets.html     (smallest tap target per element type, 380px wide)
# http://localhost:8080/tests/ui/search-highlight.html
```

Headless: `chrome --headless=new --virtual-time-budget=60000 --dump-dom <url>`.

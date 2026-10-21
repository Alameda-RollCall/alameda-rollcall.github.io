#!/usr/bin/env python3
"""Match Alameda Post articles to council votes by publication date and topic.

For each distinct meeting date in votes.json this finds the Post's *News*
articles published from a few days before to ~10 days after the meeting
(WordPress REST API), pulls the full text of the ones that concern the council,
and attaches up to two articles to a vote when the article's headline, tags or
body share distinctive words and phrases with the vote's agenda title.

Writes into votes.json:
  coverage                 per vote: [{title, url, date}] (item-level matches)
  post_council_stories     per meeting date (2022+): up to six News stories tagged
                           "City Council" (or with a Council headline) published
                           up to 5 days before / 7 days after the meeting, shown
                           on the site as an expandable list on votes without an
                           item-level match
  post_query               per vote: the three most distinctive words of the item,
                           used for the fallback "Search Alameda Post" link
  post_archive_start       first date the Post's archive can cover; votes before
                           it get no Alameda Post link at all

Caches (not committed): post_cache.json (windows), post_articles.json (bodies).

    python post_coverage.py            # fetch (cached) + match, rewrites votes.json
    python post_coverage.py --report   # print matches, don't write
"""
import argparse
import html
import json
import math
import os
import re
import sys
import time
from collections import Counter
from datetime import date, timedelta

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
VOTES = os.path.join(HERE, "votes.json")
CACHE = os.path.join(HERE, "post_cache.json")
ARTICLES = os.path.join(HERE, "post_articles.json")
API = "https://alamedapost.com/wp-json/wp/v2"
UA = {"User-Agent": "AlamedaRollCall/1.0 (civic transparency project)"}
DAYS_BEFORE, DAYS_AFTER = 4, 10
LIST_BAD_RE = re.compile(r"oakland|berkeley|san leandro|hayward|supervisor|school board|board of education|candidate|forum|meet your|"
                         r"voter guide|obituar|letters? to the editor|opinion|puzzle|postcast|news briefs|bear.s-eye", re.I)
CITY_COUNCIL_TAG = 2190        # the Post's "City Council" tag (on ~90% of its council coverage)
PREVIEW_DAYS, RECAP_DAYS = 5, 7  # stories this many days before / after a meeting
NEWS_CATEGORY = 384  # "News"; excludes Sports, Puzzles, Opinions, Podcast, Arts ...
# The Post's archive is nearly empty before 2022 (17 articles 2018-2021, 450+ in
# 2022 alone), so earlier votes cannot have coverage and get no Post link.
ARCHIVE_START = "2022-01-01"
MIN_SCORE = 30.0
MIN_SHARED = 3
MIN_IDF = 2.0  # words appearing in more than ~1 in 7 agenda items don't count
RARE_IDF = 4.0  # names and specific programs (in under ~2% of agenda items)

ROUNDUP_RE = re.compile(r"news briefs|letters? to the editor|bear.s-eye view|puzzle|postcast|opinion|"
                        r"obituar|calendar|week ahead|preview", re.I)
# Items whose titles are mostly staff names and boilerplate (closed sessions) and
# stories that are not about a council decision never get item-level matches.
SKIP_ITEM_RE = re.compile(r"^conference with|negotiators|^minutes of|^ratified bills|^designation of voting delegates", re.I)
NOT_COUNCIL_RE = re.compile(r"planning board|school board|board of education|candidate|vie for|forum|election results|"
                            r"transportation commission", re.I)


STOP = set("""
a about above after again all also an and any are as at be been before being between both but by can city
council councilmember councilmembers could did do does each for from had has have he her his how if in into is it
its just may more most no not of on one only or other our out over per she should so some such than that the their
them then there these they this those through to under up us was we were what when where which while who will with
would you your recommendation recommend authorize authorizes authorizing approve approves approving approval adopt
adopts adopting adoption resolution ordinance amending amends amend introduction introduce public hearing consider
agreement contract execute executing manager designee interim amount exceed fiscal year payable alameda california
municipal code section item items meeting minutes regular special joint certifies official record written ratified
bills accepted accept direction provide staff report update review authorized authorization approved adopted
agreements consent calendar following requested requests request establishing establish setting sets set making
makes make directing directs direct providing provides receive receives point project county second third fourth
first fifth general annual island january february march april june july august september october november december
building funding department district construction program services service street avenue park parks board commission
period term terms years
daysog herrera spencer jensen vella knox white ezzy ashcraft oddie matarrese boller pryor beaudin politzer thorne-lyman
jennifer gerry abigail adam
""".split())


def plain(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def words(text):
    return {w for w in re.findall(r"[a-z][a-z'\-]{3,}", (text or "").lower()) if w not in STOP}


def seq(text):
    return [w for w in re.findall(r"[a-z][a-z'\-]{3,}", (text or "").lower()) if w not in STOP]


def get(path, **params):
    for attempt in range(4):
        r = requests.get(f"{API}/{path}", params=params, timeout=60, headers=UA)
        if r.status_code == 200:
            time.sleep(0.4)
            return r.json()
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
    raise RuntimeError(f"failed: {path}")


def fetch_window(d, cache):
    if d in cache:
        return cache[d]
    day = date.fromisoformat(d)
    posts = get("posts", after=f"{(day - timedelta(days=DAYS_BEFORE)).isoformat()}T00:00:00",
                before=f"{(day + timedelta(days=DAYS_AFTER)).isoformat()}T23:59:59",
                per_page=100, orderby="date", _fields="id,date,link,title,excerpt,categories,tags")
    cache[d] = [{"id": p["id"], "date": p["date"][:10], "url": p["link"],
                 "title": plain(p["title"]["rendered"]), "text": plain(p["excerpt"]["rendered"]),
                 "categories": p["categories"], "tags": p["tags"]} for p in posts]
    return cache[d]


def load(path):
    return json.load(open(path)) if os.path.exists(path) else {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    data = json.load(open(VOTES))
    votes = data["votes"]
    dates = sorted({v["date"] for v in votes if v["date"] >= ARCHIVE_START})

    cache = load(CACHE)
    cache = {d: a for d, a in cache.items() if a and "categories" in a[0]} if cache else {}
    for i, d in enumerate(dates, 1):
        if d not in cache:
            try:
                fetch_window(d, cache)
            except Exception as e:
                print(f"  ! {d}: {e}", file=sys.stderr)
                continue
            if i % 25 == 0:
                json.dump(cache, open(CACHE, "w"))
    json.dump(cache, open(CACHE, "w"))

    # Tag names (for matching) and full bodies of News articles about the council.
    tag_ids = sorted({t for arts in cache.values() for a in arts for t in a["tags"]})
    tagnames = {}
    for k in range(0, len(tag_ids), 100):
        for t in get("tags", include=",".join(map(str, tag_ids[k:k + 100])), per_page=100, _fields="id,name"):
            tagnames[t["id"]] = plain(t["name"])
    arts_by_id = {a["id"]: a for arts in cache.values() for a in arts}
    news = {i: a for i, a in arts_by_id.items() if NEWS_CATEGORY in a["categories"] and not ROUNDUP_RE.search(a["title"])}
    bodies = load(ARTICLES)
    need = [i for i, a in news.items() if str(i) not in bodies and
            re.search(r"council", a["title"] + " " + a["text"] + " " + " ".join(tagnames.get(t, "") for t in a["tags"]), re.I)]
    for k in range(0, len(need), 50):
        for p in get("posts", include=",".join(map(str, need[k:k + 50])), per_page=50, _fields="id,content"):
            bodies[str(p["id"])] = plain(p["content"]["rendered"])
    json.dump(bodies, open(ARTICLES, "w"))
    print(f"{len(news)} News articles in windows, {len(bodies)} council bodies cached", file=sys.stderr)

    # IDF over agenda titles + summaries: a street name or program name counts
    # for a lot, "project" or "agreement" for nothing.
    df = Counter(w for v in votes for w in words(v["title"] + " " + v.get("summary", "")))
    n = len(votes)
    idf = lambda w: math.log(n / (1 + df[w]))

    # title-only IDF for the fallback search query (summary verbs like "proclaims"
    # and compounds like "three-year" make poor search words)
    dft = Counter(w for v in votes for w in words(v["title"]))
    idft = lambda w: math.log(n / (1 + dft[w]))

    matched = 0
    for v in votes:
        v.pop("coverage", None)
        v.pop("post_query", None)
        if v["date"] < ARCHIVE_START or SKIP_ITEM_RE.search(v["title"]):
            continue
        text = v["title"] + " " + v.get("summary", "")
        vw = {w for w in words(text) if idf(w) >= MIN_IDF}
        vs = seq(text)
        bigrams = {f"{a} {b}" for a, b in zip(vs, vs[1:])}
        scored = []
        for a in cache.get(v["date"], []):
            if a["id"] not in news or str(a["id"]) not in bodies or NOT_COUNCIL_RE.search(a["title"]):
                continue
            tags = " ".join(tagnames.get(t, "") for t in a["tags"])
            head = (a["title"] + " " + tags).lower()
            body = bodies[str(a["id"])].lower()
            aw_head = words(head)
            shared = {w for w in vw if w in aw_head or re.search(rf"\b{re.escape(w)}\b", body)}
            score = sum(idf(w) for w in shared) + sum(idf(w) for w in shared if w in aw_head)
            score += 4 * sum(1 for b in bigrams if b in body)
            rare = {w for w in shared if idf(w) >= RARE_IDF}
            head_hit = {w for w in shared if w in aw_head}
            ok = len(rare) >= 2 or (len(rare) >= 1 and head_hit and score >= 30)
            if len(shared) >= MIN_SHARED and score >= MIN_SCORE and ok:
                scored.append((score, a, sorted(shared)))
        scored.sort(key=lambda s: -s[0])
        # fallback for the site's "Search Alameda Post" link: the three most
        # distinctive words of the item (found the known article in the top 10
        # for 33% of votes, vs 10% for the old first-60-characters query)
        v["post_query"] = " ".join(sorted(words(v["title"]), key=lambda w: (-idft(w), w))[:3])
        if scored:
            matched += 1
            v["coverage"] = [{"title": a["title"], "url": a["url"], "date": a["date"]} for _, a, _ in scored[:2]]
            if args.report:
                print(f"{v['date']} | {v['title'][:72]}\n    -> {scored[0][1]['date']} {scored[0][1]['title'][:80]}  "
                      f"(score {scored[0][0]:.1f}, {scored[0][2][:7]})")

    # Council stories around each meeting (shown as an expandable list on votes
    # with no matched article): the Post's City Council tag or a "Council ..."
    # headline, previews up to PREVIEW_DAYS before and recaps up to RECAP_DAYS after.
    stories = {}
    for d in dates:
        day = date.fromisoformat(d)
        out = []
        for a in cache.get(d, []):
            if a["id"] not in news:
                continue
            ad = date.fromisoformat(a["date"])
            if not (day - timedelta(days=PREVIEW_DAYS) <= ad <= day + timedelta(days=RECAP_DAYS)):
                continue
            tagged = CITY_COUNCIL_TAG in a["tags"]
            headline = re.search(r"\bcouncil\b", a["title"], re.I)
            if (tagged or headline) and not LIST_BAD_RE.search(a["title"]):
                out.append({"title": a["title"], "url": a["url"], "date": a["date"], "kind": "recap" if ad > day else "preview"})
        out.sort(key=lambda x: (x["kind"] != "recap", x["date"]))
        if out:
            stories[d] = out[:6]
    data["post_council_stories"] = stories
    data["post_archive_start"] = ARCHIVE_START
    print(f"{matched} of {len(votes)} votes matched item-level; {len(stories)} of {len(dates)} meetings "
          f"have council stories listed", file=sys.stderr)
    if not args.report:
        from jsonio import write_data
        write_data(VOTES, data)


if __name__ == "__main__":
    main()

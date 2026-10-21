#!/usr/bin/env python3
"""Link votes to the moment their agenda item starts in the City's YouTube video.

For each meeting with captioned YouTube video (fetch_youtube.py):
  1. Legistar's event items give every agenda item's number (7-B) and title;
     each vote is matched to an item by title words (same matcher as the
     Granicus agenda index, match_video_items.py).
  2. The auto-captions are searched for the chair or clerk naming that item
     ("item 7B", "7 B", "7-B"); among the mentions, the one followed by the most
     of the item's title words wins.
A consent-calendar item that is never named aloud (they are approved together)
gets the time the regular consent calendar was taken up, marked "c". Anything
else never named gets no item time and keeps the whole-meeting link.

Writes into votes.json:
  yt_at   per vote: [YouTube video id, seconds into the video] or, for a consent
          item taken up with the rest of the consent calendar, [id, seconds, "c"]

    python match_youtube_items.py [--report]
"""
import argparse
import bisect
import json
import os
import re
import time

import requests

from match_video_items import match_votes, toks
from ytcaptions import load_cues

HERE = os.path.dirname(os.path.abspath(__file__))
VOTES = os.path.join(HERE, "votes.json")
ITEMS_CACHE = os.path.join(HERE, "legistar_items_cache.json")
API = "https://webapi.legistar.com/v1/alameda"
UA = {"User-Agent": "AlamedaRollCall/1.0 (civic transparency project)"}
LEAD_SECONDS = 4      # start slightly before the mention so the item's introduction isn't clipped
LOOKAHEAD = 90        # seconds after a mention searched for the item's title words
MIN_OVERLAP = 3       # title words that must follow a mention for it to count (2 for very short titles)
NOISE_AFTER = {"run", "minute", "minutes", "percent", "million", "thousand", "years", "year", "miles", "feet", "acres", "units", "days", "hours", "pm", "am"}
MENTION_RE = re.compile(r"\b(?:items?|agenda)?\s*#?\s*(\d{1,2})\s*[-–]?\s*([a-zA-Z])\b(?!['’])")


def get(path, **params):
    for attempt in range(4):
        r = requests.get(f"{API}/{path}", params=params, headers=UA, timeout=60)
        if r.status_code == 200:
            time.sleep(0.5)
            return r.json()
        time.sleep(2 ** attempt)
    r.raise_for_status()


def event_items(date, cache):
    if date in cache:
        return cache[date]
    items = []
    for e in get("events", **{"$filter": f"EventBodyId eq 138 and EventDate eq datetime'{date}'", "$select": "EventId"}):
        for i in get(f"events/{e['EventId']}/eventitems"):
            if i.get("EventItemAgendaNumber") and i.get("EventItemTitle"):
                items.append([i["EventItemAgendaNumber"], i.get("EventItemMatterFile") or "",
                              re.sub(r"\s+", " ", i["EventItemTitle"]).strip()])
    cache[date] = items
    return items


def mentions(cues):
    """[(seconds, 'NL')] for every spoken item number, e.g. 'item 7 B' -> (t, '7B')."""
    text, starts = "", []
    for t, x in cues:
        starts.append((len(text), t))
        text += x + " "
    offsets = [s for s, _ in starts]
    found = []
    for m in MENTION_RE.finditer(text):
        pos = bisect.bisect_right(offsets, m.start()) - 1
        found.append((starts[pos][1], f"{int(m[1])}{m[2].upper()}", pos, m.end()))
    return text, starts, found


def locate(label, title, cues, text, starts, found, rare):
    """Start second of the item: the mention of `label` followed by the most title words."""
    want = {w for w in toks(title)}
    best = None
    for t, lab, pos, end in found:
        if lab != label or re.match(r"\s*(%s)\b" % "|".join(NOISE_AFTER), text[end:end + 12], re.I):
            continue
        window = " ".join(x for tt, x in cues if t <= tt < t + LOOKAHEAD)
        shared = want & set(toks(window))
        score = sum(rare.get(w, 1.0) for w in shared)
        if len(shared) >= min(MIN_OVERLAP, max(2, len(want) - 1)) and (best is None or score > best[0] + 1e-9):
            best = (score, t)
    return best[1] if best else None


def consent_start(cues):
    """Second the regular meeting's consent calendar was taken up: the first time the chair
    says "consent calendar" and, within 2 minutes, asks whether anything is pulled, skipping
    the shorter consent calendars of closed-session and special/joint meetings."""
    for i, (t, x) in enumerate(cues):
        if not re.search(r"consent calendar", x, re.I):
            continue
        near = " ".join(y for tt, y in cues[max(0, i - 4):i + 6])
        if re.search(r"special|closed session|joint|sacic|agency|housing authority", near, re.I):
            continue
        after = " ".join(y for tt, y in cues[i:] if tt < t + 120)
        if re.search(r"\b(pull|pulled|pulling|pulls)\b", after, re.I) and re.search(r"routine|move on|moving on|next|start", near, re.I):
            return t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    data = json.load(open(VOTES))
    votes = data["votes"]
    for v in votes:
        v.pop("yt_at", None)
    cache = json.load(open(ITEMS_CACHE)) if os.path.exists(ITEMS_CACHE) else {}
    import collections
    import math
    df = collections.Counter(w for v in votes for w in toks(v["title"]))
    rare = {w: math.log(len(votes) / (1 + n)) + 0.5 for w, n in df.items()}
    linked = total = 0
    for date, ids in data.get("meeting_youtube", {}).items():
        items = event_items(date, cache)
        json.dump(cache, open(ITEMS_CACHE, "w"))
        consent_parents = {num for num, f, title in items if re.fullmatch(r"\d+", num) and title.startswith("Consent Calendar")}
        index = {date: [[k, f"{num} {f} {title}"] for k, (num, f, title) in enumerate(items) if f]}
        day_votes = [v for v in votes if v["date"] == date]
        m = match_votes(day_votes, {date: [date]}, index)
        for v in day_votes:  # the minutes call the bills item "Ratified bills ..."
            if v["id"] not in m and v["title"].startswith("Ratified bills"):
                bills = [e for e in index[date] if "Bills for Ratification" in e[1]]
                if bills:
                    m[v["id"]] = (1.0, 9, date, bills[0][0], bills[0][1])
        parsed = [(vid, *mentions(load_cues(vid))) for vid in ids]
        cue_sets = {vid: load_cues(vid) for vid in ids}
        total += len(day_votes)
        for v in day_votes:
            if v["id"] not in m:
                continue
            num, _, title = m[v["id"]][4].split(" ", 2)
            label = re.sub(r"[^0-9A-Z]", "", num.upper())
            for vid, text, starts, found in parsed:
                t = locate(label, title, cue_sets[vid], text, starts, found, rare)
                if t is not None:
                    v["yt_at"] = [vid, max(0, int(t) - LEAD_SECONDS)]
                    linked += 1
                    break
            else:
                parent = re.match(r"(\d+)-[A-Z]", num)
                if parent and parent[1] in consent_parents:
                    for vid in ids:
                        t = consent_start(cue_sets[vid])
                        if t is not None:
                            v["yt_at"] = [vid, max(0, int(t) - LEAD_SECONDS), "c"]
                            linked += 1
                            break
    print(f"{linked} of {total} votes in {len(data.get('meeting_youtube', {}))} captioned meetings linked to an item time")
    if not args.report:
        from jsonio import write_data
        write_data(VOTES, data)


if __name__ == "__main__":
    main()

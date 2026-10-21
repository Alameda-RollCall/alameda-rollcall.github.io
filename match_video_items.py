#!/usr/bin/env python3
"""Link votes to the moment their agenda item starts in the Granicus video.

Uses the agenda index cached by fetch_granicus_index.py (item title + start
second per clip; exists for most meetings from 2013 to early 2021). A vote is
matched to an index entry by the words its title shares with the entry's text,
and only when the best entry is clearly ahead of the runner-up. Consent-calendar
items that were not pulled for separate discussion have no index entry, so they
(and every later meeting) keep only the whole-meeting video link.

Writes into votes.json:
  video_at   per vote: [granicus clip id, seconds into the clip]

    python match_video_items.py [--report]
"""
import argparse
import collections
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
VOTES = os.path.join(HERE, "votes.json")
CACHE = os.path.join(HERE, "granicus_cache.json")
STOP = set("""a an and the of to for in on by with from at as or is be that this recommendation approve authorize adopt
resolution ordinance city manager council public hearing consider introduction final passage no minutes staff report""".split())
MIN_SHARED, MIN_SCORE, MIN_GAP = 3, 0.55, 0.12
GENERIC = set("alameda california municipal code chapter section amending authorizing approving fiscal year member members board commission committee".split())


def toks(s):
    s = re.sub(r"\(\d+\s*minu\w*\)", "", s, flags=re.I)
    s = re.sub(r"^\s*\d+(-[A-Z])?\s+(\d{4}-\d+\s+)?", "", s)
    return [w for w in re.findall(r"[a-z0-9][a-z0-9'\-]*", s.lower()) if w not in STOP and len(w) > 1]


def names(s):
    """Capitalized words (streets, people, lessees) once item numbers and file numbers are stripped."""
    s = re.sub(r"^\s*\d+(-[A-Z])?\s+(\d{4}-\d+\s+)?", "", s)
    return {w.lower() for w in re.findall(r"\b[A-Z][a-z]{2,}\b", s)} - STOP


# Look-alike items in one meeting that differ by a single name (the Park Street
# and Webster Street business improvement areas come up every year).
ALTERNATES = [{"park", "webster"}]


def conflicting(vote_title, entry_text, common=frozenset()):
    """True when the vote and the index entry name different things: each side
    has a distinguishing name the other lacks (e.g. two lease ordinances with
    different lessees), ignoring boilerplate and words common in agenda titles."""
    a, b = names(vote_title), names(entry_text)
    for alt in ALTERNATES:
        if (a & alt) and (b & alt) and not (a & b & alt):
            return True
    a, b = a - GENERIC - common, b - GENERIC - common
    return bool(a - b) and bool(b - a) and len(a & b) >= 1


def is_item(text):
    """Index entries for agenda items carry an item number or a file number."""
    return bool(re.match(r"\s*\d+-[A-Z0-9]", text) or re.search(r"\d{4}-\d+", text))


def match_votes(votes, videos, index):
    out = {}
    df = collections.Counter(w for v in votes for w in names(v["title"]))
    common = {w for w, n in df.items() if n / len(votes) >= 0.02}
    by_date = collections.defaultdict(list)
    for v in votes:
        by_date[v["date"]].append(v)
    for d, vs in by_date.items():
        pts = [(c, t, set(toks(x)), x) for c in videos.get(d, []) for t, x in index.get(c, []) if is_item(x)]
        pts = [p for p in pts if p[2]]
        for v in vs:
            vt = set(toks(v["title"]))
            if not vt or not pts:
                continue
            sc = []
            for c, t, s, x in pts:
                n = len(vt & s)
                sc.append((n / min(len(vt), len(s)) * 0.6 + n / len(vt | s) * 0.4, n, c, t, x))
            sc.sort(reverse=True)
            best = sc[0]
            if not os.environ.get("NO_CONFLICT") and conflicting(v["title"], best[4], common):
                continue
            if best[1] >= MIN_SHARED and best[0] >= MIN_SCORE and (len(sc) < 2 or best[0] - sc[1][0] >= MIN_GAP):
                out[v["id"]] = best
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args()
    data = json.load(open(VOTES))
    index = json.load(open(CACHE))
    for v in data["votes"]:
        v.pop("video_at", None)
    m = match_votes(data["votes"], data["meeting_videos"], index)
    for v in data["votes"]:
        if v["id"] in m:
            v["video_at"] = [m[v["id"]][2], m[v["id"]][3]]
    indexed = sum(1 for v in data["votes"] if any(index.get(c) for c in data["meeting_videos"].get(v["date"], [])))
    print(f"{len(m)} votes linked to an agenda item in the video ({indexed} votes are in meetings with an index)")
    if not args.report:
        from jsonio import write_data
        write_data(VOTES, data)


if __name__ == "__main__":
    main()

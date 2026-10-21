#!/usr/bin/env python3
"""Fetch the agenda index (item titles + start times) of each Granicus clip.

Older Alameda meetings (about 2013 to early 2021) have an index in the Granicus
player: one entry per agenda item with its start time in seconds. Later clips
have none. Results are cached in granicus_cache.json (not committed).

    python fetch_granicus_index.py
"""
import html
import json
import os
import re
import time

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "granicus_cache.json")
UA = {"User-Agent": "AlamedaRollCall/1.0 (civic transparency project)"}
POINT_RE = re.compile(r'class="index-point[^"]*"\s*role="link"\s*time="(\d+)"[^>]*>(.*?)</div>', re.S)


def parse(page):
    return [[int(t), re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", txt))).strip()]
            for t, txt in POINT_RE.findall(page)]


def main():
    data = json.load(open(os.path.join(HERE, "votes.json")))
    clips = sorted({c for ids in data["meeting_videos"].values() for c in ids}, key=int)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    for i, c in enumerate(clips, 1):
        if c in cache:
            continue
        for attempt in range(4):
            r = requests.get(f"https://alameda.granicus.com/player/clip/{c}", headers=UA, timeout=60)
            if r.status_code == 200:
                break
            time.sleep(2 ** attempt)
        else:
            print("  ! clip", c, r.status_code)
            continue
        cache[c] = parse(r.text)
        time.sleep(0.8)
        if i % 25 == 0:
            json.dump(cache, open(CACHE, "w"))
            print(i, "of", len(clips))
    json.dump(cache, open(CACHE, "w"))
    print(sum(1 for v in cache.values() if v), "of", len(cache), "clips have an agenda index")


if __name__ == "__main__":
    main()

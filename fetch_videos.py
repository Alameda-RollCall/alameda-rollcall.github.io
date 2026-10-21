#!/usr/bin/env python3
"""Attach each meeting's recorded video to votes.json.

Legistar's events API gives every City Council meeting an `EventMedia` value,
the clip id in the City's Granicus video archive. One request covers every
meeting; the player for a clip lives at
https://alameda.granicus.com/player/clip/<id>.

Writes into votes.json:
  meeting_videos   {meeting date: [clip id, ...]}, earliest meeting of the day
                   first. A date has more than one clip when the council held
                   two recorded sessions (for example a 5:30 PM closed session
                   and a 7:00 PM regular meeting). Dates with no recording are
                   left out, and the site shows no video link for them.

Legistar has no per-item timestamps, so the link opens the whole meeting video;
the Granicus player lists the agenda items.

    python fetch_videos.py
"""
import json
import os
import re

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
VOTES = os.path.join(HERE, "votes.json")
API = "https://webapi.legistar.com/v1/alameda/events"
COUNCIL_BODY_ID = 138
UA = {"User-Agent": "AlamedaRollCall/1.0 (civic transparency project)"}


def minutes_of_day(t):
    m = re.match(r"(\d+):(\d+)\s*([AP]M)", t or "", re.I)
    if not m:
        return 0
    h = int(m[1]) % 12 + (12 if m[3].upper() == "PM" else 0)
    return h * 60 + int(m[2])


def main():
    data = json.load(open(VOTES))
    dates = {v["date"] for v in data["votes"]}
    r = requests.get(API, headers=UA, timeout=60, params={
        "$filter": f"EventBodyId eq {COUNCIL_BODY_ID} and EventDate ge datetime'{min(dates)}'",
        "$select": "EventDate,EventTime,EventMedia", "$top": 1000})
    r.raise_for_status()
    by_date = {}
    for e in r.json():
        d = e["EventDate"][:10]
        if d in dates and e.get("EventMedia"):
            by_date.setdefault(d, []).append((minutes_of_day(e["EventTime"]), str(e["EventMedia"])))
    videos = {}
    for d, clips in sorted(by_date.items()):
        ids = []
        for _, c in sorted(clips):
            if c not in ids:
                ids.append(c)
        videos[d] = ids
    data["meeting_videos"] = videos
    missing = sorted(dates - set(videos))
    print(f"{len(videos)} of {len(dates)} meeting dates have video; "
          f"{sum(len(v) > 1 for v in videos.values())} have more than one clip; no video: {missing}")
    from jsonio import write_data
    write_data(VOTES, data)


if __name__ == "__main__":
    main()

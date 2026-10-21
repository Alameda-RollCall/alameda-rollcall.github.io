#!/usr/bin/env python3
"""Find each City Council meeting's video on the City of Alameda YouTube channel
and download its automatic captions (no video is downloaded).

The city has posted council meetings with captions since 2025 (a few from 2024).
Needs yt-dlp on the PATH (`pipx install yt-dlp` or `brew install yt-dlp`).

Writes into votes.json:
  meeting_youtube   {meeting date: [YouTube video id, ...]} (Part 1, Part 2 ... in order)
Caches captions in yt_cache/<id>.json3 (not committed).

    python fetch_youtube.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
VOTES = os.path.join(HERE, "votes.json")
CACHE = os.path.join(HERE, "yt_cache")
CHANNEL = "https://www.youtube.com/channel/UCWAAYtmrO1FVgAT6DszOYXQ/videos"  # City of Alameda
YTDLP = shutil.which("yt-dlp") or os.path.expanduser("~/.local/bin/yt-dlp")
SKIP_RE = re.compile(r"commission|board|town hall|authority|salaries|golf|planning", re.I)
TITLE_RE = re.compile(r"(\d{4})[ -](\d{1,2})[ -](\d{1,2})\s+(special\s+)?(city\s+council|council)", re.I)


def list_channel():
    out = subprocess.run([YTDLP, "--flat-playlist", "--print", "%(id)s|%(duration)s|%(title)s", CHANNEL],
                         capture_output=True, text=True, check=True).stdout
    found = {}
    for line in out.splitlines():
        vid, dur, title = line.split("|", 2)
        m = TITLE_RE.match(title)
        if not m or SKIP_RE.search(title):
            continue
        d = f"{m[1]}-{int(m[2]):02d}-{int(m[3]):02d}"
        found.setdefault(d, []).append((title, vid, int(float(dur or 0))))
    return {d: [v for _, v, _ in sorted(items)] for d, items in found.items()}


def main():
    data = json.load(open(VOTES))
    dates = {v["date"] for v in data["votes"]}
    found = list_channel()
    videos = {d: ids for d, ids in sorted(found.items()) if d in dates}
    skipped = sorted(set(found) - dates)
    print(f"{len(found)} council videos on the channel; {len(videos)} match a meeting in the data; unmatched dates: {skipped}")
    os.makedirs(CACHE, exist_ok=True)
    for d, ids in videos.items():
        for vid in ids:
            if os.path.exists(os.path.join(CACHE, f"{vid}.en.json3")):
                continue
            r = subprocess.run([YTDLP, "--skip-download", "--write-auto-subs", "--sub-langs", "en", "--sub-format", "json3",
                                "-o", os.path.join(CACHE, "%(id)s"), f"https://www.youtube.com/watch?v={vid}"],
                               capture_output=True, text=True)
            ok = os.path.exists(os.path.join(CACHE, f"{vid}.en.json3"))
            print(f"  {d} {vid}: {'captions saved' if ok else 'NO CAPTIONS ' + r.stderr.strip()[-120:]}")
            time.sleep(3)
    # keep only videos whose captions were fetched
    data["meeting_youtube"] = {d: [i for i in ids if os.path.exists(os.path.join(CACHE, f"{i}.en.json3"))] for d, ids in videos.items()}
    data["meeting_youtube"] = {d: ids for d, ids in data["meeting_youtube"].items() if ids}
    from jsonio import write_data
    write_data(VOTES, data)
    print(len(data["meeting_youtube"]), "meetings with captioned YouTube video")


if __name__ == "__main__":
    sys.path.insert(0, HERE)
    main()

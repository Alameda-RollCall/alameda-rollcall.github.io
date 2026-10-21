"""Read cached YouTube json3 captions into timed cues."""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
CACHE = os.path.join(HERE, "yt_cache")


def load_cues(video_id):
    """[(start_seconds, text)]: one cue per caption event, filler-free, in time order."""
    events = json.load(open(os.path.join(CACHE, f"{video_id}.en.json3")))["events"]
    cues = []
    for e in events:
        if "segs" not in e:
            continue
        text = "".join(s.get("utf8", "") for s in e["segs"]).replace("\n", " ")
        text = re.sub(r"\s+", " ", text).strip()
        if text:
            cues.append((e["tStartMs"] / 1000.0, text))
    return cues

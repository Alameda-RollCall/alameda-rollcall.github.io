#!/usr/bin/env python3
"""Add newly filed council 'Minutes of ...' matters to minutes_cache/ so
rescrape_from_cache.py + annotate_pipeline/annotate.py can rebuild votes.json.
Cache format matches the existing files: matters_list.json plus {id}.json
holding {"plain": MatterTextPlain, "file": MatterFile}."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import scrape_votes as sv

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "minutes_cache")


def main():
    lst_path = os.path.join(CACHE, "matters_list.json")
    known = json.load(open(lst_path))
    have = {m["MatterId"] for m in known}
    since = max(m["MatterIntroDate"] for m in known)[:10]
    flt = (f"MatterBodyId eq {sv.COUNCIL_BODY_ID} and MatterIntroDate ge datetime'{since}' "
           f"and startswith(MatterTitle, 'Minutes') eq true")
    new = [m for m in sv.paged(f"{sv.BASE}/matters", flt=flt, order="MatterIntroDate")
           if m["MatterId"] not in have]
    print(f"{len(new)} new matters since {since}")
    for m in new:
        mid = m["MatterId"]
        versions = sv.get(f"{sv.BASE}/matters/{mid}/versions")
        if not versions:
            continue
        text = sv.get(f"{sv.BASE}/matters/{mid}/texts/{versions[-1]['Key']}")
        with open(os.path.join(CACHE, f"{mid}.json"), "w") as f:
            json.dump({"plain": text.get("MatterTextPlain") or "", "file": m.get("MatterFile", "")}, f)
        known.append(m)
        print("  cached", mid, m["MatterTitle"][:70])
        time.sleep(0.3)
    json.dump(known, open(lst_path, "w"))


if __name__ == "__main__":
    main()

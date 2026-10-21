#!/usr/bin/env python3
"""
Re-run the (now bug-fixed) minutes parser over the full historical corpus
using the already-fetched Legistar cache in minutes_cache/, instead of
re-hitting the API for all 370 matters. Produces the same shape of output
as scrape_votes.main(), using the same parse_minutes_text / MEMBERS logic
so behavior stays identical to the live scraper.
"""
import json
import sys
import os

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import scrape_votes as sv

CACHE = os.path.join(HERE, "minutes_cache")
SINCE = "2013-08-01"
MIN_VOTERS = 3
OUT = os.path.join(HERE, "votes.scraped.historical.json")


def main():
    matters = json.load(open(os.path.join(CACHE, "matters_list.json")))
    print(f"{len(matters)} cached matters")

    out_votes = []
    missing_cache = 0
    for n, m in enumerate(matters, 1):
        mid = m["MatterId"]
        path = os.path.join(CACHE, f"{mid}.json")
        if not os.path.exists(path):
            missing_cache += 1
            continue
        cached = json.load(open(path))
        plain = cached.get("plain") or ""
        if not plain:
            continue
        matter_file = cached.get('file') or m.get('MatterFile', '')
        url = f"https://alameda.legistar.com/gateway.aspx?M=L&ID={mid}"  # MatterId, not file number
        for k, v in enumerate(sv.parse_minutes_text(plain, SINCE, matter_file=matter_file)):
            if len(v["votes"]) < MIN_VOTERS:
                continue
            v.update({
                "id": f"m{mid}-{k}",
                "summary": sv.summarize_stub(v["title"]),
                "category": sv.categorize_keyword(v["title"]),
                "url": url,
            })
            out_votes.append(v)
        if n % 50 == 0:
            print(f"  processed {n}/{len(matters)}, {len(out_votes)} votes so far")

    if missing_cache:
        print(f"WARNING: {missing_cache} matters had no cached text", file=sys.stderr)

    seen_keys, deduped = set(), []
    for v in out_votes:
        key = (v["date"], v["title"], json.dumps(v["votes"], sort_keys=True))
        if key not in seen_keys:
            seen_keys.add(key)
            deduped.append(v)
    out_votes = deduped
    print(f"Collected {len(out_votes)} votes (post-dedup)")

    from datetime import datetime, timezone
    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "Legistar Web API (alameda) — parsed from official minutes text",
        "members": sv.build_members(out_votes),
        "council_candidates_no_record": sv.COUNCIL_CANDIDATES_NO_RECORD,
        "votes": sorted(out_votes, key=lambda v: v["date"], reverse=True),
    }
    with open(OUT, "w") as f:
        json.dump(data, f, indent=1)
    print(f"Wrote {OUT}")

    dates = [v["date"] for v in out_votes]
    print(f"Date range: {min(dates)} .. {max(dates)}")


if __name__ == "__main__":
    main()

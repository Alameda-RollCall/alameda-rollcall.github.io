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

    # Keep each vote's id stable across rebuilds (ids are permalinks): a vote that
    # was already in the previous output keeps its id; a newly parsed vote gets the
    # next unused index in its matter instead of shifting everything after it.
    prev_ids, max_k = {}, {}
    if os.path.exists(OUT):
        for pv in json.load(open(OUT))["votes"]:
            pm, _, pk = pv["id"][1:].partition("-")
            prev_ids.setdefault((pm, pv["date"], pv["title"]), []).append(int(pk))
            max_k[pm] = max(max_k.get(pm, -1), int(pk))
    for ks in prev_ids.values():
        ks.sort()

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
        for v in sv.parse_minutes_text(plain, SINCE, matter_file=matter_file):
            if len(v["votes"]) < MIN_VOTERS:
                continue
            old = prev_ids.get((str(mid), v["date"], v["title"]))
            if old:
                k = old.pop(0)
            else:
                max_k[str(mid)] = k = max_k.get(str(mid), -1) + 1
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

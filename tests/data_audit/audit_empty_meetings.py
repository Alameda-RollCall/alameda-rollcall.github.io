#!/usr/bin/env python3
"""List council meetings whose minutes contain vote clauses ("seconded", "Ayes:", "roll call
vote", "unanimous") but have no vote in votes.json. These are the free-form special
meetings the parser can't itemise; fix them with EXTRA_VOTES in scrape_votes.py.
Needs minutes_cache/. Run after every rebuild:  venv/bin/python tests/data_audit/audit_empty_meetings.py"""
import glob, json, os, re, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import scrape_votes as s

have = {}
for v in json.load(open(os.path.join(ROOT, "votes.json")))["votes"]:
    have[v["date"]] = have.get(v["date"], 0) + 1
CLAUSE = re.compile(r"seconded|\bAyes?\s*[:\-]|roll call vote|unanimous", re.I)
PROCEDURAL = re.compile(r"speaking|minutes? to|adjourn", re.I)
rows = {}
for f in glob.glob(os.path.join(ROOT, "minutes_cache", "[0-9]*.json")):
    d = json.load(open(f))
    plain = s.MIDWORD_ARTIFACT_RE.sub("", d["plain"])
    starts = [m.start() for m in s.SECTION_RE.finditer(plain)]
    for i, st in enumerate(starts):
        sec = plain[st:starts[i + 1] if i + 1 < len(starts) else len(plain)]
        if "CITY COUNCIL" not in sec[:200].upper():
            continue
        date = s.parse_meeting_date(sec, matter_file=d.get("file"))
        if date and date >= "2013-08-01" and not have.get(date) and len(CLAUSE.findall(sec)) >= 1:
            rows[(date, os.path.basename(f))] = len(CLAUSE.findall(sec))
for (date, f), n in sorted(rows.items()):
    print(f"{date}  {f}  {n} vote-like clauses, 0 votes recorded")
print(f"{len(rows)} meetings to review")

#!/usr/bin/env python3
"""A3: compare each recorded vote with the last vote clause in its own source text."""
import json, re, os, sys, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import audit as au
sv = au.sv
ROOT = au.ROOT; OUT = au.OUT

raw = json.load(open(os.path.join(ROOT, "votes.scraped.historical.json")))["votes"]
byk = collections.defaultdict(list)
for v in raw: byk[(v["date"], v["title"])].append(v)

flags = collections.defaultdict(list)
n_checked = 0
for m, c in au.load_docs():
    for sec in au.sections(c["plain"]):
        date = sv.parse_meeting_date(sec, matter_file=c.get("file") or m.get("MatterFile", ""))
        if not date or date < "2013-08-01": continue
        present, rc_absent = sv.parse_roll_call(sec)
        present = sv.fix_roll_call(present, date)
        segs, ann, sec2 = au.segments_of(sec)
        for sg in segs:
            recs = byk.get((date, sg["title"]))
            if not recs: continue
            rec = recs[0]
            body = sg["body"]
            w = au.last_clause_window(body)
            pos = rec["votes"]
            if sg["starred"] and not (w and re.search(r"(carried|failed)", w)):
                continue   # consent-calendar item: no clause of its own
            if not w:
                flags["no_clause_in_segment"].append({"date": date, "title": sg["title"][:80], "pos": pos}); continue
            n_checked += 1
            exp = au.label_names(w)
            unan = bool(re.search(r"unanimous", w, re.I))
            # 1. named members whose recorded value disagrees
            for val, shorts in exp.items():
                for s in shorts:
                    if pos.get(s) != val:
                        flags["name_mismatch"].append({"date": date, "title": sg["title"][:70], "who": s, "clause_says": val,
                                                       "recorded": pos.get(s), "window": re.sub(r"\s+", " ", w)[:300]})
            # 2. unanimous clause but a recorded 'no'/abstain
            if unan and any(v in ("no", "abstain") for v in pos.values()):
                flags["unanimous_but_dissent"].append({"date": date, "title": sg["title"][:70], "pos": pos, "window": re.sub(r"\s+", " ", w)[:250]})
            # 3. recorded non-aye with no cue anywhere in segment/roll call
            for s, val in pos.items():
                if val in ("aye",): continue
                cue = False
                nm = au.SURN_RE[s]
                if val == "absent":
                    cue = s in rc_absent or re.search(r"absent|left the|arrived", body, re.I) and nm.search(body)
                elif val == "recused":
                    cue = any(nm.search(body[max(0, x.start()-250):x.end()+250]) for x in re.finditer(r"recus", body, re.I))
                elif val == "abstain":
                    cue = any(nm.search(body[max(0, x.start()-250):x.end()+250]) for x in re.finditer(r"abstain|abstention", body, re.I))
                elif val == "no":
                    cue = True  # covered by name_mismatch
                if not cue:
                    flags["unsupported_nonaye"].append({"date": date, "title": sg["title"][:70], "who": s, "recorded": val})
            # 4. cues in the segment that the record ignores
            for x in re.finditer(r"recus\w*", body, re.I):
                near = body[max(0, x.start()-200):x.end()+120]
                if re.search(r"(?:Councilmember|Vice Mayor|Mayor)\s+\w+[^.]{0,80}recus|recus[^.]{0,60}(?:Councilmember|Vice Mayor|Mayor)", near, re.I):
                    for s in au.names(near):
                        if pos.get(s) == "aye" or pos.get(s) == "no":
                            flags["recusal_cue_but_voted"].append({"date": date, "title": sg["title"][:70], "who": s, "recorded": pos.get(s), "near": re.sub(r"\s+", " ", near)[:260]})
            # 5. completeness: every present member has a position
            miss = [s for s in present if s not in pos]
            if miss:
                flags["present_without_position"].append({"date": date, "title": sg["title"][:70], "missing": miss, "pos": pos})
json.dump(flags, open(os.path.join(OUT, "audit_B.json"), "w"), indent=1)
print("checked", n_checked, {k: len(v) for k, v in flags.items()})

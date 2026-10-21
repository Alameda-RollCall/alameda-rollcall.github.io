#!/usr/bin/env python3
"""Independent audit of votes.json against the cached clerk minutes.

Run from the repository root with the project venv (needs minutes_cache/, which is
not committed):  venv/bin/python tests/data_audit/audit.py  (then audit_b.py, audit_c.py).
Writes audit_A/B/C.json to $AUDIT_OUT (default: the system temp dir).

Re-segments every minutes document (using the scraper's own section/date/roll
call helpers, which are audited separately) and compares what the text says
with what votes.json records, using *different* extraction logic (word-bounded
names, cue words) so a parser bug is not repeated here.
"""
import json, re, sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
import scrape_votes as sv

import tempfile
OUT = os.environ.get("AUDIT_OUT", tempfile.gettempdir())

# ---- independent member matcher (word-bounded) -----------------------------
SURN = {
    "MEA": [r"Ezzy\s+Ashcraft", r"Ashcraft"], "MP": [r"Pryor"], "TD": [r"Daysog"],
    "GB": [r"Boller"], "TJ": [r"Jensen"], "SC": [r"Chen"], "MG": [r"Gilmore"],
    "LT": [r"Tam"], "THS": [r"Herrera\s+Spencer", r"Spencer"], "JO": [r"Oddie"],
    "FM": [r"Matarrese"], "MV": [r"Vella"], "JKW": [r"Knox\s+White"],
}
SURN_RE = {s: re.compile(r"(?<![A-Za-z])(?:%s)(?![A-Za-z])" % "|".join(p), re.I) for s, p in SURN.items()}

def names(text):
    return {s for s, r in SURN_RE.items() if r.search(text or "")}

# liberal "this paragraph records a vote" detector
CLAUSE = re.compile(
    r"(voice vote|roll call vote|unanimous|\bAyes?\s*[:\-–]|\bNoes?\s*[:\-–]|"
    r"motion\s+(?:carried|failed|passed)|\b(?:carried|failed)\s+by\b|"
    r"failed\s+for\s+(?:lack|want)|following\s+(?:voice|roll)?\s*vote)", re.I)

def load_docs():
    matters = json.load(open(os.path.join(ROOT, "minutes_cache", "matters_list.json")))
    for m in matters:
        p = os.path.join(ROOT, "minutes_cache", f"{m['MatterId']}.json")
        if not os.path.exists(p):
            continue
        c = json.load(open(p))
        if c.get("plain"):
            yield m, c

def sections(plain):
    plain = sv.MIDWORD_ARTIFACT_RE.sub("", plain)
    starts = [m.start() for m in sv.SECTION_RE.finditer(plain)]
    for i, s in enumerate(starts):
        sec = plain[s:starts[i + 1] if i + 1 < len(starts) else len(plain)]
        if "CITY COUNCIL" not in sec[:200].upper():
            continue
        yield sec

def segments_of(section):
    """Same segmentation as the scraper (markers by ITEM_RE), minus closed-session blanking."""
    anns = list(re.finditer(r"Following the Closed Session.*?(?=\r?\n\s*\r?\n|\Z)", section, re.S))
    ann_text = [a.group(0) for a in anns]
    for am in reversed(anns):
        section = section[:am.start()] + " " * (am.end() - am.start()) + section[am.end():]
    markers = list(sv.ITEM_RE.finditer(section))
    segs = []
    for j, mk in enumerate(markers):
        end = markers[j + 1].start() if j + 1 < len(markers) else len(section)
        body = section[mk.end():end]
        para = re.split(r"\r?\n\s*\r?\n", body.strip(), maxsplit=1)[0]
        segs.append({"tag": mk.group("tag"), "starred": mk.group(1) == "*", "title": sv.clean_title(para[:300]),
                     "para": para, "body": body, "off": mk.start()})
    return segs, ann_text, section

def main():
    data = json.load(open(os.path.join(ROOT, "votes.json")))
    votes = data["votes"]
    by_date_title = collections.defaultdict(list)
    raw = json.load(open(os.path.join(ROOT, "votes.scraped.historical.json")))["votes"]
    for v in raw:
        by_date_title[(v["date"], v["title"])].append(v)

    flags = collections.defaultdict(list)
    seen_dates = set()
    for m, c in load_docs():
        plain = c["plain"]
        for sec in sections(plain):
            date = sv.parse_meeting_date(sec, matter_file=c.get("file") or m.get("MatterFile", ""))
            if not date or date < "2013-08-01":
                continue
            present, absent = sv.parse_roll_call(sec)
            present = sv.fix_roll_call(present, date)
            seen_dates.add(date)
            segs, ann_text, sec2 = segments_of(sec)
            # ---- A1: segments that contain a vote clause but yielded no vote
            for i, sg in enumerate(segs):
                if not sg["title"] or sv.TITLE_PREFIX_SKIP.match(sg["title"]) or sv.SPEAKER_VERB_RE.search(sg["para"][:250]):
                    continue
                if bool(sv.OTHER_BODY_RE.search(sg["tag"])) and not re.search(r"\bCC\b", sg["tag"]):
                    continue
                if (date, sg["title"]) in by_date_title:
                    continue
                if CLAUSE.search(sg["body"]) and not sg["starred"]:
                    flags["A1_clause_but_no_vote"].append({
                        "date": date, "matter": m["MatterId"], "title": sg["title"][:110],
                        "clause": (CLAUSE.search(sg["body"]).group(0)),
                        "tail": re.sub(r"\s+", " ", sg["body"].strip()[-260:])})
            # ---- A2: closed-session announcement paragraphs vs recorded votes
            for at in ann_text:
                n_reg = len(re.findall(r"\bregarding\b", at))
                flags["A2_announcements"].append({"date": date, "regarding": n_reg, "text": re.sub(r"\s+", " ", at)[:400]})
    json.dump({k: v for k, v in flags.items()}, open(os.path.join(OUT, "audit_A.json"), "w"), indent=1)
    print({k: len(v) for k, v in flags.items()})
    print("meeting sections seen:", len(seen_dates), " distinct vote dates:", len({v['date'] for v in votes}))
    print("dates with sections but no votes:", sorted(seen_dates - {v['date'] for v in votes}))

if __name__ == "__main__":
    main()


# ======================= A3: per-vote differential check =====================
LABELS = [("aye", r"Ayes?"), ("no", r"Noes?|Nays?"), ("abstain", r"Abstentions?|Abstained|Abstain"),
          ("absent", r"Absent"), ("recused", r"Recused?")]
LAB_ALL = re.compile(r"(?<![A-Za-z])(Ayes?|Noes?|Nays?|Abstentions?|Abstained|Abstain|Absent|Recused?)\s*[:\-–]", re.I)
VAL = {"aye": "aye", "ayes": "aye", "no": "no", "noe": "no", "noes": "no", "nay": "no", "nays": "no",
       "abstention": "abstain", "abstentions": "abstain", "abstained": "abstain", "abstain": "abstain",
       "absent": "absent", "recuse": "recused", "recused": "recused"}

ANCHOR = re.compile(r"\b(?:carried|failed|passed|adopted|approved)\b[^.]{0,90}?(?:vote|unanimous)|\bunanimous(?:ly)?\b[^.]{0,30}vote|\bmotion\s+by\s+unanimous", re.I)

def last_clause_window(body):
    ms = list(ANCHOR.finditer(body))
    if not ms:
        return None
    w = body[ms[-1].start():ms[-1].start() + 700]
    return re.split(r"\n\s*\n", w)[0]

def label_names(window):
    """{value: set(shorts)} from 'Label: names' / 'Label - 3: names' runs in the window; names
    before the first label (after 'vote:') count as ayes."""
    out = collections.defaultdict(set)
    labs = list(LAB_ALL.finditer(window))
    for i, lm in enumerate(labs):
        end = labs[i + 1].start() if i + 1 < len(labs) else len(window)
        chunk = re.split(r"[.;]\s|\.$|\]", window[lm.end():end])[0]
        out[VAL[lm.group(1).lower()]] |= names(chunk)
    # implicit ayes: "vote: Councilmembers A, B and Mayor C - 4."  (no 'Ayes' label)
    m = re.search(r"vote[s]?\s*:\s*(.*?)\s*[-–]\s*\d+\s*\.", window)
    if m and not any(l.group(1).lower().startswith("aye") for l in labs):
        out["aye"] |= names(m.group(1))
    return out

def a3(votes_raw, root_votes):
    pass

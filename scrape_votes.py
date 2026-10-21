#!/usr/bin/env python3
"""
Export Alameda City Council roll-call votes into votes.json for the
Alameda Roll Call site.

NOTE ON DATA SOURCE: Alameda uses Legistar for agendas only — the city
never populates Legistar's electronic minutes/votes module, so
/eventitems/{id}/votes, EventItemPassedFlag, EventItemTally, and
/matters/{id}/histories are empty for every meeting (verified back to
2015). The only machine-readable vote record is the *text of the draft
minutes*, which the City Clerk files as a "Minutes of ..." consent
matter whose MatterTextPlain contains the full narrative minutes.
This script fetches those matter texts and parses the clerk's highly
formulaic vote language:

    Councilmember Jensen moved approval of the Consent Calendar.
    Vice Mayor Pryor seconded the motion, which carried by unanimous
    voice vote - 5.  [Items so enacted are marked (*25-   ).]

    ... which carried by the following voice vote: Ayes: Councilmembers
    Daysog, Jensen, and Mayor Ezzy Ashcraft - 3; Noes: Councilmember
    Herrera Spencer - 1; Abstention: Councilmember Vella - 1.

Usage:
    pip install requests
    python scrape_votes.py --since 2025-01-01 --out votes.json
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone

import requests

BASE = "https://webapi.legistar.com/v1/alameda"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "AlamedaRollCall/1.0 (civic transparency project)"
COUNCIL_BODY_ID = 138  # "City Council" per /bodies

# Council roster: last-name fragments -> (short, display name, role, term).
# Covers every member who served any time since 2013-08-21 (the start of
# Legistar's Alameda record) through the current council, i.e. as far back
# as any sitting member (Ezzy Ashcraft, Daysog) has ever served. Term/role
# strings are derived from confirmed roll-call appearances in the scraped
# minutes, not assumed pre-2013 history. Names must match the clerk's
# spelling; matching is substring-based, so e.g. "Spencer" also matches
# later "Herrera Spencer" mentions after her name change.
# "Ezzy" is a nickname/middle name, so show members as just "Ashcraft".
DISPLAY_LAST = {"Ezzy Ashcraft": "Ashcraft"}
MEMBERS = {
    "Ezzy Ashcraft": ("MEA", "Marilyn Ezzy Ashcraft", "Councilmember 2013-2018; Mayor 2019-present", "2013-present"),
    "Pryor":         ("MP",  "Michele Pryor", "Vice Mayor", "2024-2028"),
    "Daysog":        ("TD",  "Tony Daysog", "Councilmember", "2013-2018, 2019-present"),
    "Boller":        ("GB",  "Greg Boller", "Councilmember", "2024-2028"),
    "Jensen":        ("TJ",  "Tracy Jensen", "Councilmember", "2022-present"),
    "Chen":          ("SC",  "Stewart Chen", "Councilmember", "through 2014"),
    "Gilmore":       ("MG",  "Marie Gilmore", "Mayor", "through 2014"),
    "Tam":           ("LT",  "Lena Tam", "Councilmember", "through 2014"),
    "Spencer":       ("THS", "Trish Herrera Spencer", "Mayor 2014-2018; Councilmember 2021-2024", "2014-2024"),
    "Oddie":         ("JO",  "Jim Oddie", "Councilmember", "2014-2022"),
    "Matarrese":     ("FM",  "Frank Matarrese", "Councilmember", "2014-2019"),
    "Vella":         ("MV",  "Malia Vella", "Councilmember", "2017-2024"),
    "Knox White":    ("JKW", "John Knox White", "Councilmember", "2019-2023"),
}

# Facts that can't be derived from roll calls. `serving` members get end=None.
# `candidacy_2026` is the office sought in the Nov 3, 2026 general election
# (candidate list matches the City Clerk's Elections page and the Alameda Post
# election page as of 2026-10-20; Zaccariah Bowling filed but is marked DNQ).
MEMBER_META = {
    "MEA": {"serving": True, "candidacy_2026": None},
    "MP":  {"serving": True, "candidacy_2026": None},
    "TD":  {"serving": True, "candidacy_2026": "Mayor"},
    "GB":  {"serving": True, "candidacy_2026": None},
    "TJ":  {"serving": True, "candidacy_2026": "Mayor"},
    "MV":  {"serving": False, "candidacy_2026": "Mayor"},
}

# 2026 council candidates with no council record (nothing to show in the roll call).
COUNCIL_CANDIDATES_NO_RECORD = [
    "Thushan Amarasiriwardena", "Maria L. Bondonno", "Marcie Johnson",
    "Tyler Savage", "Steve Slauson", "Amos White",
]


def build_members(votes):
    """Roster entries with start/end taken from each member's first and last
    roll-call appearance in `votes` (end is None for sitting members)."""
    first, last, spans = {}, {}, {}
    for v in sorted(votes, key=lambda v: v["date"]):
        for short in v["votes"]:
            first.setdefault(short, v["date"])
            prev = last.get(short)
            # A gap of 4+ months between appearances means a break in service
            # (e.g. Daysog, 2017-2018), so start a new span.
            if prev is None or (datetime.fromisoformat(v["date"]) - datetime.fromisoformat(prev)).days > 120:
                spans.setdefault(short, []).append([v["date"], v["date"]])
            spans[short][-1][1] = v["date"]
            last[short] = v["date"]
    out = []
    for frag, (s, n, r, t) in MEMBERS.items():
        meta = MEMBER_META.get(s, {})
        out.append({
            "short": s, "name": n, "role": r, "term": t,
            # Display label; frag is the clerk's spelling used for matching.
            "last": DISPLAY_LAST.get(frag, frag),
            "start": first.get(s),
            "end": None if meta.get("serving") else last.get(s),
            "spans": spans.get(s, []),
            "candidacy_2026": meta.get("candidacy_2026"),
        })
    return out


# Rough keyword categorizer for the scraper's own output (annotate_pipeline/annotate.py assigns the published categories)
CATEGORY_RULES = [
    ("Housing", r"housing|rent|tenant|shelter|homeless|affordable|density bonus|relocation|dwelling"),
    ("Transportation", r"transport|street|bike|bicycle|pedestrian|parking|transit|traffic|bridge|ferry|pavement|road|sidewalk|estuary crossing"),
    ("Public Safety", r"police|fire |fire dept|fire station|public safety|emergency|CARE team|license plate|surveillance|disaster|crime"),
    ("Budget & Finance", r"budget|bond|fiscal|tax|fee schedule|appropriat|investment policy|audit|CAFR|ACFR|debt|revenue|ratified bills"),
    ("Parks & Environment", r"park |parks|tree|climate|environment|zero waste|recycl|sea level|wetland|de-pave|open space|urban forest|stormwater"),
    ("Economic Development", r"lease|economic|business|facade|alameda point building|tenant improvement|broker|commercial|development agreement"),
    ("Governance", r"charter|ordinance amending the municipal code|appointment|commission|board |ballot|election|council rules|public comment|proclamation|minutes|bylaws"),
]

# ---------------------------------------------------------------- API helpers

def get(url, params=None, tries=4):
    for attempt in range(tries):
        r = SESSION.get(url, params=params, timeout=30)
        if r.status_code == 200:
            return r.json()
        if r.status_code in (429, 500, 502, 503):
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Failed after retries: {url}")


def paged(url, flt=None, order=None, page=1000):
    """Iterate an OData collection with $skip pagination."""
    skip = 0
    while True:
        params = {"$top": page, "$skip": skip}
        if flt:
            params["$filter"] = flt
        if order:
            params["$orderby"] = order
        batch = get(url, params)
        if not batch:
            return
        yield from batch
        if len(batch) < page:
            return
        skip += page

# ------------------------------------------------------------ minutes parsing

# A meeting section starts with a "MINUTES OF THE ..." / "Minutes of the ..."
# line (clerk switched to Title Case in 2026) immediately followed by a date
# line like "TUESDAY- -FEBRUARY 4, 2025- -7:00 P.M.". Requiring the date line
# keeps consent items titled "Minutes of the ..." from starting a section.
# The clerk's header can wrap over several lines before the "TUESDAY- -SEPTEMBER 5, 2023" line
# ("MINUTES OF THE SPECIAL JOINT MEETING OF THE CITY COUNCIL AND / SUCCESSOR AGENCY TO THE /
# COMMUNITY IMPROVEMENT COMMISSION (SACIC) / TUESDAY- -SEPTEMBER 5, 2023").
SECTION_RE = re.compile(
    r"^Minutes of the[^\r\n]*\r?\n(?:[^\r\n]*\r?\n){0,3}?[^\r\n]*?-\s*-\s*[A-Za-z]+\s+\d{1,2},\s+\d{4}",
    re.I | re.M)
DATE_RE = re.compile(r"([A-Za-z]+)-\s*-\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})\s*-\s*-")
# Fallback for the rare header with no leading weekday name.
DATE_RE_NO_WEEKDAY = re.compile(r"-\s*-\s*([A-Za-z]+\s+\d{1,2},\s+\d{4})\s*-\s*-")
WEEKDAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
            "friday": 4, "saturday": 5, "sunday": 6}

# Agenda-item paragraph markers: "(25-   )", "(25-\t)", "(*25-   )", "(26-123)",
# and joint-meeting variants like "(26-   CC)" / "(26-\tA)"
ITEM_RE = re.compile(
    r"\((\*?)\d{2}-(?P<tag>(?:[\dA-Z_/ \t-]|[Cc]ontinued|[Rr]eopened)*)\)")

# The clerk's disposition word right after an item's title: "... Not adopted." etc.
NEG_STATUS_RE = re.compile(
    r"[.\"”]\s+(?:Not\s+(?:adopted|introduced|approved|accepted|finally\s+passed|heard)|Failed|Denied|Rejected|"
    r"Withdrawn|Continued)\b", re.I)
POS_STATUS_RE = re.compile(
    r"[.\"”]\s+(?:Adopted|Introduced|Approved|Accepted|Finally\s+passed)\b", re.I)

# A lettered companion marker: "(13-409 A)", "(21-   A)", "(17-   A CC)".
SIBLING_TAG_RE = re.compile(r"^[\d\s_/-]*\b[A-Z]\b(?:\s*CC)?\s*$")

# Markers tagged only for a sibling body ("(21-  SACIC)", "(*21-01 APFA)") are
# not Council votes: they still end the previous item's segment but aren't emitted.
OTHER_BODY_RE = re.compile(r"\b(?:SACIC|APFA|CAFA|APIC|ACIC|PUB)\b")

# "... which carried by unanimous voice vote - 5."
# "... Ayes: 2. Noes: 3." -- the clerk's stated totals after the names
STATED_TALLY_RE = re.compile(r"Ayes:\s*(\d+)[.;]?\s*Noes:\s*(\d+)", re.I)

# Clerk variants handled: "carried by the by unanimous" (typo), "the ordinance was
# adopted by unanimous voice vote - 4", "the motion by unanimous voice vote - 4",
# "by a unanimous voice vote: Ayes - 5", a count written ".5", and a clause with
# no count at all ("carried by unanimous voice vote. [Absent: X - 1.]"). With no
# outcome word the clause must be about "the motion/matter/..." (UNAN_SUBJECT_RE),
# so narrative like "recommended by unanimous vote of the Planning Board" is skipped.
UNANIMOUS_RE = re.compile(
    r"\b(?:(?P<outcome>carried|failed|passed|adopted|approved)\b[^.]{0,20}?\s+)?"
    r"by\s+(?:the\s+|a\s+)?(?:by\s+(?:the\s+)?)?unanimous\b"
    r"[^.\n]*?(?:[-–—]\s*\.?(?P<n>\d+)|(?=\.\s|\.$|\[|$))", re.I)
# "carried by the following voice vote - 5." (a count with no names)
FOLLOWING_COUNT_RE = re.compile(
    r"\b(?P<outcome>carried|failed|passed|adopted|approved)\b[^.:]{0,60}?by\s+the\s+following[^:.\n]{0,30}?votes?\s*[-–]\s*(?P<n>\d+)", re.I)
UNAN_SUBJECT_RE = re.compile(r"(?:motion|matter|resolution|ordinance|item|which)\s*,?\s*$", re.I)
# "carried by unanimous roll call vote: Councilmember A: Aye; ... Mayor B: Aye. Ayes - 5."
# (the period after the last Aye defeats UNANIMOUS_RE's sentence-bounded tail).
UNANIMOUS_ROLL_RE = re.compile(
    r"\b(?P<outcome>carried|failed|passed|adopted|approved)\b[^.]{0,20}?\s+by\s+(?:the\s+|a\s+)?unanimous\s+roll\s+call\s+vote\s*:"
    r"[^\n]{0,400}?\bAyes?\s*[-–:]\s*(?P<n>\d+)", re.I)

# "... carried by the following roll call vote: Ayes: ... - 4; Noes: ... - 1."
# Also closed-session announcements ("approved the ... by the following voice
# vote:") and per-item consent exceptions ("the item carried by the following
# vote:").
FOLLOWING_RE = re.compile(
    r"\b(?P<verb>carried|failed|passed|approved|adopted|provided\s+direction)\b[^.:]{0,90}?"
    r"by\s+(?:(?:the\s+)?follow(?:ing)?|(?:a\s+)?roll\s+call)[^:]{0,40}?votes?\s*:\s*", re.I)  # "follow", "by following" are clerk typos

# Vote-clause labels. The clerk writes both "Ayes: Councilmembers X, Y - 4"
# and the reversed "Ayes: 4 - Councilmembers X, Y", so chunks are delimited by
# the labels themselves and names are pulled from whatever sits between them.
LABEL_RE = re.compile(
    r"\b(?P<label>Ayes?|Noes?|No|Nays?|Abstentions?|Abstained|Abstain|Absent|Recused?)(?:\s*[-–]\s*\d+)?\s*:", re.I)

# Group/per-name roll calls: "Councilmembers A, B and Mayor C: Ayes - 4" or
# "Daysog: No"
GROUP_RE = re.compile(
    r"(?P<who>[A-Z][^:;.]{0,140}?):\s*(?P<label>(?i:Ayes?|Yes|Noe?s?|Nays?|Abstentions?|"
    r"Abstained|Abstain|Absent|Recused?))\b", re.S)

PART_VALUE_WORDS = {
    "aye": "aye", "ayes": "aye", "yes": "aye",
    "no": "no", "noe": "no", "noes": "no", "nay": "no", "nays": "no",
    "abstention": "abstain", "abstentions": "abstain",
    "abstain": "abstain", "abstained": "abstain",
    "absent": "absent",
    "recuse": "recused", "recused": "recused",
}

# "... which carried by 4-0." (bare tally, attributable only if everyone voted)
TALLY_RE = re.compile(r"\b(?P<outcome>carried|failed)\s+by\s+(?P<a>\d)\s*[-–—]\s*(?P<n>\d)\b", re.I)

PART_VALUE = {
    "aye": "aye", "ayes": "aye",
    "no": "no", "noes": "no", "nay": "no", "nays": "no",
    "abstention": "abstain", "abstentions": "abstain",
    "abstain": "abstain", "abstained": "abstain",
    "absent": "absent",
    "recuse": "recused", "recused": "recused",
}

TITLE_PREFIX_SKIP = re.compile(r"^(Mayor|Vice Mayor|Councilmember|Former|The |There being)\b")

# Narrative paragraphs ("Jane Doe, Alameda, discussed ...") also carry (25- )
# markers in the minutes; real agenda-item titles never use these lowercase verbs.
SPEAKER_VERB_RE = re.compile(
    r"\b(discussed|stated|expressed|inquired|thanked|urged|submitted|alleged|"
    r"suggested|encouraged|outlined|announced|commented|read the|gave a|"
    r"made brief comments|made comments|offered comments|provided an update|"
    r"invited (?:people|the public)|proposed|called for|questioned|read from|"
    r"made an announcement|provided an? [\w ]{0,20}?update)\b")

CONSENT_MOVE_RE = re.compile(
    r"moved\s+(?:approval\s+of\s+)?(?:the\s+)?(?:remainder\s+of\s+the\s+)?Consent Calendar",
    re.I)


# Misspellings in the clerk's vote clauses and roll calls (each found in the minutes).
NAME_TYPOS = [
    (re.compile(r"\bKnow\s+White\b"), "Knox White"),
    (re.compile(r"\bHerera\b"), "Herrera"),
    (re.compile(r"\b(?:Aschraft|Ascraft|Ashcarft|Ashcroft)\b"), "Ashcraft"),
    (re.compile(r"\b(?:Dayosg|Daysg)\b"), "Daysog"),
    (re.compile(r"\bMatarrase\b"), "Matarrese"),
    (re.compile(r"\bVela\b"), "Vella"),
    (re.compile(r"\bSpener\b"), "Spencer"),
]


def _fix_name_typos(text):
    for rx, fix in NAME_TYPOS:
        text = rx.sub(fix, text)
    return text


def members_in(text):
    """Map a run of clerk prose to the member shorts it mentions."""
    text = _fix_name_typos(text or "")
    # Clerk text sometimes breaks a two-word surname across a line or uses a
    # non-breaking space ("Ezzy\nAshcraft"), so let any whitespace run match.
    return [info[0] for frag, info in MEMBERS.items()
            if re.search(r"\s+".join(map(re.escape, frag.split())), text or "", re.I)]


# The clerk's header names a month that contradicts the rest of the document. Confirmed
# against Legistar's agenda for the meeting: matter 2019-7477 ("Minutes ... Held on
# November 5, 2019") headed its special closed-session meeting "TUESDAY - JANUARY 5, 2019"
# (Nov 5, 2019 was a Tuesday; Jan 5, 2019 a Saturday, when the council only held an 8:30 AM
# closed session on other items).
CLERK_DATE_FIXES = {("2019-7477", "2019-01-05"): "2019-11-05"}


def parse_meeting_date(section, matter_file=None):
    d = _parse_meeting_date(section, matter_file)
    return CLERK_DATE_FIXES.get((matter_file, d), d)


def _parse_meeting_date(section, matter_file=None):
    window = section[:400]
    m = DATE_RE.search(window)
    if m:
        weekday_name, date_str = m.group(1).lower(), m.group(2)
        try:
            d = datetime.strptime(date_str.title(), "%B %d, %Y").date()
        except ValueError:
            return None
        expected = WEEKDAYS.get(weekday_name)
        if expected is not None and d.weekday() != expected:
            # The clerk's own header states a weekday inconsistent with its
            # date. Usually the weekday WORD is the typo and the date is
            # fine (most of these 28 cases). But occasionally the YEAR is
            # the typo instead -- confirmed for matter 2019-6505, whose
            # header says "THURSDAY- -JANUARY 10, 2018" (Jan 10 2018 was
            # actually a Wednesday; 2019 is a Thursday, and the item itself
            # references an "April 9, 2019" election). Don't guess from the
            # weekday alone -- cross-check against the matter's own Legistar
            # file number, which is assigned independently of this prose
            # header and is strong evidence of the true year. Only correct
            # the year when shifting it both matches the filing year AND
            # resolves the weekday.
            file_year = None
            if matter_file and "-" in matter_file:
                head = matter_file.split("-", 1)[0]
                if head.isdigit():
                    file_year = int(head)
            corrected = False
            if file_year is not None and file_year != d.year:
                for delta in (1, -1):
                    try:
                        candidate = d.replace(year=d.year + delta)
                    except ValueError:
                        continue
                    if candidate.year == file_year and candidate.weekday() == expected:
                        print(f"WARN: source date '{date_str}' (matter "
                              f"{matter_file}) says {m.group(1)} but that's a "
                              f"{d.strftime('%A')} -- correcting to "
                              f"{candidate.isoformat()} (matches filing year "
                              f"and stated weekday)", file=sys.stderr)
                        d = candidate
                        corrected = True
                        break
            if not corrected:
                print(f"WARN: source date '{date_str}' (matter {matter_file}) "
                      f"says {m.group(1)} but that's a {d.strftime('%A')} -- "
                      f"keeping date as written (weekday name is presumed to "
                      f"be the typo)", file=sys.stderr)
        return d.isoformat()
    m = DATE_RE_NO_WEEKDAY.search(window)
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1).title(), "%B %d, %Y").date().isoformat()
    except ValueError:
        return None


def parse_roll_call(section):
    """Return (present shorts, absent shorts) from the section's roll call."""
    present, absent = [], []
    m = re.search(r"Roll Call\s*[-–]\s*Present:\s*([^.]*?)\s*[-–]\s*\d+\s*\.", section, re.I)
    if m:
        present = members_in(m.group(1))
        # (a teleconference-address note can sit between "Present" and "Absent")
        m2 = re.search(r"Absent:\s*([^.]*?)\s*\.", section[m.end():m.end() + 600], re.I)
        if m2 and "none" not in m2.group(1).lower():
            absent = members_in(m2.group(1))
        # A member who wasn't there for the opening roll call but is noted
        # as arriving mid-meeting ("[Note: Councilmember Vella arrived at
        # 7:33 p.m.]") did cast votes later in the same section -- add them
        # to `present` so their later votes aren't silently dropped for
        # lacking a present-list entry. (Any votes taken before they
        # actually arrived are a separate, rarer case not handled here.)
        m3 = re.search(r"\[Note:[^\]]*?\]", section[m.end():m.end() + 700], re.I)
        if m3:
            for am in re.finditer(r"([A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*)?)\s+arrived", m3.group(0)):
                for short in members_in(am.group(1)):
                    if short not in present:
                        present.append(short)
    return present, absent


def roll_call_arrivals(section):
    """Members the roll-call notes say arrived after the meeting began."""
    m = re.search(r"Roll Call\s*[-–]\s*Present:\s*([^.]*?)\s*[-–]\s*\d+\s*\.", section, re.I)
    late = set()
    if m:
        m3 = re.search(r"\[Note:[^\]]*?\]", section[m.end():m.end() + 700], re.I)
        if m3:
            for am in re.finditer(r"([A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*)?)\s+arrived", m3.group(0)):
                late.update(members_in(am.group(1)))
    return late


def parse_parts(window, present):
    """Parse a vote clause into {short: val}, tolerating every clerk format:
    'Ayes: Councilmembers X, Y - 2; Noes: Z - 1', 'Ayes: 2 - X and Y; ...',
    'Councilmembers X, Y: Ayes - 4, Councilmember Z: No - 1', 'Ayes: 5'."""
    positions = {}
    # group/per-name form: names BEFORE the label
    for gm in GROUP_RE.finditer(window):
        val = PART_VALUE_WORDS.get(gm.group("label").lower())
        if not val:
            continue
        for short in members_in(gm.group("who")):
            positions[short] = val
    if len(positions) >= 2:
        return positions
    # label-first form: chunk runs from each label to the next label,
    # clipped at the first period/semicolon/closing bracket (names never
    # contain any of those). The clip is essential, not just tidy: a
    # closed-session "with the following report out: ..." narrative can run
    # 200+ chars with no period at all, and a bare fallback window would
    # otherwise swallow an unrelated historical name mention (e.g. "three
    # un-recused Council members (Spencer, Ezzy Ashcraft and Matarrese)
    # declined ...") straight into the vote-clause attribution.
    positions = {}
    labels = list(LABEL_RE.finditer(window))
    # "vote: Councilmembers A, B and Mayor C - 4. Noes: Councilmember D - 1." --
    # the ayes carry no label; they are the names before the first label.
    if labels and PART_VALUE_WORDS.get(labels[0].group("label").lower()) != "aye":
        lead = window[:labels[0].start()]
        if re.search(r"[-–]\s*\d+\s*\.?\s*$", lead.strip()):
            for short in members_in(lead):
                positions[short] = "aye"
    for i, lm in enumerate(labels):
        val = PART_VALUE_WORDS.get(lm.group("label").lower())
        if not val:
            continue
        end = labels[i + 1].start() if i + 1 < len(labels) else min(len(window), lm.end() + 120)
        chunk = re.split(r"[.;\]]", window[lm.end():end])[0]
        named = members_in(chunk)
        if named:
            for short in named:
                positions[short] = val
        elif val == "aye" and re.match(r"\s*\d+\s*[,;.]?\s*$", chunk):
            # bare count like "Ayes: 5" -> everyone present voted aye
            for short in present:
                positions.setdefault(short, val)
    if not positions and re.search(r"unanimous", window[:150], re.I):
        # "by the following voice votes: Vote 1: unanimous voice vote - 5, ..."
        positions = {s: "aye" for s in present}
    return positions


def apply_notes(segment, positions):
    """Clerk notes override: '[Note: Vice Mayor Pryor recused ...]'"""
    for note in re.findall(r"\[?Note:[^\]\r\n]{0,300}", segment, re.I):
        if re.search(r"by the following", note, re.I):
            continue  # vote-clause notes are parsed as events, not overrides
        for short in members_in(note):
            if re.search(r"recus", note, re.I):
                positions[short] = "recused"
            elif re.search(r"\babsent\b|left the (?:meeting|dais)|not present", note, re.I):
                positions[short] = "absent"
    return positions


# Bracketed vote-clause annotations that aren't the generic "[Note: ...]"
# form: "[Absent: Councilmember Boller - 1.]", "[Recused: Vice Mayor Pryor.]"
ABSENCE_BRACKET_RE = re.compile(r"\[(?:Absent|Recused?)\b[^\]\r\n]{0,150}\]", re.I)

# Free-prose recusal/departure sentences that carry no brackets at all, e.g.
# "Councilmember Boller announced that he was recusing himself and left the
# meeting." / "Vice Mayor Pryor recused herself from this item." These sit
# anywhere in the item's segment, often before the vote clause they explain.
RECUSAL_PROSE_RE = re.compile(
    # Case-sensitive on purpose: with re.I the name list swallowed lowercase words
    # ("Vella inquired whether Daysog's") and pinned the recusal on the wrong member.
    r"(?P<who>(?:Mayor|Vice Mayor|Councilmembers?)\s+[A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*)?"
    r"(?:,?\s+(?:and\s+)?(?:(?:Mayor|Vice Mayor|Councilmembers?)\s+)?[A-Z][\w'\-]*(?:\s+[A-Z][\w'\-]*)?){0,3})"  # "X and Vice Mayor Y"
    r"[^.]{0,100}?(?i:recus\w*|left the (?:meeting|dais)|was absent for this item)")

# Some clerks write the "Absent:"/"Abstentions:" clause as plain trailing
# prose with no brackets at all, e.g. "... carried by unanimous voice vote -
# 3.  Abstentions: Vice Mayor Ezzy Ashcraft and Mayor Gilmore - 2." Unlike
# RECUSAL_PROSE_RE this is a name LIST under one label, same shape as the
# bracketed form, just without the brackets.
TRAILING_LABEL_RE = re.compile(
    r"\b(?P<label>Absent|Recused?|Abstentions?|Abstained|Abstain):\s*"
    r"(?P<who>[^.\[\]]{0,150})", re.I)


def find_missing(text, candidates):
    """Scan an item's full segment text (not just the trailing vote clause)
    for absence/recusal cues -- bracketed or plain prose -- and return
    {short: 'absent'|'recused'|'abstain'} for whichever of `candidates` they
    explain."""
    missing = {}
    for bm in ABSENCE_BRACKET_RE.finditer(text):
        label = "recused" if re.search(r"recus", bm.group(0), re.I) else "absent"
        for short in members_in(bm.group(0)):
            if short in candidates:
                missing[short] = label
    for tm in TRAILING_LABEL_RE.finditer(text):
        label = PART_VALUE_WORDS.get(tm.group("label").lower())
        if label not in ("absent", "recused", "abstain"):
            continue
        for short in members_in(tm.group("who")):
            if short in candidates:
                missing.setdefault(short, label)
    for pm in RECUSAL_PROSE_RE.finditer(text):
        # "... left the dais at 8:25 p.m. and returned at 8:28 p.m." is a
        # momentary break, not an absence from the vote -- skip it if the
        # clerk noted a return shortly after.
        if re.search(r"\breturned\b", text[pm.end():pm.end() + 80], re.I):
            continue
        # "Councilmember Vella inquired whether Councilmember Daysog's recusal ..."
        # is a question about someone else, not Vella's recusal: the subject must be
        # followed by the verb with no inquiry word or second name in between.
        between = pm.group(0)[len(pm.group("who")):]
        if members_in(between) or re.search(
                r"\b(?:inquir\w*|ask\w*|whether|if|urged|request\w*|suggest\w*|question\w*|wonder\w*|"
                r"advis\w*|should|could|must|not|mandated|required)\b", between, re.I):
            continue
        label = "recused" if re.search(r"recus", pm.group(0), re.I) else "absent"
        for short in members_in(pm.group("who")):
            if short in candidates:
                # The clerk's trailing "[Absent: ...]" bracket also lists
                # members who recused; the prose is the more specific cue.
                if label == "recused":
                    missing[short] = label
                else:
                    missing.setdefault(short, label)
    return missing


def vote_events(text, present, absent, ctx=""):
    """All attributable vote events in text, in order: [(result, positions), ...]"""
    events = []
    for m in list(UNANIMOUS_ROLL_RE.finditer(text)) + list(FOLLOWING_COUNT_RE.finditer(text)):
        events.append(("unan", m))
    for m in UNANIMOUS_RE.finditer(text):
        if any(e[1].start() <= m.start() < e[1].end() for e in events):
            continue  # already read as a roll-call clause
        if not m.group("outcome") and not UNAN_SUBJECT_RE.search(text[max(0, m.start() - 30):m.start()]):
            continue
        # A count-less "carried by unanimous voice vote." only stands when the clerk
        # follows it with the absentee/recusal bracket or an "Ayes - N" line; otherwise
        # a later, fuller clause ("... by the following voice vote: Noes: ...") is the
        # real result.
        if not m.group("n") and not re.match(
                r"\.?\s*(?:\[?\s*(?:Absent|Recused?)\b|Ayes?\s*[-–:]\s*\d)", text[m.end():m.end() + 60], re.I):
            continue
        events.append(("unan", m))
    events += [("foll", m) for m in FOLLOWING_RE.finditer(text)]
    events += [("tally", m) for m in TALLY_RE.finditer(text)]
    out = []
    for kind, m in sorted(events, key=lambda e: e[1].start()):
        if kind == "unan":
            n = int(m.group("n")) if m.group("n") else None
            if n == len(present):
                positions = {s: "aye" for s in present}
            elif n is None:
                # No count written: everyone present who isn't noted absent/recused voted aye.
                pm = re.search(r"\r?\n\s*\r?\n", text[m.end():m.end() + 300])
                window_end = m.end() + (pm.start() if pm else 300)
                missing = find_missing(text[:window_end], present)
                positions = {s: "aye" for s in present if s not in missing}
                positions.update(missing)
            else:
                # Stated tally is short of everyone present -- someone didn't
                # vote. Never silently stamp all-present as aye; find who's
                # missing via bracket/prose cues, and only attribute the rest
                # once the numbers actually reconcile. Bound the search to
                # this vote's own paragraph (through the trailing "[Absent:
                # ...]" bracket that follows the clause on the same line) so
                # an unrelated later departure -- e.g. "Councilmember Tam
                # left the dais at 8:35 p.m. and returned at 8:37 p.m." after
                # a DIFFERENT, later item -- can't get misread as an absence
                # from THIS vote.
                pm = re.search(r"\r?\n\s*\r?\n", text[m.end():m.end() + 300])
                window_end = m.end() + (pm.start() if pm else 300)
                missing = find_missing(text[:window_end], present)
                remaining = [s for s in present if s not in missing]
                # Known clerk slip: "unanimous voice vote - 1. [Absent: X - 1.]" -- the
                # absent count written where the vote count belongs.
                absent_typo = bool(missing) and n == len(missing) and re.search(
                    r"\[Absent:[^\]]*[-–]\s*%d\b" % n, text[m.end():window_end + 40])
                if len(remaining) == n or absent_typo:
                    if absent_typo and len(remaining) != n:
                        print(f"  ! clerk count typo [{ctx}]: unanimous-{n} read as {len(remaining)}", file=sys.stderr)
                    positions = {s: "aye" for s in remaining}
                    positions.update(missing)
                else:
                    print(f"  ! tally mismatch [{ctx}]: unanimous-{n} vs "
                          f"{len(present)} present, resolved {len(missing)} "
                          f"({', '.join(missing) or 'none'}); leaving "
                          f"unexplained members unattributed", file=sys.stderr)
                    positions = {s: "aye" for s in remaining} if len(remaining) <= n else {}
                    positions.update(missing)
            outcome = m.group("outcome") or "carried"
        elif kind == "tally":
            # "carried by 4-0"
            a, n = int(m.group("a")), int(m.group("n"))
            if n == 0 and a == len(present):
                positions = {s: "aye" for s in present}
            elif n == 0:
                pm = re.search(r"\r?\n\s*\r?\n", text[m.end():m.end() + 300])
                window_end = m.end() + (pm.start() if pm else 300)
                missing = find_missing(text[:window_end], present)
                remaining = [s for s in present if s not in missing]
                if len(remaining) == a:
                    positions = {s: "aye" for s in remaining}
                    positions.update(missing)
                else:
                    positions = {}
            else:
                positions = {}
            outcome = m.group("outcome")
        else:
            # parts live in the rest of the paragraph after the "vote:" anchor
            window = re.split(r"\r?\n\s*\r?\n", text[m.end():m.end() + 500])[0]
            positions = parse_parts(window, present)
            bare = re.match(r"\s*(\d+)\s+Ayes?\b", window)
            if bare and not any(v in ("aye", "no", "abstain") for v in positions.values()):
                missing = find_missing(text[:m.end() + len(window)], present)
                remaining = [s for s in present if s not in missing]
                if len(remaining) == int(bare.group(1)):
                    positions = {s: "aye" for s in remaining}
                    positions.update(missing)
            # The trailing "[Absent: X]" bracket also lists members who
            # recused earlier in the item ("Councilmember X recused himself
            # ... and left the dais"); the prose is the more specific cue.
            gone = [s for s, v in positions.items() if v == "absent"]
            if gone:
                for s, label in find_missing(text[:m.end()], gone).items():
                    if label == "recused":
                        positions[s] = "recused"
            outcome = m.group("verb")
            # Roll-call-style clauses ("A: Aye; B: Aye. Ayes: 4. [Absent: C - 1.]")
            # list only who voted; the absent/recused member is in the bracket or prose.
            unplaced = [s for s in present if s not in positions]
            if positions and unplaced:
                for s, label in find_missing(text[:m.end() + len(window)], unplaced).items():
                    positions.setdefault(s, label)
                # "Ayes: A, B and C - 3. Councilmembers D and Mayor E - 2." -- the clerk dropped
                # the "Noes:" label; the unlabeled second list is the noes if its count matches.
                still = [s for s in unplaced if s not in positions]
                if still and any(v == "aye" for v in positions.values()):
                    for nm in re.finditer(r"((?:Councilmembers?|Vice Mayor|Mayor)[^.;\[\]]*?)\s*[-–]\s*(\d+)\s*\.", window):
                        named = [s for s in members_in(nm.group(1)) if s in still]
                        if named and len(named) == int(nm.group(2)):
                            for s in named:
                                positions[s] = "no"
        if not positions:
            continue
        for s in absent:
            positions.setdefault(s, "absent")
        apply_notes(text, positions)
        result = "failed" if outcome.lower() == "failed" else "passed"
        ayes = sum(1 for v in positions.values() if v == "aye")
        noes = sum(1 for v in positions.values() if v == "no")
        stated = STATED_TALLY_RE.search(window) if kind == "foll" else None
        if result == "passed" and ayes < 3 and noes > ayes and stated:
            if int(stated.group(1)) == ayes:
                # The clerk wrote "the motion carried" over a tally like "Ayes: 2.
                # Noes: 3."; a five-member council can't pass anything on two ayes.
                print(f"  ! result override [{ctx}]: 'carried' with {ayes} ayes, "
                      f"{noes} noes -> failed", file=sys.stderr)
                result = "failed"
        if stated and (int(stated.group(1)), int(stated.group(2))) != (ayes, noes):
            print(f"  ! tally conflict [{ctx}]: names give {ayes}-{noes}, clerk "
                  f"states {stated.group(1)}-{stated.group(2)}; left as {result}",
                  file=sys.stderr)
        out.append((result, positions))
    return out


def parse_motion(segment, present, absent, ctx=""):
    """The LAST vote event in an item segment wins (amendments and procedural
    motions come first). Returns (result, positions) or None.

    Usually correct even when a segment holds several *differing* vote
    events -- most such segments are one item worked through reconsideration
    or amendment votes, where the final one is genuinely authoritative. The
    rare failure mode is different: a missing item-boundary marker merges
    two *unrelated* agenda items into one oversized segment, and the last
    event then belongs to the wrong item entirely (confirmed once in the
    full 2013-2026 corpus: a drone-purchase item whose segment ran on 40k+
    characters into an unrelated military-equipment-report vote, tipped off
    by the clerk's own "Council must make a separate motion..." aside). Flag
    it instead of silently trusting evs[-1], so a maintainer can eyeball it."""
    evs = vote_events(segment, present, absent, ctx=ctx)
    # A long item whose only vote clause sits in its opening lines is a procedural
    # motion ("limit public speaking time to 2 minutes") taken before the discussion,
    # not the item's own vote -- the item's vote isn't in this segment.
    if evs and len(segment) > 5000:
        starts = [mm.start() for rx in (UNANIMOUS_RE, UNANIMOUS_ROLL_RE, FOLLOWING_RE, TALLY_RE)
                  for mm in rx.finditer(segment)]
        if starts and max(starts) < 0.1 * len(segment):
            print(f"  ? procedural-only vote skipped [{ctx}]", file=sys.stderr)
            return None
    if len(evs) >= 2 and len(segment) > 5000:
        dicts = [e[1] for e in evs]
        if any(dicts[i] != dicts[j] for i in range(len(dicts)) for j in range(i + 1, len(dicts))):
            print(f"  ? multi-motion segment [{ctx}]: {len(evs)} differing vote "
                  f"events over {len(segment)} chars -- verify evs[-1] is the "
                  f"right item, not a merged-in later one", file=sys.stderr)
    return evs[-1] if evs else None


def clean_title(raw):
    t = re.sub(r"\s+", " ", raw or "").strip()
    t = re.sub(r"\s*(Approved|Adopted|Introduced|Passed|Accepted)\.?\s*$", "", t)
    return t.rstrip(".").strip()


STATUS_CUT_RE = re.compile(r"[.\"”]\s+(?:Finally passed|Introduced|Adopted|Approved|Accepted|Not adopted|Failed|Continued|Withdrawn)\b\.?")


def full_title(para, rest=""):
    """The complete agenda-item title: the item's first paragraph, cut at the
    clerk's status word ("... Introduced.") so discussion text that follows
    without a blank line doesn't leak in, and capped at 800 characters."""
    t = re.sub(r"\s+", " ", para or "").strip()
    # The minutes sometimes break a title right before its dollar amount
    # ("...Compensation Not-to-Exceed" / "$2,793,808..."): take that paragraph too.
    if re.search(r"(?:to[- ]exceed|amount of|total of|compensation|exceed)\s*$", t, re.I) and re.match(r"\s*\$", rest or ""):
        t = t + " " + re.sub(r"\s+", " ", re.split(r"\r?\n\s*\r?\n", (rest or "").lstrip(), maxsplit=1)[0]).strip()
    m = STATUS_CUT_RE.search(t)
    if m:
        t = t[:m.start() + 1]
    if len(t) > 800:
        t = t[:800].rsplit(" ", 1)[0]
    return clean_title(t)


# PDF-to-text extraction occasionally bleeds a running page marker straight
# into the middle of a word when a page break falls inside it, e.g. the
# clerk's "Jensen" coming out as "J25-ensen" (a stray page/item reference
# "25-" spliced in with no space or parens). A bare 2-digit-dash sandwiched
# tight between letters is not a legitimate word shape, so it's safe to strip.
MIDWORD_ARTIFACT_RE = re.compile(r"(?<=[A-Za-z])\d{2}-(?=[A-Za-z])")


# Council tenure windows (inclusive ISO dates; None = still serving), taken
# from each member's roll-call appearances after discarding clerk typos, and
# cross-checked with city/news sources for the current council. Used to catch
# clerk errors that name someone who could not have been seated, e.g. the
# 2017-07..2018-01 roll calls list Daysog where Vella sat (every motion in
# those meetings is Vella's), and 2021-22 roll calls list Oddie for Herrera
# Spencer. A person outside their window is replaced or dropped, with a warning.
TENURE = {
    "MEA": [("2013-01-01", None)],
    "MP":  [("2024-12-17", None)],
    "TD":  [("2013-01-01", "2016-12-31"), ("2019-01-01", None)],
    "GB":  [("2024-12-17", None)],
    "TJ":  [("2022-12-20", None)],
    "SC":  [("2013-01-01", "2014-12-31")],
    "MG":  [("2013-01-01", "2014-12-31")],
    "LT":  [("2013-01-01", "2014-12-31")],
    "THS": [("2014-12-01", "2018-12-31"), ("2021-01-01", "2024-12-31")],
    "JO":  [("2014-12-01", "2020-12-31")],
    "FM":  [("2014-12-01", "2018-12-31")],
    "MV":  [("2017-01-01", "2024-12-31")],
    "JKW": [("2019-01-01", "2022-12-31")],
}


# Roll calls where the clerk's own stated tally ("Ayes: 4. Noes: 1.") can't be
# squared with the names, and surrounding evidence says which name is the typo.
# Keyed by (date, start of title); applied after parsing, logged when used.
CLERK_VOTE_FIXES = {
    # The roll call ran on into a second sentence ("The call for the question
    # continued: Vice Mayor Vella: Aye; and Mayor Ezzy Ashcraft: Aye. Ayes: 5."), so
    # the parser kept the first sentence's Vella "No" and dropped the Mayor.
    ("2021-05-18", "Consider Directing Staff to Place the Audit Report"):
        {"MV": "aye", "MEA": "aye"},
    # "Ayes: Councilmembers Daysog, Herrera Spencer, and Jensen - 3. Councilmembers
    # Vella and Mayor Ezzy Ashcraft - 2." -- the clerk left out the "Noes:" label.
    ("2023-12-05", "Adoption of Resolution Amending the Fiscal Year 2023-24 General Fund Budget"):
        {"MV": "no", "MEA": "no"},
    # CDM Smith amendment: roll call says Knox White "No" but he seconded the
    # motion and the clerk states "Ayes: 4. Noes: 1."
    ("2022-12-06", "Recommendation to Authorize the City Manager, or Designee, to Execute a Third Amendment"):
        {"JKW": "aye"},
    # Teleconference findings: Knox White voted aye on every other one in 2022
    # (only Daysog and Herrera Spencer opposed) and the clerk states "Ayes: 3. Noes: 2."
    ("2022-12-06", "Recommendation to Approve Findings to Allow City Meetings to be Conducted via Teleconference"):
        {"JKW": "aye"},
    # 2023-01-03 candidate-statement referral: the clerk's roll call lists Mayor Ezzy
    # Ashcraft as "No" (3-2) but states "Ayes: 4. Noes: 1."; the meeting video
    # (checked by the site's maintainer) shows she voted Aye, matching the total.
    ("2023-01-03", "Consider Directing Staff to Create a Requirement for Upfront Payment of Candidate Statements"):
        {"MEA": "aye"},
    # Rock Wall Winery / St. George Spirits lease ordinance: the first motion
    # (approve as staffed) failed 3-1-1, then a second motion (remove Section 4
    # and approve the contracts) carried 4-0-1 with Daysog voting aye, which is
    # how the ordinance was introduced. The unrelated "(21- )" extra-speaking-time
    # paragraph that follows splits the segment, so that final vote is lost.
    ("2021-01-05", "Introduction of Ordinance Authorizing the City Manager to Execute Lease Amendments for Rent Relief Programs to Rock Wall Winery"):
        {"TD": "aye"},
}


def apply_clerk_fixes(date, title, positions, result):
    for (d, prefix), fix in CLERK_VOTE_FIXES.items():
        if d == date and title.startswith(prefix):
            for short, val in fix.items():
                if positions.get(short) != val:
                    print(f"  ! clerk fix [{date} {title[:40]!r}]: {short} "
                          f"{positions.get(short)} -> {val}", file=sys.stderr)
                    positions[short] = val
            ayes = sum(1 for v in positions.values() if v == "aye")
            noes = sum(1 for v in positions.values() if v == "no")
            result = "passed" if ayes > noes and ayes >= 3 else "failed"
    return positions, result


def in_office(short, date):
    return any(a <= date and (b is None or date <= b) for a, b in TENURE.get(short, []))


def fix_roll_call(present, date, ctx=""):
    """Replace/drop roll-call names that fall outside the member's tenure."""
    bad = [s for s in present if not in_office(s, date)]
    if not bad:
        return present
    free = [m for m in TENURE if in_office(m, date) and m not in present]
    out = list(present)
    for s in bad:
        if len(free) == 1 and len(bad) == 1:
            print(f"  ! roll-call typo [{ctx}]: {s} -> {free[0]}", file=sys.stderr)
            out[out.index(s)] = free[0]
        else:
            print(f"  ! roll-call name outside tenure dropped [{ctx}]: {s}", file=sys.stderr)
            out.remove(s)
    return out


def fix_present_absent(present, absent, late, date, ctx=""):
    """A roll call that names one member as both present and absent (and isn't
    explained by a late arrival) has a typo; if exactly one seated member is
    unaccounted for, they are the one the clerk meant to list as present."""
    both = [s for s in present if s in absent and s not in late]
    unaccounted = [m for m in TENURE if in_office(m, date) and m not in present and m not in absent]
    if len(both) == 1 and len(unaccounted) == 1:
        print(f"  ! roll-call typo [{ctx}]: {both[0]} listed present and absent; {unaccounted[0]} -> present", file=sys.stderr)
        present = list(present)
        present[present.index(both[0])] = unaccounted[0]
    elif len(both) == 1 and not unaccounted:
        print(f"  ! roll-call typo [{ctx}]: {both[0]} listed present and absent; treated as absent", file=sys.stderr)
        present = [s for s in present if s != both[0]]
    return present


def complete_positions(positions, present, late, body, ctx=""):
    """Seated members the vote clause leaves out: a noted recusal/absence, or a
    member who arrived after the meeting began, didn't vote on this item."""
    positions = dict(positions)
    for s in present:
        if s in positions:
            continue
        cue = find_missing(body, [s]).get(s)
        if cue:
            positions[s] = cue
        elif s in late:
            positions[s] = "absent"
        else:
            print(f"  ? no position for seated member [{ctx}]: {s}", file=sys.stderr)
    return positions


def reconcile_stray(positions, present, absent, date, ctx=""):
    """Vote clauses sometimes name the wrong person (e.g. "Mayor Spencer" in
    2019 when Ezzy Ashcraft was Mayor). A name outside tenure can't have
    voted: if exactly one present member is missing from the vote, treat the
    stray name as that member; otherwise drop it."""
    stray = [k for k in positions if not in_office(k, date)]
    if not stray:
        return positions
    positions = dict(positions)
    missing = [k for k in present if k not in positions]
    for k in stray:
        if len(stray) == 1 and len(missing) == 1:
            print(f"  ! clerk name swap [{ctx}]: {k} -> {missing[0]}", file=sys.stderr)
            positions[missing[0]] = positions.pop(k)
        else:
            print(f"  ! vote name outside tenure dropped [{ctx}]: {k}", file=sys.stderr)
            del positions[k]
    return positions


def parse_minutes_text(plain, since, matter_file=None):
    """Yield vote dicts from one minutes document's plain text."""
    plain = MIDWORD_ARTIFACT_RE.sub("", plain)
    starts = [m.start() for m in SECTION_RE.finditer(plain)]
    for i, s in enumerate(starts):
        section = plain[s:starts[i + 1] if i + 1 < len(starts) else len(plain)]
        header = section[:200].upper()
        if "CITY COUNCIL" not in header:
            continue  # SACIC-only or other body
        date = parse_meeting_date(section, matter_file=matter_file)
        if not date or date < since:
            continue
        present, absent = parse_roll_call(section)
        late = roll_call_arrivals(section)
        present = fix_present_absent(present, absent, late, date, ctx=date)
        present = fix_roll_call(present, date, ctx=date)
        if len(present) < 3:
            continue  # no quorum parsed; nothing reliable to attribute

        # Closed-session votes are announced afterward in one paragraph
        # ("... announced that regarding Labor, ... by the following voice
        # vote: ...; and regarding Potential Litigation, ..."), one vote per
        # "regarding <topic>" clause. Handle these section-wide, then blank
        # them out so item segments don't re-parse the same events.
        ann_votes = []
        anns = list(re.finditer(r"Following the Closed Session.*?(?=\r?\n\s*\r?\n|\Z)",
                                section, re.S))
        for am in anns:
            parent = ""
            for chunk in re.split(r"\bregarding\b", am.group(0))[1:]:
                topic = re.split(r"[,;]", chunk, maxsplit=1)[0]
                topic = re.sub(r"^\s*the\s+", "", topic).strip()[:80]
                evs = vote_events(chunk, present, absent, ctx=f"{date} closed-session/{topic[:30]}")
                # "regarding Public Employee Performance Evaluation, ... Vote 1 regarding the
                # City Clerk was approved by unanimous voice vote - 5": name the vote for
                # the topic it falls under, not the clause that reports it.
                wm = re.match(r"(?P<who>.+?)\s+was\s+(?:approved|adopted|carried|passed|failed)\b", topic)
                if wm and parent:
                    topic = f"{parent} - {wm.group('who')}"
                elif not evs:
                    parent = topic
                for res, pos in evs:
                    ann_votes.append((topic, res, pos))
        for am in reversed(anns):
            section = section[:am.start()] + " " * (am.end() - am.start()) + section[am.end():]

        markers = list(ITEM_RE.finditer(section))
        segments = []  # (starred, title, para, body, other_body, tag)
        seg_pos = []   # section offset of each segment's marker
        for j, mk in enumerate(markers):
            end = markers[j + 1].start() if j + 1 < len(markers) else len(section)
            body = section[mk.end():end]
            para = re.split(r"\r?\n\s*\r?\n", body.strip(), maxsplit=1)[0]
            tag = mk.group("tag")
            other_body = bool(OTHER_BODY_RE.search(tag)) and not re.search(r"\bCC\b", tag)
            if other_body and segments and not segments[-1][4] \
                    and not parse_motion(segments[-1][3], present, absent):
                # A companion item for another body ("(13-417 CC)" followed by
                # "(13-03 CAFA)", "(13-03 APIC)") that shares the Council item's
                # one vote: the vote clause follows the last companion's title.
                st, ti, pa, bo, ob, tg = segments[-1]
                segments[-1] = (st, ti, pa, bo + mk.group(0) + body, ob, tg)
                continue
            segments.append((mk.group(1) == "*", clean_title(para[:300]), para, body, other_body, tag))
            seg_pos.append(mk.start())

        # The consent-calendar motion covers every asterisked item; it lives in
        # whatever narrative paragraph precedes the consent items, so find it
        # section-wide and pair it with the outcome that follows it.
        # A section can hold more than one meeting (a Special CC meeting, then a
        # Joint CC/SACIC consent calendar); each starred item takes the nearest
        # consent motion above it.
        consents = []  # (offset, parsed)
        for cm in CONSENT_MOVE_RE.finditer(section):
            # The window runs on into the first consent items, whose own
            # "[Note: X abstained ... carried by the following vote ...]"
            # clauses (bracketed or a bare "Note:" paragraph) would otherwise win as the "last" vote event and be
            # stamped on every consent item. Per-item notes are applied
            # separately via apply_notes(), so blank them out here.
            # The motion's own outcome can sit well past a long "Under discussion" run, but
            # always before the first asterisked consent item, so the window runs to there.
            nxt = re.search(r"\(\*\d{2}-", section[cm.end():cm.end() + 20000])
            wend = cm.end() + nxt.start() if nxt else cm.start() + 3000
            cwin = re.sub(r"\[?\s*Note:.*?(?:\]|\n\s*\n|$)", lambda mm: " " * len(mm.group(0)),
                          section[cm.start():max(wend, cm.start() + 3000)], flags=re.S)
            # First event, not last: it answers the consent motion itself, while
            # later ones are per-item exceptions ("Since Councilmember Daysog
            # recorded a no vote, the matter carried by the following vote:").
            cevs = vote_events(cwin, present, absent, ctx=f"{date} consent-calendar")
            consents.append((cm.start(), cevs[0] if cevs else None))

        def consent_for(pos):
            prior = [c for off, c in consents if off < pos]
            if prior:
                return prior[-1]
            return consents[0][1] if consents else None  # motion recorded after its items

        in_starred_run = False
        for si, (starred, title, para, body, other_body, tag) in enumerate(segments):
            # "(*21- ) Recommendation ... Accepted; and" / "(21- A) Resolution No. 15803 ...
            # Adopted." -- the clerk often drops the asterisk on a consent item's lettered
            # companion; it rides the same consent motion as the starred parent.
            if starred:
                in_starred_run = True
            elif in_starred_run and SIBLING_TAG_RE.match(tag):
                starred = True
            else:
                in_starred_run = False
            if other_body or not title or TITLE_PREFIX_SKIP.match(title):
                continue  # narrative ("Mayor X suggested..."), not an agenda item
            if SPEAKER_VERB_RE.search(para[:250]):
                continue  # public-comment / narrative paragraph
            # Starred items may still carry their own vote event (a clerk note
            # recording a member's exception to the blanket consent vote).
            parsed = parse_motion(body, present, absent, ctx=f"{date} {title[:50]!r}")
            if not parsed and not starred:
                # "(13-409) Resolution ... Adopted;" "(13-409 A) Resolution ... Adopted; and"
                # "(13-409 B) Resolution ... Adopted." then ONE motion for the group, written
                # after the last companion. Every companion shares that vote.
                group = ""
                for _, _, _, sbody, _, stag in segments[si + 1:]:
                    if not SIBLING_TAG_RE.match(stag):
                        break
                    group += sbody
                if group:
                    gtext = body + group
                    evs = vote_events(gtext, present, absent, ctx=f"{date} {title[:50]!r}")
                    parsed = evs[0] if evs else None
                    # A first clause in the opening lines of a long block is a procedural
                    # motion ("limit public speaking time"), not the group's vote.
                    if parsed and len(gtext) > 5000:
                        first = min(mm.start() for rx in (UNANIMOUS_RE, UNANIMOUS_ROLL_RE, FOLLOWING_RE, TALLY_RE)
                                    for mm in rx.finditer(gtext))
                        if first < 0.1 * len(gtext):
                            parsed = None
                    # A companion the clerk marked "Not adopted" / "Withdrawn" (or "Adopted" when
                    # the shared motion failed) didn't ride that motion.
                    if parsed and ((parsed[0] == "passed" and NEG_STATUS_RE.search(para))
                                   or (parsed[0] == "failed" and POS_STATUS_RE.search(para))):
                        parsed = None
            if starred and not parsed:
                # A starred parent ("(*17-  CC) Resolution No. 15272, budget")
                # followed by lettered siblings ("(17-   A CC)", "B CC", ...)
                # was voted on in the motion block after the last sibling, not
                # on consent; the first motion there is the parent's.
                group = ""
                for _, _, _, sbody, _, stag in segments[si + 1:]:
                    if not re.match(r"\s*[A-Z]\s*CC\b", stag):
                        break
                    group += sbody
                evs = vote_events(body + group, present, absent, ctx=f"{date} {title[:50]!r}") if group else []
                parsed = evs[0] if evs else consent_for(seg_pos[si])
            if not parsed:
                continue
            result, positions = parsed
            if starred:
                positions = apply_notes(body, dict(positions))
            positions = reconcile_stray(positions, present, absent, date, ctx=f"{date} {title[:40]!r}")
            positions = complete_positions(positions, present, late, body, ctx=f"{date} {title[:40]!r}")
            positions, result = apply_clerk_fixes(date, title, positions, result)
            rec = {"date": date, "title": title, "result": result,
                   "votes": positions}
            # `title` is clipped at 300 chars (hand-written overrides are keyed to
            # it); keep the complete title too so the site can show it.
            full = full_title(para, body.strip()[len(para):])
            if len(full) > len(title) + 2:
                rec["title_full"] = full
            yield rec

        # Attribute announced closed-session votes to their agenda item
        # ("Labor" -> "Conference with Labor Negotiators ...")
        seg_titles = [(t, para) for _, t, para, _, ob, _ in segments if t and not ob]
        for topic, res, pos in ann_votes:
            match = next(((t, para) for t, para in seg_titles
                          if topic and topic.lower() in t.lower()), None)
            rec = {"date": date, "title": match[0] if match else f"Closed Session - {topic}",
                   "result": res,
                   "votes": reconcile_stray(pos, present, absent, date, ctx=f"{date} closed-session")}
            if match:  # the 300-character title clip cuts long negotiator lists mid-name
                full = full_title(match[1])
                if len(full) > len(match[0]) + 2:
                    rec["title_full"] = full
            yield rec

# ------------------------------------------------------- annotation & output

def categorize_keyword(title):
    t = (title or "").lower()
    for cat, pattern in CATEGORY_RULES:
        if re.search(pattern, t):
            return cat
    return "Other"


def summarize_stub(title):
    """Trim official title into a readable capsule when not using Claude."""
    t = re.sub(r"^(Recommendation to|Adoption of Resolution|Introduction of Ordinance|Public Hearing to Consider)\s*", "", title or "", flags=re.I)
    t = t.strip().rstrip(".")
    return (t[:220] + "…") if len(t) > 220 else t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2023-01-01", help="Earliest meeting date (YYYY-MM-DD)")
    ap.add_argument("--out", default="votes.json")
    ap.add_argument("--min-voters", type=int, default=3, help="Skip items with fewer recorded votes than this")
    args = ap.parse_args()

    # Minutes are filed ~2-6 weeks after the meeting; back-date the matter
    # query a bit and filter precisely on the parsed meeting date instead.
    intro_since = args.since[:4] + "-01-01"
    flt = (f"MatterBodyId eq {COUNCIL_BODY_ID} "
           f"and MatterIntroDate ge datetime'{intro_since}' "
           f"and startswith(MatterTitle, 'Minutes') eq true")
    matters = list(paged(f"{BASE}/matters", flt=flt, order="MatterIntroDate"))
    print(f"Found {len(matters)} 'Minutes of ...' matters filed since {intro_since}")

    out_votes = []
    for n, m in enumerate(matters, 1):
        mid = m["MatterId"]
        versions = get(f"{BASE}/matters/{mid}/versions")
        if not versions:
            continue
        text = get(f"{BASE}/matters/{mid}/texts/{versions[-1]['Key']}")
        plain = text.get("MatterTextPlain") or ""
        # gateway.aspx resolves the API's MatterId to the InSite page for the
        # minutes document. (Passing the file number, e.g. "2025-4829", is
        # misread as the number 2025 and lands on an unrelated 2014 item.)
        url = f"https://alameda.legistar.com/gateway.aspx?M=L&ID={mid}"
        for k, v in enumerate(parse_minutes_text(plain, args.since, matter_file=m.get("MatterFile"))):
            if len(v["votes"]) < args.min_voters:
                continue
            v.update({
                "id": f"m{mid}-{k}",
                "summary": summarize_stub(v["title"]),
                "category": categorize_keyword(v["title"]),
                "url": url,
            })
            out_votes.append(v)
        if n % 10 == 0:
            print(f"  processed {n}/{len(matters)} minutes documents, {len(out_votes)} votes so far")
        time.sleep(0.3)  # be polite to the API

    # De-dup (revised minutes can be filed twice)
    seen_keys, deduped = set(), []
    for v in out_votes:
        k = (v["date"], v["title"], json.dumps(v["votes"], sort_keys=True))
        if k not in seen_keys:
            seen_keys.add(k)
            deduped.append(v)
    out_votes = deduped
    print(f"Collected {len(out_votes)} votes")

    data = {
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "source": "Legistar Web API (alameda) — parsed from official minutes text",
        "members": build_members(out_votes),
        "council_candidates_no_record": COUNCIL_CANDIDATES_NO_RECORD,
        "votes": sorted(out_votes, key=lambda v: v["date"], reverse=True),
    }
    with open(args.out, "w") as f:
        json.dump(data, f, indent=1)
    print(f"Wrote {args.out}")


if __name__ == "__main__":
    main()

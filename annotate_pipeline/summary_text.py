"""Plain-English rewriting of agenda-item titles into "what a YES vote does"
summaries. Pure functions, no I/O; used by annotate.py.

The City's titles are legal phrasing ("Amending the Alameda Municipal Code by
Adding Section 4-61 (Grocery Worker Hazard Pay) to Require ..."). This module
turns the common shapes into short sentences with a main verb ("Amends the city
code to require ...") and falls back to a verb-led, de-cluttered, length-capped
version of the title when no specific shape matches. It never adds facts that
are not in the title.
"""
import re

LIMIT = 25  # words

COMMON_FIRST = {"the", "a", "an", "its", "their", "all", "any", "each", "this", "that", "these", "those", "one", "two",
                "three", "four", "five", "six", "his", "her", "our", "such", "certain", "various", "additional", "new",
                "existing", "revised", "amended", "proposed", "final", "annual"}


def lc_first(s):
    """Lowercase the first word only when it is an ordinary word (article,
    determiner, adjective), never a proper noun like "Krusi" or "Central"."""
    if not s:
        return s
    head = re.match(r"[A-Za-z']+", s)
    if head and head.group(0).lower() in COMMON_FIRST:
        return s[0].lower() + s[1:]
    return s


GERUND = {
    "approving": "approves", "authorizing": "authorizes", "amending": "amends", "adopting": "adopts",
    "establishing": "establishes", "declaring": "declares", "confirming": "confirms", "setting": "sets",
    "requesting": "requests", "supporting": "supports", "calling": "calls", "continuing": "continues",
    "commending": "commends", "honoring": "honors", "recognizing": "recognizes", "accepting": "accepts",
    "appointing": "appoints", "reappointing": "reappoints", "renaming": "renames", "repealing": "repeals",
    "adding": "adds", "extending": "extends", "levying": "levies", "ordering": "orders", "denying": "denies",
    "endorsing": "endorses", "joining": "joins", "consenting": "consents", "urging": "urges", "directing": "directs",
    "providing": "provides", "awarding": "awards", "reauthorizing": "reauthorizes", "disapproving": "disapproves",
    "finding": "finds", "exploring": "explores", "allowing": "allows", "integrating": "integrates", "limiting": "limits",
    "prohibiting": "prohibits", "making": "makes", "submitting": "submits", "revising": "revises", "adjusting": "adjusts",
    "increasing": "increases", "updating": "updates", "modifying": "modifies", "implementing": "implements",
    "rescinding": "rescinds", "reaffirming": "reaffirms", "acknowledging": "acknowledges", "receiving": "receives",
    "concerning": "addresses", "granting": "grants", "creating": "creates", "designating": "designates",
    "rejecting": "rejects", "terminating": "terminates", "exempting": "exempts", "renewing": "renews",
    "deleting": "deletes", "removing": "removes", "enacting": "enacts", "opposing": "opposes", "affirming": "affirms",
    "reconsidering": "reconsiders", "requiring": "requires", "banning": "bans", "expanding": "expands",
    "transferring": "transfers", "vacating": "vacates", "considering": "considers", "reviewing": "reviews",
    "accepting": "accepts", "initiating": "initiates", "pursuing": "pursues", "waiving": "waives", "ratifying": "ratifies",
    "entering": "enters", "executing": "executes", "sending": "sends", "creating": "creates", "naming": "names",
    "consolidating": "consolidates", "certifying": "certifies", "acquiring": "acquires", "disposing": "disposes",
    "dedicating": "dedicates", "accepting": "accepts", "restating": "restates", "allocating": "allocates",
    "appropriating": "appropriates", "increasing": "increases", "decreasing": "decreases", "reducing": "reduces",
    "applying": "applies", "filing": "files", "negotiating": "negotiates", "proclaiming": "proclaims",
    "upholding": "upholds", "taking": "takes", "hiring": "hires", "shifting": "shifts", "starting": "starts",
}
INFINITIVE = {v: k for k, v in {
    "accepts": "accept", "approves": "approve", "authorizes": "authorize", "adopts": "adopt", "awards": "award",
    "establishes": "establish", "directs": "direct", "sets": "set", "confirms": "confirm", "declares": "declare",
    "amends": "amend", "ratifies": "ratify", "receives": "receive", "provides": "provide", "reviews": "review",
    "considers": "consider", "extends": "extend", "supports": "support", "endorses": "endorse", "names": "name",
    "rejects": "reject", "denies": "deny", "allocates": "allocate", "appropriates": "appropriate",
    "takes": "take", "updates": "update", "upholds": "uphold", "hires": "hire", "starts": "start",
}.items()}
INF_TO_3RD = dict(INFINITIVE)  # accept -> accepts


def _cap(s):
    return s[:1].upper() + s[1:]


def verb_lead(q):
    """Make the first verb third-person ('Approving X' / 'Approve X' -> 'Approves X'),
    also converting a later 'and Authorizing' to 'and authorizes'."""
    if re.match(r"intention to\b", q, re.I):
        return "Declares its " + q[0].lower() + q[1:]
    words = q.split(" ")
    if not words:
        return q
    i = 0
    adv = ""
    if words[0].lower() in ("formally", "preliminarily", "summarily") and len(words) > 1:
        adv = "" if words[0].lower() == "formally" else words[0].lower()
        i = 1
    head = words[i].lower().rstrip(",")
    if head in GERUND:
        verb = GERUND[head]
    elif head in INF_TO_3RD:
        verb = INF_TO_3RD[head]
    else:
        return q
    rest = words[i + 1:]
    # later coordinated gerunds: "Approving and Authorizing" / ", Authorizing"
    for j in range(len(rest) - 1):
        if rest[j].lower() in ("and", "and/or", "or") and rest[j + 1].lower().rstrip(",") in GERUND:
            rest[j + 1] = GERUND[rest[j + 1].lower().rstrip(",")] + ("," if rest[j + 1].endswith(",") else "")
    out = f"{adv + ' ' if adv else ''}{verb}".strip()
    return _cap(out) + (" " + " ".join(rest) if rest else "")


STATUS_TAIL = re.compile(r"[\"”]?\s*\.?\s*(Finally passed|Introduced|Adopted|Approved|Accepted|Not adopted|Failed|Continued)\.?\s*(\[[\d\- ]+\])?\s*$", re.I)


def clean(q):
    q = re.sub(r"\s+", " ", q or "").strip().strip('"“” ')
    q = re.sub(r"^(Summary Title|Summary):\s*", "", q, flags=re.I)
    q = STATUS_TAIL.sub("", q).strip().strip('"“” ').rstrip(".:; ")
    q = re.sub(r"\s*\[[\d\- ]+\]\s*$", "", q)
    q = re.sub(r"[.\s]*\((?:Mayor|Vice Mayor|Councilmembers?|Council Members?|Interim City Manager|City Manager|City Attorney|City Clerk)[^)]*\)\s*$", "", q, flags=re.I)
    q = re.sub(r"\bAlameda Municipal Code\b|\bAlameda Municipal Power Code\b", lambda m: "city code" if "Power" not in m.group(0) else "municipal power code", q)
    q = re.sub(r"\bthe Municipal Code\b", "the city code", q)
    q = re.sub(r"\s*\(AMC\)", "", q)
    return q


_VERB_RE = re.compile(r"\b(?i:amending|adding|repealing|deleting|eliminating|revising|renumbering|replacing|reenacting)\b")
_TARGET_RE = re.compile(r"\b(?i:(?:Article|Chapter|Section|Division|Subsection|Charter))s?\s+[\w.\-]+\s*\(([^)]{3,80})\)")


def _code_ops(q):
    """"amending Chapter XXVII (Development Fees) and repealing Section 27-4 (Alameda Point
    Development Impact Fees)": the named, section-level changes a code-amending title makes,
    each paired with the verb that most recently precedes it."""
    q = re.sub(r"\s*\((?:[A-Z][a-z]+ \d{1,2}, \d{4}|\d+)\)", "", q)
    events = sorted([(m.start(), "v", m.group(0).lower()) for m in _VERB_RE.finditer(q)] +
                    [(m.start(), "t", m.group(0)) for m in _TARGET_RE.finditer(q)])
    verb, found = None, []
    for _, kind, text in events:
        if kind == "v":
            verb = text
        elif verb:
            found.append((verb, re.sub(r"\s+", " ", text), text.lower().startswith("section")))
    if any(sec for _, _, sec in found):  # drop the enclosing chapter/article when sections are named
        found = [f for f in found if f[2]]
    by_verb = {}
    for verb, label, _ in found:
        if label not in by_verb.setdefault(verb, []):
            by_verb[verb].append(label)
    parts = [f"{v} " + " and ".join(labels[:2]) for v, labels in by_verb.items() if labels]
    return " and ".join(parts[:2])


def contract_vendor_effect(q):
    """A contract whose amounts and extension options come before the vendor: "Award a One-Year
    Contract, with the Option for Four One-Year Extensions, for an Amount Not to Exceed $363,354,
    ..., to Imperial Maintenance for Janitorial Services" -> keep who and what for."""
    q = clean(q)
    m = re.match(r"(award|authorize(?: the (?:interim )?city manager)?(?: or designee)?(?: to execute)?)\s+(an? (?:[\w-]+ ){0,3}(?:contract|agreement|amendment))\b"
                 r".*?\b(?:not[- ]to[- ]exceed|extensions?)\b.*?,\s*(?:to|with) (?!(?:the|an?) option\b)(?:the following:\s*)?(.+?) for (?!an amount|a total)([A-Za-z].+)$", q, re.I)
    if not m:
        return None
    verb = "Awards" if m.group(1).lower().startswith("award") else "Authorizes"
    return f"{verb} {lc_first(m.group(2))} to {m.group(3).strip()} for {lc_first(m.group(4).strip())}."


def plain_effect(q):
    """Specific rewrites for the common shapes; None when no shape matches."""
    q = clean(q)
    low = q.lower()

    m = re.match(r"(?:establishing|setting)\s+(?:the\s+)?appropriations limit for (?:fiscal year |fy ?)([\d\-]+)", low)
    if m:
        return f"Sets the city's annual spending cap (appropriations limit) for fiscal year {m.group(1)}."

    m = re.match(r"(?:adoption of resolution )?(?:commending|honoring|recognizing)\s+(.+?)['’]s\s+(.*(?:service|contribution|years).*)$", q, re.I)
    if m:
        tail = re.sub(r"\s*(of|to)\s+the City of Alameda\s*", " ", m.group(2)).strip()
        tail = re.sub(r"\bAlameda City Council\b", "the City Council", tail)
        return f"Honors {m.group(1)} for {lc_first(tail)}."
    m = re.match(r"(?:adoption of resolution )?(?:commending|honoring|recognizing)\s+(.+?)\s+for\s+((?:his|her|their)?\s*.*(?:service|contribution|years).*)$", q, re.I)
    if m:
        who = m.group(1)
        tail = re.sub(r"^(his|her|their)\s+", "", m.group(2).strip())
        tail = re.sub(r"\s*(of|to)\s+the City of Alameda\s*", " ", tail)
        tail = re.sub(r"\bAlameda City Council\b", "the City Council", tail)
        return f"Honors {who} for {lc_first(tail.strip())}."

    m = re.match(r"(re)?appointing\s+(.+?)\s+(?:as|to)\s+(?:a\s+|an\s+|the\s+)?(?:landlord |tenant )?member(?:s)?\s+(?:of|to)\s+(?:the\s+)?(.+)$", q, re.I)
    if m:
        body = re.sub(r",?\s*(to|for)\s+(a|an|the)?\s*(one|two|three|four|\d+)[- ]?\w*\s*(year|term).*$", "", m.group(3), flags=re.I)
        body = re.sub(r"\s*\((?:[A-Z]{3,6})\)", "", body)
        return f"{'Reappoints' if m.group(1) else 'Appoints'} {m.group(2)} to the {body}."

    m = re.match(r"amending the (?:fiscal year|fy)\s*\(?(?:fy\)?)?\s*([\d\-]+)\s+(.*?budget)\b\s*(.*)$", q, re.I)
    if m:
        yr, what, tail = m.group(1), m.group(2).lower(), m.group(3).strip()
        kind = "capital budget" if "capital" in what else "budget"
        if "general fund" in what:
            kind = "general fund budget"
        tail = re.sub(r"\s*\([\d]{5,}\)", "", tail)
        base = f"Amends the {yr} {kind}"
        if not tail:
            return base + "."
        first = tail.split(" ")[0].lower()
        if first in GERUND:
            return f"{base} by {tail[0].lower() + tail[1:]}."
        return f"{base} {lc_first(tail)}."

    m = re.match(r"approving (?:the |a )?(final|parcel|tentative|vesting tentative)\s+(?:tract )?map\b", low)
    if m:
        kind = m.group(1)
        tract = re.search(r"tract\s+(?:no\.?\s*)?(\d+)", q, re.I)
        parcel = re.search(r"parcel map no\.?\s*(\d+)", q, re.I)
        place = [p for p in re.findall(r"\(([^)]{6,60})\)", q) if not p.isupper() and not re.search(r"\d{3}", p)]
        ref = f" for Tract {tract.group(1)}" if tract else (f" (No. {parcel.group(1)})" if parcel else "")
        extra = f" ({place[0]})" if place and tract else ""
        return f"Approves a {kind} map{ref}{extra} to subdivide property."

    e = contract_vendor_effect(q)
    if e:
        return e

    # A lease ordinance: "Approving a Lease and Authorizing the City Manager to Execute Documents
    # Necessary to Implement the Terms of a Ten Year Lease with Acme for Building 12" -> say what lease, with whom
    m = re.match(r"approving\b.*?\bterms of (?:the |a |an )?(.{0,60}?\b(?:lease|license|sublease)\b.{0,30}?)\s+(?:with|between)\s+(.+)$", q, re.I)
    if m and re.search(r"\band authorizing\b", q, re.I):
        what = lc_first(m.group(1).strip().rstrip(","))
        lead = re.match(r"approving\s+(?:the |a |an )?((?:\w+\s+){0,2}amendment to (?:the |a )?(?:lease|license|sublease))\b", q, re.I)
        if lead and "amendment" not in what.lower():   # "Approving the First Amendment to the Lease and Authorizing ... Terms of the Lease with X"
            return f"Approves the {lc_first(lead.group(1).strip())} with {m.group(2).strip()}."
        art = "an" if what[:1].lower() in "aeiou" else "a"
        return f"Approves {art} {what} with {m.group(2).strip()}."

    m = re.match(r"(amending|adding|repealing|deleting|revising)\b.*?\b(city code|municipal power code)\b(.*)$", q, re.I)
    if m:
        verb = GERUND[m.group(1).lower()]
        what = "the " + m.group(2).lower()
        rest = m.group(3)
        sub = re.search(r"\(([^)]{4,70})\)", rest)
        tail = re.search(r"\b(?:to|concerning|pertaining to|regarding|relating to)\s+(.+)$", re.sub(r"\s*\([^)]*\)", "", rest), re.I)
        if tail:
            t = re.sub(r"\s*\([^)]*\)", "", tail.group(1)).strip().rstrip(".")
            joiner = "to" if re.match(r"(require|prohibit|allow|modify|establish|add|create|ban|make|clarify|streamline|comply|implement|remove|limit|change|update|amend|revise|provide|permit|authorize|increase|extend|adopt|raise|comprehensively|reduce|repeal|eliminate|expand|rename|enact|conform|correct|designate|exempt|adjust|specify|reorganize|restrict|regulate|delay|suspend)\b", t, re.I) else "on"
            return f"{_cap(verb)} {what} {joiner} {lc_first(t)}."
        ops = _code_ops(q)
        if ops:
            return f"Amends {what} by {ops}."
        by = re.sub(r"\s*\([^)]*\)", "", rest).strip(" ,.;:")
        by = re.sub(r"^(?:and\s+)", "", by.lstrip(" ,;:"))
        by = re.sub(r"^(?:by\s+)?(?:(?:Article|Chapter|Section|Division)s?\s+[\w.\-]+(?:,?\s+(?:of|and)\s+(?:the\s+)?)?)+", "", by, flags=re.I).strip(" ,.;:")
        if len(by.split()) >= 4 and by.split()[0].lower() in GERUND:
            return f"Amends {what} by {by[0].lower() + by[1:]}."
        if sub:
            return f"{_cap(verb)} {what} to cover {lc_first(sub.group(1))}."
        return f"{_cap(verb)} provisions of {what}."

    m = re.match(r"authorizing the filing of an application for\s+(.+)$", q, re.I)
    if m:
        return f"Authorizes applying for {lc_first(m.group(1))}."
    return None



# Lowercase title-case words that are plainly not names: infinitives after "to",
# gerunds after by/for/and, and generic contract nouns after an article. Names
# (Alameda Point, Jean Sweeney Park) are never touched.
TO_VERBS = {"execute", "allow", "appropriate", "increase", "require", "provide", "implement", "negotiate", "enter", "complete",
            "accept", "approve", "authorize", "modify", "establish", "prohibit", "conform", "comply", "adopt", "amend",
            "extend", "support", "continue", "apply", "submit", "ratify", "award", "waive", "adjust", "update", "revise",
            "create", "designate", "include", "address", "reduce", "transfer", "purchase", "sell", "lease", "renew",
            "fund", "pay", "reimburse", "end", "participate", "carry", "take", "make", "set", "levy", "order", "consider",
            "explore", "review", "direct", "proceed", "reject", "terminate", "execute", "ban", "clarify", "streamline"}
GENERIC_NOUNS = {"agreement", "agreements", "amendment", "amendments", "contract", "contracts", "lease", "license", "policy",
                 "report", "application", "resolution", "ordinance", "budget", "schedule", "letter", "documents", "services",
                 "purchase", "sale", "escrow", "instructions", "year", "years", "month", "term", "extension", "proposal",
                 "request", "plan", "grant", "funding", "program", "fee", "fees", "rate", "rates", "charges", "regulations"}
TERMS = re.compile(r"\b((?:One|Two|Three|Four|Five|Six|Seven|Eight|Ten|Twelve|\d+)[- ](?:Year|Month|Day)s?)\b")


def casefix(s):
    # infinitive verbs after "to" / "and" / "or" (e.g. "to Execute", "negotiate and Execute")
    def verb(m):
        w = m.group(2)
        return m.group(1) + (w.lower() if w.lower() in TO_VERBS else w)
    s = re.sub(r"\b(to |and |or )([A-Z][a-z]+)\b", verb, s)
    # participles that are never part of a name
    s = re.sub(r"\b(Concerning|Pertaining|Regarding|Relating|Including|Establishing|Governing|Authorizing|Approving|Providing|Amending)\b(?= (?:to |the |a |an |all |any |capital|rental|and ))",
               lambda m: m.group(1).lower(), s) if False else s
    s = re.sub(r"(?<=[a-z] )(Concerning|Pertaining to|Regarding|Relating to)\b", lambda m: m.group(1).lower(), s)
    s = re.sub(r"\b(by|for|and|of|including|regarding|concerning|while|then|consider) ([A-Z][a-z]+ing)\b",
               lambda m: f"{m.group(1)} " + (m.group(2).lower() if m.group(2).lower() in GERUND else m.group(2)), s)
    def art(m):
        art_, run = m.group(1), m.group(2)
        words = run.split(" ")
        if all(w.lower() in GENERIC_NOUNS or w.lower() in ("and", "or", "of") or TERMS.fullmatch(w)
               or re.fullmatch(r"(?:One|Two|Three|Four|Five|Six|Ten|\d+)-(?:Year|Month)", w) for w in words):
            return art_ + " " + " ".join(w.lower() for w in words)
        return m.group(0)
    s = re.sub(r"\b(a|an|the|this) ((?:[A-Z][\w-]*)(?: (?:and |or |of )?[A-Z][\w-]*)*)(?=[ ,.;:]|$)", art, s)
    return s


# --------------------------------------------------------------- shortening

CUT_AT = [
    r",? (?:in|for) an? (?:total )?(?:aggregate )?(?:amount|compensation|sum)\b.*$",
    r",? (?:not|no)[- ]to[- ]exceed\b(?!\s*\$).*$",
    r",? including\b.*?(?=,\s+(?:for|to|by|on|with|in|at|from)\b|$)",   # keep a later ", for <whom>" clause
    r",? pursuant to\b.*$",
    r",? in accordance with\b.*$",
    r",? in compliance with\b.*$",
    r",? as a condition (?:of|to)\b.*$",
    r",? dated as of\b.*$",
    r",? located (?:at|on)\b.*$",
    r",? effective\b.*$",
    r",? with an effective date\b.*$",
    r",? substantially in the form\b.*$",
    r",? as set forth\b.*$",
    r",? as described\b.*$",
    r",? and (?:authorizes|approves|provides|adopts|directs|authorizing|approving|providing|adopting|directing|ordering|declaring|setting)\b.*$",
    r",? (?:a|an) (?:California|Delaware|Nevada|Texas|Maryland|Ohio|Colorado) [a-z ]*(?:corporation|company|limited liability company|partnership)\b.*$",
    r",? dba\b.*$",
    r",? d/b/a\b.*$",
    r",? under\b.*$",
    r",? for the period\b.*$",
    r",? for a term of\b.*$",
    r",? with an option\b.*$",
    r",? relating to\b.*$",
    r",? in favor of\b.*$",
    r":\s.*$",
    r";\s.*$",
]
PAREN = re.compile(r"\s*\([^)]*\)")


def _n(s):
    return len(s.split())


def shorten(s, limit=LIMIT):
    """Trim to <= limit words: drop parentheticals, then trailing legal clauses
    at natural boundaries, then (last resort) cut at a word and add an ellipsis."""
    s = s.strip()
    if _n(s) <= limit:
        return s
    end = "." if s.endswith(".") else ""
    core = s.rstrip(".")
    t = PAREN.sub("", core)
    if _n(t) <= limit:
        return t.strip().rstrip(",") + end
    best = t
    for pat in CUT_AT:
        cand = re.sub(pat, "", best, flags=re.I).strip().rstrip(",")
        if cand and _n(cand) >= 6:
            best = cand
        if _n(best) <= limit:
            return best + end
    words = best.split()
    head = " ".join(words[:limit - 1])
    # prefer a clause boundary in the back half of the allowed length
    cut = head
    for m in re.finditer(r",(?= )| (?:for|and|with|from|at|in|to|on|using|by|that) ", head):
        before = head[:m.start()]
        last = before.split(" ")[-1].lower().strip(",;:")
        if _n(before) >= 9 and not re.search(r"(?:city code|municipal power code)$", before) \
                and last not in GERUND and last not in GERUND.values() and last not in ("by", "and", "or", "of", "to", "the", "a", "an"):
            cut = before
    cut = cut.rstrip(",;:")
    for _ in range(3):  # strip dangling connectors and stranded verbs
        last = cut.split(" ")[-1].lower().strip(",;:") if cut else ""
        if last in ("and", "or", "of", "to", "for", "the", "a", "an", "in", "on", "at", "by", "with", "from", "that", "which") \
                or last in GERUND or last in GERUND.values():
            cut = cut.rsplit(" ", 1)[0].rstrip(",;: ")
    return cut + "…"


def effect_sentence(q):
    """Verb-led, de-cluttered summary sentence for a resolution/ordinance title."""
    e = plain_effect(q)
    if not e:
        e = verb_lead(clean(q)).rstrip(".") + "."
    return casefix(e)


def _tidy(summary):
    s = re.sub(r"\s+", " ", summary or "").strip()
    s = re.sub(r"^[\"“”']+|[\"“”']+$", "", s)
    s = re.sub(r"\b(Summary Title|Summary):\s*", "", s)
    s = re.sub(r"\.\s*(Finally passed|Introduced|Adopted|Approved|Accepted|Not adopted)\.?\s*(\[[\d\- ]+\])?\s*$", ".", s, flags=re.I)
    s = re.sub(r":+\.$", ".", s)
    s = re.sub(r"\s+([,.;:])", r"\1", s)
    s = re.sub(r",+\s*\.", ".", s).replace(",,", ",")
    s = re.sub(r"\.\s*(Introduced|Adopted|Finally passed|Approved|Accepted)\.?(\s*\([^)]*\))?\.?$", ".", s, flags=re.I)
    s = re.sub(r",? or (?:his|her|their) designee,?", "", s, flags=re.I)
    s = re.sub(r",? or designee,?", "", s, flags=re.I)
    s = re.sub(r"^(Authorizes|Approves) for the\b", r"\1 the", s)
    s = re.sub(r"^Recommends Providing Direction to (?:City )?Staff (to|on|regarding|for)\b", r"Gives staff direction \1", s)
    if s.count("(") < s.count(")"):
        s = re.sub(r"(?<=\w)\)", "", s, count=s.count(")") - s.count("("))
    if s.count("(") > s.count(")"):
        s = re.sub(r"\s*\([^)]*$", "", s)
    first = s.split(" ")[0].lower().rstrip(",") if s else ""
    if first in GERUND or first in INF_TO_3RD or re.match(r"intention to\b", s, re.I):
        s = verb_lead(s)
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return casefix(s)


def _finish(s):
    ell = s.endswith("…")
    core = s.rstrip(".…")
    for _ in range(3):  # no sentence ends on a connector ("...to increase the.")
        m = re.search(r"(?:^|[\s;,-])(and|or|the|a|an|of|to|for|in|with|by|at|from|that|which|;|-)$", core, re.I)
        if m:
            core = core[:m.start()].rstrip(",;: -")
    return core + ("…" if ell else ".")


# Public Works project numbers and capital-project codes mean nothing to a reader:
# ", No. P.W. 04-25-08 (CIP C16000)", "(P.W. No. 04-24-13)", ", Project No. PW 02-22-18"
_PW_ID = r"(?:Project\s+)?(?:No\.?\s*)?P\.?\s?W\.?\s*(?:No\.?\s*)?\d[\d\-]*"
PROJECT_ID_RE = re.compile(r"(?:,\s*|\s+)?\(?" + _PW_ID + r"(?:\s*\(CIP\s*[A-Z]*\d+\))?\)?", re.I)
CIP_PAREN_RE = re.compile(r"\s*\(CIP\s*[A-Z]*\d+\)", re.I)


def strip_project_ids(s):
    s = CIP_PAREN_RE.sub("", PROJECT_ID_RE.sub("", s))
    return re.sub(r"\s+([,.;])", r"\1", re.sub(r",\s*([,.])", r"\1", s))


def polish_pair(summary):
    """(short, full): the <=25-word summary and, when it was cut, the complete
    cleaned sentence so the site can show the rest on hover or tap."""
    base = _tidy(strip_project_ids(summary))
    return _finish(shorten(base)), _finish(base)


def polish(summary):
    return polish_pair(summary)[0]

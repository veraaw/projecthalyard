"""Extract the target company from a raw Slack message. Pure: no file paths, no I/O.

    ex = extract("Calderon Aerospace introduced us to Kestrel Airlines, "
                 "but the account I actually need is Ironvale Steel", resolver)
    ex.target.text        # "Ironvale Steel"
    ex.target.resolution  # resolver.resolve("Ironvale Steel")

Every company mention is scored by the phrase that introduces it, never by
where it sits in the message: "the account I actually need is" scores +3,
"we need" / "I need" +2, "introduced us to" -1, "we sell into" -2, and an explicit
negation ("Not X", "X — that's a different entity") -3. The target is the best-scoring
mention with a positive score; when nothing positive is said the message has
no target (a person with no company, "a large logistics business").

A bare domain ("email domain is bexleybio.com") is a mention too, scored like
a strong cue and resolved on the domain rather than on a name.

Mentions the CRM does not know (Kingsmere Retail Group) are still extracted;
their resolution is simply unmatched, so the caller can route them to a human.

When a resolver is given, the message is also scanned for every name it knows,
in any case ("how about harrowgate health"); `known` widens that scan to more
spellings (companies on file with no CRM account). Such a mention scores +1
only when no cue fired positively and it is the sole company named that way;
two or more bare names, or a bare name beside cue-scored ones, score 0 and
leave the decision to the cues or to a human.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from golden.resolver import Resolution, Resolver

# A company span: capitalised words, stopping at punctuation or a lowercase word.
_CO = r"[A-Z][A-Za-z0-9&'-]*(?:[ \t]+[A-Z][A-Za-z0-9&'-]*)*"
_LIST = rf"{_CO}(?:(?:,[ \t]*|,?[ \t]+and[ \t]+){_CO})*"
_SPLIT = re.compile(r",[ \t]*and[ \t]+|,[ \t]*|[ \t]+and[ \t]+")
_NOT = r"(?:\b[Nn]ot[ \t]+)?"   # keeps a leading "Not" out of a span-first cue's company
_NOT_AT = r"(?![A-Za-z0-9&'-])(?![^.?!,;—]*\bat\b)"   # "reach Head of Platform Engineering at X": the title is not the company

# (cue label, regex with a <co> group, score). A mention keeps the first cue
# that fires on it, in this order.
CUES: list[tuple[str, re.Pattern, int]] = [
    ("the account I actually need is", rf"the account I actually need is (?P<co>{_CO})", 3),
    ("is the target", rf"{_NOT}(?P<co>{_CO}) is the target", 3),
    ("is the account", rf"{_NOT}(?P<co>{_CO}) is the account", 2),
    ("we need", rf"(?:we|I) need (?P<co>{_CO})", 2),
    ("need help getting to", rf"need help getting to (?P<co>{_CO})", 2),
    ("need an intro at", rf"need an intro (?:at|to|into) (?P<co>{_CO})", 2),
    ("any connections into", rf"connections? into (?P<co>{_CO})", 2),
    ("who do we know at", rf"who do we know at (?P<co>{_CO})", 2),
    ("does anyone know anyone at", rf"know(?:s)? (?:anyone|someone) at (?P<co>{_CO})", 2),
    ("trying to reach ... at", rf"trying to reach (?:the )?[^.?!,;—]*? at (?P<co>{_CO})", 2),
    ("asking again:", rf"asking again:[ \t]*(?P<co>{_CO})", 2),
    ("long shot —", rf"long shot[ \t]*[—–-][ \t]*(?P<co>{_CO})", 2),
    ("intro to", rf"intro(?:duction)?s? (?:at|to|into|with) (?P<co>{_CO})", 2),
    ("introduce us to", rf"introduce (?:me|us) to (?P<co>{_CO})", 2),
    ("connect with", rf"connect (?:me |us )?(?:with|to) (?P<co>{_CO})", 2),
    ("get in front of", rf"get(?:ting)? (?:me |us )?(?:in front of|into|in at|in with) (?P<co>{_CO})", 2),
    ("an in at", rf"\ban in (?:at|with|into) (?P<co>{_CO})", 2),
    ("anyone at", rf"(?:anyone|someone|anybody|somebody|contacts?) (?:at|inside) (?P<co>{_CO})", 2),
    ("help with", rf"help (?:me |us )?(?:with|at|into|reach|reaching) (?P<co>{_CO})", 2),
    ("reach", rf"reach(?:ing)? (?:out to )?(?P<co>{_CO}){_NOT_AT}", 2),
    ("meeting with", rf"(?:meeting|talk|speak|conversation) (?:with|at) (?P<co>{_CO})", 2),
    ("path to", rf"path (?:in)?to (?P<co>{_CO})", 1),
    ("way into", rf"(?:way|route|door|line|entry) (?:in)?to (?P<co>{_CO})", 1),
    ("not X", rf"\b[Nn]ot (?P<co>{_CO})", -3),
    ("that's a different entity", rf"{_NOT}(?P<co>{_CO})[ \t]*[—–-]+[ \t]*that's a different entity", -3),
    ("spoke to", rf"spoke (?:to|with) (?P<co>{_CO})", -1),
    ("introduced us to", rf"introduced us to (?P<co>{_CO})", -1),
    ("introduced us", rf"{_NOT}(?P<co>{_CO}) introduced us", -1),
    ("our champion at", rf"[Oo]ur champion at (?P<co>{_CO})", -1),
    ("is a supplier of theirs", rf"{_NOT}(?P<co>{_CO}) is a supplier", -1),
    ("we sell into", rf"we sell into (?P<co>{_LIST})", -2),
]
_CUES = [(label, re.compile(pat), score) for label, pat, score in CUES]

DOMAIN_CUE = "email domain"
DOMAIN_SCORE = 3
KNOWN_CUE = "known company name"
KNOWN_SCORE = 1
_DOMAIN = re.compile(r"\b(?:https?://)?(?:www\.)?([a-z0-9-]+(?:\.[a-z0-9-]+)*\.(?:com|co\.uk|ai|io|net|org|co))\b", re.I)

# The title wanted, when the message names one: a C-suite title in full or as
# initials, a VP/SVP/EVP line, or a Head of. Matched as a phrase, wherever it sits.
_WORDS = r"[A-Z][A-Za-z]+(?:[ \t](?:&|and|of)[ \t][A-Z][A-Za-z]+|[ \t][A-Z][A-Za-z]+)*"
_TITLE = rf"Chief[ \t][A-Z][a-z]+[ \t]Officer|C[A-Z]O|[SE]?VP(?:[ \t]of)?[ \t]{_WORDS}|Head[ \t]of[ \t]{_WORDS}"
TITLE_RE = re.compile(rf"(?<![A-Za-z])(?P<t>{_TITLE})(?![A-Za-z])")


@dataclass
class Mention:
    text: str
    cue: str
    score: int
    start: int
    is_domain: bool = False
    resolution: Resolution | None = None

    @property
    def company_id(self) -> str:
        return self.resolution.entity_id if self.resolution else ""


@dataclass
class Extraction:
    text: str
    mentions: list[Mention] = field(default_factory=list)

    @property
    def target(self) -> Mention | None:
        positive = [m for m in self.mentions if m.score > 0]
        if not positive:
            return None
        return max(positive, key=lambda m: (m.score, -m.start))

    @property
    def target_id(self) -> str:
        return self.target.company_id if self.target else ""


def extract(text: str, resolver: Resolver | None = None, known: re.Pattern | None = None) -> Extraction:
    text = text or ""
    if known is None and resolver is not None:
        known = resolver.names_regex()
    seen: dict[tuple[int, str], Mention] = {}

    for label, pat, score in _CUES:
        for m in pat.finditer(text):
            start = m.start("co")
            for part in _SPLIT.split(m.group("co")):
                part = part.strip()
                if not part:
                    continue
                key = (text.find(part, start), part)
                if key not in seen:
                    seen[key] = Mention(part, label, score, key[0])
                start = key[0] + len(part)

    for m in _DOMAIN.finditer(text):
        dom = m.group(1).lower()
        key = (m.start(1), dom)
        if key not in seen:
            seen[key] = Mention(dom, DOMAIN_CUE, DOMAIN_SCORE, m.start(1), is_domain=True)

    if known is not None:
        taken = [(x.start, x.start + len(x.text)) for x in seen.values()]
        found = [m for m in known.finditer(text)
                 if not any(m.start() < e and s < m.end() for s, e in taken)]
        positive = any(x.score > 0 for x in seen.values())
        score = KNOWN_SCORE if len(found) == 1 and not positive else 0
        for m in found:
            seen[(m.start(), m.group())] = Mention(m.group(), KNOWN_CUE, score, m.start())

    mentions = sorted(seen.values(), key=lambda x: x.start)
    if resolver is not None:
        for x in mentions:
            x.resolution = resolver.resolve("", x.text) if x.is_domain else resolver.resolve(x.text)
    return Extraction(text, mentions)


def extract_title(text: str) -> str:
    """The first title named in the message, or '' when none is."""
    m = TITLE_RE.search(text or "")
    return m.group("t") if m else ""


def extract_target_id(text: str, resolver: Resolver) -> str:
    """One company ID for the message, or '' when there is no target or a human must decide."""
    return extract(text, resolver).target_id

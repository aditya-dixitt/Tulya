"""Finding standard designations in a material description.

A description says "HEX BOLT M12 IS 1367 PT-3 CL 8.8" or "PIPE ASTM A106 GR.B".
Those tokens are the hook into the knowledge graph, and they are written a
dozen ways: with and without spaces, colons, full stops, "PART"/"PT", "GRADE"/
"GR", upper and lower case.

Recognition is deliberately conservative. A designation that does not match the
shape of a real standard reference is not recovered at all, because a false
designation pulls in a relationship edge and an edge is evidence a steward is
being asked to trust. Missing one costs a review; inventing one costs the
argument.

Pure module: no database, no network, no model.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# Bodies whose designations appear in CPSE material masters. Longest-first so
# "BS EN" wins over "BS", and "IS/ISO" over "IS".
BODIES = (
    "BS EN", "IS/ISO", "IS/IEC", "ASTM", "ASME", "DIN", "ISO", "IEC", "JIS",
    "SAE", "AISI", "UNS", "API", "BS", "EN", "IS",
)

_BODY_ALT = "|".join(re.escape(b).replace(r"\ ", r"\s*") for b in BODIES)

# body [sep] number [/part] [suffixes like PART 3, GR B, CLASS 8.8]
_DESIGNATION = re.compile(
    rf"\b(?P<body>{_BODY_ALT})"
    r"\s*[:\-]?\s*"
    # trailing ":2017" is the edition year and is part of the reference
    r"(?P<number>[A-Z]?\d{2,6}(?:[./-]\d{1,4})*(?::\d{4})?)"
    # "PT-3", "PT.3", "PART 3" and "CL 8.8" are all the same shape
    r"(?P<suffix>(?:\s*(?:PART|PT|GRADE|GR|CLASS|CL|TYPE|TY)\s*[-.:]?\s*[A-Z0-9.]{1,6})*)",
    re.IGNORECASE,
)

_SUFFIX_WORD = re.compile(
    r"(PART|PT|GRADE|GR|CLASS|CL|TYPE|TY)\s*[-.:]?\s*([A-Z0-9.]+)", re.IGNORECASE)
_CANON_SUFFIX = {"PT": "PART", "GR": "GRADE", "CL": "CLASS", "TY": "TYPE"}
_FLAT = re.compile(r"[^A-Z0-9]")


@dataclass(frozen=True)
class Designation:
    """One standard reference as it was written, plus its canonical key."""

    raw: str            # exactly as it appeared, for showing a steward
    body: str           # IS / ASTM / BS EN ...
    number: str         # 1367 / A106 / 10204
    parts: tuple[str, ...]   # ("PART 3", "CLASS 8.8")
    normalised: str     # IS1367PART3CLASS8.8 — matches StandardDesignation.normalised

    def as_dict(self) -> dict:
        return {"raw": self.raw, "body": self.body, "number": self.number,
                "parts": list(self.parts), "normalised": self.normalised}


def normalise(text: str) -> str:
    """The key both sides of the lookup agree on: upper, alphanumerics only.

    `StandardDesignation.normalised` is populated with this function, so a
    designation found in a description and one seeded from a standards list
    collide iff they mean the same reference.
    """
    return _FLAT.sub("", (text or "").upper())


def _parts_of(suffix: str) -> tuple[str, ...]:
    out = []
    for word, value in _SUFFIX_WORD.findall(suffix or ""):
        word = word.upper()
        out.append(f"{_CANON_SUFFIX.get(word, word)} {value.upper().rstrip('.')}")
    return tuple(out)


def find(text: str) -> list[Designation]:
    """Every standard designation in `text`, in order, de-duplicated by key."""
    seen: set[str] = set()
    out: list[Designation] = []
    for m in _DESIGNATION.finditer(text or ""):
        body = re.sub(r"\s+", " ", m.group("body").upper()).strip()
        number = m.group("number").upper()
        parts = _parts_of(m.group("suffix"))
        key = normalise(body + number + "".join(parts))
        if key in seen:
            continue
        seen.add(key)
        out.append(Designation(raw=m.group(0).strip(), body=body, number=number,
                               parts=parts, normalised=key))
    return out


def keys(text: str) -> list[str]:
    """Just the lookup keys — what a repository query needs."""
    return [d.normalised for d in find(text)]

"""Token-set ratio.

Production is rapidfuzz.fuzz.token_set_ratio. The difflib re-implementation is
kept only so the engine runs on a machine without rapidfuzz; it follows the same
procedure but on SequenceMatcher rather than Levenshtein, so the scores track
closely and are NOT bit-identical. strict mode refuses it.
"""
from __future__ import annotations

import difflib
import functools

from .backends import resolve_fuzzy

_RESOLVED = resolve_fuzzy(strict=False)
BACKEND = _RESOLVED.name

if BACKEND == "rapidfuzz":
    from rapidfuzz.fuzz import token_set_ratio as _token_set_ratio
else:  # pragma: no cover - only on machines without rapidfuzz
    def _ratio(a: str, b: str) -> float:
        if a == b:
            return 100.0
        if not a or not b:
            return 0.0
        return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() * 100.0

    def _token_set_ratio(a: str, b: str) -> float:
        ta, tb = set(a.split()), set(b.split())
        if not ta or not tb:
            return 0.0
        inter = sorted(ta & tb)
        s_i = " ".join(inter)
        s_a = " ".join(inter + sorted(ta - tb)).strip()
        s_b = " ".join(inter + sorted(tb - ta)).strip()
        if not s_i:
            return _ratio(s_a, s_b)
        return max(_ratio(s_i, s_a), _ratio(s_i, s_b), _ratio(s_a, s_b))


@functools.lru_cache(maxsize=400_000)
def token_set_ratio(a: str, b: str) -> float:
    return float(_token_set_ratio(a, b))


def describe() -> dict:
    return _RESOLVED.as_dict()

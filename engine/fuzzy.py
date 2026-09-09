"""token_set_ratio, rapidfuzz's algorithm, on the standard library.

rapidfuzz is not installable in this sandbox, so the same procedure runs on
difflib.SequenceMatcher instead of Levenshtein. Scores track rapidfuzz closely
but are not bit-identical; set SAMANVAY_FUZZY=rapidfuzz on a machine that has it.
"""
import os, difflib, functools

BACKEND = "difflib"
try:
    if os.environ.get("SAMANVAY_FUZZY", "auto") != "difflib":
        from rapidfuzz.fuzz import token_set_ratio as _rf   # noqa
        BACKEND = "rapidfuzz"
except Exception:
    BACKEND = "difflib"


def _ratio(a, b):
    if a == b:
        return 100.0
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio() * 100.0


@functools.lru_cache(maxsize=400_000)
def token_set_ratio(a: str, b: str) -> float:
    if BACKEND == "rapidfuzz":
        return _rf(a, b)
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

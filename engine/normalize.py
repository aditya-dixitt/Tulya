"""Text canonicalisation. Reads the SAME dictionary the generator corrupts with,
in the opposite direction - one source of truth for what an abbreviation means."""
import re, unicodedata, pathlib, yaml, functools

D = pathlib.Path(__file__).parent.parent / "data/dictionaries"
_ABB = yaml.safe_load(open(D / "abbreviations.yaml"))
_UNI = yaml.safe_load(open(D / "units.yaml"))

# reverse map: abbreviation -> canonical, longest first so "s.s." beats "s"
_REV = sorted(((v.lower(), k) for k, vs in _ABB.items() for v in vs),
              key=lambda t: -len(t[0]))
_UREV = sorted(((v.lower(), u["canonical"]) for u in _UNI.values() for v in u["variants"]),
               key=lambda t: -len(t[0]))

_MAT_SPLIT = re.compile(r"\b(ss|cs|ms|ci|gi|nbr)[\s\-.]*(\d{3})\b", re.I)
_WS = re.compile(r"\s+")

# One alternation instead of ~150 sequential passes. Alternatives are ordered
# longest-first, so the regex engine's leftmost-longest choice reproduces the
# behaviour of applying the longest abbreviation first.
_ABB_MAP = {a: c for a, c in _REV}
_ABB_RE = re.compile(r"(?<![a-z0-9])(" +
                     "|".join(re.escape(a) for a, _ in _REV) + r")(?![a-z0-9])")
_UNI_MAP = {v: c for v, c in _UREV}
_UNI_RE = re.compile(r"(?<![a-z])(" +
                     "|".join(re.escape(v) for v, _ in _UREV) + r")(?![a-z0-9])")


@functools.lru_cache(maxsize=200_000)
def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text)).lower()
    t = t.replace("&", " and ").replace("+", " ")
    # fractional inches must survive: 1/4 and 3/4 and 4 are three different bores
    t = re.sub(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)",
               lambda m: f"{int(m.group(1))/int(m.group(2)):g}", t)
    t = re.sub(r"[()\[\],;:/#]", " ", t)
    t = _MAT_SPLIT.sub(r"\1 \2", t)                       # ss304 -> ss 304

    t = _ABB_RE.sub(lambda m: _ABB_MAP[m.group(1)], t)    # expand abbreviations
    t = _UNI_RE.sub(lambda m: f" {_UNI_MAP[m.group(1)]} ", t)   # canonicalise units

    t = re.sub(r"\bgr\b(?!\s+[a-z]\b)", "graphite", t)   # GR=graphite, but not "GR B"
    t = re.sub(r"\b([m])\s*(\d{1,2})\s*[x*\-]\s*(\d+)", r"m\2 x \3", t)   # M12X50
    t = re.sub(r"(\d)\s*[x*]\s*(\d)", r"\1 x \2", t)
    t = re.sub(r"(\d+(?:\.\d+)?)\s*cm\b",                                  # cm -> mm
               lambda m: f"{float(m.group(1))*10:g} mm", t)
    t = re.sub(r"[.\-]+(?=\s|$)", " ", t)
    t = re.sub(r"(?<=\d)\.(?=\s)", " ", t)
    return _WS.sub(" ", t).strip()

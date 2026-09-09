"""Attribute extraction from NORMALISED text.

The engine never sees the generator's private truth - specs are recovered from
the description alone, exactly as they would be from a real ERP extract.

Comparison is deliberately THREE-STATE:
    MATCH     known on both sides and equal
    MISMATCH  known on both sides and different   -> vetoes the pair
    UNKNOWN   missing on either side              -> excluded, never a mismatch
Treating UNKNOWN as MISMATCH would turn every sparsely-described legacy row into
a false negative, which is the most common way this kind of system quietly fails.
"""
import re

MATERIALS = [  # longest phrase first so compound grades win
    ("stainless steel 316 graphite", "SS316GR"), ("stainless steel 304 graphite", "SS304GR"),
    ("compressed asbestos fibre", "CAF"), ("high tensile 8.8", "HT88"),
    ("stainless steel 316", "SS316"), ("stainless steel 304", "SS304"),
    ("galvanised iron", "GI"), ("carbon steel", "CS"), ("mild steel", "MS"),
    ("cast iron", "CI"), ("a106 gr b", "A106B"), ("wcb", "WCB"),
    ("nitrile", "NBR"), ("viton", "VITON"), ("epdm", "EPDM"), ("graphite", "GRAPHITE"),
]

_P = {
    "thread":        re.compile(r"\bm(\d{1,2})\b(?!\s*hr)"),   # not the m3/hr in a pump
    "bore_in":       re.compile(r"(\d+(?:[./]\d+)?)\s*inch\b"),
    "pressure_class":re.compile(r"\bclass\s*(\d{3,4})\b"),
    "bearing_desig": re.compile(r"\b(6\d{3}|nu\d{3}|2\d{4})\b"),
    "seal_type":     re.compile(r"\b(2rs|zz|open)\b"),
    "schedule":      re.compile(r"\bsch\s*(\d+)\b|\b(xs)\b"),
    "cores":         re.compile(r"(\d+(?:\.\d+)?)\s*core\b"),
    "csa_sqmm":      re.compile(r"(\d+(?:\.\d+)?)\s*sqmm\b"),
    "voltage_kv":    re.compile(r"(\d+(?:\.\d+)?)\s*kv\b"),
    "power_kw":      re.compile(r"(\d+(?:\.\d+)?)\s*kw\b"),
    "rpm":           re.compile(r"(\d+)\s*rpm\b"),
    "cap_m3hr":      re.compile(r"(\d+(?:\.\d+)?)\s*m3\s*hr\b"),
    "head_m":        re.compile(r"\bhead\s*(\d+(?:\.\d+)?)\s*m\b"),
    }

# Keys that identify the item. A conflict on any of these vetoes the pair.
HARD_KEYS = ["thread", "length_mm", "bore_in", "pressure_class", "material_grade",
             "bearing_desig", "seal_type", "schedule", "cores", "csa_sqmm",
             "voltage_kv", "power_kw", "rpm", "id_mm", "section_mm",
             "cap_m3hr", "head_m", "dim_mm"]



_THREAD_X = re.compile(r"\bm(\d{1,2})\s*x\s*(\d+(?:\.\d+)?)\b(?!\s*hr)")
_FASTENER = re.compile(r"\b(bolt|nut|washer|stud)\b")
_MM = re.compile(r"(\d+(?:\.\d+)?)\s*mm\b")


def _mm_fields(t):
    """Millimetre values mean different things by context; resolve by neighbours."""
    out = {}
    for m in _MM.finditer(t):
        val, pre, post = m.group(1), t[max(0, m.start() - 14):m.start()], t[m.end():m.end() + 12]
        if post.lstrip().startswith("id"):
            out["id_mm"] = _num(val)
        elif post.lstrip().startswith("section"):
            out["section_mm"] = _num(val)
        elif pre.rstrip().endswith("x"):
            out["length_mm"] = _num(val)
        elif post.lstrip().startswith("x") and _FASTENER.search(t):
            out.setdefault("thread", "M" + _num(val))   # "12 mm x 50" = M12
        else:
            out.setdefault("dim_mm", _num(val))
    return out


def _num(s):
    try:
        if "/" in s:
            a, b = s.split("/"); return f"{float(a)/float(b):g}"
        return f"{float(s):g}"
    except Exception:
        return s


def extract(norm_text: str) -> dict:
    a = {}
    for mat, code in MATERIALS:
        if mat in norm_text:
            a["material_grade"] = code
            break
    for key, pat in _P.items():
        m = pat.search(norm_text)
        if not m:
            continue
        v = next((g for g in m.groups() if g), None)
        if v is None:
            continue
        a[key] = v.upper() if key in ("seal_type", "schedule") else _num(v)
    if "thread" in a:
        a["thread"] = "M" + a["thread"]
    mmf = _mm_fields(norm_text)
    for k, v in mmf.items():
        a.setdefault(k, v)
    # "M12 x 50" with no unit still states a 50 mm length
    tx = _THREAD_X.search(norm_text)
    if tx:
        a.setdefault("thread", "M" + _num(tx.group(1)))
        a.setdefault("length_mm", _num(tx.group(2)))
    # a fastener that lost its "x" still carries its length in a bare "NN mm"
    if "length_mm" not in a and "thread" in a and "dim_mm" in a:
        a["length_mm"] = a.pop("dim_mm")
    # "hex bolt 12 mm" means an M12 bolt - fasteners are sized by thread, and this
    # is how a person types the query. Only fires when no thread was found.
    if "thread" not in a and "dim_mm" in a and _FASTENER.search(norm_text):
        a["thread"] = "M" + a.pop("dim_mm")
    if "length_mm" in a:
        a.pop("dim_mm", None)
    return a


def compare(a: dict, b: dict):
    """-> (verdicts, n_match, n_mismatch, n_known_both)"""
    v, nm, nx = {}, 0, 0
    for k in HARD_KEYS:
        x, y = a.get(k), b.get(k)
        if x is None or y is None:
            if x is not None or y is not None:
                v[k] = "UNKNOWN"
            continue
        if x == y:
            v[k] = "MATCH"; nm += 1
        else:
            v[k] = "MISMATCH"; nx += 1
    return v, nm, nx, nm + nx

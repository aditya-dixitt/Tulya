"""The national classification the codes are minted against.

A deduplicated group is not yet a *standard*. The problem statement asks for
standardisation and harmonisation of material codes, which needs three things
this file supplies:

  1. a **classification** every item lands in, so a code is readable and
     items are comparable across CPSEs by class rather than by description;
  2. the **defining specifications** for each class, so "what makes two items
     the same item" is written down per class instead of living only inside
     the scorer;
  3. a stable **class code** for the national code's middle segment.

Shape is deliberately UNSPSC-compatible - four levels, two digits each
(segment.family.class.commodity) - because every CPSE procurement stack and
GeM itself already speak that shape, and because a national scheme that
cannot be crosswalked to an international one is a dead end.

On the UNSPSC crosswalk: each class carries a `unspsc` slot and every one of
them is None. UNSPSC's code list is licensed and this build has no network
access to it; writing plausible-looking eight-digit codes from memory would
put unverifiable numbers into a government-facing artefact. The slot, the
loader and the tests are here so the crosswalk is a data import when the
team has the licensed file - not a redesign. Same discipline as the
TF-IDF-vs-MiniLM callout in RESULTS.md: the seam is built, the claim is not
made.
"""
from engine.block import category_of

UNCLASSIFIED = "99.99.99"

# segment -> (name, {family -> (name, {class -> (name, engine_category, unspsc)})})
# `engine_category` ties a class to what engine/block.py already reads out of
# the description, so classification uses no information the matcher doesn't
# have - no generator truth, no category_true column.
TAXONOMY = {
    "10": ("Piping and Fluid Handling", {
        "10": ("Pipes and Tubes", {
            "10": ("Seamless Pipe", "seamless_pipe", None),
        }),
        "20": ("Pipe Fittings", {
            "10": ("Elbow, 90 Degree", "elbow_90", None),
            "20": ("Flange, Weld Neck Raised Face", "wnrf_flange", None),
        }),
        "30": ("Valves", {
            "10": ("Ball Valve", "ball_valve", None),
            "20": ("Gate Valve", "gate_valve", None),
            "30": ("Globe Valve", "globe_valve", None),
            "40": ("Check Valve", "check_valve", None),
        }),
        "40": ("Static Sealing", {
            "10": ("Gasket, Spiral Wound", "spiral_gasket", None),
            "20": ("Gasket, Compressed Fibre", "caf_gasket", None),
            "30": ("O-Ring", "o_ring", None),
        }),
    }),
    "20": ("Fasteners", {
        "10": ("Bolts and Studs", {
            "10": ("Bolt, Hexagonal", "hex_bolt", None),
            "20": ("Bolt, Stud", "stud_bolt", None),
        }),
        "20": ("Nuts", {
            "10": ("Nut, Hexagonal", "hex_nut", None),
        }),
        "30": ("Washers", {
            "10": ("Washer, Plain", "plain_washer", None),
            "20": ("Washer, Spring", "spring_washer", None),
        }),
    }),
    "30": ("Rotating Equipment", {
        "10": ("Pumps", {
            "10": ("Pump, Centrifugal", "centrifugal_pump", None),
        }),
        "20": ("Bearings", {
            "10": ("Bearing, Ball", "ball_bearing", None),
            "20": ("Bearing, Roller", "roller_bearing", None),
        }),
    }),
    "40": ("Electrical", {
        "10": ("Rotating Electrical Machines", {
            "10": ("Motor, Induction", "induction_motor", None),
        }),
        "20": ("Cables and Conductors", {
            "10": ("Cable, XLPE Armoured", "xlpe_cable", None),
        }),
    }),
    "99": ("Unclassified", {
        "99": ("Pending Classification", {
            "99": ("Unclassified", "", None),
        }),
    }),
}

# Which specifications *define identity* inside a class. This is the written-down
# version of what the veto enforces: two items in this class are the same item
# only if these agree. Ordered most-defining first, which is also the order the
# console prints them in.
DEFINING_KEYS = {
    "10.10.10": ["bore_in", "schedule", "material_grade"],
    "10.20.10": ["bore_in", "schedule", "material_grade"],
    "10.20.20": ["bore_in", "pressure_class", "material_grade"],
    "10.30.10": ["bore_in", "pressure_class", "material_grade"],
    "10.30.20": ["bore_in", "pressure_class", "material_grade"],
    "10.30.30": ["bore_in", "pressure_class", "material_grade"],
    "10.30.40": ["bore_in", "pressure_class", "material_grade"],
    "10.40.10": ["bore_in", "pressure_class", "material_grade"],
    # A compressed-fibre gasket is specified by bore and *thickness*; it carries
    # no pressure class in any extract seen. Requiring one refused a code to
    # 100% of this class until the completeness audit caught it.
    "10.40.20": ["bore_in", "dim_mm", "material_grade"],
    "10.40.30": ["id_mm", "section_mm", "material_grade"],
    "20.10.10": ["thread", "length_mm", "material_grade"],
    "20.10.20": ["thread", "length_mm", "material_grade"],
    "20.20.10": ["thread", "material_grade"],
    "20.30.10": ["thread", "material_grade"],
    "20.30.20": ["thread", "material_grade"],
    "30.10.10": ["cap_m3hr", "head_m", "material_grade"],
    "30.20.10": ["bearing_desig", "seal_type"],
    # A roller bearing's designation is its identity. Seal type is a ball-bearing
    # variant and never appears on this class, so demanding it refused every one.
    "30.20.20": ["bearing_desig"],
    # A motor is identified by power and speed. Voltage belongs to cables, not
    # motors, and appeared on 0 of 523 motor records.
    "40.10.10": ["power_kw", "rpm"],
    "40.20.10": ["cores", "csa_sqmm", "voltage_kv"],
    UNCLASSIFIED: [],
}

# built once: engine category -> "ss.ff.cc"
_CLASS_OF_CATEGORY = {}
_CLASS_NAMES = {}
for _s, (_sn, _fams) in TAXONOMY.items():
    for _f, (_fn, _classes) in _fams.items():
        for _c, (_cn, _cat, _unspsc) in _classes.items():
            _code = f"{_s}.{_f}.{_c}"
            _CLASS_NAMES[_code] = (_sn, _fn, _cn, _unspsc)
            if _cat:
                _CLASS_OF_CATEGORY[_cat] = _code


def class_of_category(category: str) -> str:
    """Engine block category -> class code. Unknown or empty -> unclassified."""
    return _CLASS_OF_CATEGORY.get(category or "", UNCLASSIFIED)


def describe(class_code: str) -> dict:
    """Class code -> the full path, for display and for the code card."""
    seg, fam, cls = (class_code.split(".") + ["", "", ""])[:3]
    sn, fn, cn, unspsc = _CLASS_NAMES.get(
        class_code, ("Unclassified", "Pending Classification", "Unclassified", None))
    return dict(class_code=class_code, segment=seg, family=fam, klass=cls,
                segment_name=sn, family_name=fn, class_name=cn,
                unspsc=unspsc, defining_keys=DEFINING_KEYS.get(class_code, []))


def classify(norm_text: str, attrs: dict | None = None) -> dict:
    """Classify from NORMALISED text, the same input the matcher gets.

    `attrs` is accepted and unused today: the class is decided by category
    alone, and an attribute-based tie-break would need a class where two
    categories collide. Keeping the parameter means adding that later doesn't
    change every call site.
    """
    info = describe(class_of_category(category_of(norm_text)))
    info["classified"] = info["class_code"] != UNCLASSIFIED
    return info


def spec_signature(class_code: str, attrs: dict) -> str:
    """The canonical, order-stable spec string for an item in this class.

    Only the class's defining keys, always in the class's own order, so two
    records describing the same item produce the same signature even when
    their descriptions share almost no words. A key that could not be read is
    written `?` rather than dropped - a signature with holes in it must not
    collide with a complete one.
    """
    attrs = attrs or {}
    keys = DEFINING_KEYS.get(class_code, [])
    if not keys:
        return ""
    return "|".join(f"{k}={attrs[k]}" if k in attrs else f"{k}=?" for k in keys)


def signature_is_complete(class_code: str, attrs: dict) -> bool:
    """True when every defining key for the class was readable.

    The registry refuses to mint a national code on an incomplete signature -
    see engine/codegen.py. An item whose defining specs are half-unknown is
    exactly the item a catalogue must not freeze a permanent identifier onto.
    """
    keys = DEFINING_KEYS.get(class_code, [])
    return bool(keys) and all(k in (attrs or {}) for k in keys)


MIN_CORROBORATION = 2   # defining keys a member must itself confirm


def signature_match(class_code: str, attrs: dict, signature: str) -> dict:
    """How well does one record support a national code's signature?

    Group consistency proves no member *contradicts* the code. It does not
    prove a member *supports* it, and the difference is not academic. On the
    IOCL round trip, three cables whose voltage was cut off by the 40-character
    MAKTX limit sat in a group with two 6.6 kV cables. Nothing contradicted
    anything - an unreadable key is UNKNOWN - so the group was consistent, and
    a 33 kV cable was about to be stamped with a 6.6 kV national code.

    So linkage is graded rather than binary:

        conflict     the record disagrees on a defining key - never linked
        confirmed    every defining key is readable here and matches
        provisional  no disagreement, at least MIN_CORROBORATION defining keys
                     confirmed, but not all of them readable
        unsupported  too little in common to justify a permanent identifier

    `provisional` is not a weaker claim dressed up - it is written through to
    the ERP as its own status so a buyer sees it, and it generates the work
    queue for confirming those rows against the drawing or the spec sheet.
    """
    attrs = attrs or {}
    keys = DEFINING_KEYS.get(class_code, [])
    want = dict(p.split("=", 1) for p in signature.split("|")) if signature else {}
    matched, unknown, conflicting = [], [], []
    for k in keys:
        expected = want.get(k, "?")
        have = attrs.get(k)
        if have is None or expected == "?":
            unknown.append(k)
        elif str(have) == str(expected):
            matched.append(k)
        else:
            conflicting.append(k)
    if conflicting:
        status = "conflict"
    elif keys and not unknown:
        status = "confirmed"
    elif len(matched) >= MIN_CORROBORATION:
        status = "provisional"
    else:
        status = "unsupported"
    return dict(status=status, matched=matched, unknown=unknown,
                conflicting=conflicting, n_matched=len(matched))


def all_classes() -> list[dict]:
    return [describe(c) for c in sorted(_CLASS_NAMES) if c != UNCLASSIFIED]

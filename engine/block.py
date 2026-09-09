"""Blocking: replace all-pairs comparison with a bounded candidate set.

Two paths, because blocking is the one stage whose mistakes are unrecoverable -
a true pair separated here can never be scored, however good the scorer is.

  Path A  strict   category . uom . size-bucket
  Path B  relaxed  category only - used when A starves a record of candidates
  Path C  global   record whose category could not be read at all

Both blocking recall AND reduction ratio are reported by the harness; recall
alone is meaningless because it can always be bought by weakening the blocks.
"""
CATEGORY_KEYS = [
    ("weld neck raised face flange", "wnrf_flange"),
    ("compressed asbestos fibre gasket", "caf_gasket"),
    ("spiral wound gasket", "spiral_gasket"),
    ("xlpe armoured cable", "xlpe_cable"),
    ("elbow 90 degree", "elbow_90"), ("induction motor", "induction_motor"),
    ("centrifugal pump", "centrifugal_pump"), ("seamless pipe", "seamless_pipe"),
    ("hexagonal bolt", "hex_bolt"), ("hexagonal nut", "hex_nut"),
    ("spring washer", "spring_washer"), ("plain washer", "plain_washer"),
    ("stud bolt", "stud_bolt"), ("ball bearing", "ball_bearing"),
    ("roller bearing", "roller_bearing"), ("gate valve", "gate_valve"),
    ("globe valve", "globe_valve"), ("ball valve", "ball_valve"),
    ("check valve", "check_valve"), ("o-ring", "o_ring"),
    ("flange", "wnrf_flange"), ("gasket", "spiral_gasket"), ("elbow", "elbow_90"),
    ("cable", "xlpe_cable"), ("motor", "induction_motor"), ("pump", "centrifugal_pump"),
    ("pipe", "seamless_pipe"), ("bearing", "ball_bearing"), ("valve", "gate_valve"),
    ("bolt", "hex_bolt"), ("nut", "hex_nut"), ("washer", "plain_washer"),
]
SIZE_PRIORITY = ["thread", "bore_in", "bearing_desig", "csa_sqmm", "power_kw",
                 "cap_m3hr", "id_mm", "dim_mm", "length_mm"]
MIN_CANDIDATES = 2


def category_of(norm_text: str) -> str:
    for phrase, cat in CATEGORY_KEYS:
        if phrase in norm_text:
            return cat
    return ""


def size_bucket(attrs: dict) -> str:
    for k in SIZE_PRIORITY:
        if k in attrs:
            return f"{k}={attrs[k]}"
    return "NA"


MAX_KEYS = 3


def keys_for(cat, uom, attrs, max_keys=MAX_KEYS):
    """Several keys per record, all in ONE namespace.

    A record that lost its thread in a truncated description still shares a
    length key with its partner, so single-key blocking's unrecoverable misses
    become recoverable. Costs candidate pairs - which is why the harness always
    reports reduction ratio next to recall.
    """
    if not cat:
        return []
    ks = [f"{cat}|{uom}|{k}={attrs[k]}" for k in SIZE_PRIORITY if k in attrs][:max_keys]
    if len(ks) < max_keys and "material_grade" in attrs:
        ks.append(f"{cat}|{uom}|material_grade={attrs['material_grade']}")
    return ks or [f"{cat}|{uom}|NA"]


def build_multi(cats, uoms, attrs_list):
    blocks, glob, keyed = {}, [], 0
    for i, (c, u, a) in enumerate(zip(cats, uoms, attrs_list)):
        ks = keys_for(c, u, a)
        if not ks:
            glob.append(i); continue
        keyed += 1
        for k in ks:
            blocks.setdefault(k, []).append(i)
    blocks = {k: v for k, v in blocks.items() if len(v) >= MIN_CANDIDATES}
    if len(glob) >= MIN_CANDIDATES:
        blocks["__global__"] = glob
    stats = dict(used_blocks=len(blocks), keyed_records=keyed,
                 global_records=len(glob),
                 largest_block=max((len(v) for v in blocks.values()), default=0),
                 avg_keys_per_record=round(
                     sum(len(keys_for(c, u, a)) for c, u, a in
                         zip(cats, uoms, attrs_list)) / max(1, len(cats)), 2))
    return blocks, stats


def build(cats, uoms, buckets):
    """-> (assignments, stats). assignments[i] = list of block keys for record i."""
    strict, relaxed, glob = {}, {}, []
    for i, (c, u, b) in enumerate(zip(cats, uoms, buckets)):
        if not c:
            glob.append(i); continue
        strict.setdefault(f"A|{c}|{u}|{b}", []).append(i)
    for key, members in list(strict.items()):
        if len(members) < MIN_CANDIDATES:            # starved -> relax
            c = key.split("|")[1]
            relaxed.setdefault(f"B|{c}", []).extend(members)
    blocks = {k: v for k, v in strict.items() if len(v) >= MIN_CANDIDATES}
    blocks.update({k: v for k, v in relaxed.items() if len(v) >= MIN_CANDIDATES})
    if len(glob) >= MIN_CANDIDATES:
        blocks["C|global"] = glob
    stats = dict(strict_blocks=len(strict), used_blocks=len(blocks),
                 relaxed_records=sum(len(v) for v in relaxed.values()),
                 global_records=len(glob),
                 largest_block=max((len(v) for v in blocks.values()), default=0))
    return blocks, stats

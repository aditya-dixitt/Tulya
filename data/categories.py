"""
Twenty material categories with realistic Indian CPSE / oil-and-gas nomenclature.

Each category knows how to build a *canonical* description as an ordered list of
semantic chunks (head noun, then spec groups). Corruption operates on chunks, which
is how real description drift works - people reorder spec groups, not letters.

`hard_slots` names the attributes that, if changed, make it a genuinely DIFFERENT
item. Those drive hard-negative generation: we change exactly one, to an ADJACENT
value, so the text stays maximally similar while the item becomes wrong to merge.
"""
import random

THREADS   = ["M5", "M6", "M8", "M10", "M12", "M14", "M16", "M18", "M20", "M22",
             "M24", "M27", "M30", "M33", "M36"]
LENGTHS   = [16, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 90, 100,
             110, 120, 130, 150, 180, 200]
FAST_MAT  = ["stainless steel 304", "stainless steel 316", "mild steel",
             "high tensile 8.8", "galvanised iron", "carbon steel"]
BORES     = ["1/4", "1/2", "3/4", "1", "1.25", "1.5", "2", "2.5", "3", "4", "5",
             "6", "8", "10", "12", "14", "16", "18", "20", "24"]
CLASSES   = ["150", "300", "600", "900", "1500"]
VBODY     = ["carbon steel", "stainless steel 316", "stainless steel 304",
             "cast iron", "WCB"]
ENDS      = ["flanged", "screwed"]
BALLBRG   = ["6000", "6001", "6002", "6003", "6004", "6005", "6006", "6007",
             "6008", "6200", "6201", "6202", "6203", "6204", "6205", "6206",
             "6207", "6208", "6209", "6210", "6300", "6301", "6302", "6303",
             "6304", "6305", "6306", "6307", "6308", "6309", "6310"]
ROLLBRG   = ["NU203", "NU204", "NU205", "NU206", "NU207", "NU208", "NU209",
             "NU210", "22205", "22206", "22207", "22208", "22209", "22210"]
SEALS     = ["2RS", "ZZ", "OPEN"]
SCHED     = ["SCH10", "SCH20", "SCH40", "SCH80", "SCH120", "SCH160", "XS"]
PIPE_MAT  = ["A106 GR B", "stainless steel 304", "stainless steel 316",
             "carbon steel", "mild steel", "cast iron"]
GSK_MAT   = ["stainless steel 316 graphite", "stainless steel 304 graphite",
             "compressed asbestos fibre", "graphite"]
THICK     = ["1", "1.5", "2", "2.5", "3", "4", "5"]
CORES     = ["1", "2", "3", "3.5", "4"]
CSA       = ["1.5", "2.5", "4", "6", "10", "16", "25", "35", "50", "70", "95",
             "120", "150", "185", "240", "300"]
KV        = ["1.1", "3.3", "6.6", "11", "33"]
KW        = ["0.75", "1.5", "2.2", "3.7", "5.5", "7.5", "11", "15", "22", "30",
             "37", "45", "55", "75"]
RPM       = ["600", "750", "960", "1000", "1440", "1500", "2900", "3000"]
FRAME     = ["80", "90L", "100L", "112M", "132S", "160M", "180L", "200L"]
MOUNT     = ["foot mounted", "flange mounted"]
PCAP      = ["5", "10", "16", "25", "40", "50", "63", "80", "100", "125",
             "150", "200", "250", "315"]
PHEAD     = ["10", "16", "20", "25", "30", "40", "50", "60", "70", "80", "100"]
ORING_ID  = ["8", "10", "12", "15", "18", "20", "22", "25", "28", "30", "35",
             "40", "45", "50", "60", "70", "80", "90", "100", "110"]
ORING_CS  = ["1.78", "2.62", "3.53", "5.33"]
ELAST     = ["nitrile", "viton", "EPDM", "silicone", "neoprene"]


def _pick(rng, pool):
    return rng.choice(pool)


# Each builder returns (chunks, attrs). attrs is the generator's private truth,
# never read by the engine - the engine must recover attributes from text alone.
def _fastener(rng, head, standard, with_len=True):
    th, mat = _pick(rng, THREADS), _pick(rng, FAST_MAT)
    ln = _pick(rng, LENGTHS)
    chunks = [head, th] + ([f"x {ln} mm"] if with_len else []) + [mat, standard]
    a = {"thread": th, "material": mat}
    if with_len:
        a["length"] = str(ln)
    return chunks, a


def _valve(rng, head):
    b, c, m, e = _pick(rng, BORES), _pick(rng, CLASSES), _pick(rng, VBODY), _pick(rng, ENDS)
    return ([head, f'{b} inch', f"class {c}", m, e],
            {"bore": b, "pclass": c, "material": m})


CATEGORIES = {
  "hex_bolt":    dict(uom="nos", hard=["thread", "length", "material"],
                      build=lambda r: _fastener(r, "hexagonal bolt", "IS 1364")),
  "hex_nut":     dict(uom="nos", hard=["thread", "material"],
                      build=lambda r: _fastener(r, "hexagonal nut", "IS 1363", with_len=False)),
  "stud_bolt":   dict(uom="nos", hard=["thread", "length", "material"],
                      build=lambda r: _fastener(r, "stud bolt", "ASTM A193 B7")),
  "plain_washer": dict(uom="nos", hard=["thread", "material"],
                      build=lambda r: _fastener(r, "plain washer", "IS 2016", with_len=False)),
  "spring_washer": dict(uom="nos", hard=["thread", "material"],
                      build=lambda r: _fastener(r, "spring washer", "IS 3063", with_len=False)),
  "gate_valve":  dict(uom="nos", hard=["bore", "pclass", "material"],
                      build=lambda r: _valve(r, "gate valve")),
  "globe_valve": dict(uom="nos", hard=["bore", "pclass", "material"],
                      build=lambda r: _valve(r, "globe valve")),
  "ball_valve":  dict(uom="nos", hard=["bore", "pclass", "material"],
                      build=lambda r: _valve(r, "ball valve")),
  "check_valve": dict(uom="nos", hard=["bore", "pclass", "material"],
                      build=lambda r: _valve(r, "check valve")),
  "ball_bearing": dict(uom="nos", hard=["desig", "seal"],
                      build=lambda r: (lambda d, s: (["ball bearing", d, s],
                                                     {"desig": d, "seal": s}))(
                          _pick(r, BALLBRG), _pick(r, SEALS))),
  "roller_bearing": dict(uom="nos", hard=["desig"],
                      build=lambda r: (lambda d: (["roller bearing", d],
                                                  {"desig": d}))(_pick(r, ROLLBRG))),
  "spiral_gasket": dict(uom="nos", hard=["bore", "pclass", "material"],
                      build=lambda r: (lambda b, c, m: (
                          ["spiral wound gasket", f'{b} inch', f"class {c}", m],
                          {"bore": b, "pclass": c, "material": m}))(
                          _pick(r, BORES), _pick(r, CLASSES), _pick(r, GSK_MAT))),
  "caf_gasket":  dict(uom="nos", hard=["bore", "thickness"],
                      build=lambda r: (lambda b, t: (
                          ["compressed asbestos fibre gasket", f'{b} inch', f"{t} mm"],
                          {"bore": b, "thickness": t}))(_pick(r, BORES), _pick(r, THICK))),
  "seamless_pipe": dict(uom="m", hard=["bore", "sched", "material"],
                      build=lambda r: (lambda b, s, m: (
                          ["seamless pipe", f'{b} inch', s, m],
                          {"bore": b, "sched": s, "material": m}))(
                          _pick(r, BORES), _pick(r, SCHED), _pick(r, PIPE_MAT))),
  "elbow_90":    dict(uom="nos", hard=["bore", "sched", "material"],
                      build=lambda r: (lambda b, s, m: (
                          ["elbow 90 degree", f'{b} inch', s, m],
                          {"bore": b, "sched": s, "material": m}))(
                          _pick(r, BORES), _pick(r, SCHED), _pick(r, PIPE_MAT))),
  "wnrf_flange": dict(uom="nos", hard=["bore", "pclass", "material"],
                      build=lambda r: (lambda b, c, m: (
                          ["weld neck raised face flange", f'{b} inch', f"class {c}", m],
                          {"bore": b, "pclass": c, "material": m}))(
                          _pick(r, BORES), _pick(r, CLASSES), _pick(r, PIPE_MAT))),
  "xlpe_cable":  dict(uom="m", hard=["cores", "csa", "kv"],
                      build=lambda r: (lambda c, s, v: (
                          ["XLPE armoured cable", f"{c} core", f"{s} sqmm", f"{v} kv"],
                          {"cores": c, "csa": s, "kv": v}))(
                          _pick(r, CORES), _pick(r, CSA), _pick(r, KV))),
  "induction_motor": dict(uom="nos", hard=["kw", "rpm"],
                      build=lambda r: (lambda k, p, f, m: (
                          ["induction motor", f"{k} kw", f"{p} rpm", f"frame {f}", m],
                          {"kw": k, "rpm": p, "frame": f}))(
                          _pick(r, KW), _pick(r, RPM), _pick(r, FRAME), _pick(r, MOUNT))),
  "centrifugal_pump": dict(uom="nos", hard=["cap", "head", "material"],
                      build=lambda r: (lambda c, h, m: (
                          ["centrifugal pump", f"{c} m3/hr", f"head {h} m", m],
                          {"cap": c, "head": h, "material": m}))(
                          _pick(r, PCAP), _pick(r, PHEAD), _pick(r, VBODY))),
  "o_ring":      dict(uom="nos", hard=["idm", "cs", "material"],
                      build=lambda r: (lambda i, c, m: (
                          ["o-ring", f"{i} mm id", f"{c} mm section", m],
                          {"idm": i, "cs": c, "material": m}))(
                          _pick(r, ORING_ID), _pick(r, ORING_CS), _pick(r, ELAST))),
}

# Which pool each hard slot draws from - used to pick an ADJACENT value for siblings.
SLOT_POOL = {
    "thread": THREADS, "length": [str(x) for x in LENGTHS], "material": None,
    "bore": BORES, "pclass": CLASSES, "desig": None, "seal": SEALS,
    "sched": SCHED, "thickness": THICK, "cores": CORES, "csa": CSA, "kv": KV,
    "kw": KW, "rpm": RPM, "cap": PCAP, "head": PHEAD, "idm": ORING_ID, "cs": ORING_CS,
}
MAT_POOLS = [FAST_MAT, VBODY, PIPE_MAT, GSK_MAT, ELAST]
DESIG_POOLS = [BALLBRG, ROLLBRG]


def adjacent_value(slot, current, rng):
    """Nearest alternative in the same pool - keeps the sibling textually close."""
    pool = SLOT_POOL.get(slot)
    if pool is None:
        for p in (MAT_POOLS + DESIG_POOLS):
            if current in p:
                pool = p
                break
    if not pool or current not in pool:
        return None
    i = pool.index(current)
    nbrs = [j for j in (i - 1, i + 1) if 0 <= j < len(pool)]
    if not nbrs:
        return None
    return pool[rng.choice(nbrs)]


# Chunk positions that may be dropped WITHOUT destroying the item's identity.
# Real masters lose the standard code or the end type; they rarely lose the size.
# Dropping an identity-bearing chunk would manufacture pairs that no system could
# resolve, and then score the engine down for failing to resolve them.
DROPPABLE = {
    "hex_bolt": [4], "stud_bolt": [4],                 # [head, thread, len, mat, std]
    "hex_nut": [3], "plain_washer": [3], "spring_washer": [3],
    "gate_valve": [4], "globe_valve": [4],             # [head, bore, class, mat, ends]
    "ball_valve": [4], "check_valve": [4],
    "induction_motor": [3, 4],                         # frame, mounting
    "ball_bearing": [], "roller_bearing": [], "spiral_gasket": [], "caf_gasket": [],
    "seamless_pipe": [], "elbow_90": [], "wnrf_flange": [], "xlpe_cable": [],
    "centrifugal_pump": [], "o_ring": [],
}

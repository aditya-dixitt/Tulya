"""
Build a controlled CPSE material-master benchmark WITH ground truth.

Why synthetic: real master data carries no labels - nobody has marked which IOCL
row is the same bolt as which ONGC row, and that unlabelled state IS the problem
statement. Without known answers precision cannot be computed at all.

Guarantees this file is responsible for:
  * splits are made at FAMILY level (a true item + its hard-negative sibling)
    BEFORE any variant is generated, so no cluster spans two splits;
  * the test split additionally draws from corruption recipes that dev/val never
    see, so we measure generalisation to unseen mess rather than recall of our
    own recipe.
"""
import json, random, sys, pathlib, itertools
sys.path.insert(0, str(pathlib.Path(__file__).parent))
import pandas as pd, yaml
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
import tableio
from categories import CATEGORIES, adjacent_value, DROPPABLE

ROOT = pathlib.Path(__file__).parent
OUT = ROOT / "out"; OUT.mkdir(exist_ok=True)
ABBREV = yaml.safe_load(open(ROOT / "dictionaries/abbreviations.yaml"))

N_PRIMARY, N_SIBLING, SEED = 10_000, 2_000, 20260908

CPSES = [("IOCL", lambda r: f"{r.randint(10000000,10999999)}"),
         ("ONGC", lambda r: f"MAT-{r.randint(10000,99999)}"),
         ("BPCL", lambda r: f"B{r.randint(1000,9999)}"),
         ("HPCL", lambda r: f"H-{r.randint(1000,9999)}"),
         ("GAIL", lambda r: f"GL/{r.randint(10000,99999)}"),
         ("CPCL", lambda r: f"CP{r.randint(1000000,9999999)}")]

# Plants / sites within each CPSE. The duplication problem does not start at the
# boundary between two companies - it starts inside one, because every refinery,
# terminal and pipeline division has created codes independently for decades,
# often through separate ERP rollouts. Modelling the site makes that visible:
# a duplicate pair can now be intra-CPSE (two plants of one company) or
# inter-CPSE, and the console reports the split.
#
# Site names are plausible real facilities; the RECORDS remain entirely
# synthetic. Assignment is deterministic on record_id and deliberately draws no
# random numbers, so adding this field leaves the generated dataset, the scored
# pairs and every measured result bit-for-bit unchanged.
PLANTS = {
    "IOCL": ["Panipat Refinery", "Mathura Refinery", "Gujarat Refinery",
             "Haldia Refinery", "Paradip Refinery", "Northern Region Pipelines",
             "Mumbai Terminal"],
    "ONGC": ["Hazira Plant", "Uran Plant", "Ankleshwar Asset",
             "Rajahmundry Asset", "Mumbai High Offshore", "Assam Asset"],
    "BPCL": ["Mumbai Refinery", "Kochi Refinery", "Bina Refinery",
             "Irugur Terminal", "Kanpur Depot"],
    "HPCL": ["Mumbai Refinery", "Visakh Refinery", "Vijayawada Terminal",
             "Mangalore Depot", "Rewari Pipeline Station"],
    "GAIL": ["Vijaipur Complex", "Pata Petrochemical", "Hazira Compressor",
             "Vaghodia Station", "Dibiyapur Station"],
    "CPCL": ["Manali Refinery", "Cauvery Basin Refinery", "Ennore Terminal",
             "Madurai Depot"],
}


def plant_of(cpse, record_id):
    sites = PLANTS[cpse]
    return sites[record_id % len(sites)]
NOISE = ["for pump house", "spare", "assembly", "as per drawing", "store item",
         "unit-2", "shutdown spare", "std item"]
VENDOR = ["-SKF{n}", "(MAKE: L&T)", "- CAT#{n}", "/ REF {n}", "MAKE KSB"]

# ---------------------------------------------------------------- corruption ops
def op_abbrev(t, rng, p=0.75):
    for canon in sorted(ABBREV, key=len, reverse=True):
        if canon in t and rng.random() < p:
            t = t.replace(canon, rng.choice(ABBREV[canon]), 1)
    return t

def op_units(t, rng):
    import re
    def mm(m):
        v = float(m.group(1))
        c = rng.random()
        if c < .30: return f"{m.group(1)}MM"
        if c < .50: return f"{m.group(1)} M.M."
        if c < .65 and v >= 10 and v % 10 == 0: return f"{v/10:g} cm"
        return f"{m.group(1)}mm"
    t = re.sub(r"(\d+(?:\.\d+)?)\s*mm\b", mm, t)
    def inch(m):
        c = rng.random()
        if c < .35: return f'{m.group(1)}"'
        if c < .60: return f"{m.group(1)} NB"
        if c < .80: return f"{m.group(1)} in"
        return f"{m.group(1)} inch"
    return re.sub(r"(\d+(?:[./]\d+)?)\s*inch\b", inch, t)

def op_separator(t, rng):
    import re
    return re.sub(r"\s*x\s*", rng.choice(["X", "x", "*", "-", " X ", ""]), t, count=1)

def op_typo(t, rng):
    ws = [i for i, w in enumerate(t.split()) if len(w) > 4]
    if not ws: return t
    toks = t.split(); i = rng.choice(ws); w = toks[i]
    j = rng.randrange(len(w) - 1)
    c = rng.random()
    if c < .4:   w = w[:j] + w[j + 1] + w[j] + w[j + 2:]      # transpose
    elif c < .7: w = w[:j] + w[j + 1:]                         # drop
    else:        w = w[:j] + w[j] + w[j:]                      # duplicate
    toks[i] = w
    return " ".join(toks)

def op_vendor(t, rng):
    return t + " " + rng.choice(VENDOR).replace("{n}", str(rng.randint(1000, 99999)))

def op_noise(t, rng):
    return t + " " + rng.choice(NOISE)

def op_truncate(t, rng, n=46):
    return t[:n].rstrip()

def op_case(t, rng):
    c = rng.random()
    return t.upper() if c < .60 else (t.title() if c < .80 else t)

STR_OPS = {"abbrev": op_abbrev, "units": op_units, "separator": op_separator,
           "typo": op_typo, "vendor": op_vendor, "noise": op_noise,
           "truncate": op_truncate, "case": op_case}

# Recipes dev/val/test may all use.
COMMON = [["case"], ["abbrev", "case"], ["units", "case"], ["reorder", "case"],
          ["abbrev", "separator"], ["noise", "case"], ["units", "separator"],
          ["abbrev", "units"], ["typo", "case"], ["vendor", "case"],
          ["abbrev", "reorder"], ["drop", "case"]]
# Deeper stacks reserved for the locked test split ONLY.
HOLDOUT = [["abbrev", "reorder", "units", "case"],
           ["abbrev", "units", "separator", "typo"],
           ["reorder", "drop", "abbrev", "case"],
           ["abbrev", "noise", "truncate"],
           ["units", "reorder", "vendor", "typo"],
           ["abbrev", "separator", "drop", "case"]]

def render(chunks, recipe, rng, category=None):
    ch = list(chunks)
    if "drop" in recipe:                       # drop BEFORE reorder: the indices
        ok = [i for i in DROPPABLE.get(category, []) if i < len(ch)]
        if ok:                                 # refer to the canonical layout
            ch.pop(rng.choice(ok))
    if "reorder" in recipe and len(ch) > 2:
        head, rest = ch[0], ch[1:]
        rng.shuffle(rest)
        ch = ([head] + rest) if rng.random() < .7 else (rest[:1] + [head] + rest[1:])
    t = " ".join(ch)
    for name in recipe:
        if name in STR_OPS:
            t = STR_OPS[name](t, rng)
    return " ".join(t.split())

# ---------------------------------------------------------------- build items
def main():
    rng = random.Random(SEED)
    cats = list(CATEGORIES)
    items, families = [], []

    seen = set()                     # every true item must be UNIQUE.
    tries = 0                        # two clusters with identical specs would be
    while len(items) < N_PRIMARY:    # mislabelled ground truth, not a hard case.
        tries += 1
        if tries > N_PRIMARY * 60:
            break
        c = rng.choice(cats)
        chunks, attrs = CATEGORIES[c]["build"](rng)
        sig = (c, tuple(sorted(attrs.items())))
        if sig in seen:
            continue
        seen.add(sig)
        items.append(dict(cluster_id=len(items), family_id=len(families),
                          category=c, chunks=chunks, attrs=attrs,
                          uom=CATEGORIES[c]["uom"], sibling_of=None))
        families.append([len(items) - 1])

    # hard negatives: same category, ONE hard slot changed to an adjacent value
    made = 0
    order = list(range(N_PRIMARY)); rng.shuffle(order)
    for idx in order:
        if made >= N_SIBLING: break
        base = items[idx]
        slots = [s for s in CATEGORIES[base["category"]]["hard"] if s in base["attrs"]]
        rng.shuffle(slots)
        for slot in slots:
            new = adjacent_value(slot, base["attrs"][slot], rng)
            if not new: continue
            old = base["attrs"][slot]
            sig2 = (base["category"], tuple(sorted({**base["attrs"], slot: new}.items())))
            if sig2 in seen: continue
            chunks = [ch.replace(old, new) if old in ch else ch for ch in base["chunks"]]
            if chunks == base["chunks"]: continue
            a2 = dict(base["attrs"]); a2[slot] = new
            items.append(dict(cluster_id=len(items), family_id=base["family_id"],
                              category=base["category"], chunks=chunks, attrs=a2,
                              uom=base["uom"], sibling_of=base["cluster_id"]))
            families[base["family_id"]].append(len(items) - 1)
            seen.add(sig2)
            made += 1
            break

    # ------------------------------------------------------------ split FAMILIES
    fam_ids = list(range(len(families))); rng.shuffle(fam_ids)
    n = len(fam_ids); n_dev, n_val = int(.70 * n), int(.15 * n)
    split_of = {}
    for k, f in enumerate(fam_ids):
        split_of[f] = "dev" if k < n_dev else ("val" if k < n_dev + n_val else "test")

    # ------------------------------------------------------------ emit variants
    rows = []
    for it in items:
        sp = split_of[it["family_id"]]
        n_var = rng.choice([2, 3, 3, 4, 4, 5, 6])
        for v in range(n_var):
            if v == 0:
                recipe = ["case"]                       # one lightly-typed record
            elif sp == "test" and rng.random() < .5:
                recipe = rng.choice(HOLDOUT)            # unseen mess, test only
            else:
                recipe = rng.choice(COMMON)
            cp, codegen = rng.choice(CPSES)
            rows.append(dict(
                record_id=len(rows), cpse=cp,
                plant=plant_of(cp, len(rows)), legacy_code=codegen(rng),
                description=render(it["chunks"], recipe, rng, it["category"]),
                uom=it["uom"], category_true=it["category"],
                qty=rng.choice([12, 50, 120, 400, 1250, 4800, 10150]),
                unit_value=round(rng.uniform(35, 42000), 2),
                cluster_id=it["cluster_id"], family_id=it["family_id"],
                split=sp, recipe="+".join(recipe)))

    df = pd.DataFrame(rows)
    tableio.write(df, OUT / "records")
    # new benchmark => any previous locked holdout result no longer applies
    (OUT / "holdout_run.json").unlink(missing_ok=True)
    (OUT / "encoder.pkl").unlink(missing_ok=True)

    # ------------------------------------------------------------ ground truth
    pos = []
    for cid, g in df.groupby("cluster_id"):
        ids = g.record_id.tolist()
        pos += [(a, b, g.split.iloc[0]) for a, b in itertools.combinations(ids, 2)]
    tableio.write(pd.DataFrame(pos, columns=["a","b","split"]), OUT / "pairs_pos")

    by_cluster = df.groupby("cluster_id").record_id.apply(list).to_dict()
    hard = []
    for it in items:
        if it["sibling_of"] is None: continue
        A, B = by_cluster.get(it["sibling_of"], []), by_cluster.get(it["cluster_id"], [])
        if not A or not B: continue
        for _ in range(min(3, len(A) * len(B))):
            hard.append((rng.choice(A), rng.choice(B), split_of[it["family_id"]]))
    hard = list({(min(a, b), max(a, b), s) for a, b, s in hard})
    tableio.write(pd.DataFrame(hard, columns=["a","b","split"]), OUT / "pairs_hardneg")

    json.dump({"seed": SEED, "families": len(families), "clusters": len(items),
               "records": len(df), "split_counts": df.split.value_counts().to_dict(),
               "holdout_recipes": ["+".join(r) for r in HOLDOUT],
               "common_recipes": ["+".join(r) for r in COMMON]},
              open(OUT / "splits.json", "w"), indent=2)

    print(f"records        {len(df):,}")
    print(f"clusters       {len(items):,}  (families {len(families):,})")
    print(f"positive pairs {len(pos):,}")
    print(f"hard negatives {len(hard):,}")
    print(df.split.value_counts().to_string())
    print("\nsample cluster:")
    c = df[df.cluster_id == df.cluster_id.iloc[0]]
    for _, r in c.iterrows():
        print(f"  {r.cpse:5} {r.legacy_code:12} {r.description}")

if __name__ == "__main__":
    main()

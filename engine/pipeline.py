"""End-to-end: records -> normalise -> extract -> block -> embed -> retrieve ->
score -> decide. Writes the scored candidate pairs and the run statistics that
Layer A of the evaluation needs.

The encoder is fitted on DEV text only and merely applied to val/test, so no
information from the held-out splits reaches the model that scores them.
"""
import argparse, json, pickle, sys, time, pathlib
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
import tableio
from engine.normalize import normalize
from engine.attributes import extract
from engine.block import category_of, size_bucket, build_multi
from engine.embed import Encoder
from engine.index import ExactIP, BACKEND as IX_BACKEND
from engine.fuzzy import token_set_ratio, BACKEND as FZ_BACKEND
from engine.score import fuse

OUT = ROOT / "data/out"
TOPK = 20


def prepare(desc):
    norm = [normalize(t) for t in desc]
    attrs = [extract(t) for t in norm]
    return norm, attrs, [category_of(t) for t in norm], [size_bucket(a) for a in attrs]


def get_encoder(backend, df_all):
    cache = OUT / "encoder.pkl"
    if cache.exists():
        enc, fitted_backend = pickle.load(open(cache, "rb"))
        if fitted_backend == Encoder(backend).backend:
            return enc
    enc = Encoder(backend)
    dev = df_all[df_all.split == "dev"].description.tolist()
    dev_norm = [normalize(t) for t in dev]
    t0 = time.time()
    enc.fit_transform(dev_norm)
    print(f"  encoder '{enc.backend}' fitted on {len(dev_norm):,} dev texts "
          f"({time.time()-t0:.1f}s)")
    pickle.dump((enc, enc.backend), open(cache, "wb"))
    return enc


def run(split, backend="auto", topk=TOPK, verbose=True):
    t_start = time.time()
    df_all = tableio.read("data/out/records")
    enc = get_encoder(backend, df_all)

    df = df_all[df_all.split == split].reset_index(drop=True)
    ids = df.record_id.to_numpy()
    if verbose: print(f"  split '{split}': {len(df):,} records")

    t0 = time.time()
    norm, attrs, cats, buckets = prepare(df.description.tolist())
    t_prep = time.time() - t0

    t0 = time.time()
    vecs = enc.transform(norm)
    t_embed = time.time() - t0

    blocks, bstats = build_multi(cats, df.uom.tolist(), attrs)
    if verbose:
        print(f"  blocks: {bstats['used_blocks']:,} used, largest {bstats['largest_block']:,}, "
              f"{bstats['avg_keys_per_record']} keys/record, "
              f"{bstats['global_records']:,} unkeyed")

    # ---- candidate retrieval: exact top-k inner product WITHIN each block
    t0 = time.time()
    cand = {}
    for key, members in blocks.items():
        m = np.array(members)
        sub = vecs[m]
        sims, idx = ExactIP(sub).search(sub, min(topk + 1, len(m)))
        for r in range(len(m)):
            gi = m[r]
            for c in range(idx.shape[1]):
                gj = m[idx[r, c]]
                if gi == gj:
                    continue
                a, b = (gi, gj) if gi < gj else (gj, gi)
                s = float(sims[r, c])
                if cand.get((a, b), -2) < s:
                    cand[(a, b)] = s
    t_retr = time.time() - t0
    n = len(df)
    all_pairs = n * (n - 1) // 2
    if verbose:
        print(f"  candidates: {len(cand):,} pairs from {all_pairs:,} possible "
              f"(reduction {1-len(cand)/all_pairs:.6f})")

    # ---- score every candidate
    t0 = time.time()
    rows = []
    for (i, j), cos in cand.items():
        fz = token_set_ratio(norm[i], norm[j]) / 100.0
        r = fuse(max(0.0, min(1.0, cos)), fz, attrs[i], attrs[j])
        rows.append((int(ids[i]), int(ids[j]), cos, fz,
                     -1.0 if r["attr"] is None else r["attr"], r["coverage"],
                     r["score"], r["score_noveto"], r["decision"], r["vetoed"]))
    t_score = time.time() - t0

    pairs = pd.DataFrame(rows, columns=["a", "b", "cos", "fuz", "attr", "coverage",
                                        "score", "score_noveto", "decision", "vetoed"])
    tableio.write(pairs, OUT / f"pairs_{split}")
    np.save(OUT / f"vecs_{split}.npy", vecs)
    pd.DataFrame({"record_id": ids, "norm": norm,
                  "attrs": [json.dumps(a) for a in attrs],
                  "category": cats, "bucket": buckets}).pipe(
        lambda d: tableio.write(d, OUT / f"prepared_{split}"))

    stats = dict(split=split, records=n, all_pairs=all_pairs,
                 candidate_pairs=len(cand),
                 reduction_ratio=1 - len(cand) / all_pairs,
                 encoder=enc.backend, index=IX_BACKEND, fuzzy=FZ_BACKEND, topk=topk,
                 blocks=bstats,
                 timings=dict(prepare=t_prep, embed=t_embed, retrieve=t_retr,
                              score=t_score, total=time.time() - t_start),
                 decisions=pairs.decision.value_counts().to_dict())
    json.dump(stats, open(OUT / f"run_{split}.json", "w"), indent=2)
    if verbose:
        print(f"  decisions: {stats['decisions']}")
        print(f"  timings: prep {t_prep:.0f}s embed {t_embed:.0f}s "
              f"retrieve {t_retr:.0f}s score {t_score:.0f}s "
              f"total {stats['timings']['total']:.0f}s")
    return pairs, stats


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev")
    ap.add_argument("--encoder", default="auto", choices=["auto", "sbert", "tfidf-svd"])
    ap.add_argument("--topk", type=int, default=TOPK)
    a = ap.parse_args()
    run(a.split, a.encoder, a.topk)

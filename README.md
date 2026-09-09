# SAMANVAY — prototype

AI-driven standardisation and harmonisation of material codes across CPSEs.
**SIH26099 · Team AlgoRythms.**

The same physical bolt sits in three CPSE material masters under three codes and
three spellings. This finds the entries that mean the same item and proposes one
national code — with a human approving every merge and the legacy codes kept.

```bash
make demo        # generate data -> run pipeline -> select threshold -> write RESULTS.md
make panels      # the three reason panels (the demo moment)
make search Q="hex bolt 12mm stainless"
```

| on the locked test split, at t = 0.92 | |
|---|---|
| auto-suggest precision | **95.4%** (6,541 proposed, 299 wrong) |
| coverage of true duplicates | **82.6%** |
| candidate pairs after blocking | 147,130 of 24.5M possible (99.4% reduction) |

**→ [`RESULTS.md`](RESULTS.md) has the full measured evaluation** — dataset, three
evaluation layers, baselines, the holdout ledger, all of it produced by `make demo`.
No number in this repo was typed by hand. **These numbers are from the dependency-free
TF-IDF encoder, not Sentence-BERT** — see `RESULTS.md`'s backend callout before quoting
them as the production architecture's numbers.

## Why text matching alone cannot do this

```
Hexagonal Bolt 12mm x 50mm St.Steel   ==  BOLT HEX M12X50 SS304    same item, almost no shared words
BOLT HEX M12X50 SS304                 !=  BOLT HEX M16X50 SS304    different item, nearly every word shared
```

Text similarity fails in both directions at once. So two mechanisms run: one that
compares **meaning**, and one that reads the **specifications** and can overrule it.

## Pipeline

| stage | what happens |
|---|---|
| `engine/normalize.py` | expand abbreviations, canonicalise units, resolve fractions (`3/4"` ≠ `4"`) |
| `engine/attributes.py` | recover specs from text; every comparison is **MATCH / MISMATCH / UNKNOWN** |
| `engine/block.py` | multi-key blocking so a record that lost one spec still meets its partner |
| `engine/embed.py` | 384-dim sentence embeddings |
| `engine/index.py` | exact inner-product top-20 within block |
| `engine/score.py` | `0.60·cosine + 0.25·token-set + 0.15·attribute`, **hard-key veto**, coverage floor |
| `engine/explain.py` | the structured reason a steward signs off on — never a bare score |

**The veto is the heart of it.** If any specification is known on both sides and
disagrees, the score is forced to zero however similar the text is. And when too
few specs are readable, a high score is *capped at human review* rather than
trusted — `UNKNOWN` is never treated as agreement, and never as conflict.

## Swappable backends

This repo runs with zero third-party ML dependencies so it works anywhere. Each
backend has a production counterpart that is a one-flag change:

| component | default here | production | note |
|---|---|---|---|
| encoder | TF-IDF char n-gram + SVD | `all-MiniLM-L6-v2` | `--encoder sbert`. **Different numbers — re-measure.** |
| index | numpy exact inner product | `faiss.IndexFlatIP` | mathematically identical, faiss is faster |
| fuzzy | `difflib` token-set ratio | `rapidfuzz` | `SAMANVAY_FUZZY=rapidfuzz` |

[`RESULTS.md`](RESULTS.md) always states which backends produced its numbers.

## Evaluation — three layers, not one

Pair-level precision alone grades the scorer on whatever candidates it happened to
receive, and *improves* as blocking loses more true pairs. So:

- **Layer A** did the right record even reach the scorer — blocking completeness,
  Recall@20, always reported beside **reduction ratio** (recall alone is gameable
  by weakening blocks until everything is a candidate)
- **Layer B** precision / recall / F1 versus four baselines on the *same* candidates
- **Layer C** what a CPSE actually experiences — auto-suggest precision, review load

### Benchmark discipline

- splits are made at **family level** (an item plus its hard-negative sibling)
  **before** any variant is generated — splitting by record would put variants of
  the same item on both sides
- the test split additionally uses **corruption recipes dev and val never see**
- the test split is evaluated **once**, recorded with a timestamp in
  `data/out/holdout_run.json`; re-running needs `--force`
- ~2,000 **hard negatives** are planted: one spec apart, near-identical text

## Steward console

The engine only ever *proposes* — nothing merges without a human clicking
approve. `api/` is the review surface that makes that real:

```
make api            steward console at http://localhost:8000 (Flask + SQLite)
make static-demo     reports/steward_console_demo.html - a no-server, shareable copy
```

Both run the identical scoring/explain/grouping logic against the locked
test split. The live console (`api/app.py`) reads `data/out/pairs_test.csv`
directly, so approving a pair there reflects the full 4,598-pair review
queue and 6,492-pair auto-suggest queue. The static export
(`api/export_static_demo.py`) freezes a sample of 220 review-band pairs, 160
auto-suggest pairs and 25 hard-key-veto examples — each with a full
`explain()` breakdown — into one self-contained HTML file: approve / reject
/ un-merge still run for real, as a JS port of `api/grouping.py`'s
union-find, persisted to that browser's `localStorage`. It's what to send
someone who can't run Python.

Console feature surface:

- **Review queue**, ranked by priority rather than score alone — *uncertainty*
  (how close the score sits to the 0.92 cut), *thin evidence* (how few specs
  were readable on both sides) and *value at stake* (qty × unit value across
  both records, from the source rows). All three are shown on every card, so
  the ranking can be argued with.
- **Auto-suggest queue** — score ≥ 0.92, still requiring a human's sign-off.
- **"Why did SAMANVAY match these?"** — each signal with its weight *and its
  contribution to the fused score*, every hard key as MATCH / MISMATCH /
  UNKNOWN, the evidence count, and a plain verdict. A pair that clears 0.92 but
  is capped by the coverage floor is labelled `HELD — THIN EVIDENCE`, not
  "high confidence".
- **Hard-key vetoes** — the highest text-similarity pairs the engine still
  rejected, each shown against what a fuzzy matcher would have scored it.
- **Performance** (`GET /api/performance`) — a slider over the real validation
  sweep the threshold was selected from, the locked holdout result, the
  five-method baseline comparison, and what the veto is worth on planted hard
  negatives. Nothing here is recomputed for display; it is read from
  `threshold_selection.json` and `holdout_run.json`.
- **Golden records** — groups formed only by steward-approved edges
  (`api/grouping.py`), with every legacy code mapped and any member splittable
  back out.
- **Audit log** — append-only, recording the confidence at the moment of the
  decision and the before → after group state.
- **Live search** (`GET /api/search`) — same fusion scorer `demo.py` uses.

The static export adds a **Test SAMANVAY** panel: three real pairs from the
locked split (an ordinary duplicate, a duplicate whose descriptions barely
overlap, and a near-identical pair that is *not* the same part) where the
reader commits to an answer before the ground truth is revealed.

## Layout

```
data/generate.py      benchmark + ground truth + splits
data/dictionaries/    abbreviations & units - the generator corrupts with these,
                      the engine repairs with them. one source of truth.
engine/               the pipeline above
eval/harness.py       three layers + baselines
eval/select.py        threshold chosen on VALIDATION, with the reason written down
eval/report.py        RESULTS.md + charts, enforces the holdout lock
demo.py               reason panels + live search (CLI)
api/                  steward console - Flask backend, SQLite store, union-find
                      grouping, vanilla-JS front end, and the static-demo exporter
```

## Known limits

- Attribute extraction is rule-based; an unfamiliar category parses worse. That
  shows up as low coverage, which pushes pairs to review rather than producing
  wrong merges — it degrades safely.
- Some pairs are genuinely unresolvable: description loss can leave two different
  items textually identical. [`RESULTS.md`](RESULTS.md) measures this and reports
  it as a ceiling on achievable precision instead of hiding it.
- No multilingual handling yet; the dictionary layer is where it plugs in.
- The console uses SQLite and Flask, not Postgres and FastAPI, for the same
  reason the engine uses TF-IDF-SVD: this sandbox cannot reach PyPI. Both
  swaps are routing/connection-layer changes, not redesigns — `api/store.py`
  is deliberately Postgres-shaped. There's also no login/RBAC yet; every
  steward action is attributed by a free-text name field, not an account.

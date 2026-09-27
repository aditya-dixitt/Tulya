# TULYA — migration from prototype to deployable stack

**Phase 1 deliverable: the audit and the plan.** Phases 2 to 7 are implemented
and verified; the rest is sequenced below.

---

## 1. What the existing repository actually contains

7,128 lines of Python across nine packages, plus a generated single-file
console. The audit found a codebase in better shape than "prototype" suggests:
the matching engine already had clean seams for exactly the three backends the
PPT names.

| area | files | verdict |
|---|---|---|
| matching engine | `engine/` — normalize, attributes, block, embed, index, fuzzy, score, explain, pipeline | **Keep, move, harden.** Already had swappable backends for sbert / faiss / rapidfuzz. |
| API | `api/app.py` (731 lines, Flask) | **Replace** with modular FastAPI routers. Logic moves to services. |
| persistence | `api/store.py` (SQLite) | **Replace** with PostgreSQL + SQLAlchemy. Schema was already Postgres-shaped. |
| auth / RBAC | `api/auth.py` — 4 roles, maker-checker, PBKDF2 | **Keep the model, move the storage.** PBKDF2 → Argon2id. |
| grouping | `api/grouping.py` — union-find with conflict enforcement | **Keep.** Port to a service over Postgres. |
| CNMC registry | `engine/registry.py`, `engine/codegen.py` — Damm check digit, supersession | **Keep.** Move persistence to Postgres. |
| ERP connector | `erp/` — SAP MARA/MAKT/MARC/MARD, extract, write-back, revoke | **Keep as-is.** Already read-only by default with a controlled export path. |
| evaluation | `eval/` — 3-layer harness, threshold selection, holdout verify | **Keep.** Re-point at the new engine; preserve the old baseline. |
| data generation | `data/generate.py`, dictionaries | **Keep.** The dataset is the evaluated dataset; it must not be regenerated casually. |
| tests | 125 tests across 7 modules | **Keep and extend.** |
| TULYA console | `tulya/*.js`, `tulya/build.py` | **Replace** with React + Tailwind. Business logic in it moves server-side. |

### Findings that changed the design

**1. The six verdict states lived in the browser.** `tulya/model.js` computed
IDENTICAL / EQUIVALENT / CONDITIONAL / DIFFERENT / CONFLICT / UNRESOLVED
client-side. A governed decision state computed in JavaScript cannot be trusted
by an auditor, and it meant the rules existed in exactly one place — and that
place was not the backend. Moved to `backend/app/matching/verdict.py` and
persisted on `material_matches.equivalence_status`.

**2. Legacy codes are not unique within a CPSE.** The dataset has 4,480
`(cpse, legacy_code)` collisions, up to 8 rows deep, and 1,312 collisions even
within a single plant. The obvious unique constraint is wrong. Consequence:
`resolve legacy code → national code` must return a *set* of candidates and ask
the steward which plant they mean. `GET /api/materials/by-legacy/{cpse}/{code}`
returns a list for this reason, and the schema carries a non-unique index.

**3. Stock and demand did not need to be invented.** `records.csv` already
carries real `qty` and `unit_value` columns. The TULYA console had been
generating stock figures from a hash of the record id. The backend uses the
dataset's own quantities instead — still synthetic benchmark data, still
labelled SIMULATED, but derived from the evaluated dataset rather than from
nothing.

**4. Silent backend degradation was the most dangerous property in the repo.**
`engine/embed.py` fell back from Sentence-BERT to TF-IDF automatically, and only
a line in RESULTS.md recorded which had run. Addressed in Phase 3; see below.

---

## 2. Target architecture

```
React + Tailwind (Vite, TS)
        │  HttpOnly cookie + CSRF header
        ▼
FastAPI  ── routers → services → repositories
        │                    │
        │                    ├── PostgreSQL 16   (governed state, audit)
        │                    ├── FAISS IndexFlatIP (vector retrieval)
        │                    ├── Sentence-BERT   (all-MiniLM-L6-v2, 384-dim)
        │                    ├── RapidFuzz       (token_set_ratio)
        │                    └── Ollama / Llama 3.2 3B  ← extraction ONLY
        ▼
Docker Compose: frontend · backend · db · ollama
```

The LLM sits outside the decision path by construction. It converts a messy
description into structured attributes and returns `null` for anything it cannot
identify. Equivalence comes from attribute comparison, the hard-key veto, the
coverage floor and a named steward.

---

## 3. Phase status

| phase | scope | status |
|---|---|---|
| 1 | Audit and plan | **done** — this document |
| 2 | FastAPI + PostgreSQL + models + migrations + seed | **done, verified** |
| 3 | Matching engine on FAISS / RapidFuzz / Sentence-BERT, no silent fallback | **done, verified** (see §5 for what could not be executed here) |
| 4 | Ollama structured extraction, in-vocabulary validation, rule precedence | **done, verified** (19 tests / 38 cases, no network) |
| 5 | Standards knowledge graph + RAG retrieval over standard text | **done, verified** (33 tests / 39 cases, no database) |
| 6 | Workflow, review, audit, CNMC registry services | **done, verified** (54 tests, no database) |
| 6b | HTTP routers for standards, review, grouping, registry | next — blocked on a live PostgreSQL to test against |
| 7 | Analytics, procurement, impact — all server-side | **done, verified** (37 tests, no database) |
| 8 | React + Tailwind frontend | planned |
| 9 | Docker Compose, health checks, deployment config | planned |
| 10 | Full test suite + evaluation re-run | planned |

---

## 4. What Phases 2–3 delivered

**Database.** 27 tables, Alembic migration applied to a live PostgreSQL 16
instance. Governance rules are database constraints, not conventions:

- `ck_reviews_no_self_countersign` — the proposer cannot be the countersigner
- `ck_standard_relationships_verified_needs_source` — no source, no VERIFIED
- `ck_material_matches_ordered_pair` — pairs are unordered, stored canonically
- `ck_national_material_codes_superseded_needs_target` — a retired code must
  forward somewhere, because old purchase orders still carry it

**Import.** 6,995 test-split records and 19,622 attributes loaded in 8 seconds
from the existing `records.csv`. The importer refuses to run if the CSV is
missing rather than fabricating a substitute.

**Engine.** Moved to `backend/app/matching/`. Weights and thresholds now come
from configuration. `backends.py` resolves each of the three swappable stages
explicitly and, in strict mode, **raises rather than falling back**:

```
'sbert' was requested but 'sentence_transformers' is not importable.
MATCHING_STRICT is on, so TULYA will not start rather than score with
'tfidf-svd' while claiming 'sbert'.
```

Every `engine_runs` row records the exact backends that produced it, which is
the mechanism that stops a TF-IDF result being quoted as a Sentence-BERT result.

**Tests.** 28 passing against real PostgreSQL, including the guarantees the
project rests on: the veto forces 0.926 → 0.000 on M12-vs-M16; UNKNOWN never
counts as MATCH; the coverage floor caps a 0.99 score at review; 3/4" and 4"
stay distinct; FAISS `IndexFlatIP` is verified exact against brute force; strict
mode refuses to downgrade.

---

## 4b. What Phase 4 delivered

**Extraction is rules-first.** `backend/app/matching/llm_extract.py` asks the
model only about hard keys the regex extractor returned UNKNOWN for. A proposal
for a key the rules already read is discarded rather than compared — the rules
are the reproducible path, and letting a model overrule them would put the veto
on evidence nobody can re-derive from the text.

**Proposals are in-vocabulary or they are dropped.** `canonicalise()` validates
against the same `_P` patterns and `MATERIALS` table `attributes.py` uses, from
the same module, so the two extractors cannot drift apart. `"12mm"`, `"M 12"`
and `"twelve"` become `M12` or nothing. Unparseable model output is treated as
"no answer", never as an error.

**An LLM-read specification may block a merge and may never authorise one.**
This is the phase's central rule and it is enforced in `score.fuse()`, which now
takes an optional `provisional` set naming LLM-sourced keys:

| direction | counted? | why |
|---|---|---|
| MISMATCH on an LLM key | **yes — vetoes** | a hallucinated conflict costs one review; a real conflict missed costs a wrong merge |
| MATCH on an LLM key | **no — excluded from the coverage floor** | otherwise a hallucinated agreement manufactures the evidence that lets a pair merge without a human |

`coverage_verified` is reported alongside `coverage` on every scored pair, so
the distinction is visible in the API and the audit trail rather than implicit.

**Availability follows the backend rule.** `resolve_llm()` raises in strict mode
when extraction is enabled but Ollama is unreachable or the model was never
pulled, rather than silently running rules-only — the same argument as
`MATCHING_STRICT`. `make -C backend check-llm` prints the state.

**Tests.** 19 test functions, 38 cases (parametrised), in
`backend/tests/test_llm_extraction.py`, all against an `httpx.MockTransport`.
No network, no Ollama, no model weights: the guarantees are properties of the
merge and scoring rules, not of any model's output, and they hold on a laptop
with nothing on port 11434. The existing engine suite still passes unchanged —
`provisional` defaults to empty, so behaviour without the LLM is bit-identical.

---

## 4c. What Phase 5 delivered

`backend/app/standards/` — four pure modules and one repository. Only
`repository.py` touches PostgreSQL, which is why the decision rules have tests
that run anywhere.

**Designation recognition.** `designations.py` finds "IS 1367 PT-3 CL 8.8",
"IS:1367 Part 3" and "is1367 pt 3" and reduces all three to one key,
`IS1367PART3CLASS88`, using the same `normalise()` that populates
`standard_designations.normalised`. Recognition is conservative on purpose: a
thread (`M12`), a pressure class (`CLASS 600`) and a bearing designation
(`6205`) are all correctly recovered as *not* standards. Missing a real one
costs a review; inventing one puts a relationship edge in front of a steward as
though it were evidence.

**The graph answers with an effect, not a score.** `graph.assess()` returns one
of BLOCKS / SUPPORTS / INFORMS / NONE, and the schema's rule is enforced in the
code as well as the CHECK constraint: only VERIFIED or in-scope SCOPED edges
that actually carry a citation may SUPPORT. A `VERIFIED` edge with no source
resolves to INFORMS. A SCOPED edge speaks only about the attributes it names.

**The guarantee, mechanically enforced.** Decisions are ranked by
restrictiveness and `graph.apply()` cannot return a rank below the one it was
given. A CONFLICT edge blocks a pair outright; a sourced, in-scope EQUIVALENT
attaches citations and **changes no decision**. An unsourced CONFLICT still
blocks, and says "unsourced — recorded as a caution, not a fact", because
blocking is the safe direction.
`test_standards_evidence_can_never_relax_a_decision` walks every decision ×
every effect and asserts it.

**Retrieval keeps provenance or says it lost it.** `retrieval.ChunkIndex` is
exact cosine over `standard_text_chunks` via the same `ExactIP` the matcher
uses, with the encoder injected rather than constructed. A chunk with no
`source_id` is still returned but `citable` is False and its evidence row reads
`UNSOURCED — do not quote as a fact`. A similarity floor (0.35) exists because
in a small corpus the top hit is always *something*.

**The summariser writes the summary and nothing else.** `evidence.build()`
takes an optional summariser; the citation stays rule-written, the `verdict`
comes from `assess()`, and `summary_from_llm` is a column rather than an
inference. A summariser that raises leaves the rule-written summary in place.

**Tests.** 33 test functions, 39 cases, in `backend/tests/test_standards.py`.

---

## 4d. What Phase 6 delivered

`backend/app/workflow/` and `backend/app/registry/` — five pure modules, 54
tests, no database.

**The load-bearing fix: a pairwise veto is not enough.** `workflow/grouping.py`
carries a consolidated specification profile per group and refuses any approval
that would merge two profiles disagreeing on a hard key:

> A record whose description was truncated at SAP's 40-character MAKTX limit
> conflicts with nobody, because an unreadable key is UNKNOWN and UNKNOWN never
> vetoes. It can pair legitimately with a 1-inch gasket and, separately, with an
> 18-inch gasket. Neither pair is wrong. Their union is very wrong, and nothing
> at pair level is looking at it.

Measured in the prototype's ERP round trip before the fix: 21 of 516 golden
records (4.1%) held members that directly contradicted each other on a hard key.
`test_transitive_closure_cannot_smuggle_a_conflict_into_a_group` reproduces the
exact shape, asserts both pairs pass a pairwise check, and asserts the union is
refused.

A refused approval is **returned, not discarded** — a `BlockedEdge` naming the
conflict and carrying the `review_id`, with `audit.for_blocked_edge()` recording
it as loudly as an accepted one. Edges apply strongest-evidence-first, so the
one refused is deterministically the weaker; verified order-independent.

**Maker-checker, expressed rather than intended.** An approval above
`SECOND_APPROVAL_VALUE` is parked as `awaiting_second`, and `is_edge_approved()`
returns False for it, so a parked approval cannot form a group. The proposer
countersigning their own approval raises `SelfCountersign`, matching the
`no_self_countersign` CHECK. `Decision` is frozen and `countersign()` returns a
new one, so what the first approver signed is never edited by the second.
`score_at_decision` survives countersigning and withdrawal.

**Append-only is a property of the API surface.** `workflow/audit.py` offers
`event()` and nothing else, and a test asserts the names `update`, `amend`,
`correct`, `edit`, `delete`, `redact` are absent from the module rather than
trusting the docstring.

**The registry.** `registry/codegen.py` is ported unchanged from
`engine/codegen.py`. Its tests re-derive the Damm table's total anti-symmetry
from the table itself, so one mistyped cell fails the suite. Every single-digit
error and every adjacent transposition on a real code body is verified caught —
the latter being the reason for Damm over Luhn.

`registry/service.py` refuses a code for a group with no readable hard key
(`INSUFFICIENT_EVIDENCE`) rather than issuing a number that asserts an identity
nothing supports, and keeps the refusal. A member whose own description cannot
confirm the signature is mapped `PROVISIONAL` with its unknown keys listed.
`supersede()` refuses to retire a code without naming its replacement, mirroring
`superseded_needs_target`.

**Not in this phase, deliberately.** The HTTP routers for standards, review,
grouping and the registry are sequenced as 6b. Every service they will call is
written and tested; the routers need a live database to be tested honestly.

---

## 4e. What Phase 7 delivered

`backend/app/analytics/` — three pure modules, 37 tests, no database.

This phase is built against a risk named in §7 of this document: *simulated
quantities get quoted as measured savings*. Three defences, in order of how
much work they do.

**A bare float does not leave the package.** `Figure` carries a value, a
provenance and a `basis` string saying in plain words where the number came
from, and raises if the basis is empty. `procurement_opportunities` and
`impact_scenarios` both have `provenance` and `basis` as NOT NULL columns; this
is the same rule expressed where the arithmetic happens rather than only at the
storage boundary.

**Provenance is inherited, not asserted.** `derive()` takes the *weakest*
provenance among its inputs, so one SIMULATED input simulates the whole
aggregate, and a MEASURED figure cannot be reached from a SIMULATED one by any
route the package offers. Deriving from MEASURED inputs yields DERIVED, never
MEASURED — the tempting mistake is exactly one aggregation step away from the
honest label, so the lattice makes it unrepresentable.

**Nothing in the phase produces a money figure.** Quantities, coverage and a
consolidation count; no rupees. Unit value is available on a `Holding` if a
caller genuinely needs it, and no output multiplies it into a headline. A
misread quantity is an overstated stock position; a misread *saving* ends up in
a board pack. `test_the_scenario_produces_no_money_figure` asserts it.

Two behavioural rules carry the same asymmetry as the rest of the system:

* **A PROVISIONAL mapping does not authorise a transfer.** Its stock is
  reported — a planner wants to know it might be there — but excluded from
  headline availability, from coverage, and from pooled stock. Weak evidence may
  raise a question, never settle one.
* **An unresolved identity produces no recommendation.** `availability()`
  returns `UNRESOLVED_CASE` with the quantities still reported for context, and
  `compute_scenario()` refuses outright rather than returning zeros that read
  like a finding about an item nobody has confirmed.

Coverage is capped at 1.0 to match the `coverage_range` CHECK, zero demand is
handled rather than divided by, and the best source record is the largest
confirmed holding with ties broken by lowest id so the answer is stable.

---

## 5. What could not be executed in this environment

Stated plainly, because the difference matters.

| component | status |
|---|---|
| **FAISS** | **Executed.** faiss-cpu 1.15.1, `IndexFlatIP`, verified exact against brute-force cosine. |
| **RapidFuzz** | **Executed.** rapidfuzz 3.14.6, `token_set_ratio`. |
| **PostgreSQL** | **Executed.** 16.13, real migrations, real queries, real constraint violations. |
| **FastAPI** | **Executed.** 28 tests through `TestClient`. |
| **Sentence-BERT** | **Wired, not executed.** `huggingface.co` returns 403 (organisation policy) in this sandbox, so `all-MiniLM-L6-v2` weights cannot be downloaded. The code path, dimension check and strict-mode refusal are all implemented and tested. |
| **Ollama / Llama 3.2 3B** | **Implemented and unit-tested against a mock transport; not executed against a live model.** `ollama.com` and `registry.ollama.ai` return 403 in this sandbox, so no weights could be pulled. The client, prompt, JSON parsing, canonicalisation, merge policy and strict-mode refusal are all exercised by tests. What remains unverified is only how well `llama3.2:3b` itself reads a material description. |
| **Docker Compose** | **Not yet written** (Phase 9). No Docker daemon is reachable in this sandbox, so `docker compose up` will need verifying on your machine. |

Nothing in the repository claims otherwise, and no number attributed to
Sentence-BERT exists anywhere in it.

---

## 6. Evaluation policy

The existing measured results were produced by the dependency-free TF-IDF/SVD
encoder with difflib fuzzy matching. They are real, and they are **not**
Sentence-BERT numbers.

- The historical baseline is preserved and relabelled, never overwritten.
- `RESULTS.md` gains an explicit backend attribution line per run, generated
  from the `engine_runs` row rather than typed.
- The Sentence-BERT column reads NOT YET MEASURED until someone runs `make eval`
  on a machine with model access.
- Conformal calibration is shown as **PLANNED**, because it is designed but not
  implemented or validated.

---

## 7. Risks

| risk | mitigation |
|---|---|
| Sentence-BERT changes the score distribution, so thresholds tuned on TF-IDF no longer hold | Thresholds are configuration. `eval/select.py` re-selects on validation before any Sentence-BERT number is quoted. |
| Re-running the pipeline rewrites scores a steward already signed against | `reviews.score_at_decision` freezes the score at the moment of the decision. The engine's later opinion cannot silently rewrite what a person approved. |
| Ollama hallucinates a specification that was not in the text | Pydantic-validated structured output; unknown → `null`; every LLM-sourced attribute carries `source='LLM'` and is distinguishable from `source='RULE'` at query time. |
| Simulated quantities get quoted as measured savings | `provenance` and `basis` are NOT NULL columns on both scenario tables; the API cannot serialise a scenario without them. |

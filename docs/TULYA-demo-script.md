# TULYA — Prototype Demo Script

**SIH26099 · Team AlgoRythms · One Nation · One Material Code**

Open `reports/tulya_console.html` in a browser. There is no sign-in — the console
opens straight on the Control Tower. Full walkthrough is ~7 minutes; the 60-second
version is at the end.

**Three rules for whoever presents this**

1. Never say a simulated number as if it were measured. Stock, demand, coverage
   quantities and procurement values are simulated and labelled on screen — say
   "simulated" out loud when you touch them.
2. The measured figures come from a locked test split opened once, on the
   **TF-IDF-SVD** encoder. If a judge asks about Sentence-BERT, say the architecture
   uses MiniLM and this sandbox had no model access, so these are the *fallback*
   encoder's numbers — the honest floor, not the ceiling.
3. If asked something the prototype does not do, say so and point at the panel that
   admits it. The console is built to be argued with; that is the pitch.

---

## 0 · Opening line (20 seconds — before you touch anything)

> "Six oil-and-gas CPSEs. The same 40NB gate valve sits in four of their stores
> under four different codes, and nobody can see it. Not because the data is
> missing — because nothing in the country matches one company's material master
> to another's. This is TULYA. It reads those masters and issues one Common
> National Material Code per real item, and it refuses to merge anything a human
> would not."

Then: "Everything on screen is one run of our pipeline on a test split we locked
before we ever looked at it."

---

## 1 · Control Tower — the shape of the problem (45 seconds)

*Panel: Overview (opens here)*

Point at the top strip and the matching-performance chart.

> "Forty-six thousand records, six CPSEs, twenty categories. The chart is the
> threshold sweep — precision of what we auto-suggest against how much still
> needs a person. That curve is the whole engineering argument, and we will come
> back to it on the last screen."

Point at the provenance banner (the collapsible strip under the topbar).

> "This bar is on every page. Matches, scores, specifications and verdicts are
> real pipeline output. Stock and demand quantities are simulated, deterministically,
> so the demo reproduces — and they are labelled wherever they appear. We would
> rather tell you that than have you find it."

**Do not linger.** The overview is scene-setting; the argument is next.

---

## 2 · Test TULYA — hand the judges the problem (75 seconds · the hook)

*Panel: Test TULYA*

This is the strongest 90 seconds in the demo. Do not skip it and do not rush it.

> "Before I show you what our system decided, decide yourself. These are three
> genuine pairs out of the locked split."

Read case 1 aloud — both descriptions, slowly. Then:

> "Same item, or not?"

**Wait for an answer.** Let the silence sit. Then reveal.

> "That is the planted ground truth, not our engine grading its own homework."

Run the second case, and the third if the room is engaged.

> "That hesitation you just felt is the job. A storekeeper in a refinery feels it
> forty times a day, has no time, and creates a new code. That is where the
> duplicate comes from — not carelessness, ambiguity."

**Transition:** "So here is what we do about it."

---

## 3 · Hard-Key Vetoes — the thing nobody else does (75 seconds · the differentiator)

*Panel: Hard-Key Vetoes*

Jump here next, not to the queue. Lead with the refusal, not the match.

> "These are the pairs with the *highest* text similarity in the whole run that our
> system rejected outright. Any fuzzy matcher, any embedding model, hands you each
> of these as a confident match. We refuse them."

Open one veto card and read the named reason.

> "It refuses because a specification readable on both sides disagreed — pressure
> class, material grade, thread form. And it names which one. Similarity is not
> equivalence. A bolt that is dimensionally identical in a different grade of steel
> is a different item, and in a refinery that difference is a safety incident."

The number to say:

> "Eight hundred and fifty-seven hard negatives in the test split — pairs built one
> specification apart with near-identical text. Seven hundred and forty-one reached
> the scorer. It rejected **one hundred per cent** of them. With the veto switched
> off, 99.87%. That gap is small and it is the entire point: those are exactly the
> merges that would have cost someone their trust in the system."

**If a judge says "commercial tools already do fuzzy plus embeddings":** Agree
immediately. "They do — the technique isn't our novelty. The veto as a hard override,
the cross-organisational scope, on-premise sovereignty, and published reproducible
measurement are."

---

## 4 · Review Queue and Auto-Suggest — the human stays in it (60 seconds)

*Panel: Review Queue*

> "Pairs the engine will not decide alone. And it does not just hand you a list —
> it ranks by uncertainty, times thin evidence, times value at stake. All three are
> shown on every card, so a steward can argue with the ranking instead of trusting it."

Point at one card's three components.

> "Uncertainty is how close the score sits to the 0.92 cut. Thin evidence is how few
> specifications were readable on either side. Value at stake is quantity times unit
> value — simulated, as the banner says. High uncertainty on a cheap item waits.
> A marginal call on something expensive goes first."

*Switch to: Auto-Suggest*

> "Score above 0.92. High confidence. And still not merged — every one of these
> waits for a steward. **Nothing in this system merges itself.** That is a design
> decision, not a limitation we are apologising for."

Approve one pair. Let them watch the counter move.

---

## 5 · Golden Records — what actually gets issued (45 seconds)

*Panel: Golden Records*

> "That approval produced this. A golden record carrying a Common National Material
> Code."

The sentence that answers the CPSE-resistance question before it is asked:

> "Every CPSE keeps its own legacy ERP code. The CNMC *maps* them — it does not
> replace them. Nobody has to re-tag a warehouse, nobody's SAP transaction breaks,
> nobody's purchase history is orphaned. That is what makes this deployable one CPSE
> at a time instead of as a national migration project."

Point at the group's membership and the canonical description.

> "The canonical description is the member with the most specifications resolved —
> chosen, not invented. And any member can be split back out. This group exists only
> because a steward approved every single edge connecting it."

---

## 6 · Material Passport — the engineering record (30 seconds)

*Panel: Material Passport* — open one identity.

> "For any material identity: every legacy code that means it, the specifications
> recovered out of those descriptions, the standards on file, the match analysis,
> and the steward decision that issued or refused the code. This is what an engineer
> opens when they want to know why two codes were called one item."

---

## 7 · Audit Log — the governance answer (30 seconds)

*Panel: Audit Log*

> "Append-only. Every entry records what changed, the confidence at the moment of
> the decision, and who made it. So a merge can be traced back years later and
> undone. For a government deployment that is not a feature, it is the precondition."

Point at the entry from the approval you made in section 4.

> "That is the decision I took two minutes ago, with the score it had at the time."

---

## 8 · Performance — why we are not maximising F1 (60 seconds · the closer)

*Panel: Performance*

This is where a technical judge decides whether to believe you. Slow down.

> "Nothing on this page is computed for display. Every point is measured."

Drag the threshold slider.

> "Real measured points from the validation sweep, not a curve fitted for the demo.
> At our operating threshold of 0.92: **95.4% of auto-suggestions are correct, and
> 58.9% of records still need a human.** We say the second number because it is the
> one that gets hidden."

Then the sentence that separates you from every other team:

> "We did not pick the threshold that maximises F1. We put the floor on *precision*,
> because a wrong merge costs more than a missed one — a missed duplicate is money
> left on the table, a wrong merge is a wrong part fitted. And we chose it on
> validation with headroom, not at the margin."

Point at the holdout ledger.

> "That ledger is the part we are proudest of. Four recorded runs against the locked
> split. Run 3 is the informative one — we selected the threshold right at the
> validation margin and test came back at 0.9242, **below our own 0.95 target.** That
> is a failure, it is written down, it is why the selector now demands headroom, and
> it is still on the page. Every evaluation is appended to a file. Nothing is
> overwritten, so how many times we have touched the holdout is auditable rather
> than asserted."

Close:

> "One command reproduces every figure on this page. `make demo`. Nothing here was
> typed by hand."

---

## Optional panels — only if time or a question opens the door

| Panel | Say this | Use when |
|---|---|---|
| **Impact Simulator** | "Simulated. Pick a material, pick which CPSEs join, set demand — this is what *could* follow if identities are harmonised. Labelled illustrative because it is." | A judge asks about savings or ROI |
| **Procurement Intelligence** | "Decision support only. It approves nothing and moves nothing — it surfaces where an open demand could already be met from a material another CPSE holds under a different code, and routes it to review." | A judge asks "so what happens next?" |
| **Analytics** | "Harmonisation state across the records. Counts and verdicts are pipeline output; stock and demand are simulated." | A judge wants scale |
| **Standards Knowledge Graph** | "How the designations these records cite relate to each other. Every edge carries a relationship type *and* a verification state — an unverified relationship shows REQUIRES REVIEW. We never present an inferred equivalence as fact." | A judge asks about standards / IS / ASTM |
| **Collaboration** | "A case moves AI → data steward → engineering → procurement → governance. Every stage leaves a record." | A judge asks about workflow or org adoption |
| **Search** | "The same normaliser, extractor and fusion scorer the pipeline runs, against a free-text query. This offline export ships eight precomputed queries." | A judge asks to try something themselves — *set expectations first, it is precomputed* |

---

## Anticipated questions — short answers

**"Why not just use SAP MDG / GeM?"**
SAP stores codes and cannot tell you two codes mean one item; MDG's cleansing cases
cover business-partner data, not materials. GeM standardises the seller's catalogue,
not the buyer's master. NCB India under the Directorate of Standardisation already
does national codification — for defence, on the NATO system. The principle is
accepted in India. There is no civilian CPSE equivalent.

**"Will CPSEs share stock?"**
No — say this clearly. Inside one CPSE, plant-to-plant redeployment is routine, same
company, same books. Across CPSEs they are separate legal entities: a transfer is an
inter-company sale with invoicing and GST. The cross-company benefit is **price
benchmarking first** — pure information, needs no coordination, available the day the
codes are matched — then demand aggregation into one larger tender, then sector-wide
rate contracts.

**"How does it roll out?"**
One CPSE at a time, its own plants first, where the data owner already exists. No
national big-bang. Legacy codes are retained throughout, so there is no migration
cliff.

**"Is 58.9% needing review not a lot?"**
It is, and we report it rather than bury it. The alternative is a system that merges
on its own judgement, and section 3 is why we will not build that. The share falls as
stewards' decisions accumulate and as extraction improves — but we would rather ship
an honest 58.9% than a fabricated 10%.

**"Why 3B-class models / can this run on CPSE hardware?"**
On-premise, CPU-viable. Material master data does not leave the CPSE's network. For a
government deployment, sovereignty is a hard requirement, not a preference.

**"Does it learn?"**
Steward decisions accumulate as labelled data in the browser in this export, and in
the audit store in a real deployment. The engine improves from the decisions actually
taken on a CPSE's own catalogue.

---

## 60-second version

1. **Hook (15s)** — "Same valve, four CPSEs, four codes, nobody can see it. TULYA
   issues one Common National Material Code per real item."
2. **Test TULYA (20s)** — one pair, ask them to decide, reveal. "That hesitation is
   the job."
3. **Hard-Key Vetoes (15s)** — "Highest similarity in the run, rejected, and it names
   the specification it refused on. 100% of 741 hard negatives. Similarity is not
   equivalence."
4. **Performance (10s)** — "95.4% auto-suggest precision, 58.9% still needs a human,
   locked split opened once, failed run still in the ledger, `make demo` reproduces
   all of it."

---

## Pre-demo checklist

- [ ] `python3 tulya/build.py` run after any change to `tulya/modules.js`, `modules.css` or `build.py`
- [ ] Open `reports/tulya_console.html` fresh — confirm it lands on Control Tower with no sign-in
- [ ] Clear local storage (Audit Log → **Reset demo state**) so the audit log starts empty and your live approval is visible in it
- [ ] Test TULYA → **Reset the three cases**, so the answers are hidden
- [ ] Performance slider sitting at 0.92 before you begin
- [ ] Browser zoom at 100%, window maximised, sidebar visible
- [ ] Know which veto card you are opening in section 3 — pick it beforehand, do not hunt on stage

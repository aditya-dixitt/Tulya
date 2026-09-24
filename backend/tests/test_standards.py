"""Phase 5: the standards knowledge graph and RAG retrieval.

No database, no network, no model. Every rule these tests state is a property of
the decision logic, so they hold on a laptop with nothing running.

The one that matters most is `test_standards_evidence_can_never_relax_a_decision`:
it walks every decision × every effect and asserts the outcome is never less
restrictive than the input. That is the guarantee the whole phase rests on.
"""
from __future__ import annotations

import itertools

import numpy as np
import pytest

from app.standards import (
    BLOCKS, INFORMS, NONE, RANK, SUPPORTS, Chunk, ChunkIndex, Edge, Retrieved,
    apply, assess, build_evidence, find, keys, normalise,
)


# --------------------------------------------------------------------------
# designations
# --------------------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("HEX BOLT M12 IS 1367 PT-3 CL 8.8", "IS1367PART3CLASS88"),
    ("hex bolt is:1367 part 3 class 8.8", "IS1367PART3CLASS88"),
    ("PIPE ASTM A106 GR.B SCH40", "ASTMA106GRADEB"),
    ("plate bs en 10025", "BSEN10025"),
    ("BEARING ISO 15:2017", "ISO152017"),
])
def test_designations_canonicalise_to_one_key(text, expected):
    assert keys(text)[0] == expected


def test_the_same_reference_written_three_ways_is_one_key():
    written = ["IS 1367 Part 3", "IS:1367 PT-3", "is1367 pt 3"]
    assert len({keys(w)[0] for w in written}) == 1


def test_a_designation_records_how_it_was_written():
    d = find("HEX BOLT M12 IS 1367 PT-3 CL 8.8")[0]
    assert d.body == "IS" and d.number == "1367"
    assert d.parts == ("PART 3", "CLASS 8.8")
    assert d.raw.startswith("IS 1367")        # what a steward will recognise


@pytest.mark.parametrize("text", [
    "BOLT HEX M12 X 50 SS304",        # a thread is not a standard
    "CLASS 600 BALL VALVE",           # a pressure class is not a standard
    "6205 2RS BEARING",               # a bearing designation is not a standard
    "",
])
def test_nothing_that_is_not_a_standard_reference_is_recovered(text):
    assert find(text) == []


def test_duplicate_mentions_collapse():
    assert len(find("IS 1367 PT-3 ... per IS:1367 part 3")) == 1


def test_normalise_is_the_key_both_sides_agree_on():
    assert normalise("ASTM A106 Gr. B") == "ASTMA106GRB"


# --------------------------------------------------------------------------
# graph: what an edge is allowed to say
# --------------------------------------------------------------------------
def _edge(rel="EQUIVALENT", verification="VERIFIED", citation="IS 1367-3:2002 Table 4",
          scoped=(), **kw):
    return Edge(source_standard="IS 1367", target_standard="ISO 898",
                relationship=rel, verification=verification, citation=citation,
                scoped_attributes=tuple(scoped), **kw)


def test_no_edges_is_not_evidence_of_anything():
    f = assess([])
    assert f.effect == NONE and not f.citable


def test_a_sourced_in_scope_equivalence_supports():
    f = assess([_edge()])
    assert f.effect == SUPPORTS
    assert f.citable and "IS 1367-3" in f.citations[0]


def test_an_unsourced_equivalence_only_informs():
    """The schema's rule: no source, no fact."""
    f = assess([_edge(verification="REQUIRES_REVIEW", citation=None)])
    assert f.effect == INFORMS
    assert "no source" in f.reason
    assert not f.citable


def test_verified_without_a_citation_cannot_support():
    """Belt and braces for the CHECK constraint: the code refuses it too."""
    f = assess([_edge(verification="VERIFIED", citation=None)])
    assert f.effect == INFORMS


def test_a_scoped_edge_speaks_only_about_what_it_scopes():
    edge = _edge(verification="SCOPED", scoped=("bore_in", "pressure_class"))
    assert assess([edge], attributes=("bore_in",)).effect == SUPPORTS
    out = assess([edge], attributes=("thread",))
    assert out.effect == INFORMS
    assert "does not cover" in out.reason


def test_a_conflict_edge_blocks():
    f = assess([_edge(rel="CONFLICT")])
    assert f.effect == BLOCKS


def test_an_unsourced_conflict_still_blocks_but_says_so():
    """Blocking is the safe direction, so an unsourced conflict is still acted on."""
    f = assess([_edge(rel="CONFLICT", verification="UNVERIFIED", citation=None)])
    assert f.effect == BLOCKS
    assert "unsourced" in f.reason


def test_conflict_wins_over_equivalence():
    f = assess([_edge(), _edge(rel="CONFLICT")])
    assert f.effect == BLOCKS


def test_related_edges_are_context_not_evidence():
    f = assess([_edge(rel="RELATED")])
    assert f.effect == INFORMS


# --------------------------------------------------------------------------
# the guarantee
# --------------------------------------------------------------------------
def test_standards_evidence_can_never_relax_a_decision():
    """Every decision × every effect: the outcome is never less restrictive."""
    findings = [assess([]), assess([_edge()]), assess([_edge(rel="CONFLICT")]),
                assess([_edge(verification="UNVERIFIED", citation=None)])]
    for decision, finding in itertools.product(RANK, findings):
        out, _ = apply(decision, finding)
        assert RANK[out] >= RANK[decision], f"{finding.effect} relaxed {decision} -> {out}"


def test_support_never_promotes_a_review_to_auto_suggest():
    out, reason = apply("REVIEW", assess([_edge()]))
    assert out == "REVIEW"
    assert "does not change the decision" in reason


def test_support_cannot_clear_a_veto():
    out, _ = apply("REJECTED_VETO", assess([_edge()]))
    assert out == "REJECTED_VETO"


def test_a_conflict_blocks_a_pair_that_was_otherwise_auto_suggested():
    out, reason = apply("AUTO_SUGGEST", assess([_edge(rel="CONFLICT")]))
    assert out == "REJECTED_STANDARD"
    assert "CONFLICT" in reason


def test_support_does_not_resurrect_a_discarded_pair():
    out, _ = apply("DISCARD", assess([_edge()]))
    assert out == "DISCARD"


def test_an_unknown_decision_is_refused_rather_than_guessed():
    with pytest.raises(ValueError):
        apply("PROBABLY_FINE", assess([]))


# --------------------------------------------------------------------------
# retrieval
# --------------------------------------------------------------------------
class _Encoder:
    """Deterministic bag-of-words encoder. Enough to test ranking, not semantics."""

    def __init__(self, vocab):
        self.vocab = list(vocab)

    def transform(self, texts):
        out = np.zeros((len(texts), len(self.vocab)), dtype="float32")
        for i, t in enumerate(texts):
            words = set(t.lower().split())
            for j, w in enumerate(self.vocab):
                out[i, j] = 1.0 if w in words else 0.0
            n = np.linalg.norm(out[i]) or 1.0
            out[i] /= n
        return out

    fit_transform = transform


VOCAB = ["tensile", "thread", "hardness", "bore", "coating"]
CHUNKS = [
    Chunk(id=1, standard_code="IS 1367", heading="6.2 Mechanical properties",
          text="tensile strength and hardness requirements", citation="IS 1367-3:2002"),
    Chunk(id=2, standard_code="IS 1367", heading="4.1 Thread",
          text="thread tolerance and pitch", citation="IS 1367-2:2002"),
    Chunk(id=3, standard_code="ASTM A106", heading=None,
          text="bore and wall thickness", citation=None),      # deliberately unsourced
]


def _index():
    return ChunkIndex.build(CHUNKS, _Encoder(VOCAB))


def test_retrieval_ranks_by_similarity():
    hits = _index().search_text("tensile hardness", _Encoder(VOCAB), k=3)
    assert hits and hits[0].chunk.id == 1


def test_an_uncitable_chunk_is_returned_but_flagged():
    hits = _index().search_text("bore", _Encoder(VOCAB), k=3)
    assert hits[0].chunk.id == 3
    assert hits[0].citable is False


def test_irrelevant_queries_return_nothing_rather_than_the_least_bad_row():
    assert _index().search_text("coating", _Encoder(VOCAB), k=3, min_similarity=0.9) == []


def test_an_empty_corpus_retrieves_nothing_and_does_not_raise():
    ix = ChunkIndex.build([], _Encoder(VOCAB))
    assert len(ix) == 0
    assert ix.search_text("tensile", _Encoder(VOCAB)) == []


def test_describe_reports_how_much_of_the_corpus_is_citable():
    d = _index().describe()
    assert d["chunks"] == 3 and d["citable"] == 2 and d["uncitable"] == 1


# --------------------------------------------------------------------------
# evidence
# --------------------------------------------------------------------------
def test_every_consulted_edge_and_chunk_becomes_a_row():
    finding = assess([_edge()])
    hits = _index().search_text("tensile hardness", _Encoder(VOCAB), k=2)
    rows = build_evidence(42, finding, hits)
    assert len(rows) == len(finding.edges) + len(hits)
    assert all(r.match_id == 42 for r in rows)


def test_a_retrieved_chunk_is_never_a_verdict_on_its_own():
    hits = _index().search_text("tensile", _Encoder(VOCAB), k=1)
    rows = build_evidence(1, assess([]), hits)
    assert [r.verdict for r in rows if r.chunk_id] == ["REQUIRES_REVIEW"]


def test_an_uncitable_chunk_is_marked_do_not_quote():
    hits = _index().search_text("bore", _Encoder(VOCAB), k=1)
    row = build_evidence(1, assess([]), hits)[0]
    assert "UNSOURCED" in row.summary and row.provenance == "DERIVED"


def test_the_summariser_writes_the_summary_and_nothing_else():
    hits = _index().search_text("tensile", _Encoder(VOCAB), k=1)
    plain = build_evidence(1, assess([_edge()]), hits)
    summarised = build_evidence(1, assess([_edge()]), hits,
                                summariser=lambda t: "says bolts must be strong")
    chunk_plain = [r for r in plain if r.chunk_id][0]
    chunk_llm = [r for r in summarised if r.chunk_id][0]
    assert chunk_llm.summary != chunk_plain.summary
    assert chunk_llm.summary_from_llm is True
    assert chunk_llm.verdict == chunk_plain.verdict          # verdict untouched
    assert "IS 1367" in chunk_llm.summary                    # citation still rule-written


def test_a_failing_summariser_leaves_the_rule_written_summary():
    hits = _index().search_text("tensile", _Encoder(VOCAB), k=1)
    def boom(_):
        raise RuntimeError("ollama is down")
    row = [r for r in build_evidence(1, assess([]), hits, summariser=boom) if r.chunk_id][0]
    assert row.summary_from_llm is False
    assert "tensile" in row.summary


def test_consulting_the_graph_and_finding_nothing_is_itself_recorded():
    rows = build_evidence(7, assess([]))
    assert len(rows) == 1
    assert rows[0].verdict == INFORMS
    assert "no standards" in rows[0].summary

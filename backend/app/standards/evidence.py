"""Turning a graph finding and retrieved text into StandardEvidence rows.

`standard_evidence` is the audit trail for "why did TULYA bring standards into
this decision at all". One row per thing consulted: per relationship edge, and
per retrieved chunk.

The rule carried through from Phase 4 and `graph.py`: a summariser — rule-based
or the local LLM — writes the `summary` field and nothing else. It never writes
`verdict`. That comes from `graph.assess()`, which is deterministic and
reproducible from the rows in `standard_relationships`. If the model is offline,
summaries get thinner and every verdict is unchanged.

`summary_from_llm` is a column rather than an inference so that a reader can
filter the whole audit trail down to "what did a human-written rule say" without
trusting a heuristic over the text.
"""
from __future__ import annotations

from dataclasses import dataclass

from .graph import BLOCKS, INFORMS, NONE, SUPPORTS, Finding

#: StandardEvidence.verdict values. Deliberately the graph's effects plus the
#: schema default, so the audit trail speaks one vocabulary.
VERDICTS = (BLOCKS, SUPPORTS, INFORMS, "REQUIRES_REVIEW")


@dataclass(frozen=True)
class EvidenceRow:
    """Shaped for StandardEvidence(**row.as_dict()) — no ORM import needed here."""

    match_id: int
    verdict: str
    summary: str
    relationship_id: int | None = None
    chunk_id: int | None = None
    retrieval_score: float | None = None
    summary_from_llm: bool = False
    provenance: str = "DERIVED"

    def as_dict(self) -> dict:
        return {"match_id": self.match_id, "relationship_id": self.relationship_id,
                "chunk_id": self.chunk_id, "retrieval_score": self.retrieval_score,
                "verdict": self.verdict, "summary": self.summary,
                "summary_from_llm": self.summary_from_llm,
                "provenance": self.provenance}


def _edge_summary(edge) -> str:
    bits = [f"{edge.source_standard} {edge.relationship} {edge.target_standard}"]
    if edge.scoped_attributes:
        bits.append(f"scoped to {', '.join(edge.scoped_attributes)}")
    if edge.scope:
        bits.append(edge.scope)
    bits.append(f"verification {edge.verification}")
    bits.append(f"source: {edge.citation}" if edge.citation else "no source on file")
    return "; ".join(bits)


def _chunk_summary(hit) -> str:
    head = f" §{hit.chunk.heading}" if hit.chunk.heading else ""
    cite = hit.chunk.citation if hit.citable else "UNSOURCED — do not quote as a fact"
    text = hit.chunk.text.strip().replace("\n", " ")
    if len(text) > 240:
        text = text[:237].rstrip() + "..."
    return f"{hit.chunk.standard_code}{head} (similarity {hit.score:.2f}; {cite}): {text}"


def build(match_id: int, finding: Finding, retrieved=(), *, summariser=None
          ) -> list[EvidenceRow]:
    """Evidence rows for one match.

    `summariser(text) -> str | None` is optional. It only ever replaces the
    `summary` wording; a failure or a None simply keeps the rule-written one.
    """
    rows: list[EvidenceRow] = []

    for edge in finding.edges:
        rows.append(EvidenceRow(
            match_id=match_id,
            relationship_id=edge.relationship_id,
            verdict=finding.effect,
            summary=_edge_summary(edge),
            provenance="VERIFIED" if edge.sourced else "DERIVED",
        ))

    for hit in retrieved or ():
        base = _chunk_summary(hit)
        summary, from_llm = base, False
        if summariser is not None:
            try:
                s = summariser(hit.chunk.text)
            except Exception:
                s = None
            if s:
                # the citation stays in rule-written text; the model only
                # contributes the paraphrase that follows it
                summary = f"{base.split(': ', 1)[0]}: {s.strip()}"
                from_llm = True
        rows.append(EvidenceRow(
            match_id=match_id,
            chunk_id=hit.chunk.id,
            retrieval_score=round(float(hit.score), 4),
            # retrieved text is never a verdict on its own
            verdict="REQUIRES_REVIEW",
            summary=summary,
            summary_from_llm=from_llm,
            provenance="VERIFIED" if hit.citable else "DERIVED",
        ))

    if not rows and finding.effect == NONE:
        rows.append(EvidenceRow(
            match_id=match_id, verdict=INFORMS,
            summary="no standards were cited by both records, and none were retrieved",
        ))
    return rows

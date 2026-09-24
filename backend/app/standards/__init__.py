"""The standards knowledge graph and the RAG path over standard text.

Phase 5. Four pure modules and one repository:

    designations    find "IS 1367 PT-3" in a description, canonicalise it
    graph           what a recorded relationship is allowed to do to a decision
    retrieval       exact-cosine search over StandardTextChunk, citations kept
    evidence        those two, shaped into standard_evidence rows
    repository      the only module that touches the database

The rule that governs all of it, carried from Phase 4:

    External evidence may block a merge. It may never authorise one.

A CONFLICT edge can stop a pair. An EQUIVALENT edge cannot clear a hard-key
veto, cannot raise a score and cannot turn a REVIEW into an AUTO_SUGGEST — it
attaches citations for a steward to read. `graph.apply()` enforces that with a
restrictiveness rank rather than leaving it to reviewer discipline.

The second rule comes straight from the schema: a relationship without a source
is not a fact. Only VERIFIED and in-scope SCOPED edges may support anything;
the rest INFORM and are rendered as such.
"""
from .designations import Designation, find, keys, normalise  # noqa: F401
from .evidence import EvidenceRow, VERDICTS  # noqa: F401
from .evidence import build as build_evidence  # noqa: F401
from .graph import (  # noqa: F401
    BLOCKS, INFORMS, NONE, RANK, RELATIONSHIPS, SUPPORTS, VERIFICATIONS, Edge,
    Finding, apply, assess,
)
from .retrieval import Chunk, ChunkIndex, Retrieved  # noqa: F401

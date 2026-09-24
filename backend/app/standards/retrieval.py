"""RAG retrieval over standard text.

The knowledge graph answers "is there a recorded relationship". This answers
"what does the standard actually say", which is what a steward asks next and
what an auditor will ask later.

Three properties matter more than recall here:

**Every hit carries its citation, or is marked uncitable.** A chunk whose
StandardTextChunk row has no source_id is still returned — it may be the most
relevant text — but `citable` is False and the caller must render it as
unsourced. Retrieval that quietly drops provenance is how a paraphrase becomes
a fact.

**Retrieval is not a verdict.** Nothing here returns an equivalence decision.
The most a retrieved chunk does is become `StandardEvidence` attached to a
match, alongside the deterministic result, for a human to read.

**Empty means empty.** No chunks indexed, or nothing above the floor, returns
an empty list — never a nearest-neighbour that happens to be least bad. A
similarity floor exists because with a small corpus the top hit is always
*something*, and "the closest of four irrelevant paragraphs" reads as evidence
if you let it.

The encoder is injected rather than constructed, so this module never decides
which backend runs — `matching.backends` owns that, and the same Encoder
instance that embedded the material corpus should embed the standard text.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..matching.index import ExactIP


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage of standard text."""

    id: int
    standard_code: str
    text: str
    heading: str | None = None
    citation: str | None = None

    @property
    def citable(self) -> bool:
        return bool(self.citation)


@dataclass(frozen=True)
class Retrieved:
    chunk: Chunk
    score: float

    @property
    def citable(self) -> bool:
        return self.chunk.citable

    def as_dict(self) -> dict:
        return {"chunk_id": self.chunk.id, "standard_code": self.chunk.standard_code,
                "heading": self.chunk.heading, "text": self.chunk.text,
                "citation": self.chunk.citation, "citable": self.citable,
                "retrieval_score": round(float(self.score), 4)}


class ChunkIndex:
    """Exact inner-product retrieval over standard text chunks.

    Vectors are L2-normalised by the encoder, so the inner product is cosine and
    the similarity floor below is a cosine floor.
    """

    #: below this, a hit is not evidence — it is the least-bad row in a small corpus
    MIN_SIMILARITY = 0.35

    def __init__(self, chunks, vectors, index=None):
        self.chunks: list[Chunk] = list(chunks)
        self.vectors = np.ascontiguousarray(vectors, dtype="float32") \
            if len(self.chunks) else np.zeros((0, 1), dtype="float32")
        self._ix = index
        if self._ix is None and len(self.chunks):
            self._ix = ExactIP(self.vectors)

    # -- construction -----------------------------------------------------
    @classmethod
    def build(cls, chunks, encoder, *, fit: bool = False) -> "ChunkIndex":
        """`encoder` needs only .transform (or .fit_transform when fit=True).

        Fitting on standard text is offered because the corpus is fixed and
        separate from the material corpus; for Sentence-BERT it makes no
        difference, and for the TF-IDF fallback it is the difference between a
        vocabulary built on standards and one built on bolt descriptions.
        """
        chunks = list(chunks)
        if not chunks:
            return cls([], np.zeros((0, 1), dtype="float32"))
        texts = [_embed_text(c) for c in chunks]
        v = encoder.fit_transform(texts) if fit else encoder.transform(texts)
        return cls(chunks, v)

    # -- query ------------------------------------------------------------
    def search(self, query_vector, k: int = 5, *, min_similarity: float | None = None):
        """Top-k chunks above the similarity floor, most similar first."""
        if not self.chunks:
            return []
        floor = self.MIN_SIMILARITY if min_similarity is None else min_similarity
        q = np.ascontiguousarray(np.asarray(query_vector, dtype="float32").reshape(1, -1))
        sims, idx = self._ix.search(q, min(k, len(self.chunks)))
        out = []
        for s, i in zip(sims[0], idx[0]):
            if i < 0 or float(s) < floor:
                continue
            out.append(Retrieved(chunk=self.chunks[int(i)], score=float(s)))
        return out

    def search_text(self, text: str, encoder, k: int = 5, **kw):
        return self.search(encoder.transform([text])[0], k=k, **kw)

    def __len__(self) -> int:
        return len(self.chunks)

    def describe(self) -> dict:
        citable = sum(1 for c in self.chunks if c.citable)
        return {"chunks": len(self.chunks), "citable": citable,
                "uncitable": len(self.chunks) - citable,
                "min_similarity": self.MIN_SIMILARITY,
                "backend": getattr(self._ix, "backend", None)}


def _embed_text(c: Chunk) -> str:
    """Heading carries a lot of signal in standards ("6.2 Mechanical properties")."""
    return f"{c.standard_code} {c.heading or ''} {c.text}".strip()

"""Vector search.

FAISS IndexFlatIP is exhaustive: it computes every inner product and returns the
true top-k. Because the vectors are L2-normalised, that inner product is cosine,
so this stage is mathematically identical to the numpy fallback — faiss is here
for speed at scale, not for different answers.

Approximate indexes are deliberately not the default. `build_index` is the seam
where IVF or HNSW would be introduced once the corpus is large enough for the
recall/latency trade to be worth measuring; until then they add tuning risk and
a recall loss nobody has budgeted for.
"""
from __future__ import annotations

import numpy as np

from .backends import resolve_index


def build_index(vectors: np.ndarray, kind: str | None = None, strict: bool | None = None):
    resolved = resolve_index(strict=strict)
    if kind:
        resolved.name = kind
    return ExactIP(vectors, resolved)


class ExactIP:
    """Exact inner-product top-k, FAISS-backed where available."""

    def __init__(self, vectors: np.ndarray, resolved=None, strict: bool | None = None):
        self.resolved = resolved or resolve_index(strict=strict)
        self.backend = self.resolved.name
        self.v = np.ascontiguousarray(vectors, dtype="float32")
        self.ix = None
        if self.backend == "faiss-flatip":
            import faiss
            self.ix = faiss.IndexFlatIP(self.v.shape[1])
            self.ix.add(self.v)

    @property
    def ntotal(self) -> int:
        return int(self.ix.ntotal) if self.ix is not None else int(self.v.shape[0])

    def search(self, q: np.ndarray, k: int):
        k = min(k, self.v.shape[0])
        if self.ix is not None:
            return self.ix.search(np.ascontiguousarray(q, dtype="float32"), k)
        sims = q @ self.v.T
        idx = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        rows = np.arange(sims.shape[0])[:, None]
        s = sims[rows, idx]
        order = np.argsort(-s, axis=1)
        return s[rows, order], idx[rows, order]

    def save(self, path) -> None:
        """Persist so a restart does not re-embed the corpus."""
        if self.ix is None:
            np.save(str(path) + ".npy", self.v)
            return
        import faiss
        faiss.write_index(self.ix, str(path))

    @classmethod
    def load(cls, path, vectors: np.ndarray | None = None, strict: bool | None = None):
        resolved = resolve_index(strict=strict)
        if resolved.name == "faiss-flatip":
            import faiss
            obj = cls.__new__(cls)
            obj.resolved = resolved
            obj.backend = resolved.name
            obj.ix = faiss.read_index(str(path))
            obj.v = vectors if vectors is not None else np.empty(
                (obj.ix.ntotal, obj.ix.d), dtype="float32")
            return obj
        return cls(np.load(str(path) + ".npy"), resolved)

"""Exact inner-product nearest-neighbour search.

faiss.IndexFlatIP is exhaustive - it computes every inner product and takes the
top k. The numpy backend does exactly that, so results are identical, not
approximate. faiss is used when installed purely for speed at larger scale.
Approximate indexes (IVF/HNSW) are deliberately NOT used: at this corpus size
they buy nothing and add tuning risk.
"""
import numpy as np

try:
    import faiss  # noqa
    BACKEND = "faiss"
except Exception:
    BACKEND = "numpy-exact"


class ExactIP:
    def __init__(self, vectors: np.ndarray):
        self.v = np.ascontiguousarray(vectors, dtype="float32")
        if BACKEND == "faiss":
            import faiss
            self.ix = faiss.IndexFlatIP(self.v.shape[1])
            self.ix.add(self.v)

    def search(self, q: np.ndarray, k: int):
        k = min(k, self.v.shape[0])
        if BACKEND == "faiss":
            return self.ix.search(np.ascontiguousarray(q, dtype="float32"), k)
        sims = q @ self.v.T                       # cosine, vectors are normalised
        idx = np.argpartition(-sims, k - 1, axis=1)[:, :k]
        rows = np.arange(sims.shape[0])[:, None]
        s = sims[rows, idx]
        order = np.argsort(-s, axis=1)
        return s[rows, order], idx[rows, order]

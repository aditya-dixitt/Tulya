"""Sentence encoder with two interchangeable backends.

  sbert     all-MiniLM-L6-v2, 384-dim  - the architecture in the deck.
  tfidf-svd char 3-5 gram TF-IDF -> TruncatedSVD(384) - dependency-free fallback
            used where huggingface.co is unreachable (this sandbox).

Both emit L2-normalised 384-dim float32, so inner product IS cosine and every
downstream stage is identical. Whichever ran is recorded in RESULTS.md - the two
backends do NOT produce the same numbers and must never be quoted for each other.
"""
import os, numpy as np

DIM = 384


def available_backend(pref="auto"):
    if pref in ("sbert", "auto"):
        try:
            import sentence_transformers  # noqa
            return "sbert"
        except Exception:
            if pref == "sbert":
                raise RuntimeError("sentence-transformers not installed")
    return "tfidf-svd"


class Encoder:
    def __init__(self, backend="auto", seed=0):
        self.backend = available_backend(backend)
        self.seed = seed
        self._m = None

    def fit_transform(self, texts):
        if self.backend == "sbert":
            from sentence_transformers import SentenceTransformer
            self._m = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
            v = self._m.encode(list(texts), batch_size=256, convert_to_numpy=True,
                               normalize_embeddings=True, show_progress_bar=False)
            return v.astype("float32")

        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.decomposition import TruncatedSVD
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import Normalizer
        self._m = make_pipeline(
            TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3,
                            sublinear_tf=True, dtype=np.float32),
            TruncatedSVD(n_components=DIM, random_state=self.seed),
            Normalizer(copy=False))
        return self._m.fit_transform(list(texts)).astype("float32")

    def transform(self, texts):
        if self.backend == "sbert":
            return self._m.encode(list(texts), convert_to_numpy=True,
                                  normalize_embeddings=True,
                                  show_progress_bar=False).astype("float32")
        return self._m.transform(list(texts)).astype("float32")

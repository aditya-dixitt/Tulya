"""Sentence encoder.

Production is Sentence-BERT: sentence-transformers/all-MiniLM-L6-v2, 384-dim,
L2-normalised, so an inner product IS cosine and every downstream stage is
unchanged between backends.

The char-ngram TF-IDF -> TruncatedSVD(384) path is retained for development on
machines with no model access. It is NOT a silent substitute: `backends.py`
refuses it in strict mode, and whichever ran is written into every EngineRun row.
"""
from __future__ import annotations

import numpy as np

from ..config import settings
from .backends import resolve_embedding


class Encoder:
    """Fit on dev text, apply to held-out splits. Never fit on a split you score."""

    def __init__(self, backend: str | None = None, strict: bool | None = None, seed: int = 0):
        if backend is not None:
            self.resolved = resolve_embedding(strict=False)
            self.resolved.name = backend
        else:
            self.resolved = resolve_embedding(strict=strict)
        self.backend = self.resolved.name
        self.seed = seed
        self.dim = settings.EMBEDDING_DIM
        self._m = None

    # -- sbert ---------------------------------------------------------------
    def _load_sbert(self):
        from sentence_transformers import SentenceTransformer
        self._m = SentenceTransformer(settings.EMBEDDING_MODEL)
        got = self._m.get_sentence_embedding_dimension()
        if got != self.dim:
            raise ValueError(
                f"{settings.EMBEDDING_MODEL} produces {got}-dim vectors but "
                f"EMBEDDING_DIM is {self.dim}; the FAISS index would be built at "
                f"the wrong width"
            )
        return self._m

    def _encode_sbert(self, texts):
        return self._m.encode(
            list(texts), batch_size=settings.EMBEDDING_BATCH_SIZE,
            convert_to_numpy=True, normalize_embeddings=True,
            show_progress_bar=False,
        ).astype("float32")

    # -- fallback ------------------------------------------------------------
    def _fit_tfidf(self, texts):
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.pipeline import make_pipeline
        from sklearn.preprocessing import Normalizer
        self._m = make_pipeline(
            TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5), min_df=3,
                            sublinear_tf=True, dtype=np.float32),
            TruncatedSVD(n_components=self.dim, random_state=self.seed),
            Normalizer(copy=False))
        return self._m.fit_transform(list(texts)).astype("float32")

    # -- api -----------------------------------------------------------------
    def fit_transform(self, texts) -> np.ndarray:
        if self.backend == "sbert":
            self._load_sbert()
            return self._encode_sbert(texts)
        return self._fit_tfidf(texts)

    def transform(self, texts) -> np.ndarray:
        if self.backend == "sbert":
            if self._m is None:
                self._load_sbert()
            return self._encode_sbert(texts)
        return self._m.transform(list(texts)).astype("float32")

    def describe(self) -> dict:
        return self.resolved.as_dict()

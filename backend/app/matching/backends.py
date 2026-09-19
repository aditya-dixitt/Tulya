"""Backend resolution for the three swappable parts of the engine.

The prototype degraded silently: if sentence-transformers was missing it scored
with TF-IDF and carried on, and only a line in RESULTS.md recorded which had
run. That is the single most dangerous property a system like this can have,
because the number a judge or a materials manager reads is detached from the
algorithm the architecture claims.

So resolution is explicit here, and it has two modes:

  strict (production default)
      The configured backend must be importable. If it is not, resolution
      raises and the application does not start. No fallback, no warning-and-
      continue.

  permissive (development)
      Falls back, but records `degraded=True` and the reason, which /api/health
      reports and every EngineRun row stores. A run performed on a fallback can
      therefore never be mistaken later for one that was not.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field

from ..config import settings


class BackendUnavailable(RuntimeError):
    """Raised in strict mode when a configured backend cannot be loaded."""


@dataclass
class Resolved:
    name: str
    requested: str
    degraded: bool = False
    reason: str | None = None
    version: str | None = None
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "backend": self.name,
            "requested": self.requested,
            "degraded": self.degraded,
            "reason": self.reason,
            "version": self.version,
            **self.detail,
        }


def _probe(module: str) -> tuple[bool, str | None, str | None]:
    try:
        m = importlib.import_module(module)
        return True, getattr(m, "__version__", None), None
    except Exception as exc:  # pragma: no cover - environment dependent
        return False, None, f"{type(exc).__name__}: {exc}"[:200]


def _resolve(requested: str, primary: str, module: str, fallback: str,
             strict: bool) -> Resolved:
    if requested == fallback:
        return Resolved(name=fallback, requested=requested)

    ok, version, err = _probe(module)
    if ok:
        return Resolved(name=primary, requested=requested, version=version)

    if strict:
        raise BackendUnavailable(
            f"{primary!r} was requested but {module!r} is not importable ({err}). "
            f"MATCHING_STRICT is on, so TULYA will not start rather than score "
            f"with {fallback!r} while claiming {primary!r}. Install the dependency, "
            f"or set the backend to {fallback!r} explicitly for development."
        )
    return Resolved(name=fallback, requested=requested, degraded=True,
                    reason=err or f"{module} unavailable")


def resolve_embedding(strict: bool | None = None) -> Resolved:
    strict = settings.strict_backends if strict is None else strict
    req = settings.EMBEDDING_BACKEND
    if req == "auto":
        req = "sbert"
        strict = False
    r = _resolve(req, "sbert", "sentence_transformers", "tfidf-svd", strict)
    r.detail["model"] = settings.EMBEDDING_MODEL if r.name == "sbert" else "char-tfidf+svd"
    r.detail["dim"] = settings.EMBEDDING_DIM
    return r


def resolve_index(strict: bool | None = None) -> Resolved:
    strict = settings.strict_backends if strict is None else strict
    req = settings.VECTOR_INDEX
    r = _resolve("faiss-flatip" if req != "numpy-exact" else "numpy-exact",
                 "faiss-flatip", "faiss", "numpy-exact", strict)
    # IndexFlatIP is exhaustive: identical results to the numpy path, not
    # approximate. IVF/HNSW are left out deliberately — at this corpus size
    # they buy nothing and add tuning risk. The factory in index.py is where
    # they would slot in.
    r.detail["exact"] = True
    return r


def resolve_fuzzy(strict: bool | None = None) -> Resolved:
    strict = settings.strict_backends if strict is None else strict
    r = _resolve(settings.FUZZY_BACKEND, "rapidfuzz", "rapidfuzz", "difflib", strict)
    r.detail["algorithm"] = "token_set_ratio"
    return r


@dataclass
class EngineBackends:
    embedding: Resolved
    index: Resolved
    fuzzy: Resolved

    @property
    def degraded(self) -> bool:
        return any(r.degraded for r in (self.embedding, self.index, self.fuzzy))

    def as_dict(self) -> dict:
        return {
            "embedding": self.embedding.as_dict(),
            "index": self.index.as_dict(),
            "fuzzy": self.fuzzy.as_dict(),
            "degraded": self.degraded,
            "strict": settings.strict_backends,
        }

    def attribution(self) -> str:
        """One line naming exactly what produced a result. Goes into RESULTS.md."""
        tag = " [DEGRADED FALLBACK — NOT THE PRODUCTION STACK]" if self.degraded else ""
        return (f"encoder={self.embedding.name}"
                f"({self.embedding.detail.get('model')}) "
                f"index={self.index.name} fuzzy={self.fuzzy.name}{tag}")


def resolve_all(strict: bool | None = None) -> EngineBackends:
    return EngineBackends(
        embedding=resolve_embedding(strict),
        index=resolve_index(strict),
        fuzzy=resolve_fuzzy(strict),
    )

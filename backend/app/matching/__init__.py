"""The TULYA matching engine.

Pipeline order is unchanged from the prototype, because the order is the
argument: blocking happens before deep comparison so the comparison count stays
bounded, and the veto happens AFTER retrieval so a specification conflict
overrules the text score rather than quietly filtering candidates early.

    normalise -> extract attributes -> block -> embed -> retrieve
      -> fuzzy -> attribute compare -> fuse -> veto -> decide -> classify

Attribute extraction has two stages: deterministic rules first, then optional
LLM top-up for keys the rules could not read (`llm_extract`). An LLM-sourced
key may veto a pair but never counts toward the coverage floor that gates
auto-suggest, so the model can block a merge and never authorise one.
"""
from .backends import BackendUnavailable, EngineBackends, resolve_all  # noqa: F401
from .normalize import normalize  # noqa: F401
from .attributes import HARD_KEYS, compare, extract  # noqa: F401
from .llm_extract import (  # noqa: F401
    LLMUnavailable, OllamaExtractor, canonicalise, extract_with_llm, merge,
    resolve_llm,
)
from .block import build_multi, category_of, keys_for, size_bucket  # noqa: F401
from .embed import Encoder  # noqa: F401
from .index import ExactIP, build_index  # noqa: F401
from .fuzzy import token_set_ratio  # noqa: F401
from .score import ScoringConfig, fuse  # noqa: F401
from .verdict import classify  # noqa: F401
from .explain import explain, render  # noqa: F401

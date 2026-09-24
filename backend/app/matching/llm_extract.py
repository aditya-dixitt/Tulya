"""LLM attribute extraction — structured parsing only, never a decision maker.

Phase 4. The rule extractor in `attributes.py` recovers specifications with
regular expressions. It is fast, deterministic and auditable, and it fails in a
predictable way: an unfamiliar phrasing parses to nothing, which shows up as low
coverage and pushes the pair to a steward. That is a safe failure.

What it cannot do is read "twelve mil hex hd bolt, half a metre, 316 grade".
An LLM can. So the LLM is used for exactly one job — turning prose the rules
could not parse into the same structured vocabulary the rules produce — under
three constraints that keep it outside the decision path:

1. **Rules win.** A key the rule extractor recovered is never overwritten. The
   model is only ever asked about keys that came back UNKNOWN, and a proposal
   for a key that is already known is discarded rather than compared.

2. **In-vocabulary or rejected.** Every proposed value is canonicalised and
   validated against the same patterns and enums `attributes.py` uses, from the
   same module-level tables. "12mm", "M 12" and "twelve" all become "M12" or
   they are dropped. A value the rule extractor could never have produced does
   not enter the system, so downstream comparison cannot meet a shape it has no
   opinion about.

3. **It may block a merge; it may never authorise one.** This is the important
   one. An LLM-sourced hard key participates in the veto — if the model reads
   M16 on one side and the rules read M12 on the other, that pair is rejected,
   because a hallucination in that direction costs a review and a real conflict
   caught there costs nothing. But an LLM-sourced key does NOT count toward the
   coverage floor that gates auto-suggest. A hallucinated agreement therefore
   cannot manufacture the evidence that would let two records merge without a
   human. Wrong in the safe direction is a nuisance; wrong in the unsafe
   direction is the whole failure mode this project exists to prevent.

Availability follows the same rule as the matching backends: in strict mode a
configured-but-unreachable Ollama raises rather than silently disabling itself,
because "extraction quietly stopped running" is exactly the kind of degradation
that makes a later number unattributable.

    make -C backend check-llm
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from ..config import settings
from .attributes import HARD_KEYS, MATERIALS, _num

try:  # httpx is a hard dependency in requirements.txt; keep the import honest
    import httpx
except Exception:  # pragma: no cover - only in a broken install
    httpx = None  # type: ignore[assignment]


class LLMUnavailable(RuntimeError):
    """Raised in strict mode when extraction is enabled but Ollama cannot be used."""


# ---------------------------------------------------------------------------
# Vocabulary — derived from attributes.py so the two cannot drift apart
# ---------------------------------------------------------------------------
_MATERIAL_CODES = {code for _, code in MATERIALS}
_SEAL_TYPES = {"2RS", "ZZ", "OPEN"}

_THREAD_RE = re.compile(r"^M\d{1,2}$")
_SCHEDULE_RE = re.compile(r"^(\d+|XS)$")
_NUMERIC_RE = re.compile(r"^\d+(\.\d+)?$")

# Everything in HARD_KEYS that is a plain magnitude.
_NUMERIC_KEYS = {
    "length_mm", "bore_in", "pressure_class", "cores", "csa_sqmm", "voltage_kv",
    "power_kw", "rpm", "id_mm", "section_mm", "cap_m3hr", "head_m", "dim_mm",
    "bearing_desig",
}

# What the model is allowed to be asked about, and how to describe each one.
KEY_HINTS: dict[str, str] = {
    "thread":         'metric thread, format "M12"',
    "length_mm":      "length in millimetres, number only",
    "bore_in":        "nominal bore in inches, number only",
    "pressure_class": "ANSI/ASME pressure class, number only, e.g. 150",
    "material_grade": "one of: " + ", ".join(sorted(_MATERIAL_CODES)),
    "bearing_desig":  "bearing designation digits, e.g. 6205",
    "seal_type":      "one of: 2RS, ZZ, OPEN",
    "schedule":       'pipe schedule, number or "XS"',
    "cores":          "number of cores",
    "csa_sqmm":       "conductor cross-section in sq mm, number only",
    "voltage_kv":     "voltage rating in kV, number only",
    "power_kw":       "rated power in kW, number only",
    "rpm":            "rated speed in rpm, number only",
    "id_mm":          "inside diameter in millimetres, number only",
    "section_mm":     "section thickness in millimetres, number only",
    "cap_m3hr":       "capacity in cubic metres per hour, number only",
    "head_m":         "head in metres, number only",
    "dim_mm":         "principal dimension in millimetres, number only",
}

_PROMPT = """You extract engineering specifications from a material description.

Description:
{description}

Return a JSON object with EXACTLY these keys:
{keys}

Rules:
- Use null for anything the description does not state. Do not guess.
- Do not infer a value from a typical product; only report what is written.
- Values must follow the stated format exactly.
- Output JSON only, no prose.
"""


def canonicalise(key: str, value) -> str | None:
    """Put a proposed value into the exact form the rule extractor produces.

    Returns None when the value cannot be expressed in that vocabulary, which is
    treated as "the model did not answer" rather than as an error.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"null", "none", "n/a", "unknown", "-"}:
        return None

    if key == "thread":
        m = re.fullmatch(r"[Mm]?\s*(\d{1,2})(?:\s*mm)?", s)
        if not m:
            return None
        out = "M" + _num(m.group(1))
        return out if _THREAD_RE.fullmatch(out) else None

    if key == "material_grade":
        out = s.upper().replace(" ", "")
        return out if out in _MATERIAL_CODES else None

    if key == "seal_type":
        out = s.upper().replace("-", "").replace(" ", "")
        return out if out in _SEAL_TYPES else None

    if key == "schedule":
        out = s.upper().replace("SCH", "").strip()
        return out if _SCHEDULE_RE.fullmatch(out) else None

    if key in _NUMERIC_KEYS:
        s = re.sub(r"[^\d./]", "", s)
        if not s:
            return None
        out = _num(s)
        return out if _NUMERIC_RE.fullmatch(out) else None

    return None  # unknown key — refuse rather than pass it through


@dataclass
class Proposal:
    key: str
    value: str
    confidence: float
    raw: str

    def as_dict(self) -> dict:
        return {"key": self.key, "value": self.value, "source": "LLM",
                "confidence": self.confidence, "raw": self.raw}


@dataclass
class LLMResolution:
    """Mirrors matching.backends.Resolved so /api/health can report both alike."""

    enabled: bool
    model: str
    reachable: bool = False
    degraded: bool = False
    reason: str | None = None
    detail: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"enabled": self.enabled, "model": self.model,
                "reachable": self.reachable, "degraded": self.degraded,
                "reason": self.reason, **self.detail}


class OllamaExtractor:
    """Thin Ollama client. `client` is injectable so tests never touch a network."""

    def __init__(self, client=None, *, base_url: str | None = None,
                 model: str | None = None, timeout: float | None = None):
        self.base_url = (base_url or settings.OLLAMA_BASE_URL).rstrip("/")
        self.model = model or settings.OLLAMA_MODEL
        self.timeout = timeout if timeout is not None else settings.OLLAMA_TIMEOUT_SECONDS
        self._client = client

    # -- plumbing ---------------------------------------------------------
    @property
    def client(self):
        if self._client is None:
            if httpx is None:  # pragma: no cover
                raise LLMUnavailable("httpx is not installed; cannot reach Ollama")
            self._client = httpx.Client(base_url=self.base_url, timeout=self.timeout)
        return self._client

    def probe(self) -> LLMResolution:
        """Is extraction both configured and usable right now?"""
        res = LLMResolution(enabled=settings.OLLAMA_ENABLED, model=self.model)
        if not settings.OLLAMA_ENABLED:
            res.reason = "OLLAMA_ENABLED is false — extraction runs on rules only"
            return res
        try:
            r = self.client.get("/api/tags")
            r.raise_for_status()
            names = {m.get("name", "") for m in r.json().get("models", [])}
            res.reachable = True
            res.detail["models_present"] = sorted(names)
            if self.model not in names and not any(
                n.split(":")[0] == self.model.split(":")[0] for n in names
            ):
                res.degraded = True
                res.reason = (f"{self.model!r} is not pulled on this Ollama instance "
                              f"(has: {', '.join(sorted(names)) or 'nothing'})")
        except Exception as exc:
            res.degraded = True
            res.reason = f"{type(exc).__name__}: {exc}"[:200]
        return res

    # -- extraction -------------------------------------------------------
    def propose(self, normalised_text: str, missing_keys) -> list[Proposal]:
        """Ask only about keys the rules could not recover. Never about the rest."""
        keys = [k for k in missing_keys if k in KEY_HINTS]
        if not keys or not normalised_text.strip():
            return []

        prompt = _PROMPT.format(
            description=normalised_text,
            keys="\n".join(f'  "{k}": {KEY_HINTS[k]}' for k in keys),
        )
        body = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {"temperature": 0, "num_ctx": settings.OLLAMA_NUM_CTX},
        }
        r = self.client.post("/api/generate", json=body)
        r.raise_for_status()
        raw = r.json().get("response", "")
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return []                       # unparseable output is simply no answer
        if not isinstance(parsed, dict):
            return []

        out: list[Proposal] = []
        for k in keys:
            v = canonicalise(k, parsed.get(k))
            if v is None:
                continue
            out.append(Proposal(key=k, value=v, confidence=_confidence(k),
                                raw=str(parsed.get(k))))
        return out


def _confidence(key: str) -> float:
    """Enumerated keys are safer than free magnitudes — a wrong enum is usually
    rejected by canonicalisation, a wrong number is not."""
    return 0.75 if key in {"material_grade", "seal_type", "thread", "schedule"} else 0.60


def resolve_llm(strict: bool | None = None, extractor: OllamaExtractor | None = None
                ) -> LLMResolution:
    """Strict mode refuses to start rather than silently running rules-only."""
    strict = settings.strict_backends if strict is None else strict
    res = (extractor or OllamaExtractor()).probe()
    if strict and res.enabled and (res.degraded or not res.reachable):
        raise LLMUnavailable(
            f"LLM extraction is enabled but unusable ({res.reason}). "
            f"MATCHING_STRICT is on, so TULYA will not start rather than run "
            f"rules-only while configured for {res.model!r}. Start Ollama and "
            f"pull the model, or set OLLAMA_ENABLED=false explicitly."
        )
    return res


# ---------------------------------------------------------------------------
# Merge
# ---------------------------------------------------------------------------
def merge(rule_attrs: dict, proposals, *, min_confidence: float = 0.5
          ) -> tuple[dict, dict, set[str]]:
    """Combine rule and LLM attributes.

    Returns (attrs, provenance, provisional_keys) where

        attrs             the merged specification dict, same shape `extract()` returns
        provenance        key -> 'RULE' | 'LLM', for material_attributes.source
        provisional_keys  the LLM-sourced subset — these veto but do not count
                          toward the coverage floor (see the module docstring)

    A proposal for a key the rules already recovered is dropped, not compared.
    The rules are the auditable path; letting a model overrule them would mean
    the veto rests on something nobody can reproduce from the text.
    """
    attrs = dict(rule_attrs)
    provenance = {k: "RULE" for k in attrs}
    provisional: set[str] = set()

    for p in proposals:
        if p.key in attrs:
            continue
        if p.confidence < min_confidence:
            continue
        attrs[p.key] = p.value
        provenance[p.key] = "LLM"
        if p.key in HARD_KEYS:
            provisional.add(p.key)

    return attrs, provenance, provisional


def extract_with_llm(normalised_text: str, rule_attrs: dict,
                     extractor: OllamaExtractor | None = None,
                     ) -> tuple[dict, dict, set[str]]:
    """Rule attributes, topped up by the model only where the rules found nothing.

    Never raises on a model failure: extraction is an enhancement, and a pair
    that falls back to rules-only is merely held for review. Whether the model
    *should* have been reachable is `resolve_llm`'s job, at startup.
    """
    if not settings.OLLAMA_ENABLED:
        return dict(rule_attrs), {k: "RULE" for k in rule_attrs}, set()

    missing = [k for k in KEY_HINTS if k not in rule_attrs]
    try:
        proposals = (extractor or OllamaExtractor()).propose(normalised_text, missing)
    except Exception:
        proposals = []
    return merge(rule_attrs, proposals)

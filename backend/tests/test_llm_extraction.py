"""Phase 4: LLM attribute extraction.

These tests never reach a network. Ollama is replaced with an httpx
MockTransport, which is the point — the guarantees below are properties of the
merge and scoring rules, not of any particular model's output, and they must
hold on a laptop with nothing running on port 11434.

The guarantee that matters most is the last pair: an LLM-read specification can
block a merge and can never authorise one.
"""
from __future__ import annotations

import json

import httpx
import pytest

from app.config import settings
from app.matching import extract, fuse, normalize
from app.matching.llm_extract import (
    LLMUnavailable, OllamaExtractor, Proposal, canonicalise, extract_with_llm,
    merge, resolve_llm,
)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def _ollama(payload: dict | str, *, tags=("llama3.2:3b",), fail=False):
    """An OllamaExtractor wired to a fake server that answers `payload`."""
    def handler(request: httpx.Request) -> httpx.Response:
        if fail:
            raise httpx.ConnectError("connection refused", request=request)
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": [{"name": t} for t in tags]})
        body = payload if isinstance(payload, str) else json.dumps(payload)
        return httpx.Response(200, json={"response": body})

    client = httpx.Client(transport=httpx.MockTransport(handler),
                          base_url="http://ollama.test")
    return OllamaExtractor(client=client)


@pytest.fixture
def llm_on():
    original = settings.OLLAMA_ENABLED
    object.__setattr__(settings, "OLLAMA_ENABLED", True)
    yield
    object.__setattr__(settings, "OLLAMA_ENABLED", original)


# --------------------------------------------------------------------------
# vocabulary
# --------------------------------------------------------------------------
@pytest.mark.parametrize("key,raw,expected", [
    ("thread", "M12", "M12"),
    ("thread", "12", "M12"),
    ("thread", "12mm", "M12"),
    ("thread", "m 12", "M12"),
    ("material_grade", "ss304", "SS304"),
    ("material_grade", "SS 316", "SS316"),
    ("seal_type", "2-RS", "2RS"),
    ("schedule", "SCH40", "40"),
    ("schedule", "xs", "XS"),
    ("length_mm", "50 mm", "50"),
    ("bore_in", "3/4", "0.75"),
    ("pressure_class", "class 600", "600"),
])
def test_canonicalise_produces_the_rule_extractor_vocabulary(key, raw, expected):
    assert canonicalise(key, raw) == expected


@pytest.mark.parametrize("key,raw", [
    ("thread", "large"),
    ("thread", "M123"),                 # no such metric thread
    ("material_grade", "unobtainium"),  # not in the MATERIALS table
    ("seal_type", "rubber"),
    ("schedule", "heavy"),
    ("length_mm", "quite long"),
    ("not_a_key", "12"),
    ("thread", None),
    ("thread", "unknown"),
])
def test_canonicalise_rejects_anything_out_of_vocabulary(key, raw):
    assert canonicalise(key, raw) is None


def test_canonicalised_values_match_what_the_rules_would_have_produced():
    """The two extractors must speak the same language or comparison is nonsense."""
    rule = extract(normalize("BOLT HEX M12 X 50 SS304"))
    assert canonicalise("thread", "12 mm") == rule["thread"]
    assert canonicalise("material_grade", "stainless steel 304".upper().replace(" ", "")
                        ) is None  # prose is not a grade code
    assert canonicalise("material_grade", "SS304") == rule["material_grade"]


# --------------------------------------------------------------------------
# the client
# --------------------------------------------------------------------------
def test_propose_only_asks_about_keys_the_rules_missed(llm_on):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["prompt"] = json.loads(request.content)["prompt"]
        return httpx.Response(200, json={"response": json.dumps({"material_grade": "SS304"})})

    ex = OllamaExtractor(client=httpx.Client(transport=httpx.MockTransport(handler),
                                             base_url="http://ollama.test"))
    ex.propose("hex bolt m12 x 50", ["material_grade", "seal_type"])
    assert "material_grade" in seen["prompt"]
    assert "thread" not in seen["prompt"]        # the rules already read it


def test_nulls_are_dropped_not_guessed(llm_on):
    ex = _ollama({"material_grade": None, "seal_type": "2RS"})
    got = {p.key: p.value for p in ex.propose("some pump", ["material_grade", "seal_type"])}
    assert got == {"seal_type": "2RS"}


def test_unparseable_model_output_is_simply_no_answer(llm_on):
    assert _ollama("this is not json").propose("x", ["thread"]) == []


def test_out_of_vocabulary_proposals_never_enter_the_system(llm_on):
    ex = _ollama({"thread": "roughly M12ish", "material_grade": "shiny metal"})
    assert ex.propose("x", ["thread", "material_grade"]) == []


# --------------------------------------------------------------------------
# merge policy
# --------------------------------------------------------------------------
def test_rules_win_the_model_never_overrides_them():
    rule = extract(normalize("BOLT HEX M12 X 50 SS304"))
    attrs, prov, provisional = merge(rule, [Proposal("thread", "M16", 0.9, "M16")])
    assert attrs["thread"] == "M12"          # the model's M16 is discarded
    assert prov["thread"] == "RULE"
    assert "thread" not in provisional


def test_the_model_fills_only_gaps_and_is_labelled():
    rule = extract(normalize("BOLT HEX M12 X 50"))
    assert "material_grade" not in rule
    attrs, prov, provisional = merge(rule, [Proposal("material_grade", "SS304", 0.75, "ss304")])
    assert attrs["material_grade"] == "SS304"
    assert prov["material_grade"] == "LLM"
    assert prov["thread"] == "RULE"
    assert provisional == {"material_grade"}


def test_low_confidence_proposals_are_dropped():
    attrs, _, _ = merge({}, [Proposal("thread", "M12", 0.2, "12")], min_confidence=0.5)
    assert attrs == {}


def test_extraction_is_a_no_op_when_disabled():
    rule = extract(normalize("BOLT HEX M12 X 50"))
    attrs, prov, provisional = extract_with_llm("bolt hex m12 x 50", rule,
                                                extractor=_ollama({"material_grade": "SS304"}))
    assert attrs == rule and provisional == set()
    assert set(prov.values()) == {"RULE"}


def test_a_model_failure_degrades_to_rules_not_to_an_error(llm_on):
    rule = extract(normalize("BOLT HEX M12 X 50"))
    attrs, _, provisional = extract_with_llm("bolt hex m12 x 50", rule,
                                             extractor=_ollama({}, fail=True))
    assert attrs == rule and provisional == set()


# --------------------------------------------------------------------------
# the asymmetry — this is the guarantee
# --------------------------------------------------------------------------
def test_an_llm_read_spec_can_block_a_merge():
    """Model reads M16 where the rules read M12 on the other side: reject.

    Everything else about this pair agrees, so without the veto it clears
    auto-suggest outright — which is exactly why the model is allowed to veto.
    """
    a = {"thread": "M12", "length_mm": "50", "material_grade": "SS304", "bore_in": "2"}
    b = {"thread": "M16", "length_mm": "50", "material_grade": "SS304", "bore_in": "2"}
    r = fuse(0.97, 0.97, a, b, provisional={"thread"})
    assert r["vetoed"] is True
    assert r["score"] == 0.0
    assert "thread" in r["conflicts"]
    assert "LLM-read" in r["reason"]
    assert r["score_noveto"] > 0.92          # the veto is doing real work


def test_an_llm_read_spec_can_never_authorise_one():
    """The same agreement counts for a rule read and not for a model read."""
    a = {"thread": "M12", "material_grade": "SS304"}
    b = {"thread": "M12", "material_grade": "SS304"}

    rules_only = fuse(0.99, 0.99, a, b)
    assert rules_only["decision"] == "AUTO_SUGGEST"
    assert rules_only["capped"] is False

    model_read = fuse(0.99, 0.99, a, b, provisional={"material_grade"})
    assert model_read["score"] == rules_only["score"]      # same score
    assert model_read["coverage"] == 2
    assert model_read["coverage_verified"] == 1            # only one is reproducible
    assert model_read["decision"] == "REVIEW"              # held for a human
    assert model_read["capped"] is True
    assert "cannot authorise a merge" in model_read["reason"]


def test_a_pair_resting_entirely_on_the_model_is_always_reviewed():
    a = {"thread": "M12", "material_grade": "SS304"}
    b = {"thread": "M12", "material_grade": "SS304"}
    r = fuse(0.99, 0.99, a, b, provisional={"thread", "material_grade"})
    assert r["coverage_verified"] == 0
    assert r["decision"] == "REVIEW" and r["capped"] is True


# --------------------------------------------------------------------------
# availability
# --------------------------------------------------------------------------
def test_probe_reports_disabled_without_touching_the_network():
    res = OllamaExtractor(client=None).probe()
    assert res.enabled is False and res.reachable is False


def test_probe_notices_a_model_that_was_never_pulled(llm_on):
    res = _ollama({}, tags=("mistral:7b",)).probe()
    assert res.reachable is True and res.degraded is True
    assert "not pulled" in res.reason


def test_strict_mode_refuses_to_run_rules_only_while_claiming_an_llm(llm_on):
    with pytest.raises(LLMUnavailable) as exc:
        resolve_llm(strict=True, extractor=_ollama({}, fail=True))
    assert "will not start" in str(exc.value)


def test_permissive_mode_records_the_degradation_instead_of_hiding_it(llm_on):
    res = resolve_llm(strict=False, extractor=_ollama({}, fail=True))
    assert res.degraded is True and res.reason
    assert res.as_dict()["enabled"] is True

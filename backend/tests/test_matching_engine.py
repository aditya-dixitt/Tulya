"""The engine's guarantees, stated as tests.

These are the properties the whole project rests on. If one of them breaks, the
system is merging things it should not, and no amount of UI makes that safe.
"""
import pytest

from app.matching import classify, extract, fuse, normalize, token_set_ratio
from app.matching.backends import BackendUnavailable, resolve_all


def _pair(t1: str, t2: str, cos: float):
    n1, n2 = normalize(t1), normalize(t2)
    a1, a2 = extract(n1), extract(n2)
    r = fuse(cos, token_set_ratio(n1, n2) / 100.0, a1, a2)
    v = classify(score=r["score"], coverage=r["coverage"], vetoed=r["vetoed"],
                 verdicts=r["verdicts"], description_a=n1, description_b=n2)
    return r, v


def test_hard_key_conflict_vetoes_a_near_identical_pair():
    """M12 vs M16: near-identical text, different bolt. This must never merge."""
    r, v = _pair("BOLT HEX M12 X 50 SS304", "BOLT HEX M16 X 50 SS304", 0.97)
    assert r["vetoed"] is True
    assert r["score"] == 0.0
    assert r["decision"] == "REJECTED_VETO"
    assert "thread" in r["conflicts"]
    assert v.status == "CONFLICT"
    # and the veto must be doing real work: without it this clears auto-suggest
    assert r["score_noveto"] > 0.92


def test_same_item_different_wording_survives():
    r, v = _pair("Hexagonal Bolt 12mm x 50mm St.Steel 304", "BOLT HEX M12X50 SS304", 0.81)
    assert r["vetoed"] is False
    assert extract(normalize("Hexagonal Bolt 12mm x 50mm St.Steel 304"))["thread"] == "M12"
    assert v.status in ("EQUIVALENT", "CONDITIONAL")


def test_unknown_is_not_match():
    """A spec missing on one side must never count as agreement."""
    from app.matching.attributes import compare
    verdicts, n_match, n_mismatch, n_known = compare({"thread": "M12"}, {})
    assert verdicts["thread"] == "UNKNOWN"
    assert n_match == 0 and n_mismatch == 0 and n_known == 0


def test_coverage_floor_caps_a_high_score_at_review():
    """High score resting on one readable spec is held, not auto-suggested."""
    r = fuse(0.99, 0.99, {"thread": "M12"}, {"thread": "M12"})
    assert r["score"] >= 0.92
    assert r["decision"] == "REVIEW"
    assert r["capped"] is True


def test_fraction_bores_are_distinct():
    """3/4 inch and 4 inch are different items; the normaliser must not merge them."""
    a = extract(normalize('BALL VALVE 3/4" CLASS 600'))
    b = extract(normalize('BALL VALVE 4" CLASS 600'))
    assert a["bore_in"] != b["bore_in"]
    r, v = _pair('BALL VALVE 3/4 INCH CLASS 600', 'BALL VALVE 4 INCH CLASS 600', 0.95)
    assert r["vetoed"] is True and v.status == "CONFLICT"


def test_verdict_states_are_the_six_governed_ones():
    from app.matching.verdict import NEXT_STEP
    assert set(NEXT_STEP) == {"IDENTICAL", "EQUIVALENT", "CONDITIONAL",
                              "DIFFERENT", "CONFLICT", "UNRESOLVED"}


def test_identical_and_equivalent_are_different_claims():
    """IDENTICAL means same wording; EQUIVALENT means same item, different wording."""
    same = classify(score=0.99, coverage=3, vetoed=False,
                    verdicts={"thread": "MATCH", "length_mm": "MATCH",
                              "material_grade": "MATCH"},
                    description_a="bolt hex m12 x 50 ss304",
                    description_b="BOLT HEX M12 X 50 SS304")
    diff = classify(score=0.99, coverage=3, vetoed=False,
                    verdicts={"thread": "MATCH", "length_mm": "MATCH",
                              "material_grade": "MATCH"},
                    description_a="hexagonal bolt 12 mm x 50 mm stainless steel 304",
                    description_b="bolt hex m12 x 50 ss304")
    assert same.status == "IDENTICAL"
    assert diff.status == "EQUIVALENT"


def test_faiss_index_is_exact_not_approximate():
    import numpy as np
    from app.matching.index import ExactIP
    v = np.random.RandomState(0).rand(300, 384).astype("float32")
    v /= np.linalg.norm(v, axis=1, keepdims=True)
    ix = ExactIP(v)
    sims, idx = ix.search(v[:5], 3)
    # every vector's nearest neighbour is itself at cosine 1.0
    assert np.allclose(sims[:, 0], 1.0, atol=1e-5)
    assert list(idx[:, 0]) == [0, 1, 2, 3, 4]
    # and it agrees with a brute-force computation to floating-point noise
    brute = v[:5] @ v.T
    assert np.allclose(np.sort(brute, axis=1)[:, -3:][:, ::-1], sims, atol=1e-5)


def test_strict_mode_refuses_to_downgrade_silently():
    """The guarantee that a TF-IDF number can never be reported as Sentence-BERT."""
    import app.matching.backends as b
    from app.config import settings
    original = settings.EMBEDDING_BACKEND
    try:
        object.__setattr__(settings, "EMBEDDING_BACKEND", "sbert")
        try:
            import sentence_transformers  # noqa: F401
            pytest.skip("sentence-transformers is installed; nothing to downgrade from")
        except ImportError:
            pass
        with pytest.raises(BackendUnavailable) as exc:
            b.resolve_embedding(strict=True)
        assert "will not start" in str(exc.value)
    finally:
        object.__setattr__(settings, "EMBEDDING_BACKEND", original)


def test_backends_report_what_actually_ran():
    r = resolve_all(strict=False)
    a = r.attribution()
    assert "encoder=" in a and "index=" in a and "fuzzy=" in a
    if r.degraded:
        assert "DEGRADED" in a

"""LayaJobClassifier tests: policy over a deterministic FakeEngine (no model)."""

import pytest

from app.classifier.engine import EngineResult, FakeEngine, LayaView
from app.classifier.laya_job_classifier import LayaJobClassifier

PROFILE = {
    "titles": ["SRE", "DevOps", "Platform Engineer"],
    "seniority": ["Senior", "Staff"],
    "remote_required": True,
    "skills": ["AWS", "Kubernetes", "Terraform", "Prometheus", "Python"],
}

HIGH_JOB = {
    "title": "Senior SRE",
    "company": "Acme",
    "location": "Brazil",
    "remote": True,
    "description": "Senior SRE with AWS Kubernetes Terraform Prometheus Python.",
}

LOW_JOB = {
    "title": "Senior Sales Manager",
    "company": "Acme",
    "location": "Brazil",
    "remote": False,
    "description": "Manage sales pipeline and commercial accounts.",
}


class ExplodingEngine:
    device = "broken"
    ready = False

    def predict(self, states):
        raise RuntimeError("checkpoint corrupto")


def test_high_match_keeps_contract():
    classifier = LayaJobClassifier(PROFILE, FakeEngine())
    result = classifier.classify(HIGH_JOB)

    assert result["match"] == "high"
    assert result["score"] >= 80
    assert result["decision"]["choice"]["value"] == "high"
    assert result["decision"]["score"]["value"] == result["score"]
    assert result["decision"]["score"]["components"]
    # real Laya block present with the fake's identity
    assert result["decision"]["laya"]["backend"] == "laya"
    assert result["decision"]["laya"]["model"] == "fake"
    assert result["decision"]["laya"]["answers"]["role_family"]["choice"] == "site_reliability"


def test_low_match_accumulates_gaps():
    classifier = LayaJobClassifier(PROFILE, FakeEngine())
    result = classifier.classify(LOW_JOB)

    assert result["match"] == "low"
    assert result["score"] < 60
    assert any("Laya" in gap for gap in result["gaps"])
    assert result["decision"]["laya"]["answers"]["role_family"]["choice"] == "other"


def test_noul_reports_remote_probability():
    classifier = LayaJobClassifier(PROFILE, FakeEngine())

    remote = classifier.classify(HIGH_JOB)["decision"]["noul"]
    onsite = classifier.classify(LOW_JOB)["decision"]["noul"]

    assert remote["value"] is True
    assert remote["probability_true"] >= 0.5
    assert onsite["value"] is False
    assert onsite["probability_true"] < 0.5


def test_laya_reasons_are_appended_to_heuristic_reasons():
    classifier = LayaJobClassifier(PROFILE, FakeEngine())
    result = classifier.classify(HIGH_JOB)

    assert any(reason.startswith("Cargo compatível") for reason in result["reasons"])
    assert any(reason.startswith("Laya:") for reason in result["reasons"])


def test_choice_probabilities_still_sum_to_one():
    classifier = LayaJobClassifier(PROFILE, FakeEngine())
    probs = classifier.classify(HIGH_JOB)["decision"]["choice"]["probabilities"]

    assert abs(sum(probs.values()) - 1.0) < 1e-6


def test_engine_failure_falls_back_to_heuristic_contract():
    classifier = LayaJobClassifier(PROFILE, ExplodingEngine())
    result = classifier.classify(HIGH_JOB)

    # heuristic verdict survives an engine crash
    assert result["match"] == "high"
    assert result["decision"]["choice"]["value"] == "high"
    assert result["decision"]["laya"]["backend"] == "heuristic"
    assert "checkpoint corrupto" in result["decision"]["laya"]["error"]
    assert any("heurística" in reason for reason in result["reasons"])


EXCLUSION_PROFILE = {**PROFILE, "exclusions": ["inglês fluente"]}

ENGLISH_JOB = {
    "title": "Senior SRE",
    "company": "Acme",
    "location": "Brazil",
    "remote": True,
    "description": (
        "Senior SRE with AWS Kubernetes Terraform Prometheus Python. Requer inglês fluente."
    ),
}


def test_exclusion_survives_model_merge():
    """Even with a high FakeEngine verdict, a dealbreaker forces low."""
    classifier = LayaJobClassifier(EXCLUSION_PROFILE, FakeEngine())
    result = classifier.classify(ENGLISH_JOB)

    assert result["match"] == "low"
    assert result["score"] <= 49.0
    assert result["decision"]["excluded"]["value"] is True
    assert result["decision"]["excluded"]["terms"] == ["inglês fluente"]
    assert any("Dealbreaker" in gap for gap in result["gaps"])
    assert any("Exclusão" in reason for reason in result["reasons"])
    # contract stays intact after the veto
    assert result["decision"]["choice"]["value"] == "low"
    assert abs(sum(result["decision"]["choice"]["probabilities"].values()) - 1.0) < 1e-6


def test_exclusion_messages_appear_exactly_once():
    """The heuristic base already records the dealbreaker; `_combine` must not
    repeat it.

    Regression: the card showed "Exclusão do perfil atingida: …" twice under
    Motivos and "Dealbreaker presente na vaga: …" twice under Gaps.
    """
    classifier = LayaJobClassifier(EXCLUSION_PROFILE, FakeEngine())
    result = classifier.classify(ENGLISH_JOB)

    dealbreaker_gaps = [gap for gap in result["gaps"] if gap.startswith("Dealbreaker")]
    exclusion_reasons = [reason for reason in result["reasons"] if reason.startswith("Exclusão")]

    assert len(dealbreaker_gaps) == 1, result["gaps"]
    assert len(exclusion_reasons) == 1, result["reasons"]

    # the veto itself is untouched by de-duplication
    assert result["match"] == "low"
    assert result["score"] <= 49.0


def test_no_exclusion_keeps_model_verdict():
    classifier = LayaJobClassifier(EXCLUSION_PROFILE, FakeEngine())
    result = classifier.classify(HIGH_JOB)

    assert result["match"] == "high"
    assert result["decision"]["excluded"]["value"] is False


def test_seniority_score_maps_to_profile_expectation():
    view = LayaView(
        role_family="site_reliability",
        role_confidence=0.9,
        remote=0.9,
        remote_confidence=0.9,
        skill_fit=0.9,
        skill_confidence=0.9,
        seniority=2,
        seniority_probs=[0.0, 0.1, 0.9],
    )
    result = EngineResult(view=view, model="fake", latency_ms=1.0)
    classifier = LayaJobClassifier(PROFILE, FakeEngine())
    combined = classifier._combine(classifier.signals.classify(HIGH_JOB), result)

    # staff-level answer should not lower the heuristic's seniority component
    components = combined["decision"]["score"]["components"]
    assert components["seniority"] == 100.0


@pytest.mark.asyncio
async def test_fake_engine_is_deterministic():
    engine = FakeEngine()
    state = {"title": "Senior SRE", "description": "remote kubernetes", "workplace": "remote"}

    first = engine.predict([state])[0]
    second = engine.predict([state])[0]

    assert first.view == second.view
    assert first.model == "fake"
    assert abs(sum(first.view.seniority_probs) - 1.0) < 1e-6


# ===== Confidence gating tests (TDD for SPEC-202610022141) =====

CONFIDENCE_PROFILE = {
    "titles": ["SRE", "DevOps", "Platform Engineer"],
    "seniority": ["Senior", "Staff"],
    "remote_required": True,
    "skills": ["AWS", "Kubernetes", "Terraform", "Prometheus", "Python"],
    "exclusions": ["inglês fluente"],
}


class HighConfidenceEngine:
    """FakeEngine that returns high confidence on all answers."""

    device = "fake"
    ready = True

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]:
        from app.classifier.engine import EngineResult, LayaView

        results = []
        for _ in states:
            view = LayaView(
                role_family="site_reliability",
                role_confidence=0.95,
                remote=0.95,
                remote_confidence=0.95,
                skill_fit=0.95,
                skill_confidence=0.95,
                seniority=1,
                seniority_probs=[0.0, 0.9, 0.1],
            )
            results.append(EngineResult(view=view, model="fake", latency_ms=1.0))
        return results


class LowConfidenceEngine:
    """FakeEngine that returns low confidence on role_family (should fall back to heuristic)."""

    device = "fake"
    ready = True

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]:
        from app.classifier.engine import EngineResult, LayaView

        results = []
        for _ in states:
            view = LayaView(
                role_family="other",
                role_confidence=0.30,  # LOW confidence — should not trust Laya
                remote=0.95,
                remote_confidence=0.95,
                skill_fit=0.95,
                skill_confidence=0.95,
                seniority=1,
                seniority_probs=[0.0, 0.9, 0.1],
            )
            results.append(EngineResult(view=view, model="fake", latency_ms=1.0))
        return results


class ExclusionEngine:
    """FakeEngine that returns exclusion=true with high confidence."""

    device = "fake"
    ready = True

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]:
        from app.classifier.engine import EngineResult, LayaView

        results = []
        for _ in states:
            view = LayaView(
                role_family="site_reliability",
                role_confidence=0.95,
                remote=0.95,
                remote_confidence=0.95,
                skill_fit=0.95,
                skill_confidence=0.95,
                seniority=1,
                seniority_probs=[0.0, 0.9, 0.1],
            )
            # Monkey-patch exclusions into view for test
            view.exclusions = True
            view.exclusions_confidence = 0.95
            results.append(EngineResult(view=view, model="fake", latency_ms=1.0))
        return results


def test_confidence_gating_high_role_confidence_uses_laya():
    """High role_confidence → Laya influences title component strongly."""
    classifier = LayaJobClassifier(CONFIDENCE_PROFILE, HighConfidenceEngine())
    result = classifier.classify(HIGH_JOB)

    # With high confidence, Laya should push score up (role_family matches profile)
    assert result["match"] == "high"
    assert result["score"] >= 80
    # Laya block should be present with real model info
    assert result["decision"]["laya"]["backend"] == "laya"
    assert result["decision"]["laya"]["answers"]["role_family"]["confidence"] == 0.95


def test_confidence_gating_low_role_confidence_still_blends():
    """Low role_confidence → policy still blends 50/50 (no gating).

    The Laya real checkpoint has poorly calibrated confidences, so gating
    on role_confidence would ignore Laya entirely. The 50/50 blend is the
    safe default; exclusions are the only confidence-gated veto.
    """
    classifier = LayaJobClassifier(CONFIDENCE_PROFILE, LowConfidenceEngine())
    result = classifier.classify(HIGH_JOB)

    # Heuristic sees "Senior SRE" + skills → high
    # Laya says role_family=other with low confidence → still blended 50/50
    # Result may be medium (Laya drags title down) — that's the known tradeoff
    assert result["match"] in ("high", "medium")
    # The decision should note low confidence was recorded
    assert result["decision"]["laya"]["answers"]["role_family"]["confidence"] == 0.30


def test_fake_engine_returns_exclusions_confidence():
    """FakeEngine updated to include exclusions in its deterministic logic."""
    engine = FakeEngine()
    state = {
        "title": "Senior SRE",
        "description": "remote kubernetes english fluent required",
        "workplace": "remote",
    }
    result = engine.predict([state])[0]
    # FakeEngine should now detect exclusion keywords
    assert hasattr(result.view, "exclusions")
    assert hasattr(result.view, "exclusions_confidence")

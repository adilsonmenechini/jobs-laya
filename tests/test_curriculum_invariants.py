"""Invariantes do caminho B: 1 forward pass, fallback, e o Router intacto.

CA3/CA9 e R3/R5/R6. O experimento de 202610051406 mostrou que a degradação veio
de tocar o `job_state()`. Aqui o currículo nunca entra no state, então o número de
forward passes e o contrato de fallback precisam continuar valendo com um
currículo carregado em disco.
"""

import pytest

from app.classifier.engine import FakeEngine
from app.classifier.laya_classifier import LayaInspiredClassifier
from app.classifier.laya_job_classifier import LayaJobClassifier
from app.classifier.questions import QUESTIONS, job_state

PROFILE = {
    "titles": ["SRE", "DevOps", "Platform Engineer"],
    "seniority": ["Senior", "Staff"],
    "remote_required": True,
    "skills": ["AWS", "Kubernetes", "Terraform", "Prometheus", "Python"],
    "exclusions": ["inglês fluente"],
}

MARKDOWN = "# Candidate\n\n## Skills\n- Kubernetes, Terraform, AWS, Prometheus, Python\n"

HIGH_JOB = {
    "title": "Senior SRE",
    "company": "Acme",
    "location": "Brazil",
    "remote": True,
    "description": "Senior SRE with AWS Kubernetes Terraform Prometheus Python.",
}


class CountingEngine(FakeEngine):
    """Counts real `predict` calls — the CA3 measurement, not a code reading."""

    def __init__(self):
        self.calls: list[list[dict]] = []

    def predict(self, states):
        self.calls.append(list(states))
        return super().predict(states)


@pytest.fixture()
def curriculum_file(tmp_path):
    return tmp_path / "curriculum.md"


def _classify(curriculum_path, engine):
    classifier = LayaJobClassifier(PROFILE, engine, backend="fake")
    classifier.signals = LayaInspiredClassifier(PROFILE, curriculum_path)
    return classifier.classify(HIGH_JOB)


def test_one_forward_pass_per_job_with_a_curriculum(curriculum_file):
    """CA3/R3: exactly one `predict`, carrying one state, for one job."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    engine = CountingEngine()

    _classify(curriculum_file, engine)

    assert len(engine.calls) == 1
    assert len(engine.calls[0]) == 1


def test_the_forward_pass_still_answers_the_five_typed_questions(curriculum_file):
    """R3: no sixth question was introduced alongside the curriculum."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    engine = CountingEngine()

    _classify(curriculum_file, engine)

    assert set(QUESTIONS) == {
        "role_family",
        "remote",
        "seniority",
        "skill_fit",
        "exclusions",
    }


def test_the_state_that_reaches_the_model_never_mentions_the_curriculum(curriculum_file):
    """R4: the strongest form of the guarantee — the payload is inspectable."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    engine = CountingEngine()

    _classify(curriculum_file, engine)

    state = engine.calls[0][0]
    assert set(state) == {"title", "company", "location", "workplace", "description"}
    payload = " ".join(str(value) for value in state.values()).lower()
    for leaked in ("candidate", "curriculum", "currículo", "resumo"):
        assert leaked not in payload


def test_engine_failure_falls_back_to_heuristics_with_a_curriculum(curriculum_file):
    """CA9/R6: a crashing model still yields a verdict, error recorded."""

    class ExplodingEngine:
        device = "broken"
        ready = False

        def predict(self, states):
            raise RuntimeError("checkpoint corrompido")

    curriculum_file.write_text(MARKDOWN, encoding="utf-8")

    result = _classify(curriculum_file, ExplodingEngine())

    assert result["match"] in {"high", "medium", "low"}
    assert result["decision"]["laya"]["backend"] == "heuristic"
    assert "checkpoint corrompido" in result["decision"]["laya"]["error"]
    assert any("heurística" in reason for reason in result["reasons"])


def test_fallback_keeps_the_heuristic_score_contract(curriculum_file):
    """CA9: the fallback verdict is the heuristic one, curriculum aside."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    expected = LayaInspiredClassifier(PROFILE, curriculum_file).classify(HIGH_JOB)

    class ExplodingEngine:
        device = "broken"
        ready = False

        def predict(self, states):
            raise RuntimeError("boom")

    result = _classify(curriculum_file, ExplodingEngine())

    assert result["match"] == expected["match"]
    assert result["score"] == expected["score"]


def test_dealbreaker_lowers_the_fused_score_too(curriculum_file):
    """CA8 through the policy: a favourable résumé cannot lift an excluded job."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    job = {**HIGH_JOB, "description": HIGH_JOB["description"] + " Requer inglês fluente."}
    classifier = LayaJobClassifier(PROFILE, FakeEngine(), backend="fake")
    classifier.signals = LayaInspiredClassifier(PROFILE, curriculum_file)

    result = classifier.classify(job)

    assert result["match"] == "low"
    assert result["score"] <= 49.0
    assert result["decision"]["excluded"]["value"] is True


def test_two_jobs_are_two_forward_passes_not_one_batch(curriculum_file):
    """CA3 scales per job: the count must not collapse with the curriculum."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    engine = CountingEngine()
    classifier = LayaJobClassifier(PROFILE, engine, backend="fake")
    classifier.signals = LayaInspiredClassifier(PROFILE, curriculum_file)

    classifier.classify(HIGH_JOB)
    classifier.classify(HIGH_JOB)

    assert len(engine.calls) == 2
    assert all(len(call) == 1 for call in engine.calls)


def test_job_state_is_a_pure_function_of_the_job(curriculum_file):
    """R4: no hidden global state leaks a curriculum into the Router payload."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    LayaInspiredClassifier(PROFILE, curriculum_file).classify(HIGH_JOB)

    assert job_state(HIGH_JOB) == job_state(HIGH_JOB)
    assert set(job_state(HIGH_JOB)) == {
        "title",
        "company",
        "location",
        "workplace",
        "description",
    }

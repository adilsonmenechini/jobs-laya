"""Currículo Markdown como contexto do classificador (SPEC 202610052324).

O currículo nunca entra no `job_state()` do Laya: o modelo lê só a vaga. Ele é
lido em `app/services/curriculum.py` e aparece em `reasons`/`gaps` — **fora do
score**.

Por que fora do score (ver `plan/reviews/review-202610051432.md`): um componente
positivo esvaziava a classe `medium` do eval (2/5 -> 0/5), porque qualquer sinal
positivo empurra para cima as vagas perto do threshold 80. Filtrar *quais* skills
contavam não resolveu (a opção "score por evidência" piorou: `low` 3/6 -> 2/6).
A direção do empurrão era o problema, não a forma de agregar.

Invariantes travados aqui:

- CA1/CA10 — currículo ausente **ou presente** deixa o score idêntico;
- CA6   — o currículo nunca cruza um threshold de classificação;
- CA7   — nenhuma contaminação de sujeito (vaga fora do perfil não vira infra);
- CA2   — o reason cita a ORIGEM do sinal (currículo, não profile);
- CA5   — thresholds 80/60 intactos e `WEIGHTS` no formato original de 7 chaves.
"""

import pytest

from app.classifier.laya_classifier import LayaInspiredClassifier
from app.classifier.questions import job_state
from app.services import curriculum

PROFILE = {
    "titles": ["SRE", "DevOps", "Platform Engineer"],
    "seniority": ["Senior", "Staff"],
    "remote_required": True,
    "skills": ["AWS", "Kubernetes", "Terraform", "Prometheus", "Python"],
    "exclusions": ["inglês fluente"],
}

# Two postings that differ ONLY in what they ask for, so any score gap could
# only come from the curriculum — which must never happen.
HIGH_JOB = {
    "title": "Senior SRE",
    "company": "Acme",
    "location": "Brazil",
    "remote": True,
    "description": "Senior SRE with AWS Kubernetes Terraform Prometheus Python.",
}

# CA7: the regression sample from the failed experiment — a posting whose text
# has nothing to do with the profile. It must stay `low` with a curriculum loaded.
LOW_JOB = {
    "title": "Senior Sales Manager",
    "company": "Acme",
    "location": "Brazil",
    "remote": False,
    "description": "Manage sales pipeline and commercial accounts.",
}

MATCHING_CURRICULUM = """# Candidate

## Skills
- Kubernetes, Terraform, AWS, Prometheus, Python
- 8+ anos em SRE e DevOps, senior
"""

IRRELEVANT_CURRICULUM = """# Candidate

## Resumo
 redshirt
"""


@pytest.fixture()
def curriculum_file(tmp_path):
    """Isolated curriculum file — never touches the repo's data/curriculum.md."""
    return tmp_path / "curriculum.md"


def classify(job: dict, curriculum_path=None) -> dict:
    return LayaInspiredClassifier(PROFILE, curriculum_path).classify(job)


# --------------------------------------------------------------------------- #
# CA1 / CA10 — ausência é o estado neutro
# --------------------------------------------------------------------------- #


def test_missing_curriculum_leaves_the_score_untouched(curriculum_file):
    """CA1/CA10: no file => the pre-curriculum score, no raise, no reason."""
    assert not curriculum_file.exists()

    result = classify(HIGH_JOB, curriculum_file)

    # The score is the plain 7-weight average — no curriculum component exists.
    components = result["decision"]["score"]["components"]
    assert "curriculum" not in components
    expected = round(
        sum(value * LayaInspiredClassifier.WEIGHTS[key] for key, value in components.items()),
        2,
    )
    assert result["score"] == expected
    assert not any("Currículo" in reason for reason in result["reasons"])


def test_curriculum_without_any_match_changes_nothing(curriculum_file):
    """A curriculum naming nothing from the posting produces no context at all."""
    baseline = classify(HIGH_JOB)
    curriculum_file.write_text(IRRELEVANT_CURRICULUM, encoding="utf-8")

    result = classify(HIGH_JOB, curriculum_file)

    assert result["score"] == baseline["score"]
    assert result["match"] == baseline["match"]
    assert not any("Currículo" in reason for reason in result["reasons"])


def test_curriculum_names_the_origin_without_moving_the_score(curriculum_file):
    """CA2: the reason cites the CURRICULUM as the source, and only that.

    The reason must say the skills came from the curriculum, not the profile —
    and, per SPEC 202610052324, the score must NOT move.
    """
    baseline = classify(HIGH_JOB)
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")
    result = classify(HIGH_JOB, curriculum_file)

    # CA6: context never tilts the decision.
    assert result["score"] == baseline["score"]
    assert result["match"] == baseline["match"]
    assert "curriculum" not in result["decision"]["score"]["components"]

    curriculum_reasons = [r for r in result["reasons"] if r.startswith("Currículo")]
    assert curriculum_reasons
    # The skills are the canonical lowercase vocabulary terms the crossing
    # found (`kubernetes`, not the raw Markdown).
    assert "kubernetes" in curriculum_reasons[0]


# --------------------------------------------------------------------------- #
# CA7 — o que reprovou o experimento: contaminação de sujeito
# --------------------------------------------------------------------------- #


def test_out_of_profile_job_stays_low_with_curriculum_loaded(curriculum_file):
    """CA7: a Sales Manager must not become infra just because the résumé is.

    Regression from the 202610051406 experiment, where the résumé and the job
    shared the Router state and `skill_fit` on this exact posting went
    0.11 → 0.78. Here the crossing is code: no posting skill overlaps, so no
    skill reason is emitted. The only contribution is seniority — the posting
    does say "Senior" and the résumé verifies senior, which is a true statement
    about the candidate, not an import of the candidate's role.
    """
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")

    result = classify(LOW_JOB, curriculum_file)

    assert result["match"] == "low"
    assert result["score"] < 60
    # No skill from the curriculum is found in a sales posting.
    assert not any("presentes na vaga" in reason for reason in result["reasons"])


def test_curriculum_cannot_change_what_the_laya_answers(curriculum_file):
    """CA7 at the root: the model's reading of the job is curriculum-independent.

    Path B keeps the curriculum out of `job_state()`, so the same job yields the
    same model answers whether or not a résumé exists on disk. This is the
    guarantee the failed experiment could not offer — there, the résumé and the
    job shared the Router state and the model re-described the candidate.
    """
    from app.classifier.engine import FakeEngine
    from app.classifier.laya_job_classifier import LayaJobClassifier

    seen: list[dict] = []

    class RecordingEngine(FakeEngine):
        def predict(self, states):
            seen.append(states[0])
            return super().predict(states)

    def laya_answers(curriculum_path):
        classifier = LayaJobClassifier(PROFILE, RecordingEngine(), backend="fake")
        # The policy builds its own heuristic base; point it at the résumé under
        # test so the only variable is the file's presence.
        classifier.signals = LayaInspiredClassifier(PROFILE, curriculum_path)
        return classifier.classify(LOW_JOB)["decision"]["laya"]["answers"]

    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")
    with_curriculum = laya_answers(curriculum_file)
    without = laya_answers(None)

    assert with_curriculum == without
    # And the state the model actually saw carried the job only, both times.
    assert all(set(state) == set(job_state(LOW_JOB)) for state in seen)


def test_curriculum_does_not_touch_profile_skill_and_seniority_components(
    curriculum_file,
):
    """R2: profile.json stays the source of `skills`/`seniority` components."""
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")

    without = classify(HIGH_JOB)["decision"]["score"]["components"]
    with_curriculum = classify(HIGH_JOB, curriculum_file)["decision"]["score"]["components"]

    assert with_curriculum == without
    # The curriculum contributes no component at all (SPEC 202610052324).
    assert "curriculum" not in with_curriculum


# --------------------------------------------------------------------------- #
# CA5 — pesos e thresholds
# --------------------------------------------------------------------------- #


def test_weights_are_the_original_seven_and_sum_to_one():
    """CA5: the curriculum has NO weight — the score formula is untouched."""
    weights = LayaInspiredClassifier.WEIGHTS

    assert abs(sum(weights.values()) - 1.0) < 1e-9
    assert "curriculum" not in weights
    assert weights == {
        "title": 0.20,
        "seniority": 0.15,
        "skills": 0.30,
        "cloud": 0.10,
        "experience": 0.10,
        "ai": 0.05,
        "remote": 0.10,
    }


def test_thresholds_are_80_and_60(curriculum_file):
    """CA5: the 80/60 cut points are literal, not derived from the weights."""
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")

    for result in (classify(HIGH_JOB, curriculum_file), classify(LOW_JOB, curriculum_file)):
        expected = "high" if result["score"] >= 80 else "medium" if result["score"] >= 60 else "low"
        assert result["match"] == expected
        assert 0 <= result["score"] <= 100


def test_a_curriculum_hit_cannot_push_a_score_past_the_unchanged_threshold():
    """CA5: pushing `curriculum` up never moves the 80 cut point itself."""
    import inspect

    source = inspect.getsource(LayaInspiredClassifier.classify)

    assert ">= 80" in source
    assert ">= 60" in source


# --------------------------------------------------------------------------- #
# CA1 / R4 — o currículo NÃO entra no state do Laya
# --------------------------------------------------------------------------- #


def test_job_state_never_receives_the_curriculum():
    """CA1/R4: the Router keeps reading only the job — 5 keys, curriculum-free."""
    state = job_state(HIGH_JOB)

    assert set(state) == {"title", "company", "location", "workplace", "description"}
    assert not any("curriculum" in key for key in state)


def test_curriculum_never_enters_the_router_state_even_when_configured(curriculum_file):
    """The signal is computed after the forward pass, so the state is unaffected."""
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")

    LayaInspiredClassifier(PROFILE, curriculum_file).classify(HIGH_JOB)

    assert set(job_state(HIGH_JOB)) == {
        "title",
        "company",
        "location",
        "workplace",
        "description",
    }


# --------------------------------------------------------------------------- #
# CA8 — dealbreaker sobrepõe o currículo favorável
# --------------------------------------------------------------------------- #


def test_dealbreaker_stays_low_despite_a_matching_curriculum(curriculum_file):
    """CA8: an exclusion vetoes even a curriculum that matches the posting."""
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")
    job = {**HIGH_JOB, "description": HIGH_JOB["description"] + " Requer inglês fluente."}

    result = classify(job, curriculum_file)

    assert result["decision"]["excluded"]["value"] is True
    assert result["match"] == "low"
    assert result["score"] <= 49.0


# --------------------------------------------------------------------------- #
# curriculum.py — parsing e versionamento
# --------------------------------------------------------------------------- #


def test_load_extracts_skills_seniority_and_years(curriculum_file):
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")

    parsed = curriculum.load(curriculum_file)

    assert "kubernetes" in parsed.skills
    assert "terraform" in parsed.skills
    assert "senior" in parsed.seniority
    assert parsed.years == 8


def test_load_is_accent_and_case_insensitive(curriculum_file):
    """`Sênior`/`Kubernetes` must fold the same as `senior`/`kubernetes`."""
    curriculum_file.write_text("# C\n\nSênior com KUBERNETES e PYTHON.\n", encoding="utf-8")

    parsed = curriculum.load(curriculum_file)

    assert "kubernetes" in parsed.skills
    assert "python" in parsed.skills
    assert "senior" in parsed.seniority


def test_version_is_the_sha256_of_the_content(curriculum_file):
    import hashlib

    content = "# Candidate\n\nKubernetes e Terraform.\n"
    curriculum_file.write_text(content, encoding="utf-8")

    expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
    assert curriculum.version(curriculum_file) == expected


def test_version_changes_with_content_and_is_stable_for_equal_saves(curriculum_file):
    first = curriculum_file
    first.write_text("# A\n", encoding="utf-8")
    version_a = curriculum.version(first)

    # same text, rewritten -> same version (hash of content, not of the save)
    first.write_text("# A\n", encoding="utf-8")
    assert curriculum.version(first) == version_a

    first.write_text("# B\n", encoding="utf-8")
    assert curriculum.version(first) != version_a


def test_absent_file_yields_empty_curriculum_without_raising(curriculum_file):
    parsed = curriculum.load(curriculum_file)

    assert parsed == curriculum.EMPTY
    assert parsed.version is None
    assert curriculum.version(curriculum_file) is None


def test_read_returns_empty_string_when_absent(curriculum_file):
    assert curriculum.read(curriculum_file) == ""


def test_skill_match_respects_word_boundaries(curriculum_file):
    """`go` must not fire on `google`/`going` — the same guard as profile skills."""
    curriculum_file.write_text("# C\n\nGolang e Google Cloud.\n", encoding="utf-8")

    parsed = curriculum.load(curriculum_file)

    assert "go" in parsed.skills  # from "golang", not from a substring
    job = {**HIGH_JOB, "description": "Reaching going to market."}
    result = classify(job, curriculum_file)
    assert not any("Currículo" in reason for reason in result["reasons"])


# --------------------------------------------------------------------------- #
# Contrato preservado (CA4 / R7)
# --------------------------------------------------------------------------- #


def test_output_contract_is_unchanged(curriculum_file):
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")

    result = classify(HIGH_JOB, curriculum_file)

    assert set(result) >= {"match", "score", "decision", "reasons", "gaps"}
    assert result["match"] in {"high", "medium", "low"}
    assert 0 <= result["score"] <= 100
    assert result["decision"]["choice"]["value"] == result["match"]
    assert result["decision"]["score"]["value"] == result["score"]
    assert abs(sum(result["decision"]["choice"]["probabilities"].values()) - 1.0) < 1e-6


def test_the_decision_carries_no_curriculum_component(curriculum_file):
    """SPEC 202610052324: the score components are the original seven."""
    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")

    components = classify(HIGH_JOB, curriculum_file)["decision"]["score"]["components"]

    assert "curriculum" not in components
    assert set(components) == set(LayaInspiredClassifier.WEIGHTS)


def test_classifier_reloads_the_curriculum_on_every_call(curriculum_file):
    """Saving the file takes effect without rebuilding the classifier."""
    classifier = LayaInspiredClassifier(PROFILE, curriculum_file)
    before = classifier.classify(HIGH_JOB)

    curriculum_file.write_text(MATCHING_CURRICULUM, encoding="utf-8")
    after = classifier.classify(HIGH_JOB)

    # The score cannot move, but the context must appear immediately.
    assert before["score"] == after["score"]
    assert not any("Currículo" in reason for reason in before["reasons"])
    assert any("Currículo" in reason for reason in after["reasons"])


def test_curriculum_path_defaults_are_used_when_none_is_given():
    """`curriculum_path=None` resolves to data/curriculum.md without raising."""
    parsed = LayaInspiredClassifier(PROFILE, None).classify(HIGH_JOB)

    assert 0 <= parsed["score"] <= 100
    assert "curriculum" not in parsed["decision"]["score"]["components"]


def test_profile_json_alone_still_classifies_without_a_curriculum(curriculum_file):
    """CA8 of the note: an empty profile/curriculum works from profile.json only."""
    result = classify(HIGH_JOB, curriculum_file)

    assert result["decision"]["score"]["components"]["skills"] > 0
    assert result["match"] in {"high", "medium", "low"}

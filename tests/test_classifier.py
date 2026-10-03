from app.classifier.laya_classifier import LayaInspiredClassifier

PROFILE = {
    "titles": ["SRE", "DevOps", "Platform Engineer"],
    "seniority": ["Senior", "Staff"],
    "remote_required": True,
    "skills": ["AWS", "Kubernetes", "Terraform", "Prometheus", "Python"],
}


def test_high_match():
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "Senior SRE",
            "location": "Brazil",
            "remote": True,
            "description": "Senior SRE with AWS Kubernetes Terraform Prometheus Python.",
        }
    )
    assert result["match"] == "high"
    assert result["score"] >= 80
    assert result["decision"]["choice"]["value"] == "high"
    assert result["decision"]["score"]["value"] == result["score"]


def test_low_match():
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "Senior Sales Manager",
            "location": "Brazil",
            "remote": False,
            "description": "Manage sales pipeline and commercial accounts.",
        }
    )
    assert result["match"] == "low"
    assert result["score"] < 60
    assert result["gaps"]


def test_remote_is_explicit_decision():
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "Platform Engineer",
            "location": "Brazil",
            "remote": True,
            "description": "Kubernetes platform role.",
        }
    )
    assert result["decision"]["noul"]["value"] is True


def test_probabilities_sum_to_one():
    classifier = LayaInspiredClassifier(PROFILE)
    for remote in (True, False):
        result = classifier.classify(
            {
                "title": "Senior SRE",
                "location": "Brazil",
                "remote": remote,
                "description": "AWS Kubernetes Terraform.",
            }
        )
        probs = result["decision"]["choice"]["probabilities"]
        assert abs(sum(probs.values()) - 1.0) < 1e-6


PROFILE_WITH_EXCLUSIONS = {
    **PROFILE,
    "exclusions": ["inglês fluente", "híbrido"],
}


def test_exclusion_vetoes_high_match():
    classifier = LayaInspiredClassifier(PROFILE_WITH_EXCLUSIONS)
    result = classifier.classify(
        {
            "title": "Senior SRE",
            "location": "Brazil",
            "remote": True,
            "description": (
                "Senior SRE with AWS Kubernetes Terraform Prometheus Python. "
                "Requer inglês fluente para reuniões com o time global."
            ),
        }
    )
    assert result["match"] == "low"
    assert result["score"] <= 49.0
    assert result["decision"]["excluded"]["value"] is True
    assert result["decision"]["excluded"]["terms"] == ["inglês fluente"]
    assert any("Dealbreaker" in gap for gap in result["gaps"])
    assert result["decision"]["choice"]["value"] == "low"
    assert abs(sum(result["decision"]["choice"]["probabilities"].values()) - 1.0) < 1e-6


def test_exclusion_matches_accent_insensitive_and_case_insensitive():
    classifier = LayaInspiredClassifier(PROFILE_WITH_EXCLUSIONS)
    result = classifier.classify(
        {
            "title": "Staff DevOps",
            "location": "Brazil",
            "remote": True,
            "description": "INGLES fluente para o time; modelo HIBRIDO de trabalho.",
        }
    )
    assert result["decision"]["excluded"]["value"] is True
    assert sorted(result["decision"]["excluded"]["terms"]) == ["híbrido", "inglês fluente"]


def test_job_without_exclusion_keeps_high_match():
    classifier = LayaInspiredClassifier(PROFILE_WITH_EXCLUSIONS)
    result = classifier.classify(
        {
            "title": "Senior SRE",
            "location": "Brazil",
            "remote": True,
            "description": "Senior SRE with AWS Kubernetes Terraform Prometheus Python.",
        }
    )
    assert result["match"] == "high"
    assert result["decision"]["excluded"]["value"] is False


def test_exclusion_uses_word_boundaries():
    # "ingles" must not match inside "inglesa" (word boundary guard)
    classifier = LayaInspiredClassifier({**PROFILE, "exclusions": ["ingles"]})
    result = classifier.classify(
        {
            "title": "SRE",
            "location": "Brazil",
            "remote": True,
            "description": "Role para atuar com a jornada de conteúdo em língua inglesa.",
        }
    )
    assert result["decision"]["excluded"]["value"] is False


# ------------------------------------------------- real-jobs fixes (SPEC 202610030015)


def test_seniority_detected_from_years_of_experience():
    """'5+ anos de experiência' must count as seniority even without 'Senior'."""
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "SRE",
            "location": "Brazil",
            "remote": True,
            "description": "Kubernetes Terraform AWS. Requisitos 5+ anos de experiência.",
        }
    )
    assert result["decision"]["score"]["components"]["seniority"] == 100.0


def test_seniority_matches_accented_ptbr():
    """'Sênior' (accented) must match profile's 'Senior'."""
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "Engenheiro Sênior",
            "location": "Brazil",
            "remote": True,
            "description": "AWS Kubernetes Terraform Prometheus Python.",
        }
    )
    assert result["decision"]["score"]["components"]["seniority"] == 100.0


def test_skills_score_scales_with_few_matches():
    """A job citing 4 of 8 profile skills must reach 80, not be capped by a
    denominator larger than what a real posting typically names."""
    big_profile = {
        **PROFILE,
        "skills": [
            "AWS",
            "Kubernetes",
            "Terraform",
            "Prometheus",
            "Python",
            "Docker",
            "Helm",
            "ArgoCD",
        ],
    }
    classifier = LayaInspiredClassifier(big_profile)
    result = classifier.classify(
        {
            "title": "SRE",
            "location": "Brazil",
            "remote": True,
            "description": "AWS Kubernetes Terraform Prometheus.",
        }
    )
    assert result["decision"]["score"]["components"]["skills"] == 80.0


def test_profile_covers_common_market_skills():
    """data/profile.json must include skills that dominate real high-jobs."""
    import json
    from pathlib import Path

    profile = json.loads(Path("data/profile.json").read_text(encoding="utf-8"))
    skills = {s.lower() for s in profile["skills"]}
    for skill in ("git", "linux", "sql", "gcp", "jenkins", "shell"):
        assert skill in skills, f"{skill} ausente do profile.json"


# ------------------------------------------------- option A fixes (SPEC 202610030015)


def test_skill_go_does_not_match_inside_other_words():
    """'Go' is a real profile skill but a substring of 'google'/'going'."""
    classifier = LayaInspiredClassifier({**PROFILE, "skills": ["Go"]})
    result = classifier.classify(
        {
            "title": "Data Engineer",
            "location": "Brazil",
            "remote": True,
            "description": "Google Cloud, going to production, maintain pipelines.",
        }
    )
    assert result["decision"]["score"]["components"]["skills"] == 0.0


def test_skill_go_matches_as_standalone_word():
    classifier = LayaInspiredClassifier({**PROFILE, "skills": ["Go"]})
    result = classifier.classify(
        {
            "title": "Backend Engineer",
            "location": "Brazil",
            "remote": True,
            "description": "We write services in Go and Python.",
        }
    )
    assert result["decision"]["score"]["components"]["skills"] == 100.0


def test_chief_counts_as_profile_seniority():
    """'Chief' is the PT-BR/EN equivalent of the profile's top levels."""
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "Chief AWS DevOps Engineer",
            "location": "Brazil",
            "remote": True,
            "description": "Kubernetes Terraform AWS Prometheus Python.",
        }
    )
    assert result["decision"]["score"]["components"]["seniority"] == 100.0


def test_lead_counts_as_profile_seniority():
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "Lead Platform Engineer",
            "location": "Brazil",
            "remote": True,
            "description": "Kubernetes Terraform AWS Prometheus Python.",
        }
    )
    assert result["decision"]["score"]["components"]["seniority"] == 100.0


def test_junior_still_below_profile_seniority():
    """'Júnior' must not satisfy a profile asking for Senior/Staff/Principal."""
    classifier = LayaInspiredClassifier(PROFILE)
    result = classifier.classify(
        {
            "title": "Engenheiro Júnior",
            "location": "Brazil",
            "remote": True,
            "description": "Kubernetes Terraform AWS Prometheus Python.",
        }
    )
    assert result["decision"]["score"]["components"]["seniority"] == 50.0

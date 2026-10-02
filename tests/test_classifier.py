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

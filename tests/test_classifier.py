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

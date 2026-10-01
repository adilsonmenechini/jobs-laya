"""Classifier factory: `laya` (default), `fake` (no model) or `heuristic`."""

from app.classifier.engine import FakeEngine, get_engine
from app.classifier.laya_classifier import LayaInspiredClassifier
from app.classifier.laya_job_classifier import LayaJobClassifier
from app.config import settings


def build_classifier(profile: dict):
    """Backend selection with automatic fallback to the heuristic classifier.

    `laya` imports torch/laya lazily: if the engine cannot be created (missing
    model, unsupported device), classification degrades instead of failing.
    """
    backend = settings.classifier_backend.lower()
    if backend == "heuristic":
        return LayaInspiredClassifier(profile)
    try:
        engine = FakeEngine() if backend == "fake" else get_engine()
        return LayaJobClassifier(profile, engine)
    except Exception:
        return LayaInspiredClassifier(profile)

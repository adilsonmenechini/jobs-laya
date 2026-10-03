"""The Laya side: one forward pass answers every typed question about a job.

An `Engine` protocol with a
real `LayaEngine` (Router + background warm-up + lock) and a deterministic
`FakeEngine` used by tests and by CLASSIFIER_BACKEND=fake — the test suite
never imports torch or downloads a checkpoint.
"""

import threading
import time
from dataclasses import dataclass, field
from typing import Protocol

from app.classifier.questions import QUESTIONS


@dataclass
class LayaView:
    role_family: str
    role_confidence: float
    remote: float
    remote_confidence: float
    skill_fit: float
    skill_confidence: float
    seniority: int
    seniority_probs: list[float] = field(default_factory=list)
    exclusions: bool = False
    exclusions_confidence: float = 0.0


@dataclass
class EngineResult:
    view: LayaView
    model: str
    latency_ms: float


class Engine(Protocol):
    device: str

    @property
    def ready(self) -> bool: ...

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]: ...


def to_result(raw: dict, latency_ms: float) -> EngineResult:
    """Reads Laya's Router.predict output into the numbers the policy uses."""
    answers = raw.get("answers") or {}
    role = answers.get("role_family") or {}
    remote = answers.get("remote") or {}
    fit = answers.get("skill_fit") or {}
    seniority = answers.get("seniority") or {}
    exclusions = answers.get("exclusions") or {}

    raw_probs = seniority.get("probabilities") or {}
    ordered = sorted(raw_probs.items(), key=lambda pair: int(pair[0]))
    probs = [float(value) for _, value in ordered]

    view = LayaView(
        role_family=str(role.get("choice") or "other"),
        role_confidence=float(role.get("answer_confidence") or 0.0),
        remote=float(remote.get("noul") or 0.0),
        remote_confidence=float(remote.get("answer_confidence") or 0.0),
        skill_fit=float(fit.get("noul") or 0.0),
        skill_confidence=float(fit.get("answer_confidence") or 0.0),
        seniority=int(seniority.get("score") or 0),
        seniority_probs=probs,
        exclusions=bool(exclusions.get("noul") or False),
        exclusions_confidence=float(exclusions.get("answer_confidence") or 0.0),
    )
    routing = raw.get("routing") or {}
    model = routing.get("model") or raw.get("model") or "laya"
    return EngineResult(view=view, model=str(model), latency_ms=latency_ms)


class LayaEngine:
    """Laya's Router. Checkpoints load in the background at first use, so the
    API keeps answering while the model (re)compiles."""

    def __init__(self, device: str | None = None, preload: bool = True):
        import torch
        from laya import Router

        if device is None:
            if torch.cuda.is_available():
                device = "cuda"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        self.device = device
        self._router = Router(device=device, max_loaded=2)
        self._lock = threading.Lock()
        self._ready = threading.Event()
        if preload:
            threading.Thread(target=self._warm, daemon=True).start()
        else:
            self._ready.set()

    def _warm(self) -> None:
        # One English and one Portuguese pass load the checkpoint and compile kernels.
        warmups = [
            {
                "title": "Senior SRE",
                "description": "Remote reliability role",
                "workplace": "remote",
            },
            {
                "title": "Engenheiro DevOps",
                "description": "Vaga remota de plataforma",
                "workplace": "remote",
            },
        ]
        with self._lock:
            for state in warmups:
                self._router.predict(state, QUESTIONS)
        self._ready.set()

    @property
    def ready(self) -> bool:
        return self._ready.is_set()

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]:
        self._ready.wait()
        results = []
        # Torch forwards are not safe to interleave on one model; serializing is cheap here.
        with self._lock:
            for state in states:
                start = time.perf_counter()
                raw = self._router.predict(state, QUESTIONS)
                results.append(to_result(raw, (time.perf_counter() - start) * 1000))
        return results


class FakeEngine:
    """Deterministic stand-in: keyword rules instead of a model.

    Used by the test suite and available as CLASSIFIER_BACKEND=fake for
    exercising the full pipeline without downloading a checkpoint.
    """

    device = "fake"
    ready = True

    def predict(self, states: list[dict[str, str]]) -> list[EngineResult]:
        results = []
        for state in states:
            text = " ".join(str(value) for value in state.values()).lower()

            remote = 0.9 if ("remote" in text or "remoto" in text) else 0.1
            infra = any(
                word in text
                for word in (
                    "kubernetes",
                    "terraform",
                    "aws",
                    "devops",
                    "sre",
                    "reliability",
                    "platform",
                    "cloud",
                    "prometheus",
                )
            )
            skill_fit = 0.9 if infra else 0.1

            if "sales" in text or "marketing" in text:
                family = "other"
            elif "llm" in text or "machine learning" in text or " ai " in f" {text} ":
                family = "ai_ml"
            elif "devops" in text:
                family = "devops"
            elif "platform" in text:
                family = "platform_cloud"
            elif "sre" in text or "reliability" in text:
                family = "site_reliability"
            else:
                family = "other"

            # Confidence varies by how clear the signal is
            if family in ("devops", "site_reliability", "ai_ml"):
                role_confidence = 0.85
            elif family == "platform_cloud":
                role_confidence = 0.70
            else:
                role_confidence = 0.50  # "other" is less certain

            if any(word in text for word in ("staff", "principal", "lead")):
                seniority = 2
            elif "senior" in text:
                seniority = 1
            else:
                seniority = 0
            weights = (
                [0.6, 0.3, 0.1]
                if seniority == 0
                else ([0.1, 0.8, 0.1] if seniority == 1 else [0.05, 0.15, 0.8])
            )

            exclusion_terms = (
                "inglês fluente",
                "ingles fluente",
                "inglês avançado",
                "ingles avancado",
                "fluent english",
                "advanced english",
                "english fluency",
            )
            exclusions = any(term in text for term in exclusion_terms)
            exclusions_confidence = 0.9 if exclusions else 0.1

            view = LayaView(
                role_family=family,
                role_confidence=role_confidence,
                remote=remote,
                remote_confidence=max(remote, 1 - remote),
                skill_fit=skill_fit,
                skill_confidence=max(skill_fit, 1 - skill_fit),
                seniority=seniority,
                seniority_probs=weights,
                exclusions=exclusions,
                exclusions_confidence=exclusions_confidence,
            )
            results.append(EngineResult(view=view, model="fake", latency_ms=1.0))
        return results


_ENGINE: Engine | None = None


def get_engine(device: str | None = None, preload: bool = True) -> Engine:
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = LayaEngine(device=device or None, preload=preload)
    return _ENGINE


def peek_engine() -> Engine | None:
    """Status only — never instantiates (keeps startup/downloads out of tests)."""
    return _ENGINE

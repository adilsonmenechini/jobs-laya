"""Laya-backed classifier: the model reads the text, heuristics read the facts,
a small policy combines both — same output contract as the heuristic classifier.

Laya answers typed questions (choice, noul, score) in one forward pass;
deterministic signals (matched skills, seniority hits, remote flag) stay in
code; the policy merges them into
`{match, score, decision{choice,score,noul}, reasons, gaps}` so API, storage
and tests do not care which engine produced the verdict.
"""

from app.classifier.engine import Engine, EngineResult
from app.classifier.laya_classifier import LayaInspiredClassifier
from app.classifier.questions import job_state

# seniority rubric answers map to what the profile accepts: junior/mid, senior, staff+
SENIORITY_VALUE = (0.0, 85.0, 100.0)
ROLE_FAMILIES_IN_PROFILE = {"site_reliability", "devops", "platform_cloud", "ai_ml"}


class LayaJobClassifier:
    def __init__(self, profile: dict, engine: Engine, backend: str) -> None:
        self.profile = profile
        self.engine = engine
        # Provenance: which backend produced this decision. Required — a silent
        # default of "laya" is exactly the lie this parameter exists to prevent.
        self.backend = backend
        self.signals = LayaInspiredClassifier(profile)

    def classify(self, job: dict) -> dict:
        base = self.signals.classify(job)
        try:
            result = self.engine.predict([job_state(job)])[0]
        except Exception as exc:  # engine crash must never lose the heuristic verdict
            return self._fallback(base, exc)
        return self._combine(base, result)

    def _fallback(self, base: dict, exc: Exception) -> dict:
        reasons = [*base["reasons"], f"Laya indisponível, usando heurística: {exc}"]
        decision = dict(base["decision"])
        decision["laya"] = {"backend": "heuristic", "error": str(exc)}
        return {**base, "decision": decision, "reasons": reasons}

    def _combine(self, base: dict, result: EngineResult) -> dict:
        view = result.view
        components = dict(base["decision"]["score"]["components"])
        reasons = list(base["reasons"])
        gaps = list(base["gaps"])

        # --- policy: Laya reads the language, code keeps the facts ---
        # Remote: always use Laya's answer when profile requires it (binary signal)
        if self.profile.get("remote_required"):
            components["remote"] = round(view.remote * 100, 2)

        # Title: 50/50 blend (Laya's role_family is useful but not fully trusted)
        if view.role_family in ROLE_FAMILIES_IN_PROFILE:
            components["title"] = round(max(components["title"], 75.0), 2)
        else:
            components["title"] = round(min(components["title"], 40.0), 2)

        # Skills: 50/50 blend
        components["skills"] = round(0.5 * components["skills"] + 0.5 * view.skill_fit * 100, 2)

        # Seniority: 50/50 blend
        seniority_value = SENIORITY_VALUE[min(2, max(0, view.seniority))]
        components["seniority"] = round(0.5 * components["seniority"] + 0.5 * seniority_value, 2)

        # SPEC 202610051432: the weights now carry the `curriculum` component.
        # Divide by the ACTIVE weights so a zeroed curriculum leaves the score
        # exactly where it was before this change (CA1/CA6 — no 0.9x squeeze).
        active = [key for key in components if key != "curriculum" or components[key]]
        score = round(
            sum(components[key] * LayaInspiredClassifier.WEIGHTS[key] for key in active)
            / sum(LayaInspiredClassifier.WEIGHTS[key] for key in active),
            2,
        )
        match = "high" if score >= 80 else "medium" if score >= 60 else "low"

        reasons.append(f"Laya: papel {view.role_family} ({view.role_confidence:.0%})")
        if view.remote >= 0.5:
            reasons.append(f"Laya: remoto com {view.remote:.0%} de probabilidade")
        if view.skill_fit >= 0.5:
            reasons.append(f"Laya: fit de skills com {view.skill_fit:.0%}")

        if view.skill_fit < 0.5:
            gaps.append("Laya: baixo fit com o perfil de skills")
        if self.profile.get("remote_required") and view.remote < 0.5:
            gaps.append("Laya: não identificou trabalho remoto")
        if view.seniority == 0:
            gaps.append("Laya: senioridade abaixo do esperado")

        # Dealbreaker veto survives the model merge: exclusions are absolute.
        # The heuristic base already recorded the dealbreaker in `reasons` and
        # `gaps` — this block only re-applies the veto to the merged score.
        excluded_block = base["decision"].get("excluded") or {"value": False, "terms": []}

        # Laya exclusion veto: disabled until the model is fine-tuned with the
        # exclusions question. The current checkpoint answers it unreliably.

        probabilities = LayaInspiredClassifier._match_probabilities(score)

        if excluded_block.get("value"):
            score = min(score, 49.0)
            match = "low"
            probabilities = LayaInspiredClassifier._match_probabilities(score)

        decision = {
            "choice": {
                "value": match,
                "confidence": max(probabilities.values()),
                "probabilities": probabilities,
            },
            "score": {
                "value": score,
                "confidence": round(min(1.0, abs(score - 50) / 50), 4),
                "components": components,
            },
            "noul": {
                "value": bool(view.remote >= 0.5),
                "confidence": round(view.remote_confidence, 4),
                "probability_true": round(view.remote, 4),
            },
            "excluded": excluded_block,
            "laya": {
                "backend": self.backend,
                "model": result.model,
                "latency_ms": round(result.latency_ms, 2),
                "answers": {
                    "role_family": {
                        "choice": view.role_family,
                        "confidence": round(view.role_confidence, 4),
                    },
                    "remote": {"noul": round(view.remote, 4)},
                    "skill_fit": {"noul": round(view.skill_fit, 4)},
                    "seniority": {
                        "score": view.seniority,
                        "probabilities": view.seniority_probs,
                    },
                    "exclusions": {
                        "noul": view.exclusions,
                        "confidence": round(view.exclusions_confidence, 4),
                    },
                },
            },
        }
        return {
            "match": match,
            "score": score,
            "decision": decision,
            "reasons": reasons,
            "gaps": gaps,
        }

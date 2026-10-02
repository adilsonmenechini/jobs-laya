import re
import unicodedata
from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    value: str | float | bool
    confidence: float
    probabilities: dict[str, float]
    rationale: str


class LayaInspiredClassifier:
    """Typed-decision classifier inspired by Laya.

    The implementation is deterministic for the MVP. Its output contract mirrors
    the useful Laya pattern: typed choice/score/yes-no decisions with confidence,
    probabilities and rationale. A real Laya inference engine can replace this
    class later without changing the API or persistence layer.
    """

    WEIGHTS = {
        "title": 0.20,
        "seniority": 0.15,
        "skills": 0.30,
        "cloud": 0.10,
        "experience": 0.10,
        "ai": 0.05,
        "remote": 0.10,
    }

    def __init__(self, profile: dict):
        self.profile = profile
        self.skills = {self._norm(x) for x in profile.get("skills", [])}
        self.titles = {self._norm(x) for x in profile.get("titles", [])}
        self.seniority = {self._norm(x) for x in profile.get("seniority", [])}
        # Dealbreakers ("inglês fluente", "híbrido", …): matched accent-insensitively.
        self.exclusions = [
            (original, folded)
            for original in profile.get("exclusions", [])
            if (folded := self._fold(original))
        ]

    @staticmethod
    def _norm(value: str) -> str:
        return re.sub(r"\s+", " ", value.lower().strip())

    @staticmethod
    def _fold(value: str) -> str:
        """Lowercase + strip accents so "inglês fluente" matches "ingles fluente"."""
        stripped = unicodedata.normalize("NFKD", value.lower().strip())
        return re.sub(r"\s+", " ", "".join(c for c in stripped if not unicodedata.combining(c)))

    def exclusion_hits(self, text: str) -> list[str]:
        """Exclusion terms present in `text` (word-boundary, accent-insensitive)."""
        folded = self._fold(text)
        return [
            original
            for original, term in self.exclusions
            if re.search(rf"\b{re.escape(term)}\b", folded)
        ]

    @staticmethod
    def _contains(text: str, term: str) -> bool:
        return term in text

    def classify(self, job: dict) -> dict:
        title = self._norm(job.get("title", ""))
        description = self._norm(job.get("description", ""))
        text = f"{title} {description}"
        matched_skills = sorted(skill for skill in self.skills if self._contains(text, skill))

        title_hits = [t for t in self.titles if t in title]
        seniority_hits = [s for s in self.seniority if s in title or s in description]

        title_score = (
            min(100, 60 + 20 * len(title_hits)) if title_hits else self._role_similarity(title)
        )
        seniority_score = 100 if seniority_hits else 50
        skill_denominator = max(1, min(10, len(self.skills)))
        skills_score = min(100, (len(matched_skills) / skill_denominator) * 100)

        cloud_terms = {"aws", "azure", "gcp", "cloud", "kubernetes", "terraform"}
        cloud_hits = [x for x in cloud_terms if x in text]
        cloud_score = min(100, len(cloud_hits) * 25)

        experience_score = (
            100 if seniority_hits else (70 if "senior" in text or "staff" in text else 50)
        )

        ai_terms = {
            "ai",
            "artificial intelligence",
            "llm",
            "rag",
            "langchain",
            "langgraph",
            "machine learning",
        }
        ai_hits = [x for x in ai_terms if x in text]
        ai_score = min(100, len(ai_hits) * 25)

        remote = bool(job.get("remote")) or "remote" in text or "remoto" in text
        remote_score = 100 if (remote or not self.profile.get("remote_required", False)) else 0

        excluded = self.exclusion_hits(text)

        components = {
            "title": round(title_score, 2),
            "seniority": round(seniority_score, 2),
            "skills": round(skills_score, 2),
            "cloud": round(cloud_score, 2),
            "experience": round(experience_score, 2),
            "ai": round(ai_score, 2),
            "remote": round(remote_score, 2),
        }

        score = round(sum(components[k] * self.WEIGHTS[k] for k in components), 2)
        if excluded:
            # Dealbreaker found: no score can rescue it — veto to low.
            score = min(score, 49.0)
        match = "high" if score >= 80 else "medium" if score >= 60 else "low"

        reasons = []
        if title_hits:
            reasons.append(f"Cargo compatível: {', '.join(sorted(title_hits))}")
        if matched_skills:
            reasons.append(f"Skills encontradas: {', '.join(matched_skills[:12])}")
        if seniority_hits:
            reasons.append(f"Senioridade identificada: {', '.join(sorted(seniority_hits))}")
        if remote:
            reasons.append("Vaga indica trabalho remoto")
        if ai_hits:
            reasons.append(f"AI/LLM relacionado: {', '.join(ai_hits[:8])}")
        if excluded:
            reasons.append(f"Exclusão do perfil atingida: {', '.join(excluded)}")

        gaps = []
        if excluded:
            gaps.append(f"Dealbreaker presente na vaga: {', '.join(excluded)}")
        if not matched_skills:
            gaps.append("Nenhuma skill do perfil foi encontrada na descrição")
        elif len(matched_skills) < 4:
            gaps.append("Poucas skills do perfil foram encontradas")
        if not seniority_hits:
            gaps.append("Senioridade não identificada claramente")
        if self.profile.get("remote_required") and not remote:
            gaps.append("Remoto não identificado")

        choice_probs = self._match_probabilities(score)
        decision = {
            "choice": {
                "value": match,
                "confidence": max(choice_probs.values()),
                "probabilities": choice_probs,
            },
            "score": {
                "value": score,
                "confidence": round(min(1.0, abs(score - 50) / 50), 4),
                "components": components,
            },
            "noul": {
                "value": remote,
                "confidence": 1.0 if "remote" in text or "remoto" in text else 0.6,
                "probability_true": 1.0 if remote else 0.0,
            },
            "excluded": {
                "value": bool(excluded),
                "terms": excluded,
            },
        }

        return {
            "match": match,
            "score": score,
            "decision": decision,
            "reasons": reasons,
            "gaps": gaps,
        }

    def _role_similarity(self, title: str) -> float:
        role_terms = {
            "sre": {"reliability", "platform", "devops", "site reliability"},
            "devops": {"platform", "cloud", "infrastructure", "reliability"},
            "platform": {"devops", "sre", "infrastructure", "cloud"},
            "ai": {"machine learning", "llm", "mlops", "genai"},
        }
        for profile_title in self.titles:
            for key, related in role_terms.items():
                if key in profile_title and any(x in title for x in related):
                    return 65.0
        return 30.0

    @staticmethod
    def _match_probabilities(score: float) -> dict[str, float]:
        if score >= 80:
            high = min(0.99, 0.80 + (score - 80) / 100)
            medium = round((1 - high) * 0.75, 4)
            low = round(1 - high - medium, 4)
        elif score >= 60:
            medium = min(0.90, 0.60 + (score - 60) / 100)
            high = round((1 - medium) * 0.25, 4)
            low = round(1 - medium - high, 4)
        else:
            low = min(0.95, 0.55 + (60 - score) / 100)
            medium = round((1 - low) * 0.75, 4)
            high = round(1 - low - medium, 4)
        return {"high": high, "medium": medium, "low": low}

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from app.services.curriculum import Curriculum
from app.services.curriculum import load as load_curriculum


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

    # SPEC 202610052324: the curriculum does NOT enter the score.
    #
    # Measured (plan/reviews/review-202610051432.md): a positive component
    # moves every score up, pushing postings near the 80 threshold over it and
    # emptying `medium` (2/5 -> 0/5). Filtering *which* skills counted did not
    # help — the direction was the problem, not the aggregation. So the
    # curriculum stays out of `WEIGHTS` entirely and surfaces in reasons/gaps,
    # where it informs the decision without tilting it.
    #
    # These are the original weights, restored verbatim.
    WEIGHTS = {
        "title": 0.20,
        "seniority": 0.15,
        "skills": 0.30,
        "cloud": 0.10,
        "experience": 0.10,
        "ai": 0.05,
        "remote": 0.10,
    }

    # PT-BR → EN title mapping for common roles
    PTBR_TITLES = {
        "engenheiro de ia": "ai engineer",
        "engenheiro ia": "ai engineer",
        "engenheiro de ml": "ml engineer",
        "engenheiro ml": "ml engineer",
        "engenheiro de plataforma": "platform engineer",
        "engenheiro de devops": "devops engineer",
        "engenheiro devops": "devops engineer",
        "engenheiro de sre": "sre",
        "engenheiro sre": "sre",
        "engenheiro de cloud": "cloud engineer",
        "engenheiro cloud": "cloud engineer",
        "engenheiro de dados": "data engineer",
        "analista de devops": "devops analyst",
        "analista devops": "devops analyst",
        "analista de sre": "sre analyst",
        "analista sre": "sre analyst",
        "analista de cloud": "cloud analyst",
        "analista cloud": "cloud analyst",
        "analista de dados": "data analyst",
        "arquiteto de soluções": "solutions architect",
        "arquiteto de cloud": "cloud architect",
        "coordenador de devops": "devops coordinator",
        "coordenador sre": "sre coordinator",
        "especialista em sre": "sre specialist",
        "especialista devops": "devops specialist",
        "especialista cloud": "cloud specialist",
        "especialista em cloud": "cloud specialist",
        "lead ai platform engineer": "ai platform engineer",
        "staff platform engineer": "platform engineer",
        "principal platform engineer": "platform engineer",
        "senior data platform engineer": "data platform engineer",
        "forward deployed engineer": "forward deployed engineer",
        "site reliability engineer": "sre",
        "automation and ot network engineer": "network engineer",
        "murex environment and configuration manager": "configuration manager",
        "manager delivery solutions architects": "solutions architect manager",
        "product operations intern": "product operations intern",
        "inside sales representative": "sales representative",
        "fraud disputes intern": "intern",
        "software engineer back end": "backend engineer",
        "senior data developer": "data developer",
        "engenheiro de ia tradicional e ia generativa": "ai engineer",
        "engenheiro de agentes de ia": "ai agent engineer",
        "ai engineer": "ai engineer",
        "fullstack ai engineer": "ai engineer",
        "cloud engineer": "cloud engineer",
        "devops engineer": "devops engineer",
        "devops": "devops",
        "sre": "sre",
        "platform engineer": "platform engineer",
    }

    # PT-BR → EN skills mapping
    PTBR_SKILLS = {
        "kubernetes": "kubernetes",
        "k8s": "kubernetes",
        "terraform": "terraform",
        "aws": "aws",
        "amazon web services": "aws",
        "azure": "azure",
        "gcp": "gcp",
        "google cloud": "gcp",
        "docker": "docker",
        "python": "python",
        "go": "go",
        "golang": "go",
        "linux": "linux",
        "ci/cd": "ci/cd",
        "ci cd": "ci/cd",
        "pipeline": "pipeline",
        "observabilidade": "observability",
        "observability": "observability",
        "monitoramento": "monitoring",
        "monitoracao": "monitoring",
        "sre": "sre",
        "devops": "devops",
        "cloud": "cloud",
        "nuvem": "cloud",
        "computação em nuvem": "cloud",
        "infraestrutura": "infrastructure",
        "infra": "infrastructure",
        "automação": "automation",
        "automacao": "automation",
        "container": "container",
        "conteiner": "container",
        "microserviços": "microservices",
        "microservices": "microservices",
        "api": "api",
        "rest": "rest",
        "graphql": "graphql",
        "banco de dados": "database",
        "database": "database",
        "sql": "sql",
        "nosql": "nosql",
        "mongodb": "mongodb",
        "postgres": "postgres",
        "postgresql": "postgres",
        "mysql": "mysql",
        "redis": "redis",
        "kafka": "kafka",
        "spark": "spark",
        "hadoop": "hadoop",
        "airflow": "airflow",
        "dbt": "dbt",
        "snowflake": "snowflake",
        "databricks": "databricks",
        "machine learning": "machine learning",
        "ml": "ml",
        "deep learning": "deep learning",
        "ia": "ai",
        "inteligência artificial": "ai",
        "inteligencia artificial": "ai",
        "llm": "llm",
        "rag": "rag",
        "langchain": "langchain",
        "langgraph": "langgraph",
        "openai": "openai",
        "gpt": "gpt",
        "claude": "claude",
        "gemini": "gemini",
        "prompt": "prompt",
        "agent": "agent",
        "agente": "agent",
        "mcp": "mcp",
    }

    def __init__(self, profile: dict, curriculum_path: str | Path | None = None):
        self.profile = profile
        # Optional curriculum (path B): read on every classify() so a file save
        # takes effect without rebuilding the classifier. None => default path.
        self.curriculum_path = curriculum_path
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

    # Years-of-experience signals: real postings rarely write "Senior", they
    # write "5+ anos de experiência". Matched against the whole text.
    EXPERIENCE_PATTERN = re.compile(r"(\d{1,2})\s*\+?\s*(anos?|years?|yr)", re.IGNORECASE)
    # Seniority expressed as a level, so a posting saying "Chief" satisfies a
    # profile asking for "Staff" without the profile having to name every title.
    SENIORITY_LEVELS = {
        "intern": 0,
        "estágio": 0,
        "estagiário": 0,
        "junior": 1,
        "júnior": 1,
        "pleno": 2,
        "mid": 2,
        "senior": 3,
        "sênior": 3,
        "especialista": 3,
        "lead": 4,
        "líder": 4,
        "staff": 4,
        "coordenador": 4,
        "principal": 5,
        "chief": 5,
        "head": 5,
    }

    @staticmethod
    def _contains(text: str, term: str) -> bool:
        return term in text

    @staticmethod
    def _skill_in(text: str, skill: str) -> bool:
        """Word-boundary skill match: 'Go' must not fire on 'google'/'going'."""
        return re.search(rf"\b{re.escape(skill)}\b", text) is not None

    def _map_ptbr_title(self, title: str) -> str:
        """Map PT-BR job titles to EN equivalents for matching."""
        # Direct mapping
        if title in self.PTBR_TITLES:
            return self.PTBR_TITLES[title]

        # Partial mapping (check if any PT-BR keyword is in the title)
        for ptbr, en in self.PTBR_TITLES.items():
            if ptbr in title:
                return en

        return title

    def _map_ptbr_text(self, text: str) -> str:
        """Map PT-BR skills and terms to EN equivalents."""
        result = text
        for ptbr, en in self.PTBR_SKILLS.items():
            result = result.replace(ptbr, en)
        return result

    @property
    def _profile_seniority_floor(self) -> int:
        """Lowest level the profile accepts; 0 when nothing is configured."""
        levels = [self.SENIORITY_LEVELS[s] for s in self.seniority if s in self.SENIORITY_LEVELS]
        return min(levels) if levels else 0

    def _seniority_hits(self, text: str) -> list[str]:
        """Seniority signals, accent-insensitive and years-aware.

        A posting rarely writes the profile's exact word ("Senior"); PT-BR ads
        write "Sênior", "Chief", or "5+ anos de experiência". All count as long
        as they reach the profile's floor — "Pleno"/"Júnior" sit below it.
        """
        folded = self._fold(text)
        floor = self._profile_seniority_floor

        hits = [
            expected
            for expected in self.seniority
            if re.search(rf"\b{re.escape(expected)}\b", folded)
        ]
        if not hits:
            for word, level in self.SENIORITY_LEVELS.items():
                if level >= floor and re.search(rf"\b{re.escape(self._fold(word))}\b", folded):
                    hits.append(word)
                    break
        if not hits:
            years = [int(n) for n, _ in self.EXPERIENCE_PATTERN.findall(text)]
            if years and max(years) >= 5:
                hits.append("5+ anos de experiência")
        return hits

    def _curriculum_seniority(self, curriculum: Curriculum, matched_text: str) -> tuple[bool, bool]:
        """(requirement met, confrontable) for the candidate's verified seniority.

        Only signals when BOTH sides state something: a level or years asked by
        the posting vs. the level/years verified by the curriculum. The profile
        floor is never touched — this feeds `reasons` only.
        """
        if not curriculum.seniority and curriculum.years is None:
            return False, False

        folded = self._fold(matched_text)
        job_levels = [
            level
            for word, level in self.SENIORITY_LEVELS.items()
            if re.search(rf"(?<!\w){re.escape(self._fold(word))}(?!\w)", folded)
        ]
        job_years = [int(n) for n, _ in self.EXPERIENCE_PATTERN.findall(matched_text)]
        candidate_level = max(
            (
                self.SENIORITY_LEVELS[term]
                for term in curriculum.seniority
                if term in self.SENIORITY_LEVELS
            ),
            default=None,
        )

        checks = []
        if job_levels and candidate_level is not None:
            checks.append(candidate_level >= max(job_levels))
        if job_years and curriculum.years is not None:
            checks.append(curriculum.years >= max(job_years))
        if not checks:
            return False, False
        return all(checks), True

    def _curriculum_context(self, matched_text: str) -> tuple[list[str], bool]:
        """What the curriculum proves about this posting — narrative only.

        Returns (skills both sides share, seniority requirement met). These
        feed `reasons`/`gaps`; they never reach `WEIGHTS` (see the note there
        for the measurement that ruled out a score component). A missing file
        or no overlap => ([], False), so the classification is byte-identical to
        the pre-curriculum behaviour.
        """
        curriculum = load_curriculum(self.curriculum_path)
        if curriculum.version is None:
            return [], False

        shared = sorted(s for s in curriculum.skills if self._skill_in(matched_text, s))
        seniority_met, _ = self._curriculum_seniority(curriculum, matched_text)
        return shared, seniority_met

    def classify(self, job: dict) -> dict:
        title = self._norm(job.get("title", ""))
        description = self._norm(job.get("description", ""))
        text = f"{title} {description}"

        # Map PT-BR titles and skills to EN for matching. The original title
        # stays in the text: the mapping resolves the role, but words like
        # "Sênior" only exist in the source string.
        mapped_title = self._map_ptbr_title(title)
        mapped_description = self._map_ptbr_text(description)
        matched_text = f"{title} {mapped_title} {mapped_description}"

        matched_skills = sorted(
            skill for skill in self.skills if self._skill_in(matched_text, skill)
        )

        title_hits = [t for t in self.titles if t in mapped_title]
        seniority_hits = self._seniority_hits(matched_text)

        title_score = (
            min(100, 60 + 20 * len(title_hits))
            if title_hits
            else self._role_similarity(mapped_title)
        )
        seniority_score = 100 if seniority_hits else 50
        # A real posting names 2-4 skills; a denominator sized after the whole
        # profile (27 skills) would keep every score pinned in the low band.
        skill_denominator = max(1, min(5, len(self.skills)))
        skills_score = min(100, (len(matched_skills) / skill_denominator) * 100)

        cloud_terms = {"aws", "azure", "gcp", "cloud", "kubernetes", "terraform", "nuvem"}
        cloud_hits = [x for x in cloud_terms if self._skill_in(matched_text, x)]
        cloud_score = min(100, len(cloud_hits) * 25)

        experience_score = (
            100
            if seniority_hits
            else (70 if re.search(r"\b(senior|staff)\b", self._fold(matched_text)) else 50)
        )

        ai_terms = {
            "ai",
            "artificial intelligence",
            "llm",
            "rag",
            "langchain",
            "langgraph",
            "machine learning",
            "ia",
            "inteligência artificial",
            "aprendizado de máquina",
        }
        ai_hits = [x for x in ai_terms if self._skill_in(matched_text, x)]
        ai_score = min(100, len(ai_hits) * 25)

        remote = bool(job.get("remote")) or "remote" in matched_text or "remoto" in matched_text
        remote_score = 100 if (remote or not self.profile.get("remote_required", False)) else 0

        excluded = self.exclusion_hits(matched_text)
        # Context only: read after the score so it cannot influence it.
        curriculum_matches, curriculum_seniority_met = self._curriculum_context(matched_text)

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
        # The origin must be explicit: the frontend cannot present these as
        # profile findings. Curriculum context, never a score input.
        if curriculum_matches:
            reasons.append(f"Currículo confirma: {', '.join(curriculum_matches[:12])}")
        if curriculum_seniority_met:
            reasons.append("Currículo confirma: senioridade atende aos requisitos da vaga")
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

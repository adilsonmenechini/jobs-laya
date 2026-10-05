"""Markdown curriculum as a deterministic classifier signal (SPEC 202610051432).

Path B: the curriculum NEVER enters the Laya `job_state()` — the model reads
only the job. It is read here and turned into the `curriculum` score component
computed in code, after the forward pass (see `LayaInspiredClassifier`).

The file is optional (`data/curriculum.md`): missing or unreadable yields an
empty curriculum instead of raising (CA1/CA10). The version is the sha256 of
the CONTENT, never a timestamp — two saves of the same text keep one version.
"""

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

DEFAULT_PATH = "data/curriculum.md"

# Free-form markdown: skills are found by scanning the whole text (bullets and
# prose alike) for known terms, accent-insensitive and word-bounded. Aliases map
# to the canonical term the job description carries after the classifier's
# PT-BR mapping, so both sides of the crossing use the same spelling.
SKILL_VOCABULARY = {
    # cloud & infrastructure
    "aws": "aws",
    "amazon web services": "aws",
    "azure": "azure",
    "gcp": "gcp",
    "google cloud": "gcp",
    "cloud": "cloud",
    "nuvem": "cloud",
    "kubernetes": "kubernetes",
    "k8s": "kubernetes",
    "docker": "docker",
    "terraform": "terraform",
    "terragrunt": "terragrunt",
    "ansible": "ansible",
    "puppet": "puppet",
    "helm": "helm",
    "kustomize": "kustomize",
    "argocd": "argocd",
    "argo cd": "argocd",
    "flux": "flux",
    "openshift": "openshift",
    "rancher": "rancher",
    "nomad": "nomad",
    "consul": "consul",
    "vault": "vault",
    "packer": "packer",
    "vagrant": "vagrant",
    "eks": "eks",
    "gke": "gke",
    "aks": "aks",
    "vmware": "vmware",
    "openstack": "openstack",
    # observability
    "prometheus": "prometheus",
    "grafana": "grafana",
    "loki": "loki",
    "datadog": "datadog",
    "new relic": "new relic",
    "splunk": "splunk",
    "opentelemetry": "opentelemetry",
    "jaeger": "jaeger",
    "zabbix": "zabbix",
    "nagios": "nagios",
    "observability": "observability",
    "observabilidade": "observability",
    "monitoring": "monitoring",
    "monitoramento": "monitoring",
    # cicd & git
    "jenkins": "jenkins",
    "gitlab": "gitlab",
    "github": "github",
    "github actions": "github actions",
    "circleci": "circleci",
    "bitbucket": "bitbucket",
    "ci/cd": "ci/cd",
    "ci cd": "ci/cd",
    "pipeline": "pipeline",
    "pipelines": "pipeline",
    "devops": "devops",
    "sre": "sre",
    "git": "git",
    # security & policy
    "opa": "opa",
    "gatekeeper": "gatekeeper",
    "kyverno": "kyverno",
    "trivy": "trivy",
    "sonarqube": "sonarqube",
    # runtime & languages
    "linux": "linux",
    "bash": "bash",
    "shell": "shell",
    "python": "python",
    "go": "go",
    "golang": "go",
    "java": "java",
    "javascript": "javascript",
    "typescript": "typescript",
    "rust": "rust",
    "ruby": "ruby",
    # data
    "sql": "sql",
    "postgres": "postgres",
    "postgresql": "postgres",
    "mysql": "mysql",
    "mongodb": "mongodb",
    "redis": "redis",
    "kafka": "kafka",
    "rabbitmq": "rabbitmq",
    "elasticsearch": "elasticsearch",
    "spark": "spark",
    "hadoop": "hadoop",
    "airflow": "airflow",
    "dbt": "dbt",
    "snowflake": "snowflake",
    "databricks": "databricks",
    # ai & llm
    "machine learning": "machine learning",
    "deep learning": "deep learning",
    "llm": "llm",
    "rag": "rag",
    "langchain": "langchain",
    "langgraph": "langgraph",
    "crewai": "crewai",
    "openai": "openai",
    "gpt": "gpt",
    "claude": "claude",
    "gemini": "gemini",
    "ollama": "ollama",
    "pytorch": "pytorch",
    "tensorflow": "tensorflow",
    "mlops": "mlops",
    "agent": "agent",
    "agente": "agent",
    "mcp": "mcp",
    "prompt": "prompt",
    "ia": "ai",
    "inteligencia artificial": "ai",
    # api & delivery practices
    "api": "api",
    "rest": "rest",
    "graphql": "graphql",
    "microservices": "microservices",
    "microservicos": "microservices",
    "scrum": "scrum",
    "agile": "agile",
    "jira": "jira",
}

# Accent-stripped seniority claims the résumé can make. Every term is a key of
# `LayaInspiredClassifier.SENIORITY_LEVELS`, so the crossing can read levels.
SENIORITY_VOCABULARY = (
    "intern",
    "junior",
    "pleno",
    "mid",
    "senior",
    "especialista",
    "lead",
    "staff",
    "coordenador",
    "principal",
    "chief",
    "head",
)

YEARS_PATTERN = re.compile(r"(\d{1,3})\s*\+?\s*(?:anos|years?)", re.IGNORECASE)


@dataclass(frozen=True)
class Curriculum:
    """Parsed curriculum. `version is None` means the file is absent/unreadable."""

    version: str | None
    skills: frozenset[str]
    seniority: frozenset[str]
    years: int | None


EMPTY = Curriculum(version=None, skills=frozenset(), seniority=frozenset(), years=None)


def _fold(text: str) -> str:
    """Lowercase + strip accents so "Sênior"/"Kubernetes" match any spelling."""
    stripped = unicodedata.normalize("NFKD", text.lower())
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", stripped)


def _contains(folded_text: str, term: str) -> bool:
    """Word-boundary match that also works for terms ending in '/', '+', '.'."""
    return re.search(rf"(?<!\w){re.escape(term)}(?!\w)", folded_text) is not None


def read(path: str | Path | None = None) -> str:
    """Raw markdown, or "" when the file is absent/unreadable — never raises."""
    try:
        return Path(path or DEFAULT_PATH).read_text(encoding="utf-8")
    except OSError:
        return ""


def load(path: str | Path | None = None) -> Curriculum:
    """Parse the curriculum file into skills, seniority and content hash.

    Missing file => `EMPTY` (version None, no skills). Present file => version
    is the sha256 hex of the bytes on disk, even when nothing was extracted.
    """
    target = Path(path or DEFAULT_PATH)
    try:
        raw = target.read_bytes()
    except OSError:
        return EMPTY

    folded = _fold(raw.decode("utf-8", errors="replace"))
    skills = frozenset(
        canonical for alias, canonical in SKILL_VOCABULARY.items() if _contains(folded, alias)
    )
    seniority = frozenset(term for term in SENIORITY_VOCABULARY if _contains(folded, term))
    years = max((int(n) for n in YEARS_PATTERN.findall(folded)), default=None)
    return Curriculum(
        version=hashlib.sha256(raw).hexdigest(),
        skills=skills,
        seniority=seniority,
        years=years,
    )


def version(path: str | Path | None = None) -> str | None:
    """Content hash of the curriculum file; None when it does not exist."""
    return load(path).version

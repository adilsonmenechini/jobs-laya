"""The typed questions Laya answers about every job posting, in one forward pass.

Written to Laya's documented limits: every `noul` carries explicit criteria
(without them the English checkpoint answers "no" whatever the state), and
`choice` keys are descriptive, never yes/no words.
"""

QUESTIONS = {
    "role_family": {
        "type": "choice",
        "instructions": "What is the primary role of the job in `title` and `description`?",
        "criteria": {
            "site_reliability": (
                "keeps production systems running: reliability, incidents, on-call, SRE"
            ),
            "devops": "CI/CD, pipelines, automation, release engineering",
            "platform_cloud": (
                "internal developer platform, infrastructure as code, cloud, Kubernetes"
            ),
            "ai_ml": "machine learning, LLM or AI engineering work",
            "other": "a role outside infrastructure, reliability, platform or AI engineering",
        },
    },
    "remote": {
        "type": "noul",
        "instructions": "Is the job in `title` and `description` offered as fully remote?",
        "criteria": {
            "true": "fully remote, work from anywhere or home office",
            "false": "on-site or hybrid with required office days",
        },
    },
    "seniority": {
        "type": "score",
        "instructions": "How senior is the job in `title` and `description`?",
        "criteria": ["junior or mid level", "senior level", "staff, principal or lead level"],
    },
    "skill_fit": {
        "type": "noul",
        "instructions": (
            "Does the job in `description` match a profile of Kubernetes, Terraform, "
            "AWS, observability and scripting?"
        ),
        "criteria": {
            "true": (
                "it asks for cloud, infrastructure, Kubernetes, Terraform, IaC "
                "or observability skills"
            ),
            "false": "it asks for skills unrelated to infrastructure or reliability",
        },
    },
}


def job_state(job: dict, max_description_chars: int = 800) -> dict[str, str]:
    """The state Laya reads. Kept short: the English checkpoint reads ~320 tokens."""
    return {
        "title": str(job.get("title") or "")[:200],
        "company": str(job.get("company") or "")[:100],
        "location": str(job.get("location") or "")[:100],
        "workplace": "remote" if job.get("remote") else "on-site or hybrid",
        "description": str(job.get("description") or "")[:max_description_chars],
    }

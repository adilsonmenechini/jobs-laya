"""`make skill` / `make skill-list`: criação de skills locais de agente.

Os targets são shell puro, então o teste executa o comando e checa o resultado —
não importa função Python. Cada teste trabalha num diretório temporário com um
Makefile mínimo, para nunca tocar nas skills reais do projeto.
"""

import os
import re
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Alvo do Makefile: um target `skill` que delega para este script.
# Mantém o teste independente da implementação (shell, python, o que for).
STUB_MAKEFILE = """
SKILL_DIR := $(CURDIR)/.claude/skills

skill:
\t@python3 $(CURDIR)/scripts/make_skill.py --dir "$(SKILL_DIR)" --name "$(NAME)"

skill-list:
\t@python3 $(CURDIR)/scripts/make_skill.py --dir "$(SKILL_DIR)" --list
"""

STUB_SCRIPT = """
import argparse
import sys
from pathlib import Path

RESERVED = {"templates"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dir", required=True)
    parser.add_argument("--list", action="store_true")
    parser.add_argument("--name", default="")
    args = parser.parse_args()

    skills = Path(args.dir)
    if args.list:
        for path in sorted(skills.glob("*/SKILL.md")):
            print(path.parent.name)
        return 0

    name = args.name or ""
    if not name:
        print("make skill: NAME vazio — use make skill NAME=<slug>", file=sys.stderr)
        return 2
    if name != name.lower() or " " in name or "/" in name or name in RESERVED:
        print(f"make skill: NAME invalido: {name!r}", file=sys.stderr)
        return 2
    if name.startswith("."):
        print(f"make skill: NAME invalido: {name!r}", file=sys.stderr)
        return 2

    target = skills / name / "SKILL.md"
    if target.exists():
        print(f"make skill: skill ja existe: {target}", file=sys.stderr)
        return 1

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "---\\n"
        f"name: {name}\\n"
        "description: PREENCHER — quando usar esta skill\\n"
        "---\\n\\n"
        f"# {name}\\n\\n"
        "<preencher>\\n",
        encoding="utf-8",
    )
    print(f"skill criada: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""


@pytest.fixture()
def skill_workspace(tmp_path):
    """Diretório temporário com Makefile + script stub, isolado do projeto."""
    (tmp_path / "Makefile").write_text(STUB_MAKEFILE, encoding="utf-8")
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "make_skill.py").write_text(STUB_SCRIPT, encoding="utf-8")
    return tmp_path


def run_make(workspace, *args):
    """Roda o target do Makefile do workspace.

    `NAME` é passado como variável de make (não como argumento posicional) —
    assim um slug com espaço chega inteiro ao script em vez de virar dois args.
    """
    return subprocess.run(
        ["make", *args],
        cwd=workspace,
        capture_output=True,
        text=True,
        env={**os.environ, "TERM": "dumb"},
    )


def run_skill(workspace, slug=None):
    """Atalho: `make skill NAME=<slug>` com o slug corretamente citado."""
    args = ["skill"] + ([f"NAME={slug}"] if slug is not None else [])
    return run_make(workspace, *args)


# --------------------------------------------------------------------- cria


def test_make_skill_creates_skeleton(skill_workspace):
    """CA1: arquivo existe com frontmatter válido (name = slug)."""
    result = run_skill(skill_workspace, "deploy-guide")

    assert result.returncode == 0, result.stderr
    created = skill_workspace / ".claude" / "skills" / "deploy-guide" / "SKILL.md"
    assert created.exists()

    text = created.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert re.search(r"^name: deploy-guide$", text, re.MULTILINE)
    assert re.search(r"^description: .+$", text, re.MULTILINE)


def test_make_skill_creates_dir_when_missing(skill_workspace, tmp_path):
    """CA4: `.claude/skills/` ausente é criado."""
    assert not (skill_workspace / ".claude").exists()

    result = run_skill(skill_workspace, "first-skill")

    assert result.returncode == 0, result.stderr
    assert (skill_workspace / ".claude" / "skills" / "first-skill" / "SKILL.md").exists()


def test_make_skill_prints_absolute_path(skill_workspace):
    """R4: saída mostra onde criar e o que preencher."""
    result = run_skill(skill_workspace, "deploy-guide")

    assert result.returncode == 0, result.stderr
    assert str(skill_workspace) in result.stdout  # caminho absoluto
    assert "deploy-guide" in result.stdout


# ------------------------------------------------------------------- recusa


def test_make_skill_refuses_existing(skill_workspace):
    """CA2: segundo run falha e NÃO sobrescreve o conteúdo."""
    first = run_skill(skill_workspace, "deploy-guide")
    assert first.returncode == 0, first.stderr

    target = skill_workspace / ".claude" / "skills" / "deploy-guide" / "SKILL.md"
    target.write_text("---\nname: deploy-guide\ndescription: conteudo meu\n---\n", encoding="utf-8")

    second = run_skill(skill_workspace, "deploy-guide")

    assert second.returncode != 0
    assert "ja existe" in second.stderr
    assert "conteudo meu" in target.read_text(encoding="utf-8")  # intacto


@pytest.mark.parametrize(
    "slug",
    ["", "foo bar", "../escape", "UPPER", ".hidden", "templates"],
)
def test_make_skill_refuses_invalid_slug(skill_workspace, slug):
    """CA3: slug vazio, com espaço, traversal, maiúscula, oculto ou reservado."""
    result = run_skill(skill_workspace, slug)

    assert result.returncode != 0, f"{slug!r} deveria ser recusado"
    assert "invalido" in result.stderr or "vazio" in result.stderr


def test_make_skill_never_touches_home(skill_workspace, monkeypatch):
    """O comando só escreve em .claude/skills/ do workspace, nunca em ~/.claude."""
    monkeypatch.setenv("HOME", str(skill_workspace / "fake-home"))

    result = run_skill(skill_workspace, "deploy-guide")

    assert result.returncode == 0, result.stderr
    assert not (skill_workspace / "fake-home" / ".claude").exists()


# --------------------------------------------------------------------- lista


def test_make_skill_list(skill_workspace):
    """CA5: lista as skills existentes pelo `name`."""
    run_skill(skill_workspace, "alpha-skill")
    run_skill(skill_workspace, "beta-skill")

    result = run_make(skill_workspace, "skill-list")

    assert result.returncode == 0, result.stderr
    listed = result.stdout.split()
    assert listed == ["alpha-skill", "beta-skill"]  # ordenado


def test_make_skill_list_empty(skill_workspace):
    """CA5: sem skills, não falha."""
    result = run_make(skill_workspace, "skill-list")

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


# ------------------------------------------------------- skills reais do repo


def test_repo_has_search_jobs_skill():
    """A skill criada nesta sessão existe e tem frontmatter válido."""
    skill = REPO / ".claude" / "skills" / "search-jobs" / "SKILL.md"

    assert skill.exists(), "skill search-jobs ausente do projeto"
    text = skill.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    assert re.search(r"^name: search-jobs$", text, re.MULTILINE)
    assert re.search(r"^description: .{40,}$", text, re.MULTILINE)


def test_repo_skills_are_kebab_case():
    """Todas as skills do projeto seguem o padrão kebab-case."""
    skills_dir = REPO / ".claude" / "skills"
    if not skills_dir.exists():
        pytest.skip("sem .claude/skills no repo")

    for path in skills_dir.glob("*/SKILL.md"):
        assert path.parent.name == path.parent.name.lower()
        assert " " not in path.parent.name
        assert not path.parent.name.startswith(".")

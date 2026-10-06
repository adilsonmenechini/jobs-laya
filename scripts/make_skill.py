"""Cria e lista skills locais de agente (.claude/skills/).

Chamado pelo Makefile:

    make skill NAME=<slug>     # cria o esqueleto de uma skill
    make skill-list            # lista as skills do projeto

Somente escreve em `.claude/skills/` do projeto — nunca em `~/.claude/`,
nunca no código. O `description` do frontmatter é placeholder: quem escreve o
corpo é o agente.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

RESERVED = {"templates", "models", "_partials"}
KEBAB = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

SKELETON = """\
---
name: {name}
description: PREENCHER — quando usar esta skill (o agente le isto para decidir se a aciona)
---

# {name}

## When to Use
<preencher: que pedido faz esta skill ser acionada, e quando NAO usar>

## How to Apply
<preencher: passos, comandos, formato de saida>

## Gotchas
<preencher: o que ja deu errado e como evitar>
"""


def fail(message: str) -> int:
    print(f"make skill: {message}", file=sys.stderr)
    return 2


def create(skills_dir: Path, name: str) -> int:
    if not name:
        return fail("NAME vazio — use make skill NAME=<slug>")
    if not KEBAB.match(name):
        return fail(
            f"NAME inválido: {name!r} — use kebab-case minúsculo "
            "(ex.: deploy-guide); sem espaços, barra, ponto ou maiúscula"
        )
    if name in RESERVED:
        return fail(f"NAME reservado: {name!r}")

    target = skills_dir / name / "SKILL.md"
    if target.exists():
        return fail(f"skill já existe: {target} (não sobrescrevo — edite o arquivo)")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(SKELETON.format(name=name), encoding="utf-8")
    print(f"skill criada: {target}")
    print("próximo passo: preencher description (frontmatter) e as seções do corpo.")
    return 0


def list_skills(skills_dir: Path) -> int:
    if not skills_dir.is_dir():
        print(f"nenhuma skill em {skills_dir}")
        return 0
    for path in sorted(skills_dir.glob("*/SKILL.md")):
        print(path.parent.name)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", required=True, help="diretório .claude/skills")
    parser.add_argument("--list", action="store_true", help="lista as skills")
    parser.add_argument("--name", default="", help="slug da skill a criar")
    args = parser.parse_args()

    skills_dir = Path(args.dir).expanduser().resolve()
    if args.list:
        return list_skills(skills_dir)
    if not args.name:
        return fail("falta NAME — use make skill NAME=<slug>")
    return create(skills_dir, args.name)


if __name__ == "__main__":
    raise SystemExit(main())

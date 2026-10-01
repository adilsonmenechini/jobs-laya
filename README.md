# LinkedIn Job Classifier

MVP local para:

1. buscar vagas no **LinkedIn** (browser local, Patchright) e no **GeekHunter**
   (HTTP público, sem login);
2. obter detalhes;
3. normalizar e deduplicar;
4. classificar contra um perfil profissional;
5. salvar em SQLite;
6. listar e filtrar pela API.

A arquitetura usa **Laya de verdade** (o modelo de decisões tipadas da ConvAI,
`laya[serve]`): o classifier combina as respostas `choice`, `score` e `noul`
do modelo com sinais determinísticos (skills, senioridade, remoto) numa
política local — probabilidades calibradas em vez de geração livre.

## Stack

- Python 3.13+
- FastAPI
- SQLAlchemy
- SQLite
- Pydantic
- Laya (`laya[serve]`) + torch/transformers
- Patchright (Chromium local)
- BeautifulSoup
- pytest
- ruff

## 1. Instalar

```bash
make install
```

ou manualmente:

```bash
uv sync --extra dev
uv run patchright install chromium
```

## 2. Login do LinkedIn (uma vez)

O projeto usa um browser local próprio (Patchright). Rode:

```bash
make login
# equivalente a: uv run python -m app.linkedin.login
```

Uma janela do Chromium abre na página de login do LinkedIn. Faça login ali —
suas credenciais vão direto para o navegador, nunca passam por este código.
A sessão fica salva no perfil persistente `~/.linkedin-laya/profile/` e é
reusada por todas as chamadas seguintes. Repita o `make login` só se o cookie
`li_at` expirar.

## 3. Rodar a API

```bash
make run
# equivalente a: uv run uvicorn app.main:app --reload --port 3080
```

Dashboard (frontend estático servido pela própria API):

<http://localhost:3080/>

Ele lista as vagas classificadas com score, probabilidades, motivos e gaps,
filtros (fonte/match/remoto/score/texto) e o formulário **Buscar e classificar**
que dispara o sync (com seletor de fonte: LinkedIn, GeekHunter ou todas).
O badge no topo mostra o backend do classifier.

Swagger:

<http://localhost:3080/docs>

## 4. Perfil e classificador

O perfil padrão está em `data/profile.json`. Altere os títulos, senioridade,
skills, cloud e preferências de remoto.

O backend do classifier é escolhido por `CLASSIFIER_BACKEND`:

| Valor | O que é |
|---|---|
| `laya` (default) | Laya real via `laya[serve]` — 4 perguntas tipadas em 1 forward pass, combinadas com os sinais heurísticos. A **primeira classificação baixa o checkpoint (~800MB)** do Hugging Face. |
| `fake` | Mesma política, mas com `FakeEngine` determinístico (keywords) — pipeline completo sem modelo. |
| `heuristic` | Só a heurística antiga (`LayaInspiredClassifier`), sem modelo. |

Device automático (`cuda` > `mps` > `cpu`); pode fixar com `LAYA_DEVICE`.
Se o engine falhar, a classificação **cai para a heurística automaticamente**
e o motivo fica registrado em `decision.laya.error` — nunca perde o veredito.

Perguntas do Laya (todas em um passe, em `app/classifier/questions.py`):

- `role_family` (choice): site_reliability / devops / platform_cloud / ai_ml / other
- `remote` (noul): é vaga remota?
- `seniority` (score): junior/mid → senior → staff/principal
- `skill_fit` (noul): casa com o perfil de infra/Kubernetes/Terraform/cloud?

`GET /health` mostra `{backend, laya_ready, device}` — o modelo só carrega no
primeiro uso, nunca no startup (mantém boot e testes sem download).

## 5. Fontes (LinkedIn e GeekHunter)

O sync suporta `source: "linkedin" | "geekhunter" | "all"` (default `linkedin`):

| Fonte | Backend | Login | Notas |
|---|---|---|---|
| `linkedin` | browser local (Patchright) | `make login` uma vez | mesmo comportamento de sempre |
| `geekhunter` | HTTP público (`httpx`) + JSON-LD | não precisa | sem browser; delay configurável |
| `all` | roda as duas | — | falha de uma fonte não derruba a outra; o response traz `errors` por fonte |

```bash
curl -X POST http://localhost:3080/jobs/sync \
  -H 'Content-Type: application/json' \
  -d '{"keywords": ["SRE"], "source": "geekhunter", "limit": 10}'
# {"synced": 10, "errors": {}}
```

Deduplicação é por `(source, source_id)` — a mesma vaga re-sincronizada
atualiza, nunca duplica, e o mesmo `source_id` de fontes diferentes convive
no mesmo banco. Filtro na listagem: `GET /jobs?source=geekhunter`.

Config do GeekHunter (`.env`):

```text
GEEKHUNTER_BASE_URL=https://www.geekhunter.com
GEEKHUNTER_DELAY_SECONDS=1.0
GEEKHUNTER_PAGE_SIZE=25
GEEKHUNTER_TIMEOUT_S=30.0
```

Os dados vêm do JSON-LD das páginas públicas (`ItemList` na listagem,
`JobPosting` no detalhe), com fallback para o DOM renderizado. Somente
leitura: nenhuma tool de escrita em nenhuma fonte.

## 6. Buscar vagas

```bash
curl -X POST http://localhost:3080/jobs/sync \
  -H 'Content-Type: application/json' \
  -d '{
    "keywords": ["SRE", "DevOps", "Platform Engineer", "AI Engineer"],
    "location": "Brazil",
    "limit": 25,
    "fetch_details": true
  }'
```

A resposta informa quantas vagas foram coletadas e classificadas, mais um
mapa `errors` por fonte (vazio quando tudo funcionou):

```json
{"synced": 25, "errors": {}}
```

## 7. Listar

```bash
curl "http://localhost:3080/jobs?match=high&limit=20"
```

Outros filtros:

```text
GET /jobs
GET /jobs?match=medium
GET /jobs?remote=true
GET /jobs?query=kubernetes
GET /jobs?min_score=70
GET /jobs?source=geekhunter
GET /jobs/{job_id}
GET /profile
GET /health
```

## 8. Tools locais do LinkedIn (read-only)

A API expõe uma camada de *tools* locais modelada no catálogo do
[`stickerdaniel/linkedin-mcp-server`](https://github.com/stickerdaniel/linkedin-mcp-server),
mas com backend 100% local: browser Patchright controlado por este projeto,
**sem MCP e sem scraping separado**. Escopo atual: **somente leitura de vagas**
— nenhuma tool de escrita (mensagens, conexões, candidaturas). Navegações são
sequenciais, com delay configurável (`LINKEDIN_DELAY_SECONDS`) para reduzir
risco de bloqueio.

```bash
# descoberta (name, description, input_schema)
curl http://localhost:3080/tools

# search_jobs(keywords, location, limit)
curl -X POST http://localhost:3080/tools/search_jobs \
  -H 'Content-Type: application/json' \
  -d '{"keywords": "SRE", "location": "Brazil", "limit": 10}'

# get_job_details(job_id)
curl http://localhost:3080/tools/get_job_details/1234567890

# get_saved_jobs(limit)
curl "http://localhost:3080/tools/get_saved_jobs?limit=10"
```

Comportamento de erro: `422` entrada inválida, `404` vaga inexistente,
`502` falha do backend (browser/sessão LinkedIn indisponível).

Os tools são puros (não gravam no SQLite) — para persistir e classificar, use
`POST /jobs/sync`.

## 9. Testes, linter e pre-commit

```bash
make test
make lint
```

`make install` já registra os hooks do git (senão, `make hooks`). A cada
`git commit` roda, nesta ordem:

1. higiene (`pre-commit-hooks`): whitespace, EOF, yaml/toml válidos,
   arquivos >500KB, detecção de chave privada;
2. `ruff check --fix` + `ruff format` (mesma versão do projeto, `v0.16.9`);
3. `bandit -r app -ll` — análise de segurança estática (achados médios+;
   neste momento: 0 achados no `app/`);
4. `gitleaks git --staged --redact` — caça a segredos no diff staged
   (usa o binário do `brew install gitleaks`; precisa estar no PATH);
5. `pytest -q` — a suíte roda em ~0.5s (DB temporário e `FakeEngine`,
   sem download de modelo e sem browser).

Rodar manualmente sobre tudo:

```bash
uv run pre-commit run --all-files
```

## Estrutura

```text
.
├── CLAUDE.md
├── README.md
├── Makefile
├── pyproject.toml
├── .env.example
├── data/
│   └── profile.json
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── models.py
│   ├── schemas.py
│   ├── static/               # dashboard (index.html, app.js, style.css)
│   ├── classifier/
│   │   ├── __init__.py       # build_classifier (laya | fake | heuristic)
│   │   ├── laya_classifier.py    # heurístico (fallback)
│   │   ├── laya_job_classifier.py # política Laya + sinais
│   │   ├── engine.py         # LayaEngine / FakeEngine (protocol Engine)
│   │   └── questions.py      # perguntas tipadas choice/noul/score
│   ├── linkedin/
│   │   ├── browser.py
│   │   ├── errors.py
│   │   ├── local_client.py
│   │   ├── login.py
│   │   ├── parsing.py
│   │   ├── scrape.py
│   │   └── tools.py
│   ├── sources/               # providers pluggables (Protocol JobSource)
│   │   ├── __init__.py        # build_sources (registry injetável)
│   │   ├── base.py            # JobSource + SourceUnavailableError
│   │   ├── linkedin.py        # adapter do LinkedInBrowserClient
│   │   └── geekhunter.py      # httpx + BeautifulSoup/JSON-LD (sem login)
│   └── services/
│       └── jobs.py            # sync dispatcher por fonte + listagem
└── tests/
    ├── fixtures/            # HTML de exemplo dos parsers
    ├── test_classifier.py
    ├── test_laya_job_classifier.py
    ├── test_dashboard.py
    ├── test_api.py
    ├── test_tools.py
    ├── test_api_tools.py
    ├── test_scrape.py
    ├── test_sources.py
    ├── test_geekhunter.py
    ├── test_geekhunter_source.py
    ├── test_jobs_source.py
    ├── test_sync_dispatcher.py
    ├── test_db_migration.py
    └── test_browser_client.py
```

## Limitações do MVP

- A integração LinkedIn depende de uma sessão autenticada do usuário
  (`make login`); o perfil da sessão vive fora do repo em `~/.linkedin-laya/`.
  O GeekHunter não precisa de login (HTTP público).
- O LinkedIn proíbe acesso automatizado — use com moderação e por conta própria.
  O GeekHunter também é acessado com delay configurável
  (`GEEKHUNTER_DELAY_SECONDS`); respeite o robots/termos de uso.
- O classifier usa o modelo Laya real quando `CLASSIFIER_BACKEND=laya` (default),
  com fallback automático para a heurística local; os thresholds (80/60) são
  escolhas de política, não probabilidades calibradas para contratação.
- O score é aderência ao perfil configurado — não é garantia de contratação.
- Conteúdo do GeekHunter é em PT-BR: skills/sênioridade podem mapear
  diferente do LinkedIn para o mesmo perfil.
- Não há candidatura automática (nenhuma fonte tem tool de escrita).

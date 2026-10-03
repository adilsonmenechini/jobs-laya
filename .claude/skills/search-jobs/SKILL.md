---
name: search-jobs
description: Buscar, coletar e filtrar vagas de emprego neste repositório via API local — sincronizar fontes (LinkedIn, GeekHunter, Gupy, Indeed, Glassdoor), listar/classificar vagas contra o perfil, inspecionar por que uma vaga recebeu low/medium/high, ou rodar o eval do classificador. Use quando o pedido for sobre vagas, sync, filtros de vaga, score/match, ou "buscar/achar vagas de X".
---

# Search Jobs

Interface de leitura do `job-classifier`: coleta vagas de 5 fontes, classifica
contra `data/profile.json` e serve por HTTP. **Somente leitura** — não existe
nenhum caminho de escrita nas fontes (sem candidatura, mensagem ou conexão).

## 1. Subir a API

```bash
make run          # uvicorn app.main:app --reload --port 3080
```

Dashboard em <http://localhost:3080/> · Swagger em `/docs`.

Se a API já estiver no ar, confirme com `GET /health` — ele reporta as fontes
configuradas, o backend do classifier e se o modelo Laya já carregou. **Não**
instancie clientes ou modelos por conta própria: `/health` existe justamente
para isso ficar barato.

## 2. Coletar vagas (sync)

```bash
curl -X POST http://localhost:3080/jobs/sync \
  -H 'Content-Type: application/json' \
  -d '{"keywords": ["SRE", "DevOps"], "location": "Brazil", "limit": 10,
       "source": "all", "fetch_details": true, "hours_old": 168}'
# → {"synced": 10, "errors": {}}
```

| Campo | Valores | Nota |
|---|---|---|
| `source` | `linkedin` `geekhunter` `gupy` `indeed` `glassdoor` `all` | default `all` |
| `hours_old` | `0` (sem filtro) · `24` · `72` · `168` · `720` | `0` mantém tudo |
| `fetch_details` | `true`/`false` | `true` = mais lento, descrição completa |
| `location` | livre — `Brazil`, cidade, `remoto` | mapeado por fonte |

**Falha parcial é normal.** Uma fonte indisponível volta em `errors` com HTTP
200; as demais continuam. Fonte desconhecida → 503. Só leia `errors` quando
precisar saber *qual* fonte falhou — nunca assuma que o sync inteiro falhou
porque veio `errors`.

`linkedin` exige sessão autenticada: `make login` uma vez. As outras quatro
não precisam de login.

## 3. Listar e filtrar

```bash
curl "http://localhost:3080/jobs?match=high&remote=true&min_score=80&limit=20"
curl "http://localhost:3080/jobs?location=sao paulo"
curl "http://localhost:3080/jobs?source=gupy&query=kubernetes"
```

| Filtro | Tipo |
|---|---|
| `match` | `high` \| `medium` \| `low` |
| `source` | mesma lista do sync |
| `remote` | `true` \| `false` |
| `location` | substring de cidade/país (case-insensitive) |
| `min_score` | 0–100 |
| `query` | substring em título, empresa ou descrição |
| `limit` / `offset` | até 200 |

Ordem fixa: **mais novo primeiro**, `score` quebrando empate. Nunca reordene
no cliente — a ordenação não é parâmetro.

## 4. Ler o veredito

Cada vaga traz `match`, `score`, `decision`, `reasons` e `gaps`:

- **`match`/`score`** — `high ≥ 80`, `medium ≥ 60`, `low` abaixo. Os thresholds
  são **escolha de política, não probabilidades calibradas**; o score mede
  aderência ao perfil configurado, não chance de contratação.
- **`reasons`** — o que a vaga tem de bom (skills encontradas, remoto, cargo).
- **`gaps`** — o que faltou. É a primeira coisa a ler para entender um `low`.
- **`decision.excluded`** — dealbreaker do perfil (`exclusions` em
  `data/profile.json`, ex.: "inglês fluente"). Quando `value: true` o score é
  **forçado a ≤ 49 e o match vira `low`**, independente de todo o resto.
- **`decision.laya`** — backend, modelo e latência. Se `backend: "heuristic"`,
  o modelo falhou e o veredito veio só da heurística.

### Antes de afirmar que uma vaga é ruim

Rode `GET /jobs/{id}` e leia `gaps`. Um `low` por "Poucas skills do perfil
foram encontradas" é diferente de um `low` por dealbreaker: o primeiro se
descreve como baixa aderência ao perfil, o segundo é recusa.

## 5. Perfil

`GET /profile` devolve `titles`, `seniority`, `skills`, `focus`,
`remote_required`, `exclusions`.

O campo **`focus` é declarado mas nunca lido pelo matching** — quem decide é
`titles`. Não baseie uma resposta em `focus` sem conferir `titles` também.

## 6. Eval do classificador

```bash
uv run python eval/evaluate_real.py --backend fake    # sem download, ~1s
uv run python eval/evaluate.py --backend fake         # 18 samples sintéticos
```

Relatório em `eval/evaluation_real.md`. **Não misture os dois números**: são
datasets distintos (67 vagas reais vs 18 sintéticas).

Estado conhecido (2026-10-03): heurística 38/67 · `high` 17/35 · `low` 16/20.
O score **discrimina mal as classes** — medianas sobrepostas (high 51.8 /
low 41.6). Não afirme que o classifier é preciso sem citar esses números.

## Cuidados

- **Nunca** trate `synced` como número de vagas *novas*: é o total processado;
  a deduplicação por `(source, source_id)` faz re-sync atualizar, não duplicar.
- **Não** invente `errors` — só o que o response trouxer.
- Descrições da Gupy abrem com texto de marketing da empresa e os requisitos
  vêm depois; não conclua "vaga sem requisitos" olhando só o começo do texto.

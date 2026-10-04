# PENDENTE DE AI MEMORY — 202610032156

AI Memory indisponível nesta sessão (0 recursos MCP expostos, verificado via
`list_mcp_resources`). Conteúdo que seria gravado lá, para sincronizar quando o
serviço voltar (§7 do CLAUDE.md):

## Decisão arquitetural: `/health` reporta config, card reporta fato

- `/health.classifier.backend` lê `settings.classifier_backend` → é a
  **configuração vigente** do processo.
- `decision.laya.backend` no card é **persistido** na hora da classificação.
- São respostas diferentes a perguntas diferentes; o dashboard as apresentava
  lado a lado sem rotular, o que parecia contradição.

## Gotcha: `decision.laya.backend` era hardcoded

`app/classifier/laya_job_classifier.py` escreve `"backend": "laya"` fixo, até
para `FakeEngine`. Reproduzido: sync com `CLASSIFIER_BACKEND=fake` grava
`backend=laya, model=fake`. `model` vem do engine, `backend` não.

## Aula: não confundir dado velho com defeito

Ao investigar "badge vs card", a primeira query pegou a linha errada e o
resultado parecia mostrar engine real rodando onde era fake. A causa era
`updated_at` em UTC (SQLite) vs `datetime.now()` local (UTC-3). Verificar o
timestamp da linha inspecionada antes de concluir.

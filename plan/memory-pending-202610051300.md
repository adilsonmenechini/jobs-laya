# MEMORY PENDING — 202610051300

AI Memory indisponível em 2026-10-05 (CLI `ai-memory` 2.5.2: servidor em
`127.0.0.1:49374` responde 405 em `/admin/write-page`; spool local com 4243
eventos pendentes há 2+ dias). Conteúdo a sincronizar quando o serviço
voltar — depois de sync, deletar este arquivo.

Páginas a criar (rascunho completo em `plan/tasks/lessons-202610051300.md`):

1. `lessons/parallel-sessions-tree-and-timestamp.md` (kind: gotcha)
   — Timestamp e working tree são recursos compartilhados entre sessões
   paralelas: checar `git status`/branch/mtimes/`plan/sdd/spec-<TS>.md`
   antes de iniciar; havendo colisão, worktree isolado + timestamp novo
   com confirmação do usuário; nunca checkout/stash na tree ocupada.

2. `lessons/resource-leak-fix-must-cover-error-paths.md` (kind: rule)
   — Leak "cria e nunca libera" mapeia TODOS os caminhos de saída
   (sucesso, 503/config, exceção, timeout); quem constrói fecha
   (`try/finally` + ownership: injetado ≠ construído). Caso vivido:
   `resolve_sources` construía o registry e o descartava no raise de 503.

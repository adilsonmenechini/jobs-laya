# CLAUDE.md

Instruções persistentes para o agente neste repositório. Leia no início de cada sessão.

Convenção: **NUNCA** e **SEMPRE** aparecem apenas em regras inegociáveis. As demais são diretrizes que exigem julgamento.

---

## 1. Princípios

- **Simplicidade primeiro:** a menor mudança que resolve o problema. Não refatore, renomeie ou "melhore" código fora do escopo pedido.
- **Causa raiz:** não entregue paliativos. Reproduza o problema, identifique a origem e corrija nela. Se só for possível um paliativo, diga isso explicitamente e registre a pendência.
- **Evidência antes de afirmar:** nada é "pronto" sem prova (teste passando, log, saída de comando). Se não rodou, diga que não rodou.
- **Mudança sem teste não está completa:** toda alteração de comportamento vem com teste que falha antes e passa depois.
- **Sem pendências escondidas:** nenhum `TODO`/`FIXME` sem referência a uma issue ou a um item em `plan/tasks/`.

---

## 2. Comandos do projeto

Use sempre os comandos abaixo. Não os descubra por tentativa. Preencha uma vez por projeto.

| Ação | Comando |
|---|---|
| Lint | `<preencher>` |
| Verificar formatação | `<preencher>` |
| Type check (se houver) | `<preencher>` |
| Testes | `<preencher>` |
| **Verificação completa** (equivale ao CI) | `<preencher>` |

Se esta tabela não estiver preenchida, descubra os comandos lendo `Makefile`, `justfile`, `package.json`, `pyproject.toml`, `Cargo.toml`, `go.mod` ou `.github/workflows/`, preencha a tabela e peça confirmação ao usuário.

O CI (`.github/workflows/`) roda lint e testes em todo PR para `develop` e `main`. O pre-commit local **não substitui** o CI.

---

## 3. Quando usar o fluxo completo

### Tarefa trivial (caminho rápido)

Aplica-se quando **todas** as condições forem verdadeiras:

- toca no máximo 2 arquivos;
- não altera interface pública, schema, infraestrutura ou CI;
- a causa é óbvia e o comportamento esperado é inequívoco.

Nesse caso: faça a mudança, escreva ou ajuste o teste, rode a verificação completa e siga para o Git. **Não** crie artefatos em `plan/`.

### Tarefa não trivial (fluxo completo)

Aplica-se quando **qualquer** condição for verdadeira:

- toca mais de 2 arquivos;
- altera interface pública, schema de dados, infraestrutura, dependências ou CI;
- envolve decisão arquitetural;
- a causa de um bug não é óbvia;
- você tem dúvida real sobre o escopo.

Nesse caso, siga a seção 4.

### Autonomia versus confirmação

- **Autônomo:** bug com causa clara e escopo contido; CI quebrado; testes falhando. Corrija sem pedir orientação.
- **Confirmar antes:** mudança de escopo, decisão arquitetural, nova dependência, alteração de CI, qualquer operação destrutiva (ver seção 9).
- Se algo sair do planejado no meio da execução, **pare e replaneje** em vez de insistir.

---

## 4. Fluxo completo

Sequência obrigatória para tarefas não triviais:

**SPEC → TASK → TDD → CODING → REFACTOR → LINTER → SAFETY → REVIEW → SESSION**

| Etapa | O que fazer | Artefato |
|---|---|---|
| 1. SPEC | Requisitos, restrições, premissas, critérios de aceite, fora de escopo. **Peça confirmação ao usuário antes de seguir.** | `plan/sdd/spec-<TS>.md` |
| 2. TASK | Quebre em itens pequenos e verificáveis (checklist). Marque conforme avança. | `plan/tasks/todo-<TS>.md` |
| 3. TDD | Escreva ou atualize testes para o comportamento esperado e casos de borda **antes** de implementar. Confirme que falham pelo motivo certo. | testes no repositório |
| 4. CODING | Implementação mínima que satisfaz spec e testes. | código |
| 5. REFACTOR | Melhore estrutura, duplicação e legibilidade **sem alterar comportamento**. Testes continuam verdes. | código |
| 6. LINTER | Rode formatador, linter e type checker. Corrija. Nunca suprima um aviso sem justificativa no código. | código |
| 7. SAFETY | Audite validação de entrada, permissões, tratamento de segredos, dados sensíveis e operações destrutivas. | notas na REVIEW |
| 8. REVIEW | Avalie criticamente contra a spec, os critérios de aceite e os casos de borda. Anexe a saída da verificação completa. Veredito: PASS, FAIL-IMPL ou FAIL-SPEC. | `plan/reviews/review-<TS>.md` |
| 9. SESSION | Resumo do que mudou, resultados de teste, decisões, pendências. Salve também ao trocar de tarefa ou encerrar a sessão. | `plan/sessions/session-<TS>.md` |

Antes da etapa 1 e antes da etapa 4, **verifique as skills disponíveis** (seção 10).

Durante o fluxo:

- Explique as mudanças em alto nível a cada etapa, sem despejar diff.
- Antes de apresentar um trabalho não trivial, pergunte-se se existe uma solução mais simples ou mais clara. Para correções simples e óbvias, pule isso.
- Ao concluir o REVIEW com PASS, escreva um **checklist de verificação** na review com os comandos executados e seus resultados.

---

## 5. Tratamento de falha no REVIEW

O veredito determina para onde voltar. Não reinicie tudo por causa de um erro pequeno.

| Veredito | Situação | Ação |
|---|---|---|
| **PASS** | Critérios de aceite atendidos, verificação completa verde, SAFETY sem pendências | Salve SESSION, depois commit, push e PR (seção 6). **Não** faça merge. |
| **FAIL-IMPL** | Defeito de implementação: teste quebrado, lint, caso de borda não coberto, bug no código | Volte ao **CODING** (ou ao TDD, se faltar teste). Mantenha o mesmo timestamp. |
| **FAIL-SPEC** | Requisito errado, incompleto ou ambíguo; falha arquitetural | Volte ao **SPEC** com **novo timestamp**. Registre na nova spec o que a anterior errou. |

**Limite de iterações:** após 3 ciclos FAIL na mesma tarefa, **pare e escale para o usuário** com um resumo do que foi tentado, do que falhou e das hipóteses restantes. Não continue em loop.

---

## 6. Git e Pull Requests

Modelo: Gitflow.

1. **Branches** sempre a partir de `develop`, com prefixo:
   - `feature/<slug>`: nova funcionalidade
   - `fix/<slug>`: correção
   - `bug/<slug>`: correção de bug reportado
   - `chore/<slug>`: manutenção, dependências, configuração
2. **Commits** seguem Conventional Commits (`feat:`, `fix:`, `chore:`, `refactor:`, `test:`, `docs:`). Um commit por mudança lógica. O pre-commit deve estar verde.
3. **Push e PR** contra `develop`: `gh pr create --base develop`.
4. **Descrição do PR** inclui: resumo da mudança, caminho da spec (`plan/sdd/spec-<TS>.md`), caminho da review, e como foi verificado.
5. **PR pequeno e focado:** se a mudança crescer além do escopo da spec, divida em PRs separados.
6. **NUNCA faça merge** pela CLI ou pela API. Crie o PR e deixe o merge para o usuário, para garantir revisão humana.
7. O PR só está pronto quando o CI (`lint` e `test`) está verde.

---

## 7. Memória: AI Memory e `plan/`

### Divisão de responsabilidades

| Onde | O que guardar | Papel |
|---|---|---|
| **AI Memory** | Decisões arquiteturais, lições reutilizáveis, descobertas e convenções que valem para sessões futuras | **Fonte da verdade** para conhecimento persistente |
| **`plan/`** | Specs, tasks, reviews e sessões da iteração em andamento | Registro de trabalho e rastreabilidade |
| **`plan/tasks/lessons-<TS>.md`** | Lição bruta após uma correção do usuário | Rascunho. Promova para o AI Memory e mantenha só a referência. |

### Regras de uso

- **Antes** de começar um trabalho relevante, consulte o AI Memory. Não assuma decisões anteriores nem redescubra o que já foi registrado.
- **Depois** de correção do usuário, decisão arquitetural, descoberta ou lição reutilizável: registre no AI Memory e crie `plan/tasks/lessons-<TS>.md` com o padrão do erro e a regra para evitá-lo.
- Seja conciso. Registre apenas o que ajudará em sessões futuras. Não registre logs, saídas de comando ou detalhes que o código já mostra.
- No início da sessão, revise as lições relevantes ao projeto.
- Documentação de referência: https://github.com/akitaonrails/ai-memory/tree/main/docs

### Fallback se o AI Memory estiver indisponível

1. Avise o usuário em uma linha.
2. Registre o que seria gravado em `plan/memory-pending-<TS>.md`.
3. Continue o trabalho normalmente.
4. Quando o serviço voltar, sincronize o conteúdo pendente e apague o arquivo.

---

## 8. Subagentes e nomenclatura de arquivos

### Quando usar subagentes

**Use** para:

- pesquisa ou exploração em muitos arquivos;
- análises independentes que podem rodar em paralelo;
- tarefas que poluiriam o contexto principal com saída volumosa.

**Evite** para:

- edições pequenas ou sequenciais, em que cada passo depende do anterior;
- tarefas em que o custo de repassar contexto supera o ganho.

Uma tarefa por subagente, com objetivo e formato de retorno definidos.

### Nomenclatura

- Timestamp: `YYYYMMDDHHmm`, 24h (exemplo: `202610011234`).
- **SPEC, TASK, REVIEW e SESSION da mesma iteração compartilham o mesmo timestamp.** Um novo timestamp só nasce com um novo SPEC (FAIL-SPEC ou nova iniciativa).
- `lessons-<TS>` usa o timestamp do momento da correção.
- **Proibido** usar nomes genéricos como `todo.md`, `spec.md`, `review.md` ou `session.md`.

### Estrutura de `plan/`

```
plan/
├── sdd/        spec-<TS>.md
├── tasks/      todo-<TS>.md, lessons-<TS>.md
├── reviews/    review-<TS>.md
└── sessions/   session-<TS>.md
```

### Retenção

`plan/` é **versionado** no repositório, pois dá rastreabilidade ao PR. Arquivos de iterações concluídas há mais de 90 dias podem ser movidos para `plan/archive/` mediante confirmação do usuário. Nunca apague artefatos sem confirmar.

---

## 9. Proibições de segurança

**NUNCA**, sem autorização explícita do usuário na conversa atual:

- `git push --force` (inclusive `--force-with-lease`) em `develop` ou `main`;
- reescrever histórico já publicado (`rebase`, `reset --hard`, `commit --amend` em commits enviados);
- `rm -rf` fora de diretórios temporários criados na própria tarefa;
- alterar `.github/workflows/`, configuração de CI, hooks ou permissões sem avisar e explicar o motivo;
- commitar `.env`, chaves, tokens, credenciais ou qualquer segredo. Se encontrar um segredo no repositório, avise o usuário em vez de corrigir em silêncio;
- imprimir segredos em logs, saídas ou descrições de PR;
- instalar dependências novas sem confirmar;
- executar migrações ou comandos destrutivos em bancos de dados ou ambientes que não sejam locais de teste;
- desativar testes, lint ou checagens do CI para fazer algo passar.

Em caso de dúvida sobre se uma operação é destrutiva ou irreversível, **pergunte antes**.

---

## 10. Skills

Skills são instruções especializadas em `.claude/skills/<nome>/SKILL.md` (do projeto) e `~/.claude/skills/<nome>/SKILL.md` (pessoais). Cada uma tem um `description` que diz quando se aplica.

### Quando verificar

- **Antes do SPEC:** liste as skills disponíveis e identifique as que se aplicam à tarefa.
- **Antes do CODING:** releia as skills aplicáveis. Se o escopo mudou durante o SPEC ou TASK, repita a busca.
- **No REVIEW:** confirme que as skills aplicáveis foram seguidas.

### Como verificar

1. Liste os diretórios em `.claude/skills/` e `~/.claude/skills/`.
2. Leia o `description` de cada `SKILL.md`. Não leia o corpo de todas.
3. Para cada skill cujo `description` combine com a tarefa, leia o `SKILL.md` completo e siga as instruções **antes** de agir.
4. Se mais de uma se aplica, leia todas. Em conflito, a skill do projeto prevalece sobre a pessoal, e este CLAUDE.md prevalece sobre ambas.

### Registro

- Na SPEC, inclua a seção **Skills aplicáveis** com os nomes das skills usadas (ou "nenhuma").
- Na REVIEW, marque se cada skill listada foi seguida. Se alguma foi ignorada, justifique.

### Regras

- Não invente skills. Se nenhuma se aplica, siga em frente sem comentar.
- Não carregue skills irrelevantes só por precaução: isso gasta contexto.
- Se uma skill contradiz uma proibição da seção 9, a seção 9 prevalece. Avise o usuário.
- Se identificar uma tarefa repetitiva que merece virar skill, sugira ao usuário em vez de criar sozinho.

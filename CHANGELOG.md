# Changelog

Formato baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
versões em [SemVer](https://semver.org/lang/pt-BR/).

## [Não publicado]

## [0.2.0] — 2026-10-06

Promoção de `develop` para `main`: 17 PRs, 199 arquivos. CI com `lint`,
`security` e `test` verdes no merge.

### Adicionado

- **Fonte Indeed** (PR #9) — quinta fonte de vagas, via API GraphQL pública,
  sem browser e sem login. Descrição e data já vêm na busca; pagina por `cursor`.
- **Kanban de candidaturas** (PRs #20, #21) — colunas `CHECK` / `RUNNING` /
  `DONE` persistidas em `kanban_jobs`, com snapshot próprio: o card sobrevive ao
  clean das vagas coletadas. A ação **+ Add** move a vaga para o Kanban e a
  retira da lista de Vagas.
- **Currículo em Markdown** (PR #24) — contexto opcional em
  `data/curriculum.md`, editável em Configurações → Perfil. O classificador
  extrai skills, senioridade e anos, e registra em `reasons` e em
  `curriculum_version` (sha256 do conteúdo) gravado na vaga. **Não altera
  `score` nem `match`**: com o currículo carregado, o eval é bit-a-bit igual ao
  baseline.
- **Job `security` no CI** (PR #8) — `bandit` + `gitleaks` como rede de segurança
  para commits feitos com `--no-verify` ou por ferramenta.
- **Skill local de agente** (PR #13) — `make skill` e `make skill-list` para
  skills versionadas no repositório.
- **API do currículo** — `GET /curriculum` e `PUT /curriculum`, com escrita
  atômica e recusa acima de 200 KB.

### Mudado

- **Dashboard reorganizado** (PRs #19, #21) — menu lateral com Vagas, Kanban e
  Configurações; Perfil e Dados viraram abas dentro de Configurações, com
  deep-link (`#/configuracoes/perfil`, `#/configuracoes/dados`).
- **Estilo das abas movido para `style.css`** (PR #22) — deixa de haver `<style>`
  inline no `index.html`.

### Corrigido

- **Backend exibida passa a ser verdadeira** (PR #15) — badge e card mostravam
  `"laya"` por default silencioso mesmo quando a heurística tinha respondido.
- **Falha de uma fonte não derruba as outras** (PR #16) — isolamento para
  qualquer classe de exceção, não só para as do sync.
- **Deadline global no sync e retry** em Gupy e GeekHunter (PR #17).
- **`httpx` client fechado e `source_id` estável** no GeekHunter (PR #18).
- **Veto de `exclusions` do Laya desabilitado** (PR #10) — o checkpoint responde
  de forma aleatória a perguntas que não foi treinado para responder.
- **Senioridade por nível e matching por fronteira de palavra** (PR #11) — `go`
  não casa mais com `google`.
- **Descrições completas no eval** e dois rótulos inconsistentes corrigidos
  (PR #12).
- **Data ISO formatada, dealbreaker duplicado, erro 422 legível e a11y**
  (PR #14).
- **`INDEED_CO`** — o README documentava `INDEED_COUNTRY`, que o código nunca
  leu.
- **`make eval` quebrado desde o PR #15** — `eval/evaluate.py` e
  `eval/evaluate_real.py` chamavam `LayaJobClassifier` sem o argumento
  obrigatório `backend`.

### Conhecido

- O **currículo é contexto, não sinal**: aparece em `reasons` mas não move o
  score. Duas variantes com o currículo como componente de score foram
  implementadas e medidas — ambas esvaziam a classe `medium` do eval, porque
  qualquer componente positivo empurra para cima as vagas que estão a 1–2 pontos
  do threshold 80. Fazer o Laya usar o currículo de verdade exige fine-tuning.
- O **score não discrimina** as classes nas 67 vagas reais (medianas de `high`
  e `low` sobrepostas). Redesenhar a representação é o caminho; reponderar os
  pesos não resolve.
- A aba **Dados** ainda é um container: a organização interna (tecnologias,
  experiências, preferências) não foi construída.

[Não publicado]: https://github.com/adilsonmenechini/jobs-laya/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/adilsonmenechini/jobs-laya/compare/v0.1.0...v0.2.0

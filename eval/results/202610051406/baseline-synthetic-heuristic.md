# Evaluation

Measured with `python eval/evaluate.py --backend heuristic` — heuristics only (no model) — over the 18 labeled jobs in `eval/samples/` (7 high, 5 medium, 6 low; 12 English, 6 Portuguese).
This is a small, hand-made inbox: the numbers show how the parts work together, not how the classifier does on real postings. Label a few hundred of your own jobs and refit the thresholds before trusting a verdict.

| Screener | Exact matches | high | medium | low |
|---|---|---|---|---|
| Heuristics only | 12/18 | 7/7 | 2/5 | 3/6 |
| Laya only | — (backend without model) | — | — | — |
| Combined policy | 12/18 | 7/7 | 2/5 | 3/6 |

| Job | Expected | Heuristics only | Laya only | Combined | Laya answers |
|---|---|---|---|---|---|
| senior-sre-remote-en.json | high | high (88) | — | high (88) | — |
| staff-platform-engineer-remote-en.json | high | high (86) | — | high (86) | — |
| principal-reliability-remote-en.json | high | high (88) | — | high (88) | — |
| ai-engineer-llm-remote-en.json | high | high (84) | — | high (84) | — |
| devops-engineer-remote-en.json | high | high (86) | — | high (86) | — |
| cloud-engineer-remote-en.json | medium | high (88) ✗ | — | high (88) ✗ | — |
| mlops-remote-en.json | medium | medium (80) | — | medium (80) | — |
| devops-hybrid-london-en.json | medium | medium (78) | — | medium (78) | — |
| devops-sales-engineer-en.json | low | medium (78) ✗ | — | medium (78) ✗ | — |
| product-marketing-cloud-keywords-en.json | low | high (88) ✗ | — | high (88) ✗ | — |
| sales-manager-remote-en.json | low | low (41) | — | low (41) | — |
| frontend-engineer-remote-en.json | low | low (41) | — | low (41) | — |
| engenheiro-devops-senior-remoto-pt.json | high | high (91) | — | high (91) | — |
| sre-plataforma-remoto-pt.json | high | high (88) | — | high (88) | — |
| engenheiro-cloud-remoto-pt.json | medium | high (88) ✗ | — | high (88) ✗ | — |
| devops-pleno-remoto-pt.json | medium | high (88) ✗ | — | high (88) ✗ | — |
| devops-junior-remoto-pt.json | low | medium (74) ✗ | — | medium (74) ✗ | — |
| estagio-contabilidade-presencial-pt.json | low | low (18) | — | low (18) | — |

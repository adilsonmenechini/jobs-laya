# Evaluation

Measured with `python eval/evaluate.py --backend laya` — backend `laya` (mps, median: english 943 ms, multilingual 431 ms) — over the 18 labeled jobs in `eval/samples/` (7 high, 5 medium, 6 low; 12 English, 6 Portuguese).
This is a small, hand-made inbox: the numbers show how the parts work together, not how the classifier does on real postings. Label a few hundred of your own jobs and refit the thresholds before trusting a verdict.

| Screener | Exact matches | high | medium | low |
|---|---|---|---|---|
| Heuristics only | 12/18 | 7/7 | 2/5 | 3/6 |
| Laya only | 7/18 | 5/7 | 1/5 | 1/6 |
| Combined policy | 8/18 | 3/7 | 2/5 | 3/6 |

| Job | Expected | Heuristics only | Laya only | Combined | Laya answers |
|---|---|---|---|---|---|
| senior-sre-remote-en.json | high | high (88) | low (59) ✗ | medium (71) ✗ | other, remote 0.60, fit 0.72, sen 1 |
| staff-platform-engineer-remote-en.json | high | high (86) | high (87) | medium (77) ✗ | platform_cloud, remote 0.56, fit 0.74, sen 1 |
| principal-reliability-remote-en.json | high | high (88) | low (59) ✗ | medium (70) ✗ | other, remote 0.51, fit 0.71, sen 1 |
| ai-engineer-llm-remote-en.json | high | high (84) | high (84) | high (83) | ai_ml, remote 0.60, fit 0.68, sen 1 |
| devops-engineer-remote-en.json | high | high (86) | high (86) | medium (77) ✗ | devops, remote 0.59, fit 0.73, sen 1 |
| cloud-engineer-remote-en.json | medium | high (88) ✗ | high (88) ✗ | high (81) ✗ | platform_cloud, remote 0.53, fit 0.79, sen 1 |
| mlops-remote-en.json | medium | medium (80) | high (87) ✗ | medium (79) | ai_ml, remote 0.56, fit 0.74, sen 1 |
| devops-hybrid-london-en.json | medium | medium (78) | medium (73) | medium (78) | devops, remote 0.45, fit 0.73, sen 1 |
| devops-sales-engineer-en.json | low | medium (78) ✗ | high (86) ✗ | medium (73) ✗ | devops, remote 0.56, fit 0.74, sen 1 |
| product-marketing-cloud-keywords-en.json | low | high (88) ✗ | high (86) ✗ | high (80) ✗ | platform_cloud, remote 0.55, fit 0.72, sen 1 |
| sales-manager-remote-en.json | low | low (41) | low (54) | low (44) | other, remote 0.56, fit 0.60, sen 1 |
| frontend-engineer-remote-en.json | low | low (41) | high (85) ✗ | low (55) | devops, remote 0.60, fit 0.70, sen 1 |
| engenheiro-devops-senior-remoto-pt.json | high | high (91) | high (92) | high (87) | site_reliability, remote 0.91, fit 0.87, sen 1 |
| sre-plataforma-remoto-pt.json | high | high (88) | high (91) | high (83) | site_reliability, remote 0.82, fit 0.84, sen 1 |
| engenheiro-cloud-remoto-pt.json | medium | high (88) ✗ | high (87) ✗ | high (82) ✗ | platform_cloud, remote 0.65, fit 0.76, sen 1 |
| devops-pleno-remoto-pt.json | medium | high (88) ✗ | high (89) ✗ | high (83) ✗ | devops, remote 0.88, fit 0.79, sen 1 |
| devops-junior-remoto-pt.json | low | medium (74) ✗ | high (94) ✗ | medium (74) ✗ | devops, remote 0.90, fit 0.92, sen 1 |
| estagio-contabilidade-presencial-pt.json | low | low (18) | medium (72) ✗ | low (45) | devops, remote 0.47, fit 0.71, sen 1 |

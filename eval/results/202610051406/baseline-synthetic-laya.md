# Evaluation

Measured with `python eval/evaluate.py --backend laya` — backend `laya` (mps, median: english 479 ms, multilingual 209 ms) — over the 18 labeled jobs in `eval/samples/` (7 high, 5 medium, 6 low; 12 English, 6 Portuguese).
This is a small, hand-made inbox: the numbers show how the parts work together, not how the classifier does on real postings. Label a few hundred of your own jobs and refit the thresholds before trusting a verdict.

| Screener | Exact matches | high | medium | low |
|---|---|---|---|---|
| Heuristics only | 12/18 | 7/7 | 2/5 | 3/6 |
| Laya only | 6/18 | 4/7 | 1/5 | 1/6 |
| Combined policy | 5/18 | 1/7 | 1/5 | 3/6 |

| Job | Expected | Heuristics only | Laya only | Combined | Laya answers |
|---|---|---|---|---|---|
| senior-sre-remote-en.json | high | high (88) | medium (60) ✗ | medium (72) ✗ | other, remote 0.65, fit 0.75, sen 1 |
| staff-platform-engineer-remote-en.json | high | high (86) | high (88) | medium (79) ✗ | platform_cloud, remote 0.72, fit 0.78, sen 1 |
| principal-reliability-remote-en.json | high | high (88) | high (81) | medium (76) ✗ | site_reliability, remote 0.50, fit 0.61, sen 1 |
| ai-engineer-llm-remote-en.json | high | high (84) | medium (78) ✗ | medium (80) ✗ | ai_ml, remote 0.54, fit 0.52, sen 1 |
| devops-engineer-remote-en.json | high | high (86) | high (88) | medium (79) ✗ | devops, remote 0.73, fit 0.76, sen 1 |
| cloud-engineer-remote-en.json | medium | high (88) ✗ | high (90) ✗ | high (83) ✗ | platform_cloud, remote 0.62, fit 0.83, sen 1 |
| mlops-remote-en.json | medium | medium (80) | high (88) ✗ | high (82) ✗ | ai_ml, remote 0.74, fit 0.77, sen 1 |
| devops-hybrid-london-en.json | medium | medium (78) | medium (72) | medium (77) | devops, remote 0.36, fit 0.71, sen 1 |
| devops-sales-engineer-en.json | low | medium (78) ✗ | high (86) ✗ | medium (73) ✗ | devops, remote 0.60, fit 0.71, sen 1 |
| product-marketing-cloud-keywords-en.json | low | high (88) ✗ | high (82) ✗ | medium (79) ✗ | platform_cloud, remote 0.62, fit 0.62, sen 1 |
| sales-manager-remote-en.json | low | low (41) | low (35) | low (38) | other, remote 0.66, fit 0.11, sen 1 |
| frontend-engineer-remote-en.json | low | low (41) | medium (77) ✗ | low (55) | platform_cloud, remote 0.81, fit 0.51, sen 1 |
| engenheiro-devops-senior-remoto-pt.json | high | high (91) | medium (73) ✗ | medium (79) ✗ | devops, remote 0.76, fit 0.82, sen 0 |
| sre-plataforma-remoto-pt.json | high | high (88) | high (89) | high (82) | devops, remote 0.77, fit 0.79, sen 1 |
| engenheiro-cloud-remoto-pt.json | medium | high (88) ✗ | high (91) ✗ | high (84) ✗ | devops, remote 0.74, fit 0.86, sen 1 |
| devops-pleno-remoto-pt.json | medium | high (88) ✗ | high (91) ✗ | high (84) ✗ | devops, remote 0.87, fit 0.84, sen 1 |
| devops-junior-remoto-pt.json | low | medium (74) ✗ | medium (76) ✗ | medium (68) ✗ | devops, remote 0.93, fit 0.91, sen 0 |
| estagio-contabilidade-presencial-pt.json | low | low (18) | medium (78) ✗ | low (44) | site_reliability, remote 0.11, fit 0.86, sen 1 |

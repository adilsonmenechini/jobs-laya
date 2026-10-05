# Evaluation

Measured with `python eval/evaluate.py --backend fake` — backend `fake` (fake, median: fake 1 ms) — over the 18 labeled jobs in `eval/samples/` (7 high, 5 medium, 6 low; 12 English, 6 Portuguese).
This is a small, hand-made inbox: the numbers show how the parts work together, not how the classifier does on real postings. Label a few hundred of your own jobs and refit the thresholds before trusting a verdict.

| Screener | Exact matches | high | medium | low |
|---|---|---|---|---|
| Heuristics only | 12/18 | 7/7 | 2/5 | 3/6 |
| Laya only | 16/18 | 7/7 | 4/5 | 5/6 |
| Combined policy | 14/18 | 7/7 | 4/5 | 3/6 |

| Job | Expected | Heuristics only | Laya only | Combined | Laya answers |
|---|---|---|---|---|---|
| senior-sre-remote-en.json | high | high (88) | high (93) | high (85) | platform_cloud, remote 0.90, fit 0.90, sen 1 |
| staff-platform-engineer-remote-en.json | high | high (86) | high (96) | high (84) | platform_cloud, remote 0.90, fit 0.90, sen 2 |
| principal-reliability-remote-en.json | high | high (88) | high (96) | high (86) | site_reliability, remote 0.90, fit 0.90, sen 2 |
| ai-engineer-llm-remote-en.json | high | high (84) | high (93) | high (89) | ai_ml, remote 0.90, fit 0.90, sen 1 |
| devops-engineer-remote-en.json | high | high (86) | high (93) | high (82) | devops, remote 0.90, fit 0.90, sen 1 |
| cloud-engineer-remote-en.json | medium | high (88) ✗ | medium (76) | high (80) ✗ | site_reliability, remote 0.90, fit 0.90, sen 0 |
| mlops-remote-en.json | medium | medium (80) | medium (76) | medium (79) | ai_ml, remote 0.90, fit 0.90, sen 0 |
| devops-hybrid-london-en.json | medium | medium (78) | medium (80) | medium (77) | devops, remote 0.10, fit 0.90, sen 1 |
| devops-sales-engineer-en.json | low | medium (78) ✗ | low (49) | medium (64) ✗ | other, remote 0.90, fit 0.90, sen 0 |
| product-marketing-cloud-keywords-en.json | low | high (88) ✗ | low (49) | medium (73) ✗ | other, remote 0.90, fit 0.90, sen 0 |
| sales-manager-remote-en.json | low | low (41) | low (37) | low (42) | other, remote 0.90, fit 0.10, sen 2 |
| frontend-engineer-remote-en.json | low | low (41) | low (34) | low (40) | other, remote 0.90, fit 0.10, sen 1 |
| engenheiro-devops-senior-remoto-pt.json | high | high (91) | high (93) | high (87) | devops, remote 0.90, fit 0.90, sen 1 |
| sre-plataforma-remoto-pt.json | high | high (88) | high (93) | high (85) | site_reliability, remote 0.90, fit 0.90, sen 1 |
| engenheiro-cloud-remoto-pt.json | medium | high (88) ✗ | low (49) ✗ | medium (73) | other, remote 0.90, fit 0.90, sen 0 |
| devops-pleno-remoto-pt.json | medium | high (88) ✗ | medium (76) | medium (78) | devops, remote 0.90, fit 0.90, sen 0 |
| devops-junior-remoto-pt.json | low | medium (74) ✗ | medium (76) ✗ | medium (67) ✗ | devops, remote 0.90, fit 0.90, sen 0 |
| estagio-contabilidade-presencial-pt.json | low | low (18) | low (4) | low (17) | other, remote 0.10, fit 0.10, sen 0 |

# Evaluation (real samples)

Backend: `fake` — 67 vagas reais rotuladas
(35 high, 12 medium, 20 low)

| Screener | Exact matches | high | medium | low |
|---|---|---|---|---|
| Heuristics only | 25/67 | 4/35 | 2/12 | 19/20 |
| Combined policy | 20/67 | 0/35 | 1/12 | 19/20 |

| Job | Source | Expected | Heuristics | Combined |
|---|---|---|---|---|
| geekhunter_ai-engin.json | geekhunter | high | high (91) | medium (73) ✗ |
| geekhunter_analista.json | geekhunter | low | low (49) | low (49) |
| geekhunter_desenvol.json | geekhunter | medium | low (55) ✗ | low (56) ✗ |
| geekhunter_deveops-.json | geekhunter | high | low (52) ✗ | low (56) ✗ |
| geekhunter_devops--.json | geekhunter | high | high (91) | medium (73) ✗ |
| geekhunter_devops-s.json | geekhunter | low | low (49) | low (49) |
| geekhunter_engenhei.json | geekhunter | high | medium (66) ✗ | medium (62) ✗ |
| geekhunter_ml-engin.json | geekhunter | high | low (49) ✗ | low (49) ✗ |
| geekhunter_platform.json | geekhunter | low | low (44) | low (49) |
| geekhunter_principa.json | geekhunter | low | low (41) | low (26) |
| geekhunter_qa-engin.json | geekhunter | low | low (54) | low (58) |
| geekhunter_senior-d.json | geekhunter | low | low (49) | low (49) |
| geekhunter_senior-m.json | geekhunter | low | low (34) | low (49) |
| geekhunter_site-rel.json | geekhunter | high | low (59) ✗ | low (51) ✗ |
| geekhunter_sre---en.json | geekhunter | high | low (47) ✗ | low (45) ✗ |
| geekhunter_sre--sen.json | geekhunter | high | high (85) | medium (70) ✗ |
| geekhunter_sre-seni.json | geekhunter | high | high (81) | medium (73) ✗ |
| gupy_12198836.json | gupy | high | low (31) ✗ | low (42) ✗ |
| gupy_12220389.json | gupy | medium | low (47) ✗ | low (53) ✗ |
| gupy_12298004.json | gupy | high | low (41) ✗ | low (56) ✗ |
| gupy_12421688.json | gupy | high | low (50) ✗ | medium (61) ✗ |
| gupy_12455072.json | gupy | medium | medium (65) | low (57) ✗ |
| gupy_12459907.json | gupy | high | low (44) ✗ | low (58) ✗ |
| gupy_12498580.json | gupy | medium | low (37) ✗ | low (45) ✗ |
| gupy_12533478.json | gupy | high | low (38) ✗ | low (47) ✗ |
| gupy_12534574.json | gupy | high | low (28) ✗ | low (39) ✗ |
| gupy_12566261.json | gupy | high | low (41) ✗ | low (48) ✗ |
| gupy_12571250.json | gupy | high | low (28) ✗ | low (39) ✗ |
| gupy_12590656.json | gupy | high | medium (68) ✗ | medium (65) ✗ |
| gupy_12607005.json | gupy | medium | low (41) ✗ | low (56) ✗ |
| gupy_12613042.json | gupy | high | low (43) ✗ | low (48) ✗ |
| gupy_12614793.json | gupy | high | low (38) ✗ | low (39) ✗ |
| gupy_12628069.json | gupy | medium | low (40) ✗ | low (45) ✗ |
| gupy_12640842.json | gupy | medium | low (50) ✗ | low (48) ✗ |
| gupy_12650308.json | gupy | high | medium (68) ✗ | low (56) ✗ |
| gupy_12656910.json | gupy | low | low (50) | low (41) |
| gupy_12657833.json | gupy | high | low (31) ✗ | low (37) ✗ |
| gupy_12659312.json | gupy | high | low (30) ✗ | low (28) ✗ |
| gupy_12664961.json | gupy | medium | low (52) ✗ | low (37) ✗ |
| indeed_013f671b.json | indeed | low | medium (61) ✗ | medium (64) ✗ |
| indeed_0655c7aa.json | indeed | high | low (48) ✗ | medium (62) ✗ |
| indeed_0e73a4f4.json | indeed | low | low (18) | low (17) |
| indeed_0fa714c2.json | indeed | low | low (20) | low (38) |
| indeed_205c42ed.json | indeed | medium | low (28) ✗ | low (25) ✗ |
| indeed_50292bec.json | indeed | high | medium (62) ✗ | medium (64) ✗ |
| indeed_5d411b5d.json | indeed | low | low (18) | low (17) |
| indeed_5ea5c7cf.json | indeed | high | low (59) ✗ | low (48) ✗ |
| indeed_61a28b15.json | indeed | high | medium (68) ✗ | medium (68) ✗ |
| indeed_6a29acc2.json | indeed | high | low (28) ✗ | low (39) ✗ |
| indeed_6c93724c.json | indeed | high | low (38) ✗ | low (39) ✗ |
| indeed_7aefd65e.json | indeed | low | low (54) | low (46) |
| indeed_827582ee.json | indeed | high | medium (62) ✗ | low (56) ✗ |
| indeed_89f7c633.json | indeed | medium | medium (66) | medium (62) |
| indeed_8f19678e.json | indeed | medium | low (32) ✗ | low (35) ✗ |
| indeed_91ddb9a0.json | indeed | low | low (18) | low (17) |
| indeed_aca2611e.json | indeed | low | low (31) | low (34) |
| indeed_ae59986d.json | indeed | low | low (20) | low (38) |
| indeed_af7140d9.json | indeed | low | low (51) | low (59) |
| indeed_c010e7d1.json | indeed | low | low (41) | low (26) |
| indeed_c42b3253.json | indeed | low | low (42) | low (55) |
| indeed_cd668d69.json | indeed | high | medium (64) ✗ | medium (66) ✗ |
| indeed_df875d8f.json | indeed | high | low (57) ✗ | medium (63) ✗ |
| indeed_e368d4f9.json | indeed | high | low (52) ✗ | low (57) ✗ |
| indeed_edc225d7.json | indeed | high | medium (62) ✗ | medium (64) ✗ |
| indeed_edfeab7b.json | indeed | high | medium (62) ✗ | medium (62) ✗ |
| indeed_f0b55248.json | indeed | low | low (31) | low (26) |
| indeed_f275e834.json | indeed | medium | low (42) ✗ | low (36) ✗ |

# Thesis

Name : Kim Jae-Wook (Ким Джэ-Ук)

Email : dzhkim@edu.hse.ru

Group : МНКДН241

Degree Program : Master's program

Year : 2nd year

Faculty : Computer Science (Факультет Компьютерных Наук)

Educational Program : Data Science (Науки о данных)


# 🎯 Automated Sentiment-Controlled Chat Generation in Live Streaming
# 🎯 Автоматизированная генерация чата с управляемой тональностью в прямых трансляциях


A multi-track architecture for automated real-time chat generation in Korean live streaming environments. Runs entirely on local hardware without cloud dependency.

---

## 📌 Overview

Live streaming chat is real-time, fast-paced, and dominated by short reactions and rapid topic shifts. Standard dialogue models cannot meet its latency budget. This thesis proposes a multi-track architecture that separates two functions with incompatible computational profiles.

- **Track 1** provides rule-based instant responses anchored to the empirical distribution of live chat.
- **Track 3** provides probabilistic sentiment-controlled interventions via EXAONE 3.5 2.4B Instruct.

The system targets SOOP, a Korean live streaming platform, and runs on a single local machine.

---

## 📊 Key Results

| Metric | Method 1 (multi-track) |
|---|---|
| Average response latency | 1.51 seconds |
| Malformed output rate | 0% |
| Speedup vs EXAONE 3.5 7.8B baseline | ~253x |
| Multi-rater naturalness vs 7.8B baseline | no statistically significant difference |

Multi-rater human evaluation involved 20 participants and 880 ratings per method.

---

## 🗂 Repository Structure

```
Thesis/
├── README.md                            ← this file
├── source_code/
│   ├── README.md                        ← module overview
│   ├── (core pipeline modules)
│   ├── (data acquisition modules)
│   └── for_Track3_Test/
│       ├── README.md                    ← Track 3 sub-experiment variants
│       └── (relaxed-config modules)
├── inputs/                              evaluation input sets
├── results/                             per-method evaluation outputs
├── data_analysis/                       keyword frequency artifacts (TSV)
├── survey/                              anonymized multi-rater scores
├── stats/                               statistical analysis scripts
├── environment.yml                      Miniforge conda environment
└── requirements.txt                     pip dependencies
```

---

## 🧱 Contributions

1. **Long-running chat acquisition pipeline** for the SOOP live streaming platform
2. **Multi-track architecture** that addresses the latency-quality trade-off on local hardware
3. **Live-chat-specific evaluation protocol** combining latency distribution analysis, multi-rater naturalness evaluation, and Track 3 model size comparison

---

## 📦 Where to Look Next

- For module-level details and how the pipeline is wired together, see `source_code/README.md`.
- For the relaxed-config variants used in Section 4 evaluations, see `source_code/for_Track3_Test/README.md`.
- For raw evaluation data and statistical analysis, see the `results/`, `survey/`, and `stats/` directories.

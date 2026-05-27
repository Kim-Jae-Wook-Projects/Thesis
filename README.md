# Thesis

Name : Kim Jae-Wook (Ким Джэ-Ук)

Email : dzhkim@edu.hse.ru

Group : МНКДН241

Degree Program : Master's program

Year : 2nd year

Faculty : Computer Science (Факультет Компьютерных Наук)

Educational Program : Data Science (Науки о данных)

<br>

## 🎯 Тема : Автоматизированная генерация чата с управляемой тональностью в прямых трансляциях
## 🎯 Title : Automated Sentiment-Controlled Chat Generation in Live Streaming

<br>


A multi-track architecture for automated real-time chat generation in Korean live streaming environments. Runs entirely on local hardware without cloud dependency.

---

## 📌 Overview

Live streaming chat is real-time, fast-paced, and dominated by short reactions and rapid topic shifts. Standard dialogue models cannot meet its latency budget. This thesis proposes a multi-track architecture that separates two functions with incompatible computational profiles.

- **Track 1** provides rule-based instant responses anchored to the empirical distribution of live chat.
- **Track 3** provides probabilistic sentiment-controlled interventions via EXAONE 3.5 2.4B Instruct.

The system targets SOOP, a Korean live streaming platform, and runs on a single local machine.

---

## 📊 Key Results

Four methods compared on identical 110 input messages.

| Method | Latency | Malformed | Naturalness (1 to 5) |
|---|---|---|---|
| **Method 1 (multi-track)** | 1.51 s | 0 | 3.36 |
| Method 2 (EXAONE 4.0 1.2B baseline) | 2.01 s | 17 | 2.54 |
| Method 3 (EXAONE 3.5 2.4B baseline) | 5.36 s | 0 | 3.40 |
| Method 4 (EXAONE 3.5 7.8B baseline) | 382.06 s | 0 | 3.51 |

Method 1 is the fastest of the four methods with zero malformed outputs. Its naturalness is statistically equivalent to both the same-size 2.4B baseline (Method 3) and the 3.25 times larger 7.8B baseline (Method 4), based on Bonferroni-corrected Wilcoxon tests with p = 1.000 and p = 0.570 respectively. Multi-rater human evaluation involved 20 participants and 880 ratings per method.

---

## 🗂 Repository Structure

```
Thesis/
├── README.md                            ← this file
├── Survey/
│   └── naturalness_survey_dataset.xlsx
├── compatibility_issue/
│   └── README.md
└── source_code/
    ├── for_Track3_Test/
    │   ├── DoNotReadMe.md               ← Track 3 sub-experiment variants
    │   ├── pipeline_for_T3_Test.py
    │   └── run_realtime_focus_csv_for_T3_Test.py
    ├── ChatDataExtraction_main.py
    ├── DoNotReadMe.md                   ← module overview
    ├── Track1Rule.py
    ├── Track3Rule.py
    ├── backends.py
    ├── baseline_fullgen.py
    ├── chat_collector_main.py
    ├── chat_sender_focus.py
    ├── chat_storage_monitor.py
    ├── pipeline.py
    ├── resources.py
    ├── run_realtime_focus_csv.py
    └── runner_fullgen_csv.py
```

---

## 🧱 Contributions

1. **Long-running chat acquisition pipeline** for the SOOP live streaming platform
2. **Multi-track architecture** that addresses the latency-quality trade-off on local hardware
3. **Live-chat-specific evaluation protocol** combining latency distribution analysis, multi-rater naturalness evaluation, and Track 3 model size comparison

---

## 📦 Where to Look Next

- For module-level details and how the pipeline is wired together, see `source_code/DoNotReadMe.md`.
- For the relaxed-config variants used in Section 4 evaluations, see `source_code/for_Track3_Test/DoNotReadMe.md`.

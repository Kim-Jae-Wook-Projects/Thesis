
# 🧩 Source Code Modules

Implementation of the multi-track architecture and baseline runners used in the thesis.

---

## 📐 System Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CSV (chat data stream)                       │
│                          │                                      │
│                          ▼                                      │
│              ┌───────────────────────┐                          │
│              │ run_realtime_focus_   │  ← Main real-time runner │
│              │ csv.py                │    (tail + route + gate) │
│              └───────────┬───────────┘                          │
│                          │                                      │
│              ┌───────────▼───────────┐                          │
│              │     pipeline.py       │  ← Core processing       │
│              │(TrackRouter+Pipeline) │                          │
│              └──┬────────────────┬───┘                          │
│                 │                │                              │
│       ┌─────────▼─────┐  ┌──────▼──────────┐                    │
│       │ Track1Rule.py │  │ Track3Rule.py   │                    │
│       │(rules,instant)│  │ (POS/NEG prob,  │                    │
│       │               │  │  punchlines)    │                    │
│       └───────────────┘  └──────┬──────────┘                    │
│                                 │                               │
│                        ┌────────▼─────────────────┐             │
│                        │      backends.py         │             │
│                        │(EXAONE 3.5 2.4B Instruct)│             │
│                        └──────────────────────────┘             │
│                                                                 │
│  ┌──────────────┐  ┌────────────────────────┐                   │
│  │ resources.py │  │ chat_sender_focus.py   │                   │
│  │ (text utils) │  │ (clipboard paste send) │                   │
│  └──────────────┘  └────────────────────────┘                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🧱 Module Overview

### ⚡ Core Pipeline

| Module | Role | Key Mechanism |
|:---|:---|:---|
| **`run_realtime_focus_csv.py`** | Method 1 entry point | Tails CSV produced by data acquisition, routes messages through pipeline, manages **OutputGate** (max 1 output per 10 incoming chats in production, 1-per-4 in evaluation) |
| **`pipeline.py`** | 3-track core | Contains **TrackRouter** for Track 3 trigger logic and **Pipeline** class connecting all tracks |

### 🎯 Track Modules

| Module | Track | Purpose | Latency |
|:---|:---|:---|:---|
| **`Track1Rule.py`** | Track 1 | 16 priority-ordered **deterministic rules** for instant responses (keyword detection, repeated character mirroring, token-level exact matching) | **~0 ms** |
| **`Track3Rule.py`** | Track 3 | **Probability-based** stance decision (POS/NEG) with curated candidate lists for opinion-steering punchline generation | **~7.6 s** (queued) |

> A disabled Track 2 keyword-based emotion classifier is retained in `pipeline.py` as a future bridge between Track 1 and Track 3 for finer emotion categories such as sadness, anger, and surprise.

### 🤖 Model Backend

| Module | Role | Model |
|:---|:---|:---|
| **`backends.py`** | Provides **ExaonePunchlineGenerator** for Korean sentence-ending refinement | EXAONE 3.5 2.4B Instruct (local, on-device) |

### 🧪 Baseline Runners

| Module | Role |
|:---|:---|
| **`runner_fullgen_csv.py`** | Method 2, 3, 4 baseline runner. Routes every message through a single LLM |
| **`baseline_fullgen.py`** | LLM full-generation implementation. Auto-detects Instruct (chat template) vs Base (few-shot continuation) model |

### 🛠 Shared Utilities

| Module | Role |
|:---|:---|
| **`resources.py`** | `normalize_text()`, `clamp_text()`, `strip_forbidden()` and shared text utilities. Also provides **ReactionBank**, a fallback response selector for empty or too-short Track 3 outputs |
| **`chat_sender_focus.py`** | Clipboard paste-based message sender (`pyperclip` + `pyautogui`). Requires user to manually focus chat input box. Avoids **Korean IME composition breakage** that occurs with direct keyboard input |

### 📡 Data Acquisition

| Module | Role |
|:---|:---|
| **`ChatDataExtraction_main.py`** | Selenium-based DOM crawler for SOOP live streaming chat. Extracts rank, nickname, and message via **CSS color grouping** |
| **`chat_collector_main.py`** | CSV append writer with periodic snapshot generation |
| **`chat_storage_monitor.py`** | Sliding-window status reporter (message counts, rank distribution, top nicknames, frequent words) |
| **`keyword_mining_from_chat_csv.py`** | Frequency analysis across unigrams, bigrams, and special fragments |

---

## 🔄 Message Flow

```
Incoming chat message
        │
        ▼
   [Own message?] ──YES──▶ SKIP
        │ NO
        ▼
   [Track 1 match?] ──YES──▶ Generate response ──▶ Output Filter ──▶ Send
        │ NO                                        ▲
        ▼                                           │
   [Track 3 trigger?]                               │
   (≥2 opinion-seeking                              │
    patterns in 60s                                 │
    + 120s cooldown)                                │
        │ YES                                       │
        ▼                                           │
   Add to pending queue ──▶ Drain every 0.6s ───────┘
   (POS/NEG probability
    + EXAONE post-processing)
```

**Output Filter** applies: ① block `"ㅍ"` single-char output (Cmd+V leak via Korean IME), ② max 1 reply per 10 incoming messages (exempt: `"ㅋ"` or `"ㅇㅇㄱ"`), ③ drop if same as last 3 sent messages.

---

## ⚙️ Quick Start (Method 1, production)

```bash
# 1. Start data acquisition (separate terminal)
python ChatDataExtraction_main.py

# 2. Start Method 1 real-time chat generation
python run_realtime_focus_csv.py \
    --csv chat.csv \
    --bot-nick "YOUR_NICKNAME" \
    --chats-per-output 10 \
    --debug-stats
```

> ⚠️ **Prerequisite**: Manually focus your cursor on the chat input box before running. The sender uses clipboard paste (`Cmd+V` on macOS) to avoid Korean IME composition breakage.

For the relaxed-config variants used in Section 4 evaluations, see [`for_Track3_Test/README.md`](./for_Track3_Test/README.md).

---

## 📦 Dependencies

- Python 3.9+
- `selenium`, `pyautogui`, `pyperclip`
- `torch==2.2.2`, `transformers==4.43.0`, `tokenizers==0.19.1` (Miniforge-based conda environment)
- EXAONE 3.5 2.4B Instruct model (runs locally)

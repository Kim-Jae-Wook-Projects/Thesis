
# 🧰 Track 3 Sub-Experiment Variants

This directory contains two modules that mirror the parent `source_code/` pipeline but with **relaxed Track 3 trigger conditions**. These variants are used exclusively for the Track 3 evaluations reported in Section 4 of the thesis.

---

## 🤔 Why a Separate Folder

The production multi-track architecture (Section 3.2) requires two or more opinion-seeking patterns within a 60-second sliding window, followed by a 120-second cooldown, before Track 3 can fire. This pacing is appropriate for live deployment.

For thesis-scale evaluation, however, this pacing produces too few Track 3 outputs within a finite test set (110 inputs in Section 4.1, 30 opinion-request inputs in Section 4.3). The variants in this directory therefore relax the trigger conditions so that every opinion-request input produces a Track 3 output within reasonable wall-clock time.

This relaxation parallels the OutputGate relaxation from 1-per-10 to 1-per-4 already described in Section 3.1.

---

## 📊 Parameter Differences

| Parameter | Production (parent dir) | Evaluation (this dir) |
|---|---|---|
| `trigger_threshold` | 2 | 1 |
| `trigger_window_sec` | 60.0 (active via `_prune`) | (disabled, `_prune` returns immediately) |
| `track3_cooldown_sec` | 120.0 | 0.0 |
| OutputGate `chats_per_output` (CLI flag) | 10 | 4 |

The OutputGate value is a runtime CLI flag rather than a config field, so it is passed at command line.

---

## 📁 Modules

| Module | Purpose |
|:---|:---|
| **`pipeline_for_T3_Test.py`** | 3-track pipeline with relaxed `RouterConfig` defaults |
| **`run_realtime_focus_csv_for_T3_Test.py`** | Entry point matching the relaxed configuration |

These mirror `pipeline.py` and `run_realtime_focus_csv.py` in the parent `source_code/` directory. They differ only in the `RouterConfig` default values and the `_prune` method behavior. All other modules (`Track1Rule.py`, `Track3Rule.py`, `backends.py`, `resources.py`, `chat_sender_focus.py`) are imported unchanged from the parent directory.

---

## 🎯 When to Use

- **Use this directory** when reproducing the evaluation results in Section 4 of the thesis. This includes the four-method comparison (Section 4.1), the naturalness evaluation survey (Section 4.2), the Track 3 model size comparison (Section 4.3), and the temperature sensitivity analysis.
- **Use the parent `source_code/` directory** for actual production deployment, where realistic pacing matters.

---

## ⚙️ Usage

```bash
# Evaluation run, mirroring Section 4 settings
python run_realtime_focus_csv_for_T3_Test.py \
    --csv chat.csv \
    --bot-nick "YOUR_NICKNAME" \
    --chats-per-output 4 \
    --debug-stats
```

The `--chats-per-output 4` flag matches the OutputGate evaluation setting documented in Section 3.1.

---

## 🔗 Related Sections in the Thesis

- Section 3.1, OutputGate relaxation paragraph: justifies the 1-per-4 evaluation rate
- Section 3.2, Trigger mechanism paragraph: lists the trigger conditions relaxed here
- Section 4.1, Section 4.3: report the evaluations that use this directory

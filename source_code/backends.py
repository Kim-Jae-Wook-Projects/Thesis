# backends.py

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import re

# Lazy imports to keep import-time light
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForSequenceClassification, AutoModelForCausalLM
except Exception:  # pragma: no cover
    torch = None
    AutoTokenizer = None
    AutoModelForSequenceClassification = None
    AutoModelForCausalLM = None


@dataclass
class EmotionClassifierConfig:
    model_name_or_path: str = "monologg/koelectra-base-v3-discriminator"
    device: str = "cuda"  # "cpu" also ok
    max_length: int = 128

    # label mapping
    # This default is a safe placeholder; align to your trained checkpoint.
    id2label: Optional[dict] = None


class EmotionClassifierKoElectra:
    def __init__(self, cfg: EmotionClassifierConfig) -> None:
        if torch is None:
            raise RuntimeError("torch/transformers not available. Install torch + transformers.")

        self.cfg = cfg
        self.device = torch.device(cfg.device if torch.cuda.is_available() and cfg.device.startswith("cuda") else "cpu")

        self.tokenizer = AutoTokenizer.from_pretrained(cfg.model_name_or_path)
        self.model = AutoModelForSequenceClassification.from_pretrained(cfg.model_name_or_path)
        self.model.to(self.device)
        self.model.eval()

        if cfg.id2label is None:
            # Conservative default buckets
            self.id2label = {
                0: "neutral",
                1: "positive",
                2: "negative",
                3: "surprise",
                4: "anger",
                5: "sad",
            }
        else:
            self.id2label = dict(cfg.id2label)

    def _heuristic_emotion(self, text: str) -> Optional[str]:
        t = text.strip()
        if not t:
            return "neutral"
        if re.search(r"(ㅋㅋ|ㅎㅎ)", t):
            return "positive"
        if re.search(r"(ㅠㅠ|ㅜㅜ)", t):
            return "sad"
        if re.search(r"(!{2,}|헐|와\b|미쳤)", t):
            return "surprise"
        return None

    @torch.no_grad()
    def predict(self, text: str) -> Tuple[str, float]:
        h = self._heuristic_emotion(text)
        if h is not None:
            return h, 0.51

        enc = self.tokenizer(
            text,
            truncation=True,
            max_length=self.cfg.max_length,
            return_tensors="pt",
        )
        enc = {k: v.to(self.device) for k, v in enc.items()}
        logits = self.model(**enc).logits
        probs = torch.softmax(logits, dim=-1).squeeze(0)
        idx = int(torch.argmax(probs).item())
        score = float(probs[idx].item())
        label = self.id2label.get(idx, "neutral")
        return label, score


@dataclass
class ExaoneBackendConfig:
    model_name_or_path: str = "LGAI-EXAONE/EXAONE-3.5-2.4B-Instruct"
    device: str = "cuda"
    max_new_tokens: int = 32
    temperature: float = 0.9
    top_p: float = 0.92
    repetition_penalty: float = 1.05

    # generation constraints
    stop_on_newline: bool = True


class ExaonePunchlineGenerator:
    def __init__(self, cfg: ExaoneBackendConfig) -> None:
        if torch is None:
            raise RuntimeError("torch/transformers not available. Install torch + transformers.")

        self.cfg = cfg
        self.device = torch.device(cfg.device if torch.cuda.is_available() and cfg.device.startswith("cuda") else "cpu")

        self.tokenizer = AutoTokenizer.from_pretrained(
            cfg.model_name_or_path,
            use_fast=True,
            trust_remote_code=True,
        )
        self.model = AutoModelForCausalLM.from_pretrained(
            cfg.model_name_or_path,
            dtype=getattr(torch, "float16", None),
            trust_remote_code=True,
        )
        self.model.to(self.device)
        self.model.eval()

    @torch.no_grad()
    def generate_one_line(self, prompt: str) -> str:
        enc = self.tokenizer(prompt, return_tensors="pt")
        enc = {k: v.to(self.device) for k, v in enc.items()}

        out = self.model.generate(
            **enc,
            max_new_tokens=self.cfg.max_new_tokens,
            do_sample=True,
            temperature=self.cfg.temperature,
            top_p=self.cfg.top_p,
            repetition_penalty=self.cfg.repetition_penalty,
            eos_token_id=self.tokenizer.eos_token_id,
            pad_token_id=self.tokenizer.eos_token_id,
        )
        decoded = self.tokenizer.decode(out[0], skip_special_tokens=True)

        # keep only suffix after the last "출력:" marker if present
        if "출력:" in decoded:
            decoded = decoded.split("출력:", 1)[-1]

        decoded = decoded.strip()

        if self.cfg.stop_on_newline:
            decoded = decoded.splitlines()[0].strip()

        return decoded

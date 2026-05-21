# baseline_fullgen.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Optional, Tuple

try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM
except Exception:
    torch = None
    AutoTokenizer = None
    AutoModelForCausalLM = None

from resources import normalize_text, clamp_text, strip_forbidden

_LEADING_MARKERS_RX = re.compile(r"^\s*([-\u2022*>]+)\s*")

# Emoji / symbol removal regex (covers all common Unicode emoji ranges)
_EMOJI_RX = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map
    "\U0001F1E0-\U0001F1FF"  # flags
    "\U0001F900-\U0001F9FF"  # supplemental emoticons
    "\U0001FA00-\U0001FAFF"  # supplemental symbols
    "\U00002702-\U000027B0"  # dingbats
    "\U0000FE00-\U0000FE0F"  # variation selectors
    "\U0000200D"             # zero width joiner
    "\U000023E9-\U000023FA"  # misc symbols
    "\U00002600-\U000026FF"  # misc symbols
    "\U00002300-\U000023FF"  # misc technical
    "]+",
    flags=re.UNICODE,
)

# ----------------------------
# Instruct model: System Prompt (method 3)
# ----------------------------
_SYSTEM_PROMPT = (
    "You are a viewer watching an AfreecaTV live stream. "
    "Read the previous conversation flow and the current chat message from other viewers, "
    "and react in Korean using a short, natural internet broadcasting style. "
    "You must reply with only one single line, and it must be very short (1 to 4 words). "
    "Do not use any emoji."
)

# ----------------------------
# Base model: Few-shot prompt (method 2)
# ----------------------------
# These examples intentionally do NOT overlap with any of the 16 Track 1 rules.
# They teach only the response FORMAT (short, casual, Korean internet slang),
# NOT the specific answers. The LLM must generate from its own capability.
_FEW_SHOT_PROMPT_TEMPLATE = (
    "input: 저거 뭐야 처음 봐\n"
    "output: 나도 처음 봄\n"
    "\n"
    "input: 아 배고프다\n"
    "output: 치킨 시켜\n"
    "\n"
    "input: 오늘 방송 재밌네\n"
    "output: ㄹㅇ 개꿀잼\n"
    "\n"
    "input: {message}\n"
    "output:"
)


def _is_instruct_model(model_name: str) -> bool:
    """Check if model name indicates an instruction-tuned model."""
    name_lower = (model_name or "").lower()
    return "instruct" in name_lower


@dataclass
class BaselineFullGenConfig:
    model_name_or_path: str = "LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct"
    device: str = "cpu"

    max_new_tokens: int = 24
    temperature: float = 0.9
    top_p: float = 0.92
    repetition_penalty: float = 1.05

    max_output_chars: int = 60
    forbidden_chars: str = "\u00b7"
    stop_on_newline: bool = True

    system_prompt: str = _SYSTEM_PROMPT
    fewshot_prompt_template: str = _FEW_SHOT_PROMPT_TEMPLATE


class BaselineFullGen:
    def __init__(self, cfg: Optional[BaselineFullGenConfig] = None) -> None:
        if torch is None:
            raise RuntimeError("torch/transformers not available.")

        self.cfg = cfg or BaselineFullGenConfig()
        self._is_instruct = _is_instruct_model(self.cfg.model_name_or_path)

        use_cuda = torch.cuda.is_available() and self.cfg.device.startswith("cuda")
        self.device = torch.device(self.cfg.device if use_cuda else "cpu")
        self._dtype = torch.float16 if use_cuda else torch.float32

        mode_str = "Instruct (chat template)" if self._is_instruct else "Base (few-shot)"
        print(f"[BaselineFullGen] Loading model: {self.cfg.model_name_or_path}")
        print(f"[BaselineFullGen] Mode: {mode_str}")
        print(f"[BaselineFullGen] Device: {self.device} | Dtype: {self._dtype}")

        load_start = time.time()

        self.tokenizer = AutoTokenizer.from_pretrained(
            self.cfg.model_name_or_path,
            use_fast=True,
            trust_remote_code=True,
        )

        self.model = AutoModelForCausalLM.from_pretrained(
            self.cfg.model_name_or_path,
            dtype=self._dtype,
            trust_remote_code=True,
        )
        self.model.to(self.device)
        self.model.eval()

        print(f"[BaselineFullGen] Model loaded in {time.time() - load_start:.1f}s")

    def _build_prompt(self, message: str, context: str) -> str:
        if self._is_instruct:
            return self._build_prompt_instruct(message, context)
        else:
            return self._build_prompt_fewshot(message)

    def _build_prompt_instruct(self, message: str, context: str) -> str:
        """Instruct model: chat template with system prompt and context."""
        ctx_text = context if context.strip() else "(No previous context)"

        messages = [
            {"role": "system", "content": self.cfg.system_prompt},
            {"role": "user", "content": f"Previous Context: {ctx_text}\nCurrent Chat: {message}"},
        ]

        try:
            prompt = self.tokenizer.apply_chat_template(
                messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            prompt = (
                f"{self.cfg.system_prompt}\n\n"
                f"Previous Context: {ctx_text}\n"
                f"Current Chat: {message}\n"
                f"Response:"
            )
        return prompt

    def _build_prompt_fewshot(self, message: str) -> str:
        """Base model: few-shot continuation with no context injection."""
        return self.cfg.fewshot_prompt_template.format(message=message)

    def _postprocess(self, decoded: str) -> str:
        decoded = decoded.strip()

        if self.cfg.stop_on_newline and decoded:
            decoded = decoded.splitlines()[0].strip()

        # Block few-shot pattern continuation (base model may try to
        # generate "input: ..." as the next example instead of stopping)
        if "input:" in decoded:
            decoded = decoded.split("input:")[0].strip()

        decoded = _LEADING_MARKERS_RX.sub("", decoded).strip()
        decoded = strip_forbidden(decoded, self.cfg.forbidden_chars)

        # Remove all emoji/symbol characters (safety net for macOS clipboard paste)
        decoded = _EMOJI_RX.sub("", decoded).strip()

        decoded = clamp_text(decoded, self.cfg.max_output_chars)

        return decoded

    @torch.no_grad()
    def generate(self, message: str, context: str = "") -> Tuple[str, float]:
        msg = normalize_text(message)
        if not msg:
            return "", 0.0

        prompt = self._build_prompt(msg, context)

        t0 = time.time()

        try:
            enc = self.tokenizer(prompt, return_tensors="pt")
            enc = {k: v.to(self.device) for k, v in enc.items()}

            # Record input token length BEFORE generation
            input_length = enc["input_ids"].shape[1]

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

            # Decode ONLY the newly generated tokens (skip prompt tokens entirely)
            generated_tokens = out[0][input_length:]
            decoded = self.tokenizer.decode(generated_tokens, skip_special_tokens=True)

            latency = time.time() - t0

            response = self._postprocess(decoded)
            return response, latency

        except Exception as e:
            latency = time.time() - t0
            print(f"[BaselineFullGen] Generation error: {e}")
            return "", latency
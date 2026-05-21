# resources.py
"""
Shared resources (single source of truth):
- normalize_text / tokenize helpers
- ReactionBank: (judgement, reaction) sampler from CSV
- TopicState: low-frequency topic tracking
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Deque, Dict, List, Optional
from collections import deque
import csv
import os
import re
import time
import random


# ----------------------------
# Common text utilities (SSOT)
# ----------------------------

_ws_rx = re.compile(r"\s+")
_leading_mark_rx = re.compile(r"^\s*(?:[-•*>\u2022]+\s*)+")
_zero_width = "\u200b"

_token_rx = re.compile(r"[가-힣]+|[a-zA-Z0-9]+")


def normalize_text(text: str) -> str:
    if text is None:
        return ""
    t = str(text)
    t = t.replace(_zero_width, "").strip()
    t = _ws_rx.sub(" ", t)
    return t


def clamp_text(text: str, max_chars: int) -> str:
    t = normalize_text(text)
    if max_chars is None or int(max_chars) < 0:
        return t
    if len(t) <= int(max_chars):
        return t
    return t[: int(max_chars)].rstrip()


def strip_forbidden(text: str, forbidden: str = "·") -> str:
    t = normalize_text(text)
    for ch in forbidden:
        t = t.replace(ch, "")
    return t


def strip_leading_markers(text: str) -> str:
    """Remove common list/bullet prefixes from a single line."""
    t = str(text) if text is not None else ""
    t = t.replace(_zero_width, "").lstrip()
    t = _leading_mark_rx.sub("", t)
    return t.strip()


def tokenize_ko_simple(text: str) -> List[str]:
    t = normalize_text(text)
    return _token_rx.findall(t)


# ----------------------------
# ReactionBank
# ----------------------------

@dataclass
class ReactionSample:
    judgement: str
    reaction: str


class ReactionBank:
    """
    Optional CSV sampler.

    역할:
    - Track3 출력이 비어 있거나 너무 짧을 때(예: 길이 < 2) "대체 문구"를 제공하는 용도.
    - CSV가 없으면(파일 미존재) 로딩을 '조용히' 스킵.

    CSV expected columns (flexible):
    - judgement (or tone/label)
    - reaction (or text/utterance)
    """

    def __init__(self, path: str) -> None:
        self.path = path
        self.rows: List[ReactionSample] = []
        self._load_optional()

    def _load_optional(self) -> None:
        if not self.path:
            return
        if not os.path.exists(self.path):
            return

        with open(self.path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                j = (r.get("judgement") or r.get("tone") or r.get("label") or "neutral").strip()
                txt = (r.get("reaction") or r.get("text") or r.get("utterance") or "").strip()
                if not txt:
                    continue
                self.rows.append(ReactionSample(judgement=j, reaction=txt))

    def has_rows(self) -> bool:
        return bool(self.rows)

    def sample(self, judgement: Optional[str] = None) -> Optional[ReactionSample]:
        if not self.rows:
            return None
        if judgement is None:
            return random.choice(self.rows)
        cand = [x for x in self.rows if x.judgement == judgement]
        if not cand:
            return random.choice(self.rows)
        return random.choice(cand)


# ----------------------------
# Topic state
# ----------------------------

@dataclass
class TopicConfig:
    update_interval_sec: float = 3 * 60 * 60  # 3 hours
    max_signal_buffer: int = 500
    top_k: int = 6
    min_token_len: int = 2


class TopicState:
    def __init__(self, cfg: TopicConfig) -> None:
        self.cfg = cfg
        self._signals: Deque[str] = deque(maxlen=cfg.max_signal_buffer)
        self._topic: str = ""
        self._last_update_ts: float = 0.0

    def observe(self, message: str, now_ts: Optional[float] = None) -> None:
        ts = float(now_ts) if now_ts is not None else time.time()
        tokens = [t for t in tokenize_ko_simple(message) if len(t) >= self.cfg.min_token_len]
        if tokens:
            self._signals.extend(tokens)

        if (ts - self._last_update_ts) >= self.cfg.update_interval_sec:
            self._topic = self._compute_topic()
            self._last_update_ts = ts

    def _compute_topic(self) -> str:
        if not self._signals:
            return ""
        freq: Dict[str, int] = {}
        for t in self._signals:
            freq[t] = freq.get(t, 0) + 1
        top = sorted(freq.items(), key=lambda x: (-x[1], x[0]))[: self.cfg.top_k]
        return " / ".join([w for w, _c in top])

    def current_topic(self) -> str:
        return self._topic
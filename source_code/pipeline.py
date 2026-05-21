# pipeline.py


from __future__ import annotations

from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
from collections import deque
import time
import re
import random

from resources import (
    normalize_text,
    TopicState,
    TopicConfig,
    clamp_text,
    strip_forbidden,
)

from backends import (
    EmotionClassifierKoElectra,
    EmotionClassifierConfig,
    ExaonePunchlineGenerator,
    ExaoneBackendConfig,
)

from Track1Rule import Track1Rules
from Track3Rule import Track3Rules, Track3RuleConfig, Judgement

# ----------------------------
# Local helpers
# ----------------------------

_LEADING_MARKERS_RX = re.compile(r"^\s*([-•*>\u2022]+)\s*")
# LLM 출력 검증용: 라틴 알파벳(a-z, A-Z) 감지
_LATIN_RX = re.compile(r"[a-zA-Z]")
# LLM 출력 검증용: 한글(완성형 음절 + 자모) 1자 이상 포함 여부
_HANGUL_RX = re.compile(r"[\uAC00-\uD7AF\u3130-\u318F]")

def _strip_leading_markers(s: str) -> str:
    if not s:
        return ""
    return _LEADING_MARKERS_RX.sub("", s).strip()

# ----------------------------
# Track decisions / configs
# ----------------------------

@dataclass
class RouterConfig:
    trigger_threshold: int = 1
    # 요청하신 키워드들이 정규식에 정확히 추가되어 있다.
    trigger_regex: str = r"(어때\??|어떰\??|ㅇㄸ\??|어떤\s*데|어떤\s*가|어떤\s*거|어떤\s*거야|어떤\s*지|어떤\s*것|ㅈㅉㅇㅇ|진짜|탕핑|핑핑이|시진핑|중국|ㅇㅇ|ㄱㄱ|ㅇㅋ|맞아|맞아요|ㄴㄴ|어떻게 보|어떻게 해야)"
    track3_cooldown_sec: float = 0.0
    track3_max_output_chars: int = 60

@dataclass
class Track1Config:
    repeat_rx_to_unit: Optional[Dict[str, str]] = None
    token_to_unit: Optional[Dict[str, str]] = None
    interjection_o_rx: Optional[str] = None
    max_repeat: int = 5 

@dataclass
class Track2Config:
    enabled: bool = True
    keyword_map: Dict[str, List[str]] = field(default_factory=lambda: {
        "positive": ["ㅋㅋ", "ㅎㅎ", "좋", "굿", "최고", "인정", "레전드"],
        "negative": ["노잼", "별로", "비추", "싫", "망", "최악"],
        "sad": ["ㅠㅠ", "ㅜㅜ", "슬프", "눈물", "힘들"],
        "anger": ["빡", "열받", "화나", "짜증"],
        "surprise": ["헐", "와", "미쳤", "ㄷㄷ", "충격", "대박", "??"],
    })
    label_to_judgement: Dict[str, str] = field(default_factory=lambda: {
        "positive": "좋은듯",
        "negative": "비추",
        "sad": "애매",
        "anger": "비추",
        "surprise": "레전드",
        "neutral": "애매",
    })

@dataclass
class Track3Config:
    enabled: bool = True
    forbidden_chars: str = "·"
    max_chars: int = 60
    p_pos: float = 0.5
    p_neg: float = 0.5
    # 파이프라인 단독 LLM 발동 조건 (Track3Rule의 트리거와 함께 작용함)
    must_llm_lines: Tuple[str, ...] = ("잘 모르겠", "모르겠", "어렵")
    forbid_bare_short: bool = True
    # LLM 출력이 입력 대비 이 글자 수 이상 길어지면 차단
    max_added_chars: int = 12

@dataclass
class PipelineConfig:
    router: RouterConfig = field(default_factory=RouterConfig)
    track1: Track1Config = field(default_factory=Track1Config)
    track2: Track2Config = field(default_factory=Track2Config)
    track3: Track3Config = field(default_factory=Track3Config)
    topic: TopicConfig = field(default_factory=TopicConfig)
    emotion: EmotionClassifierConfig = field(default_factory=EmotionClassifierConfig)
    exaone: ExaoneBackendConfig = field(default_factory=ExaoneBackendConfig)

# ----------------------------
# Router (Track3 trigger only)
# ----------------------------

class TrackRouter:
    def __init__(self, cfg: RouterConfig) -> None:
        self.cfg = cfg
        self._trig_rx = re.compile(cfg.trigger_regex)
        self._trig_hits: Deque[float] = deque()
        self._last_track3_ts: float = 0.0

    def _trig_match(self, text: str) -> bool:
        t = normalize_text(text)
        if not t:
            return False
        return bool(self._trig_rx.search(t))

    def observe_message(self, message: str, now_ts: float) -> None:
        if self._trig_match(message):
            self._trig_hits.append(float(now_ts))

    def _prune(self, now_ts: float) -> None:
        pass

    def decide_track3(self, now_ts: float) -> Tuple[bool, str]:
        self._prune(now_ts)
        hits = len(self._trig_hits)
        cooldown_ok = (float(now_ts) - float(self._last_track3_ts)) >= float(self.cfg.track3_cooldown_sec)
        request_track3 = cooldown_ok and (hits >= int(self.cfg.trigger_threshold))
        if request_track3:
            return True, f"trigger_hits({hits}/{self.cfg.trigger_threshold})"
        return False, "no_track3"

    def mark_track3_requested(self, now_ts: float) -> None:
        self._last_track3_ts = float(now_ts)
        self._trig_hits.clear()

# ----------------------------
# Track2 (키워드 기반 감정 -> "판단 키워드" 출력)
# ----------------------------

class Track2Engine:
    def __init__(self, cfg: Track2Config, classifier: Optional[EmotionClassifierKoElectra] = None) -> None:
        self.cfg = cfg
        self.classifier = classifier
        self._rx: Dict[str, re.Pattern] = {}
        for label, kws in (cfg.keyword_map or {}).items():
            parts = []
            for k in kws:
                if k == "??": parts.append(r"\?\?")
                else: parts.append(re.escape(k))
            pat = "(" + "|".join(parts) + ")" if parts else r"$"
            self._rx[label] = re.compile(pat)

    def _keyword_label(self, message: str) -> Optional[str]:
        t = normalize_text(message)
        if not t: return None
        for label in ["anger", "sad", "negative", "surprise", "positive"]:
            rx = self._rx.get(label)
            if rx and rx.search(t): return label
        return None

    def can_handle(self, message: str) -> bool:
        return self._keyword_label(message) is not None

    def render(self, message: str) -> str:
        label = self._keyword_label(message) or "neutral"
        return self.cfg.label_to_judgement.get(label, "애매")

# ----------------------------
# Track3 (트리거 이후: 확률 기반 POS/NEG 분기 + 규칙 출력)
# ----------------------------

@dataclass
class Track3Job:
    text: str
    topic_hint: str = ""
    now_ts: float = 0.0

class Track3Worker:
    def __init__(
        self,
        cfg: Track3Config,
        backend: ExaonePunchlineGenerator,
        rules: Track3Rules,
    ) -> None:
        self.cfg = cfg
        self.backend = backend
        self.rules = rules
        self._pending: Deque[Track3Job] = deque()

        self._moreuget_fallbacks = ["모르겠네", "잘 모르겠네", "애매하네"]
        self._difficult_fallbacks = ["어렵네", "좀 어렵다", "그건 어렵네"]
        self._not_sure_fallbacks = ["잘 모르겠네", "잘 모르겠는데", "애매한데"]

        # few-shot 예시: 귀여운 종결어미(당/넹/징) + 잘 모르겠 추가
        # POS/NEG에서 같은 입력에 서로 다른 종결어미를 사용하여 다양성 확보
        # 호출마다 shuffle하여 출력 편향 완화
        self._pos_examples: List[Tuple[str, str]] = [
            ("어렵", "어렵당 ㅋㅋㅋ"),
            ("모르겠", "모르겠넹 ㅋㅋㅋ"),
            ("심각한 문제는 아닐듯", "심각한 문제는 아닌듯 ㅋㅋㅋ"),
            ("잘 모르겠", "잘 모르겠징 ㅋㅋㅋ"),
        ]
        self._neg_examples: List[Tuple[str, str]] = [
            ("어렵", "어렵징 ㅠㅠㅠ"),
            ("모르겠", "모르겠당 ㅠㅠㅠ"),
            ("문제가 있어 보일듯", "문제가 있어 보이는듯 ㅠㅠㅠ"),
            ("잘 모르겠", "잘 모르겠넹 ㅠㅠㅠ"),
        ]

    def submit(self, job: Track3Job) -> None:
        self._pending.append(job)

    def has_pending(self) -> bool:
        return bool(self._pending)

    # 한국어 few-shot 프롬프트로 전면 교체
    # - 영문 규칙 6줄 → 한국어 지시 1줄 + 예시 4쌍
    # - 예시는 "→" 포맷 사용 ("출력:" 는 맨 끝 1회만 → backends.py split 안전)
    # - 호출마다 예시 순서를 셔플하여 종결어미 편향 완화
    def _build_polish_prompt(self, base_line: str, style: str, judgement: Judgement) -> str:
        if judgement == "POS":
            suffix = "ㅋㅋㅋ"
            examples = list(self._pos_examples)
        else:
            suffix = "ㅠㅠㅠ"
            examples = list(self._neg_examples)

        random.shuffle(examples)

        prompt = f"아래 채팅의 어미만 살짝 다듬고 끝에 {suffix}를 붙여서 한 줄로 출력해.\n\n"
        for inp, out in examples:
            prompt += f"{inp} → {out}\n"
        prompt += f"\n입력: {base_line}\n출력:"

        return prompt

    def _fallback_finalize(self, base_line: str) -> str:
        br = normalize_text(base_line)
        if br == "모르겠": return random.choice(self._moreuget_fallbacks)
        if br == "어렵": return random.choice(self._difficult_fallbacks)
        if br == "잘 모르겠": return random.choice(self._not_sure_fallbacks)
        return br

    # LLM 출력 검증: 빈 문자열/공백, 라틴 알파벳, 한글 미포함 검사
    def _is_valid_output(self, text: str) -> bool:
        if not text or not text.strip():
            return False
        if _LATIN_RX.search(text):
            return False
        if not _HANGUL_RX.search(text):
            return False
        return True

    # 검증 실패 시 안전한 대체 문구 반환
    def _safe_fallback(self, judgement: Judgement, base_line: str) -> str:
        # 먼저 기존 _fallback_finalize 로 처리 가능한지 시도
        fb = self._fallback_finalize(base_line)
        if fb and self._is_valid_output(fb):
            return fb
        # 그래도 유효하지 않으면 Track3Rule의 규칙 풀에서 선택
        pool = self.rules.cfg.pos_lines if judgement == "POS" else self.rules.cfg.neg_lines
        if not pool:
            pool = ["ㄱㄱ"] if judgement == "POS" else ["아닌듯"]
        return random.choice(pool)

    def _polish_if_needed(self, base_line: str, judgement: Judgement, force_llm: bool = False) -> str:
        br = normalize_text(base_line)
        must = set(self.cfg.must_llm_lines or ())
        
        # force_llm이 True이거나, 기존 must_llm_lines에 해당하면 LLM 태움
        if not force_llm and br not in must:
            return base_line

        # 프롬프트에 judgement를 넘겨서 ㅋㅋㅋ/ㅠㅠㅠ 처리
        prompt = self._build_polish_prompt(br, style="구어체", judgement=judgement)
        out = self.backend.generate_one_line(prompt)

        out = _strip_leading_markers(out)
        out = strip_forbidden(out, self.cfg.forbidden_chars)
        out = clamp_text(out, self.cfg.max_chars)

        # 빈 문자열, 라틴 알파벳 포함, 한글 미포함 → 차단
        if not self._is_valid_output(out):
            return self._safe_fallback(judgement, br)

        # 입력 대비 글자 수 초과 → 차단 (Track3 전용)
        if len(out) - len(br) > self.cfg.max_added_chars:
            return self._safe_fallback(judgement, br)

        return out

    def step(self, limit: int = 1) -> List[str]:
        outs: List[str] = []
        n = max(1, int(limit))

        for _ in range(n):
            if not self._pending:
                break

            job = self._pending.popleft()

            # 1. Judgement(POS/NEG) 결정
            judgement: Judgement = self.rules.choose_judgement()

            # 2. Track3Rule.py 에서 3개의 값을 리턴 받도록 Unpacking 수정
            base_line, should_use_llm, final_judgement = self.rules.generate(job.text, judgement=judgement)
            
            base_line = _strip_leading_markers(base_line)
            base_line = strip_forbidden(base_line, self.cfg.forbidden_chars)
            base_line = clamp_text(base_line, self.cfg.max_chars)

            if not base_line:
                continue

            # 3. LLM 폴리싱 단계로 값들(base_line, 긍/부정 상태, LLM 개입여부) 넘김
            line = self._polish_if_needed(base_line, judgement=final_judgement, force_llm=should_use_llm)
            line = _strip_leading_markers(line)
            line = strip_forbidden(line, self.cfg.forbidden_chars)
            line = clamp_text(line, self.cfg.max_chars)

            if self.cfg.forbid_bare_short:
                if line.strip() in {"모르겠", "잘 모르겠", "어렵"}:
                    line = self._fallback_finalize(line.strip())

            if line:
                outs.append(line)

        return outs

# ----------------------------
# Pipeline
# ----------------------------

class Pipeline:
    def __init__(self, cfg: PipelineConfig) -> None:
        self.cfg = cfg
        self.router = TrackRouter(cfg.router)
        self.track1 = Track1Rules(cfg.track1)
        self.track2_enabled = bool(getattr(cfg.track2, "enabled", True))
        self.track2_engine = Track2Engine(cfg.track2, classifier=None)
        self.topic_state = TopicState(cfg.topic)
        self.exaone = ExaonePunchlineGenerator(cfg.exaone)

        r_cfg = Track3RuleConfig(
            p_pos=float(cfg.track3.p_pos),
            p_neg=float(cfg.track3.p_neg),
        )
        self.track3_rules = Track3Rules(r_cfg)

        self.track3 = Track3Worker(
            cfg.track3,
            backend=self.exaone,
            rules=self.track3_rules,
        )

    def process_message(self, message: str, ts: Optional[float] = None) -> List[str]:
        now_ts = float(ts) if ts is not None else time.time()
        msg = normalize_text(message)
        if not msg:
            return []

        try:
            self.topic_state.observe(msg, now_ts)
        except Exception:
            pass

        self.router.observe_message(msg, now_ts)

        outs: List[str] = []

        if self.track1.can_handle(msg):
            r = self.track1.respond(msg)
            if r: outs.append(r)
            return outs

        if self.track2_enabled and self.track2_engine.can_handle(msg):
            outs.append(self.track2_engine.render(msg))
            return outs

        return outs

    def should_request_track3(self, now_ts: float) -> Tuple[bool, str]:
        return self.router.decide_track3(float(now_ts))

    def _safe_topic_hint(self) -> str:
        try:
            if hasattr(self.topic_state, "get_topic_hint"):
                v = getattr(self.topic_state, "get_topic_hint")()
                return str(v).strip() if v else ""
            if hasattr(self.topic_state, "current_topic"):
                v = getattr(self.topic_state, "current_topic")()
                return str(v).strip() if v else ""
        except Exception:
            return ""
        return ""

    def submit_track3(self, text: str, ts: Optional[float] = None) -> None:
        now_ts = float(ts) if ts is not None else time.time()
        self.router.mark_track3_requested(now_ts)
        topic_hint = self._safe_topic_hint()
        self.track3.submit(Track3Job(text=str(text), topic_hint=topic_hint, now_ts=now_ts))

    def drain_pending(self, limit: int = 4) -> List[str]:
        if not self.track3.has_pending():
            return []
        return self.track3.step(limit=limit)

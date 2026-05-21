# Track3Rule.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal, Tuple, Dict
import random
import re

from resources import normalize_text

Judgement = Literal["POS", "NEG"]

@dataclass
class KeywordRule:
    pos_lines: List[str]
    neg_lines: List[str]

@dataclass
class Track3RuleConfig:
    # 확률 분기 (POS + NEG = 1.0 권장)
    p_pos: float = 0.5
    p_neg: float = 0.5

    # 기본 확장 가능한 후보군 (짧고 채팅스러운 형태 우선)
    pos_lines: List[str] = field(default_factory=lambda: [
        "ㄱㄱ",
        "가보자",
        "오케이",
        "좋은듯",
        "괜찮은듯",
        "ㅇㅇ ㄱㄱ",
        "ㄹㅇ ㄱㄱ",
        "인정 ㄱㄱ",
        "그거 ㄱㅊ은듯",
    ])

    # [수정] "모르겠", "어렵", "잘 모르겠" 추가
    # → _llm_trigger_words에 등록되어 있으므로 선택 시 LLM 폴리싱 자동 발동
    # → 키워드 매칭에 걸리지 않는 트리거(어때, 어떰, ㅇㄸ, 어떤거 등)에서 도달 가능
    neg_lines: List[str] = field(default_factory=lambda: [
        "아닌듯",
        "패스",
        "비추",
        "별로인듯",
        "그건 좀",
        "ㄴㄴ",
        "ㅇㄴ",
        "그거 비추",
        "그건 좀 애매",
        "모르겠",
        "어렵",
        "잘 모르겠",
    ])

    # 커스텀 키워드 규칙 (1:1 매핑 및 통일)
    keyword_rules: Dict[str, KeywordRule] = field(default_factory=lambda: {
        "ㅈㅉㅇㅇ": KeywordRule(pos_lines=["ㅈㅉㅇㅇ ??"], neg_lines=["ㅈㅉㅇㅇ ??"]),
        "진짜": KeywordRule(pos_lines=["ㅈㅉㅇㅇ ??"], neg_lines=["ㅈㅉㅇㅇ ??"]),
        "탕핑": KeywordRule(pos_lines=["탕핑도 권리다 !"], neg_lines=["탕핑 ㅠㅠㅠ"]),
        "핑핑이": KeywordRule(pos_lines=["또진핑 ??", "핑핑이 ㅋㅋㅋ"], neg_lines=["아 또진핑이야 ㅠㅠ", "핑핑이 ㅡㅡ"]),
        "시진핑": KeywordRule(pos_lines=["또진핑 ??", "핑핑이 ㅋㅋㅋ"], neg_lines=["아 또진핑이야 ㅠㅠ", "핑핑이 ㅡㅡ"]),
        "중국": KeywordRule(pos_lines=["대륙 스케일 보소 ㅋㅋ"], neg_lines=["또국 ?", "또 당신입니까 ㅋㅋㅋ", "또 그 나라 짜증난다 ㅡㅡ", "에휴 ... 또 중국이야 ㅋㅋㅋ"]),
        "ㅇㅇ": KeywordRule(pos_lines=["ㅇㅇ"], neg_lines=["ㄴㄴ"]),
        "ㄱㄱ": KeywordRule(pos_lines=["ㄱㄱ"], neg_lines=["ㄴㄴ"]),
        "ㅇㅋ": KeywordRule(pos_lines=["ㅇㅋ"], neg_lines=["ㄴㄴ"]),
        "맞아": KeywordRule(pos_lines=["맞아"], neg_lines=["ㄴㄴ"]),
        "맞아요": KeywordRule(pos_lines=["맞아요"], neg_lines=["ㄴㄴ"]),
        "ㄴㄴ": KeywordRule(pos_lines=["ㄴㄴ"], neg_lines=["ㄴㄴ"]),
        "어떻게 보": KeywordRule(
            pos_lines=[
                "심각한 문제는 아닐듯",
                "크게 문제는 없어 보일듯",
                "생각보다 괜찮아 보이는데",
                "큰 걱정까진 아닐듯",
                "이 정도면 나쁘지 않은듯",
                "의외로 괜찮은 편인듯",
                "생각만큼 심각하진 않은듯",
                "그럭저럭 괜찮아 보이는데",
                "지켜보면 될 정도는 되는듯",
                "아직은 괜찮아 보일듯",
            ],
            neg_lines=[
                "별로 아닌가",
                "문제가 있어 보일듯",
                "좀 불안해 보이는데",
                "이건 다시 봐야 할듯",
                "생각보다 별로일수도",
                "좀 애매해 보이는데",
                "좋게 보이진 않는듯",
                "은근 문제 있어 보이는데",
                "이대로는 좀 아닌듯",
                "조금 위험해 보일수도",
            ],
        ),
        "어떻게 해야": KeywordRule(pos_lines=["잘 되겠죠 뭐 ㅋㅋㅋ"], neg_lines=["와 진짜 난감하겠네"]),
    })

class Track3Rules:
    def __init__(self, cfg: Track3RuleConfig) -> None:
        self.cfg = cfg
        # LLM을 무조건 태울 특정 문구들 (기존 + 요청하신 확장 후보)
        self._llm_trigger_words = {
            "난감하겠네", "별로 아닌가", "문제가 있어 보일듯", "심각한 문제는 아닐듯",
            "잘 모르겠", "모르겠", "어렵",
            "크게 문제는 없어 보일듯", "생각보다 괜찮아 보이는데", "큰 걱정까진 아닐듯",
            "이 정도면 나쁘지 않은듯", "의외로 괜찮은 편인듯", "생각만큼 심각하진 않은듯",
            "그럭저럭 괜찮아 보이는데", "지켜보면 될 정도는 되는듯", "아직은 괜찮아 보일듯",
            "좀 불안해 보이는데", "이건 다시 봐야 할듯", "생각보다 별로일수도",
            "좀 애매해 보이는데", "좋게 보이진 않는듯", "은근 문제 있어 보이는데",
            "이대로는 좀 아닌듯", "조금 위험해 보일수도",
        }

    def choose_judgement(self) -> Judgement:
        """
        확률 분기:
        - r < p_pos -> POS
        - else -> NEG
        """
        p_pos = float(self.cfg.p_pos)
        p_neg = float(self.cfg.p_neg)

        # 안전장치: 음수 방지, 합이 0이면 기본 0.5
        if p_pos < 0: p_pos = 0.0
        if p_neg < 0: p_neg = 0.0
        s = p_pos + p_neg
        if s <= 0:
            p_pos = 0.5; p_neg = 0.5; s = 1.0
        p_pos = p_pos / s # normalize

        r = random.random()
        return "POS" if r < p_pos else "NEG"

    def _should_use_llm(self, text: str) -> bool:
        # 텍스트 자체나, 텍스트의 앞부분이 trigger_words에 포함되는지 확인
        t = text.strip()
        for w in self._llm_trigger_words:
            if t.startswith(w) or w in t:
                return True
        return False

    def generate(self, message: str, judgement: Judgement) -> Tuple[str, bool, Judgement]:
        """
        판단/반응 원문(=출력 채팅)과 LLM 개입 여부, 그리고 사용된 judgement(접미사 처리용)를 생성한다.
        """
        norm_msg = normalize_text(message)

        # 1. 키워드 매칭 우선 처리
        for kw, rule in self.cfg.keyword_rules.items():
            if kw in norm_msg: # 부분 문자열 매칭
                pool = rule.pos_lines if judgement == "POS" else rule.neg_lines
                if not pool:
                    pool = rule.pos_lines if rule.pos_lines else ["ㅇㅇ"]
                selected = random.choice(pool).strip()
                return selected, self._should_use_llm(selected), judgement

        # 2. 기본 로직 (키워드 없음)
        pool = self.cfg.pos_lines if judgement == "POS" else self.cfg.neg_lines
        if not pool:
            pool = ["ㄱㄱ"] if judgement == "POS" else ["아닌듯"]
        
        selected = random.choice(pool).strip()
        return selected, self._should_use_llm(selected), judgement
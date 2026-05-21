# Track1Rule.py
# -*- coding: utf-8 -*-

from __future__ import annotations


from typing import Dict, List, Optional, Tuple
import random
import re


from resources import normalize_text, tokenize_ko_simple



# ---- Track1 SSOT defaults (여기만 늘리면 Track1 확장됨) ----
DEFAULT_REPEAT_RX_TO_UNIT: Dict[str, str] = {
    r"ㅋ{2,}": "ㅋ",
    r"ㅎ{2,}": "ㅎ",
    r"ㅠ{2,}": "ㅠ",
    r"ㅜ{2,}": "ㅜ",
    r"ㄷ{2,}": "ㄷ",
}


DEFAULT_TOKEN_TO_UNIT: Dict[str, str] = {
    "굿": "굿",
    "ㅇㅈ": "ㅇㅈ",
}


# (3) "헉" 포함 시 랜덤 응답 후보
DEFAULT_HEOK_VARIANTS: List[str] = [
    "헉",
    "허거덩",
    "헐랭",
    "헐",
]


# (6) "나는" 포함 시 랜덤 응답 후보
DEFAULT_NANEUN_VARIANTS: List[str] = [
    "그렇군요",
    "그렇군용",
    "아하 그렇군용",
    "아하 그렇군요",
]


# (7) "키키" 포함 시 랜덤 응답 후보
DEFAULT_KIKI_VARIANTS: List[str] = [
    "키키",
    "ㅋ ㅣ ㅋ ㅣ",
]


# (8) ㅠ/ㅜ/서운 포함 시 랜덤 응답 후보
DEFAULT_SAD_VARIANTS: List[str] = [
    "ㅠㅠㅠ",
    "ㅜㅜㅜ",
]


# (8-1) [신규] "쩔수" 포함 시 랜덤 응답 후보
DEFAULT_JJEOLSU_VARIANTS: List[str] = [
    "쩔수 ㅠ",
    "쩔수 ㅠㅠ",
    "쩔수 ㅠㅠㅠ",
]


# (9) "와" 포함 시 랜덤 응답 후보
DEFAULT_WA_VARIANTS: List[str] = [
    "와",
    "와아",
    "와아아",
]


# (11) "좋" 포함 시 랜덤 응답 후보
DEFAULT_GOOD_VARIANTS: List[str] = [
    "좋당",
    "좋습니다",
    "좋습니당",
    "좋네용",
    "좋군요",
    "좋아",
    "좋아용",
    "조씁니당",
    "굳",
    "굿",
    "굳굳",
    "굿굿",
    "굳굳굳",
    "굿굿굿",
]


# (12) "아하" 또는 "ㅇㅎ" 포함 시 랜덤 응답 후보
DEFAULT_AHA_VARIANTS: List[str] = [
    "아하",
    "아항",
    "ㅇㅎ",
    "그렇군요",
    "그렇군용",
]


# (13) "캬" 포함 시 랜덤 응답 후보
DEFAULT_KYA_VARIANTS: List[str] = [
    "캬",
    "캬아",
    "캬 ~",
    "캬 ㅏㅏㅏㅏ",
]


# (14) "짠" 포함 시 랜덤 응답 후보
DEFAULT_JJAN_VARIANTS: List[str] = [
    "짠",
    "짠 !",
    "짠짠",
]


# (15) "안녕" 포함 시 랜덤 응답 후보
DEFAULT_HELLO_VARIANTS: List[str] = [
    "안녕하세용",
    "안뇽하세용",
    "안녕하세요 ~",
    "안뇽하세요",
    "하이요 !",
]


# (16) "대륙남" 포함 시 랜덤 응답 후보
DEFAULT_DAERYUKNAM_VARIANTS: List[str] = [
    "킹륙남",
    "대륙남 굿",
    "대륙남 짱이다 ㅋㅋㅋ",
    "륙남이 형 멋지당 ~ !",
]


# (11-1) [수정] "ㄷㅇㅎㅇ" 포함 시 랜덤 응답 후보 (기존 16-1에서 이동)
DEFAULT_DWHW_VARIANTS: List[str] = [
    "ㄷㅇㅎㅇ",
    "ㄷㅇㅎㅇ !",
    "ㄷㅇㅎㅇ ~ !",
    "ㄷㅇㅎㅇ !!",
]


# (16-2) "어서오세" 포함 시 랜덤 응답 후보
DEFAULT_EOSEOOSE_VARIANTS: List[str] = [
    "어서오세용",
    "어서오세요 ~",
]


# (17-1) [신규] "하" 단독 시 랜덤 응답 후보
DEFAULT_HA_SOLO_VARIANTS: List[str] = [
    "하 ... ㅠㅠ",
    "하 ... ㅠㅠㅠ",
]


DEFAULT_INTERJECTION_O_RX: str = r"(^|\s)오([~!?.]+)?($|\s)"


# (17) 메시지 전체가 물음표만(2개 이상)인 경우만 매칭
DEFAULT_QMARK_ONLY_RX: str = r"^\?{2,}$"


# (17-1) [신규] "하" 단독 (메시지 전체가 "하"만, 뒤에 공백/느낌표/물결 허용)
DEFAULT_HA_SOLO_RX: str = r"^하[~!?.…\s]*$"


# (1) "ㅇㅇㄱ" 공백 허용 (1회 이상이면 True)
DEFAULT_YYG_RX: str = r"(ㅇ\s*ㅇ\s*ㄱ)"


# (1) 로그 라인에서 NickName/Message 파싱 (대소문자 혼용 허용)
DEFAULT_LINE_PARSE_RX: str = r"nickname\s*:\s*(?P<nick>.*?)\s+message\s*:\s*(?P<msg>.*)$"


# (1) 별풍선 조건 대상 닉네임 (정확히)
DEFAULT_BALLOON_NICKNAME: str = "신설아♡"



class Track1Rules:
    def __init__(self, cfg) -> None:
        self.cfg = cfg


        self._max_repeat = max(1, int(getattr(cfg, "max_repeat", 5)))


        rep_over = getattr(cfg, "repeat_rx_to_unit", None)
        tok_over = getattr(cfg, "token_to_unit", None)
        o_over = getattr(cfg, "interjection_o_rx", None)


        yyg_over = getattr(cfg, "yyg_rx", None)
        parse_over = getattr(cfg, "line_parse_rx", None)
        balloon_nick_over = getattr(cfg, "balloon_nickname", None)


        qmark_over = getattr(cfg, "qmark_only_rx", None)
        ha_solo_over = getattr(cfg, "ha_solo_rx", None)


        good_over = getattr(cfg, "good_variants", None)
        aha_over = getattr(cfg, "aha_variants", None)
        heok_over = getattr(cfg, "heok_variants", None)
        naneun_over = getattr(cfg, "naneun_variants", None)
        kiki_over = getattr(cfg, "kiki_variants", None)
        sad_over = getattr(cfg, "sad_variants", None)
        wa_over = getattr(cfg, "wa_variants", None)
        kya_over = getattr(cfg, "kya_variants", None)
        jjan_over = getattr(cfg, "jjan_variants", None)
        hello_over = getattr(cfg, "hello_variants", None)
        daeryuknam_over = getattr(cfg, "daeryuknam_variants", None)
        dwhw_over = getattr(cfg, "dwhw_variants", None)
        eoseoose_over = getattr(cfg, "eoseoose_variants", None)
        ha_solo_v_over = getattr(cfg, "ha_solo_variants", None)
        jjeolsu_over = getattr(cfg, "jjeolsu_variants", None)


        repeat_map: Dict[str, str] = dict(DEFAULT_REPEAT_RX_TO_UNIT)
        if isinstance(rep_over, dict) and rep_over:
            repeat_map.update({str(k): str(v) for k, v in rep_over.items()})


        token_map: Dict[str, str] = dict(DEFAULT_TOKEN_TO_UNIT)
        if isinstance(tok_over, dict) and tok_over:
            token_map.update({str(k): str(v) for k, v in tok_over.items()})


        o_rx_str = str(o_over) if (o_over is not None and str(o_over).strip()) else DEFAULT_INTERJECTION_O_RX
        yyg_rx_str = str(yyg_over) if (yyg_over is not None and str(yyg_over).strip()) else DEFAULT_YYG_RX
        parse_rx_str = str(parse_over) if (parse_over is not None and str(parse_over).strip()) else DEFAULT_LINE_PARSE_RX
        balloon_nick = (
            str(balloon_nick_over).strip()
            if (balloon_nick_over is not None and str(balloon_nick_over).strip())
            else DEFAULT_BALLOON_NICKNAME
        )
        qmark_rx_str = str(qmark_over) if (qmark_over is not None and str(qmark_over).strip()) else DEFAULT_QMARK_ONLY_RX
        ha_solo_rx_str = str(ha_solo_over) if (ha_solo_over is not None and str(ha_solo_over).strip()) else DEFAULT_HA_SOLO_RX


        def _coerce_list(over, default_list: List[str]) -> List[str]:
            lst: List[str] = list(default_list)
            if isinstance(over, list) and over:
                lst = [str(x) for x in over if str(x).strip()]
            return lst


        self._good_variants = _coerce_list(good_over, DEFAULT_GOOD_VARIANTS)
        self._aha_variants = _coerce_list(aha_over, DEFAULT_AHA_VARIANTS)
        self._heok_variants = _coerce_list(heok_over, DEFAULT_HEOK_VARIANTS)
        self._naneun_variants = _coerce_list(naneun_over, DEFAULT_NANEUN_VARIANTS)
        self._kiki_variants = _coerce_list(kiki_over, DEFAULT_KIKI_VARIANTS)
        self._sad_variants = _coerce_list(sad_over, DEFAULT_SAD_VARIANTS)
        self._wa_variants = _coerce_list(wa_over, DEFAULT_WA_VARIANTS)
        self._kya_variants = _coerce_list(kya_over, DEFAULT_KYA_VARIANTS)
        self._jjan_variants = _coerce_list(jjan_over, DEFAULT_JJAN_VARIANTS)
        self._hello_variants = _coerce_list(hello_over, DEFAULT_HELLO_VARIANTS)
        self._daeryuknam_variants = _coerce_list(daeryuknam_over, DEFAULT_DAERYUKNAM_VARIANTS)
        self._dwhw_variants = _coerce_list(dwhw_over, DEFAULT_DWHW_VARIANTS)
        self._eoseoose_variants = _coerce_list(eoseoose_over, DEFAULT_EOSEOOSE_VARIANTS)
        self._ha_solo_variants = _coerce_list(ha_solo_v_over, DEFAULT_HA_SOLO_VARIANTS)
        self._jjeolsu_variants = _coerce_list(jjeolsu_over, DEFAULT_JJEOLSU_VARIANTS)


        self._repeat_rx: List[Tuple[re.Pattern, str]] = [(re.compile(pat), unit) for pat, unit in repeat_map.items()]
        self._token_to_unit = token_map
        self._o_rx = re.compile(o_rx_str)
        self._yyg_unit_rx = re.compile(yyg_rx_str)
        self._line_parse_rx = re.compile(parse_rx_str, flags=re.IGNORECASE)
        self._balloon_nickname = balloon_nick
        self._qmark_only_rx = re.compile(qmark_rx_str)
        self._ha_solo_rx = re.compile(ha_solo_rx_str)


    def _parse_line(self, raw: str) -> Tuple[str, str]:
        s = raw or ""
        m = self._line_parse_rx.search(s)
        if not m:
            return "", s
        nick = (m.group("nick") or "").strip()
        msg = (m.group("msg") or "").strip()
        return nick, msg


    def _msg_has_yyg(self, msg_text: str) -> bool:
        t = normalize_text(msg_text)
        if not t:
            return False
        return bool(self._yyg_unit_rx.search(t))


    def _is_qmark_only(self, msg_text: str) -> bool:
        t = normalize_text(msg_text)
        if not t:
            return False
        return bool(self._qmark_only_rx.match(t))


    def _is_ha_solo(self, msg_text: str) -> bool:
        t = normalize_text(msg_text)
        if not t:
            return False
        return bool(self._ha_solo_rx.match(t))


    def can_handle(self, message: str) -> bool:
        raw = message or ""
        nick, msg = self._parse_line(raw)


        t_msg = normalize_text(msg)
        if not t_msg:
            return False


        # (1) NickName: 신설아♡ + 별풍선 OR (메시지 내 ㅇㅇㄱ 1회 이상)
        if (nick == self._balloon_nickname and ("별풍선" in t_msg)) or self._msg_has_yyg(msg):
            return True


        # (2) "ㅇㅈ" 포함
        if "ㅇㅈ" in t_msg:
            return True


        # (3) "헉" 포함
        if "헉" in t_msg:
            return True


        # (3-1) "ㅈㅉㅇㅇ" 또는 "진짜" 포함
        if ("ㅈㅉㅇㅇ" in t_msg) or ("진짜" in t_msg):
            return True


        # (4) "ㅍㄴㅍㄴ" 포함
        if "ㅍㄴㅍㄴ" in t_msg:
            return True


        # (5) "ㅅㅅ" 포함
        if "ㅅㅅ" in t_msg:
            return True


        # (5-1) [신규] "잘들립니다" 또는 "잘 들립니다" 포함
        if ("잘들립니다" in t_msg) or ("잘 들립니다" in t_msg):
            return True


        # (6) "나는" 포함
        if "나는" in t_msg:
            return True


        # (6-1) [신규] "했지요","있다함" 등 포함
        if any(kw in t_msg for kw in ("했지요", "있다함", "있다 함", "있다고함", "있다고 함", "하네요")):
            return True


        # (7) "키키" 포함
        if "키키" in t_msg:
            return True


        # (8) ㅠ/ㅜ/서운 포함
        if ("ㅠ" in t_msg) or ("ㅜ" in t_msg) or ("서운" in t_msg):
            return True


        # (8-1) [신규] "쩔수" 포함
        if "쩔수" in t_msg:
            return True


        # (9) "와" 포함
        if "와" in t_msg:
            return True


        # (10) "역시" 포함
        if "역시" in t_msg:
            return True


        # (11) "좋" 포함
        if "좋" in t_msg:
            return True


        # (11-1) [수정] "ㄷㅇㅎㅇ" 포함 (ㅇㅎ 보다 먼저 검사!)
        if "ㄷㅇㅎㅇ" in t_msg:
            return True


        # (12) "아하" 또는 "ㅇㅎ" 포함
        if ("아하" in t_msg) or ("ㅇㅎ" in t_msg):
            return True


        # (13) "캬" 포함
        if "캬" in t_msg:
            return True


        # (14) "짠" 포함
        if "짠" in t_msg:
            return True


        # (15) "안녕" 포함
        if "안녕" in t_msg:
            return True


        # (16) "대륙남" 포함
        if "대륙남" in t_msg:
            return True


        # (16-2) "어서오세" 포함
        if "어서오세" in t_msg:
            return True


        # (17) 메시지 전체가 '??' 이상 인 경우만
        if self._is_qmark_only(msg):
            return True


        # (17-1) [신규] "하" 단독
        if self._is_ha_solo(msg):
            return True


        # (18) 반복 문자
        for rx, _unit in self._repeat_rx:
            if rx.search(t_msg):
                return True


        # (19) 토큰 매칭
        toks = tokenize_ko_simple(t_msg)
        for tok in toks:
            if tok in self._token_to_unit:
                return True


        # (20) "오" 감탄사
        if self._o_rx.search(t_msg):
            return True


        return False


    def respond(self, message: str) -> Optional[str]:
        raw = message or ""
        nick, msg = self._parse_line(raw)


        t_msg = normalize_text(msg)
        if not t_msg:
            return None


        # (1) NickName: 신설아♡ + 별풍선 OR (메시지 내 ㅇㅇㄱ 1회 이상) -> 즉시 "ㅇㅇㄱ"
        if (nick == self._balloon_nickname and ("별풍선" in t_msg)) or self._msg_has_yyg(msg):
            return "ㅇㅇㄱ"


        # (2) "ㅇㅈ" 포함 -> "ㅇㅈ" 또는 "ㅇㅈㅇㅈ"
        if "ㅇㅈ" in t_msg:
            n = random.randint(1, 2)
            return "ㅇㅈ" * n


        # (3) "헉" 포함
        if "헉" in t_msg:
            return random.choice(self._heok_variants) if self._heok_variants else "헉"


        # (3-1) "ㅈㅉㅇㅇ" 또는 "진짜" 포함
        if ("ㅈㅉㅇㅇ" in t_msg) or ("진짜" in t_msg):
            return "ㅈㅉㅇㅇ ??"


        # (4) "ㅍㄴㅍㄴ" 포함
        if "ㅍㄴㅍㄴ" in t_msg:
            return "ㅍㄴㅍㄴ"


        # (5) "ㅅㅅ" 포함
        if "ㅅㅅ" in t_msg:
            return "ㅅㅅㅅ"


        # (5-1) [신규] "잘들립니다" 또는 "잘 들립니다" 포함
        if ("잘들립니다" in t_msg) or ("잘 들립니다" in t_msg):
            return "잘 들립니당"


        # (6) "나는" 포함
        if "나는" in t_msg:
            return random.choice(self._naneun_variants) if self._naneun_variants else "그렇군요"


        # (6-1) [신규] "했지요","있다함" 등 포함
        if any(kw in t_msg for kw in ("했지요", "있다함", "있다 함", "있다고함", "있다고 함", "하네요")):
            return "그렇군용"


        # (7) "키키" 포함
        if "키키" in t_msg:
            return random.choice(self._kiki_variants) if self._kiki_variants else "키키"


        # (8) ㅠ/ㅜ/서운 포함
        if ("ㅠ" in t_msg) or ("ㅜ" in t_msg) or ("서운" in t_msg):
            return random.choice(self._sad_variants) if self._sad_variants else "ㅠㅠㅠ"


        # (8-1) [신규] "쩔수" 포함
        if "쩔수" in t_msg:
            return random.choice(self._jjeolsu_variants) if self._jjeolsu_variants else "쩔수 ㅠㅠㅠ"


        # (9) "와" 포함
        if "와" in t_msg:
            return random.choice(self._wa_variants) if self._wa_variants else "와"


        # (10) "역시" 포함
        if "역시" in t_msg:
            n = random.randint(2, 5)
            return "역시 " + ("ㅋ" * n)


        # (11) "좋" 포함
        if "좋" in t_msg:
            return random.choice(self._good_variants) if self._good_variants else "좋습니다"


        # (11-1) [수정] "ㄷㅇㅎㅇ" 포함 (ㅇㅎ 보다 먼저 검사!)
        if "ㄷㅇㅎㅇ" in t_msg:
            return random.choice(self._dwhw_variants) if self._dwhw_variants else "ㄷㅇㅎㅇ"


        # (12) "아하" 또는 "ㅇㅎ" 포함
        if ("아하" in t_msg) or ("ㅇㅎ" in t_msg):
            return random.choice(self._aha_variants) if self._aha_variants else "아하"


        # (13) "캬" 포함
        if "캬" in t_msg:
            return random.choice(self._kya_variants) if self._kya_variants else "캬"


        # (14) "짠" 포함
        if "짠" in t_msg:
            return random.choice(self._jjan_variants) if self._jjan_variants else "짠"


        # (15) "안녕" 포함
        if "안녕" in t_msg:
            return random.choice(self._hello_variants) if self._hello_variants else "안녕하세요 ~"


        # (16) "대륙남" 포함
        if "대륙남" in t_msg:
            return random.choice(self._daeryuknam_variants) if self._daeryuknam_variants else "킹륙남"


        # (16-2) "어서오세" 포함
        if "어서오세" in t_msg:
            return random.choice(self._eoseoose_variants) if self._eoseoose_variants else "어서오세용"


        # (17) 메시지 전체가 '??' 이상 -> 출력은 '?' 2~5개
        if self._is_qmark_only(msg):
            n = random.randint(2, 5)
            return "?" * n


        # (17-1) [신규] "하" 단독
        if self._is_ha_solo(msg):
            return random.choice(self._ha_solo_variants) if self._ha_solo_variants else "하 ... ㅠㅠ"


        # (18) 반복 문자
        for rx, unit in self._repeat_rx:
            if rx.search(t_msg):
                n = random.randint(1, self._max_repeat)
                return unit * n


        # (19) 토큰 매칭
        toks = tokenize_ko_simple(t_msg)
        for tok in toks:
            unit = self._token_to_unit.get(tok)
            if unit:
                if tok == "ㅇㅈ":
                    n = random.randint(1, 2)
                    return unit * n
                n = random.randint(1, self._max_repeat)
                return unit * n


        # (20) "오" 감탄사
        if self._o_rx.search(t_msg):
            n = random.randint(1, self._max_repeat)
            return "오" * n


        return None

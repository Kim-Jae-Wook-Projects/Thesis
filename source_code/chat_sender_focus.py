# chat_sender_focus.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import List, Set, Optional

try:
    import pyautogui
except Exception:  # pragma: no cover
    pyautogui = None

try:
    import pyperclip
except Exception:  # pragma: no cover
    pyperclip = None

@dataclass
class FocusSenderConfig:
    # Rate limit (avoid spam / platform throttling)
    min_interval_sec: float = 1.5

    # Dedup (avoid sending same line repeatedly)
    dedup_cache_size: int = 200

    # Paste-based send for Korean stability
    use_clipboard_paste: bool = True
    paste_hotkey_mod: str = "command"  # macOS: command+v

    # Timing controls
    hotkey_inter_key_sec: float = 1.0   # 1.0초로 증가
    pre_paste_delay_sec: float = 1.0    # 1.0초로 증가
    post_paste_delay_sec: float = 0.5   # 0.5초로 증가

    # Send action
    send_key: str = "enter"  # usually enter; change if platform needs different
    send_hotkey_mod: Optional[str] = None  # for example ! "command" for cmd+enter


class FocusChatSender:
    """
    Korean-safe sender:
    - Assumes user manually focuses the chat input box.
    - Sends message via clipboard paste (Cmd+V) to avoid Korean IME composition breakage.
    - Presses Enter (or a hotkey) to submit.
    """

    def __init__(self, cfg: Optional[FocusSenderConfig] = None) -> None:
        if pyautogui is None:
            raise RuntimeError("pyautogui not available. Install: pip install pyautogui")

        self.cfg = cfg or FocusSenderConfig()

        if self.cfg.use_clipboard_paste and pyperclip is None:
            raise RuntimeError("pyperclip not available. Install: pip install pyperclip")

        self._last_send_ts: float = 0.0
        self._dedup: List[str] = []
        self._dedup_set: Set[str] = set()

        pyautogui.PAUSE = 0.0
        pyautogui.FAILSAFE = True  # move mouse to top-left corner to abort immediately

    def _dedup_ok(self, text: str) -> bool:
        t = (text or "").strip()
        if not t:
            return False
        if t in self._dedup_set:
            return False
        self._dedup.append(t)
        self._dedup_set.add(t)
        if len(self._dedup) > int(self.cfg.dedup_cache_size):
            old = self._dedup.pop(0)
            self._dedup_set.discard(old)
        return True

    def _rate_limit_ok(self) -> bool:
        now = time.monotonic()
        return (now - self._last_send_ts) >= float(self.cfg.min_interval_sec)

    def _mark_sent(self) -> None:
        self._last_send_ts = time.monotonic()

    def _safe_hotkey(self, modifier: str, key: str) -> None:
        """
        강제로 1.0초 이상의 딜레이를 주어 Mac OS가 Command 키를
        완벽히 인식할 수 있도록 보장합니다.
        """
        # 외부 cfg 설정과 무관하게 무조건 최소 1.0초를 강제
        delay = max(1.0, float(self.cfg.hotkey_inter_key_sec))

        pyautogui.keyDown(modifier)
        time.sleep(delay)

        pyautogui.keyDown(key)
        time.sleep(delay)

        pyautogui.keyUp(key)
        time.sleep(delay)

        pyautogui.keyUp(modifier)

    def _do_send_key(self) -> None:
        if self.cfg.send_hotkey_mod:
            self._safe_hotkey(self.cfg.send_hotkey_mod, self.cfg.send_key)
        else:
            pyautogui.press(self.cfg.send_key)

    def send(self, text: str) -> bool:
        msg = (text or "").strip()
        if not msg:
            return False
        if not self._dedup_ok(msg):
            return False
        if not self._rate_limit_ok():
            return False

        try:
            if self.cfg.use_clipboard_paste:
                pyperclip.copy(msg)

                # 클립보드에 값이 들어갈 수 있도록 최소 1.0초를 강제로 대기
                pre_delay = max(1.0, float(self.cfg.pre_paste_delay_sec))
                time.sleep(pre_delay)

                self._safe_hotkey(self.cfg.paste_hotkey_mod, "v")

                if self.cfg.post_paste_delay_sec > 0:
                    time.sleep(float(self.cfg.post_paste_delay_sec))
            else:
                pyautogui.write(msg, interval=0.03)

            self._do_send_key()
            self._mark_sent()
            return True
        except Exception:
            return False
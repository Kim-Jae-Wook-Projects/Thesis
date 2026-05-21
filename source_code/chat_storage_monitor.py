# chat_storage_monitor.py
# -*- coding: utf-8 -*-

import os
import re
from datetime import datetime
from collections import Counter, deque
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _ts_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _get_default_status_dir(
    base_dir: str = "output",
    sub_dir: str = "chat_storage_monitor",
) -> str:
    """
    기본 출력 디렉터리: <현재 파일 위치>/output/chat_storage_monitor
    """
    root = Path(__file__).resolve().parent
    out_dir = (root / base_dir / sub_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    return str(out_dir)


def is_system_saved_after_message(rank_str: str, nickname_str: str, message_str: str) -> bool:
    """
    NickName이 "This chat was saved after HH:MM:SS." 이면 CSV에 저장하지 않음
    - 일반적으로 Rank/Message가 [NONE]인 시스템 라인
    """
    nick = (nickname_str or "").strip()
    if not re.match(r"^This chat was saved after \d{2}:\d{2}:\d{2}\.$", nick):
        return False

    r = (rank_str or "").strip()
    m = (message_str or "").strip()
    return (r == "" or r == "[NONE]") and (m == "" or m == "[NONE]")


def tokenize_simple(msg: str) -> List[str]:
    msg = (msg or "").strip()
    if not msg or msg == "[NONE]":
        return []
    tokens = re.findall(r"[0-9A-Za-z가-힣]+", msg)
    return [t for t in tokens if len(t) >= 2]


class ChatStorageMonitor:
    """
    - feed(): record를 10분 윈도우에 누적
    - maybe_write_report(): 10분마다 status TXT를 '새 파일명'으로 누적 생성

    출력물 저장 위치 정책:
    1) 외부에서 status_dir=... 를 넘기면 그 경로 사용
    2) 아니면 기본값: output/chat_storage_monitor
    """

    def __init__(
        self,
        window_sec: int = 600,
        report_interval_sec: int = 600,
        status_dir: Optional[str] = None,          # 기존 코드가 넘기는 인자
        base_output_dir: str = "output",
        status_subdir: str = "chat_storage_monitor",
    ):
        self.window_sec = int(window_sec)
        self.report_interval_sec = int(report_interval_sec)

        # status_dir가 오면 그대로 사용, 없으면 output/<subdir> 사용
        self.status_dir = (status_dir or _get_default_status_dir(base_dir=base_output_dir, sub_dir=status_subdir))
        _ensure_dir(self.status_dir)

        self.recent: deque[Tuple[float, Dict[str, str]]] = deque()
        self.next_report_ts: Optional[float] = None

        self.total_written_csv = 0
        self.total_filtered = 0
        self.total_seen = 0

    def bump_seen(self, total_seen: int) -> None:
        self.total_seen = int(total_seen)

    def bump_written_csv(self, n: int = 1) -> None:
        self.total_written_csv += int(n)

    def bump_filtered(self, n: int = 1) -> None:
        self.total_filtered += int(n)

    def feed(self, now_mono: float, record: Dict[str, str]) -> None:
        self.recent.append((now_mono, record))

    def _trim(self, now_mono: float) -> None:
        cutoff = now_mono - self.window_sec
        while self.recent and self.recent[0][0] < cutoff:
            self.recent.popleft()

    def _write_report(self, window_records: List[Dict[str, str]]) -> str:
        rank_counter = Counter()
        nick_counter = Counter()
        word_counter = Counter()
        none_msg_cnt = 0

        for r in window_records:
            rank = (r.get("rank") or "").strip() or "[NONE]"
            nick = (r.get("nickname") or "").strip()
            msg = (r.get("message") or "").strip()

            rank_counter[rank] += 1
            if nick:
                nick_counter[nick] += 1
            if msg == "" or msg == "[NONE]":
                none_msg_cnt += 1
            for w in tokenize_simple(msg):
                word_counter[w] += 1

        out_path = os.path.join(self.status_dir, f"{_ts_for_filename()}_status.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("[CHAT MONITOR REPORT]\n")
            f.write(f"Time: {_now_iso()}\n")
            f.write(f"Window: last {self.window_sec} sec\n\n")

            f.write("[Totals]\n")
            f.write(f"- total_seen(msg_id): {self.total_seen}\n")
            f.write(f"- total_written_csv: {self.total_written_csv}\n")
            f.write(f"- total_filtered: {self.total_filtered}\n\n")

            f.write("[Window]\n")
            f.write(f"- new_records_in_window: {len(window_records)}\n")
            f.write(f"- message == [NONE] or empty: {none_msg_cnt}\n\n")

            f.write("[Rank Distribution]\n")
            for k, v in rank_counter.most_common():
                f.write(f"- {k}: {v}\n")
            f.write("\n")

            f.write("[Top Nicknames]\n")
            for nick, cnt in nick_counter.most_common(10):
                f.write(f"- {nick}: {cnt}\n")
            if not nick_counter:
                f.write("- (none)\n")
            f.write("\n")

            f.write("[Top Words]\n")
            for w, cnt in word_counter.most_common(10):
                f.write(f"- {w}: {cnt}\n")
            if not word_counter:
                f.write("- (none)\n")

        return out_path

    def maybe_write_report(self, now_mono: float) -> Optional[str]:
        if self.next_report_ts is None:
            self.next_report_ts = now_mono + self.report_interval_sec
            return None
        if now_mono < self.next_report_ts:
            return None

        self._trim(now_mono)
        window_records = [r for _, r in self.recent]
        out = self._write_report(window_records)

        self.next_report_ts += self.report_interval_sec
        return out


def main() -> None:
    # import 용. 단독 테스트 시 출력 디렉터리만 확인
    m = ChatStorageMonitor()
    print(f"[chat_storage_monitor] status_dir: {m.status_dir}")


if __name__ == "__main__":
    main()

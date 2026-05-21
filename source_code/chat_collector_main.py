# chat_collector_main.py
# -*- coding: utf-8 -*-

import os
import csv
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


def _ts_for_filename() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path: str) -> None:
    Path(path).mkdir(parents=True, exist_ok=True)


def _get_default_out_dir(base_dir: str = "output", sub_dir: str = "chat_collector_main") -> Path:
    """
    기본 출력 디렉터리: <현재 파일 위치>/output/chat_collector_main
    """
    root = Path(__file__).resolve().parent
    out_dir = (root / base_dir / sub_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _normalize_path_under_out_dir(p: str, out_dir: Path) -> str:
    """
    - p가 절대경로면 그대로 사용
    - p가 상대경로면 out_dir 하위로 붙여서 사용
    """
    p_obj = Path(p)
    if p_obj.is_absolute():
        return str(p_obj)
    return str((out_dir / p_obj).resolve())


def init_csv_if_needed(csv_path: str, fieldnames: List[str], encoding: str = "utf-8-sig") -> None:
    if os.path.exists(csv_path) and os.path.getsize(csv_path) > 0:
        return

    # 상위 디렉터리 생성
    Path(csv_path).parent.mkdir(parents=True, exist_ok=True)

    with open(csv_path, "w", newline="", encoding=encoding) as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()


class ChatCSVCollector:
    """
    - append(): 채팅 dict를 CSV에 누적 저장
    - maybe_snapshot(): 주기마다 스냅샷 CSV를 '새 파일명'으로 누적 생성

    출력물 저장 위치 정책(호환성 유지):
    - 기존처럼 csv_path / snapshot_dir 를 외부에서 넘길 수 있음(시그니처 유지)
    - 다만 csv_path/snapshot_dir가 "상대경로"라면, 자동으로 output/chat_collector_main/ 아래로 정리
      예) csv_path="chat.csv" -> output/chat_collector_main/chat.csv
          snapshot_dir="snapshots" -> output/chat_collector_main/snapshots
    - 절대경로를 넘기면 사용자가 지정한 위치 그대로 사용
    """

    def __init__(
        self,
        csv_path: str,
        fieldnames: List[str],
        encoding: str = "utf-8-sig",
        snapshot_dir: str = "snapshots",
        snapshot_interval_sec: int = 600,
        enable_snapshot: bool = True,
        base_output_dir: str = "output",
        out_subdir: str = "chat_collector_main",
    ):
        self.fieldnames = fieldnames
        self.encoding = encoding

        # 기본 output 하위 디렉터리
        self.out_dir = _get_default_out_dir(base_dir=base_output_dir, sub_dir=out_subdir)

        # 상대경로로 들어오면 out_dir 아래로 정리, 절대경로면 그대로 사용
        self.csv_path = _normalize_path_under_out_dir(csv_path, self.out_dir)
        self.snapshot_dir = _normalize_path_under_out_dir(snapshot_dir, self.out_dir)

        self.snapshot_interval_sec = int(snapshot_interval_sec)
        self.enable_snapshot = bool(enable_snapshot)

        self.next_snapshot_ts: Optional[float] = None

        init_csv_if_needed(self.csv_path, self.fieldnames, encoding=self.encoding)

    def append(self, record: Dict[str, str]) -> None:
        with open(self.csv_path, "a", newline="", encoding=self.encoding) as f:
            w = csv.DictWriter(f, fieldnames=self.fieldnames)
            w.writerow(record)

    def _create_snapshot(self) -> str:
        _ensure_dir(self.snapshot_dir)

        if not os.path.exists(self.csv_path) or os.path.getsize(self.csv_path) == 0:
            return ""

        snap_path = os.path.join(self.snapshot_dir, f"chat_snapshot_{_ts_for_filename()}.csv")
        shutil.copy2(self.csv_path, snap_path)
        return snap_path

    def maybe_snapshot(self, now_mono: float) -> Optional[str]:
        if not self.enable_snapshot:
            return None
        if self.next_snapshot_ts is None:
            self.next_snapshot_ts = now_mono + self.snapshot_interval_sec
            return None
        if now_mono < self.next_snapshot_ts:
            return None

        out = self._create_snapshot()
        self.next_snapshot_ts += self.snapshot_interval_sec
        return out


def main() -> None:
    # import 용이 기본. 단독 테스트 시 기본 저장 경로 확인
    out_dir = _get_default_out_dir()
    print(f"[chat_collector_main] out_dir: {out_dir}")
    print(f"[chat_collector_main] default examples:")
    print(f"  - csv_path='chat_data.csv' -> {out_dir / 'chat_data.csv'}")
    print(f"  - snapshot_dir='snapshots' -> {out_dir / 'snapshots'}")


if __name__ == "__main__":
    main()

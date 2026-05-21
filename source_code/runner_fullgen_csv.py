# runner_fullgen_csv.py
# -*- coding: utf-8 -*-


from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import time
from collections import deque
from datetime import datetime
from typing import Deque, Dict, List

# ---- run_realtime_focus_csv.py 에서 CSV tailing 유틸리티 재사용 ----
from run_realtime_focus_csv import (
    TailState,
    tail_csv_append_lines,
    _safe_norm_text,
    _is_blocked_single_char,
    _prune_ttl_map,
)

# ---- 전송 모듈 (run_realtime_focus_csv.py 와 동일) ----
from chat_sender_focus import FocusChatSender, FocusSenderConfig

# ---- 비교 실험용 LLM 전체 생성 클래스 ----
from baseline_fullgen import BaselineFullGen, BaselineFullGenConfig


# ----------------------------
# 문맥 버퍼
# ----------------------------

CONTEXT_SIZE = 5  # 직전 5개 메시지를 문맥으로 기록


class ContextBuffer:
    """최근 N개 메시지를 유지하는 간단한 버퍼."""

    def __init__(self, size: int = CONTEXT_SIZE) -> None:
        self._size = max(1, int(size))
        self._buf: Deque[str] = deque(maxlen=self._size)

    def observe(self, message: str) -> None:
        """새 메시지를 버퍼에 추가한다."""
        t = _safe_norm_text(message)
        if t:
            self._buf.append(t)

    def snapshot(self) -> List[str]:
        """
        현재 버퍼의 스냅샷을 반환한다.
        길이가 CONTEXT_SIZE 보다 적으면 빈 문자열로 채운다.
        반환 리스트: [context_1(가장 오래된), ..., context_N(가장 최근)]
        """
        items = list(self._buf)
        # 부족한 만큼 앞쪽에 빈 문자열 채움
        while len(items) < self._size:
            items.insert(0, "")
        return items


# ----------------------------
# 결과 CSV 관리
# ----------------------------

RESULT_FIELDS = [
    "seq",
    "msg_id",
    "ts_original",
    "ts_response",
    "nickname",
    "context_1",
    "context_2",
    "context_3",
    "context_4",
    "context_5",
    "message",
    "response",
    "sent",
    "latency_sec",
    "response_len",
]


def _init_result_csv(path: str) -> None:
    """
    결과 CSV 파일을 초기화한다.
    [v2 수정] 기존 파일이 존재하고 내용이 있으면 덮어쓰지 않는다.
    파일이 없거나 빈 파일일 때만 헤더를 새로 작성한다.
    """
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    # 기존 파일이 있고 내용이 있으면 건드리지 않음
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"[INFO] 기존 결과 파일 발견, 이어쓰기 모드: {path}")
        return

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
    print(f"[INFO] 새 결과 파일 생성: {path}")


def _backup_result_csv(path: str) -> None:
    """
    기존 결과 파일이 있으면 자동 백업을 생성한다.
    백업 파일명: 원본_backup_YYYYMMDD_HHMMSS.csv
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return

    base, ext = os.path.splitext(path)
    backup = f"{base}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    shutil.copy2(path, backup)
    print(f"[INFO] 기존 결과 백업 완료: {backup}")


def _get_last_seq(path: str) -> int:
    """
    기존 결과 CSV 에서 마지막 seq 번호를 읽어온다.
    이어쓰기 시 seq 가 1 부터 다시 시작되지 않도록 한다.
    파일이 없거나 읽기 실패 시 0 을 반환한다.
    """
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return 0

    last_seq = 0
    try:
        with open(path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                try:
                    s = int(row.get("seq", 0))
                    if s > last_seq:
                        last_seq = s
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    return last_seq


def _append_result(path: str, record: dict) -> None:
    """결과 CSV 파일에 한 행을 추가한다."""
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writerow(record)


# ----------------------------
# 요약 통계
# ----------------------------

def _print_summary(
    total_seen: int,
    total_processed: int,
    total_nonempty: int,
    total_sent: int,
    latencies: List[float],
    model_name: str,
) -> None:
    """실험 종료 시 요약 통계를 stdout 에 출력한다."""
    print("\n" + "=" * 60)
    print("[SUMMARY]")
    print(f"  Model                      : {model_name}")
    print(f"  Total messages seen        : {total_seen}")
    print(f"  Total messages processed   : {total_processed}")
    print(f"  Non-empty responses        : {total_nonempty}")
    print(f"  Actually sent to chat      : {total_sent}")

    if latencies:
        avg_lat = sum(latencies) / len(latencies)
        sorted_lat = sorted(latencies)
        n = len(sorted_lat)
        mid = n // 2
        if n % 2 == 1:
            median_lat = sorted_lat[mid]
        else:
            median_lat = (sorted_lat[mid - 1] + sorted_lat[mid]) / 2.0
        min_lat = sorted_lat[0]
        max_lat = sorted_lat[-1]
        print(f"  Avg  latency (sec)         : {avg_lat:.4f}")
        print(f"  Median latency (sec)       : {median_lat:.4f}")
        print(f"  Min  latency (sec)         : {min_lat:.4f}")
        print(f"  Max  latency (sec)         : {max_lat:.4f}")
    else:
        print("  (no latency data)")

    print("=" * 60)
    sys.stdout.flush()


# ----------------------------
# Main
# ----------------------------

def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "비교 실험 runner: LLM 전체 생성 (방법 2, 3). "
            "ChatDataExtraction_main.py 와 동시에 실행하여 "
            "동일 VOD 채팅을 LLM 으로 처리하고, 생성된 응답을 라이브 채팅에 전송한다."
        )
    )

    # ---- 필수 ----
    ap.add_argument(
        "--csv", dest="csv_path", required=True,
        help=(
            "ChatDataExtraction_main.py 가 생성하는 chat CSV 경로. "
            '예: "output/chat_collector_main/chat.csv"'
        ),
    )
    ap.add_argument(
        "--model", dest="model_name", required=True,
        help=(
            "HuggingFace 모델 이름 또는 로컬 경로. "
            "예: LGAI-EXAONE/EXAONE-4.0-1.2B"
        ),
    )
    ap.add_argument(
        "--bot-nick", dest="bot_nick", required=True,
        help="봇 닉네임 (자기 메시지 건너뛰기 + 전송 시 필수)",
    )

    # ---- 결과 출력 ----
    ap.add_argument(
        "--output", dest="output_csv", default="result_fullgen.csv",
        help="결과 CSV 저장 경로 (기본: result_fullgen.csv)",
    )

    # ---- 선택 ----
    ap.add_argument(
        "--max-messages", dest="max_messages", type=int, default=0,
        help=(
            "최대 처리 메시지 수 (0 = 무제한). "
            "7.8B 모델은 CPU 에서 매우 느리므로 적절한 수를 지정 권장. "
            "예: --max-messages 200"
        ),
    )
    ap.add_argument(
        "--device", dest="device", default="cpu",
        help="torch device (기본: cpu, NVIDIA GPU 사용 시: cuda)",
    )

    # ---- 전송 제어 (run_realtime_focus_csv.py 와 동일 인자 패턴) ----
    ap.add_argument(
        "--min-interval-sec", dest="min_interval_sec", type=float, default=0.0,
        help="전송 최소 간격 (초, 기본: 0.0)",
    )
    ap.add_argument(
        "--dedup-cache-size", dest="dedup_cache_size", type=int, default=3,
        help="최근 N 개 이내 중복 출력 방지 (기본: 3)",
    )
    ap.add_argument(
        "--dedup-ttl-sec", dest="dedup_ttl_sec", type=float, default=0.0,
        help="TTL 기반 중복 차단 초 (기본: 0.0 = OFF)",
    )
    ap.add_argument(
        "--dedup-ttl-prune-sec", dest="dedup_ttl_prune_sec", type=float, default=20.0,
        help="TTL 맵 정리 주기 (초, 기본: 20.0)",
    )

    # ---- 디버그 ----
    ap.add_argument(
        "--debug-stats", dest="debug_stats", action="store_true",
        help="10초마다 STAT 라인 출력",
    )

    args = ap.parse_args()

    # ---- 경로 검증 ----
    csv_path = os.path.expanduser(str(args.csv_path))
    csv_path = os.path.abspath(csv_path)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    output_csv = os.path.expanduser(str(args.output_csv))
    output_csv = os.path.abspath(output_csv)

    bot_nick = str(args.bot_nick).strip()
    if not bot_nick:
        raise ValueError("--bot-nick is required and must be non-empty")

    max_messages = max(0, int(args.max_messages))
    model_name = str(args.model_name).strip()

    # ---- Sender 초기화 (run_realtime_focus_csv.py 와 동일 패턴) ----
    sender_cfg = FocusSenderConfig(
        min_interval_sec=float(args.min_interval_sec),
    )
    sender = FocusChatSender(sender_cfg)

    # ---- BaselineFullGen 초기화 (모델 로딩) ----
    gen_cfg = BaselineFullGenConfig(
        model_name_or_path=model_name,
        device=str(args.device),
    )
    gen = BaselineFullGen(gen_cfg)

    # ---- 기존 결과 파일 자동 백업 ----
    _backup_result_csv(output_csv)

    # ---- 결과 CSV 초기화 (기존 파일이 있으면 이어쓰기) ----
    _init_result_csv(output_csv)

    # ---- 기존 seq 번호 이어받기 ----
    seq_offset = _get_last_seq(output_csv)
    if seq_offset > 0:
        print(f"[INFO] 기존 데이터 {seq_offset}건 발견, seq={seq_offset + 1} 부터 이어쓰기")

    # ---- CSV tailing 초기화 ----
    tail = TailState(start_at_end=True)

    # ---- 문맥 버퍼 ----
    ctx_buf = ContextBuffer(size=CONTEXT_SIZE)

    # ---- Dedup (run_realtime_focus_csv.py 와 동일 패턴) ----
    dedup_n = max(1, int(args.dedup_cache_size))
    sent_recent: Deque[str] = deque(maxlen=dedup_n)

    sent_ttl: Dict[str, float] = {}
    dedup_ttl_sec = max(0.0, float(args.dedup_ttl_sec))
    dedup_ttl_prune_sec = max(1.0, float(args.dedup_ttl_prune_sec))

    # ---- 통계 변수 ----
    total_seen = 0
    total_processed = 0
    total_nonempty = 0
    total_sent = 0
    latencies: List[float] = []
    last_stat_ts = 0.0

    # ---- 시작 정보 출력 ----
    print(f"[INFO] tailing         : {csv_path}")
    print(f"[INFO] model           : {model_name}")
    print(f"[INFO] output          : {output_csv}")
    print(f"[INFO] bot-nick        : {bot_nick}")
    print(f"[INFO] max-messages    : {max_messages if max_messages > 0 else 'unlimited'}")
    print(f"[INFO] device          : {args.device}")
    print(f"[INFO] dedup_recent_n  : {dedup_n}")
    print(f"[INFO] dedup_ttl_sec   : {dedup_ttl_sec}")
    print(f"[INFO] context_size    : {CONTEXT_SIZE}")
    print(f"[INFO] seq_offset      : {seq_offset}")
    print()
    print("[INFO] Waiting for new messages in CSV ...")
    sys.stdout.flush()

    # ---- 메인 루프 ----
    try:
        while True:
            rows = tail_csv_append_lines(csv_path, tail, poll_sec=0.1)
            now_ts = time.time()

            # ---- 디버그 통계 (run_realtime_focus_csv.py 패턴) ----
            if args.debug_stats and (now_ts - last_stat_ts) >= 10.0:
                last_stat_ts = now_ts
                print(
                    f"[STAT] ctx_buf={len(ctx_buf._buf)} "
                    f"sent_recent={len(sent_recent)} "
                    f"processed={total_processed} "
                    f"sent={total_sent}"
                )
                sys.stdout.flush()

            for r in rows:
                nickname = _safe_norm_text(r.get("nickname", ""))
                msg = _safe_norm_text(r.get("message", ""))
                msg_id = _safe_norm_text(r.get("msg_id", ""))
                ts_original = _safe_norm_text(r.get("ts", ""))

                # ---- 필터링 (run_realtime_focus_csv.py 와 동일) ----
                if not msg or msg == "[NONE]":
                    continue

                total_seen += 1

                # 봇 자신의 메시지 건너뜀
                if nickname == bot_nick:
                    continue

                # ---- 문맥 스냅샷 (LLM 호출 전에 현재 버퍼 캡처) ----
                ctx_snapshot = ctx_buf.snapshot()

                # ---- 문맥 버퍼에 현재 메시지 추가 (다음 메시지의 문맥이 됨) ----
                ctx_buf.observe(msg)

                # ---- LLM 전체 생성 ----
                response, latency = gen.generate(msg)

                total_processed += 1
                latencies.append(latency)
                now_ts = time.time()

                # ---- 전송 판단 ----
                actually_sent = False

                if response:
                    # "ㅍ" 단독 출력 차단 (run_realtime_focus_csv.py 와 동일)
                    if _is_blocked_single_char(response):
                        response = ""

                if response:
                    total_nonempty += 1

                    # 최근 N 개 이내 중복이면 전송 안함
                    if response in sent_recent:
                        pass
                    # TTL 기반 차단
                    elif dedup_ttl_sec > 0.0 and response in sent_ttl and (now_ts - sent_ttl[response]) < dedup_ttl_sec:
                        pass
                    else:
                        # 전송 시도
                        send_ok = sender.send(response)
                        if send_ok:
                            actually_sent = True
                            total_sent += 1
                            sent_recent.append(response)
                            sent_ttl[response] = now_ts

                # ---- [v2] 결과 CSV 에 기록 (seq_offset 반영) ----
                current_seq = seq_offset + total_processed
                result_record = {
                    "seq": current_seq,
                    "msg_id": msg_id,
                    "ts_original": ts_original,
                    "ts_response": datetime.now().isoformat(timespec="seconds"),
                    "nickname": nickname,
                    "context_1": ctx_snapshot[0],
                    "context_2": ctx_snapshot[1],
                    "context_3": ctx_snapshot[2],
                    "context_4": ctx_snapshot[3],
                    "context_5": ctx_snapshot[4],
                    "message": msg,
                    "response": response,
                    "sent": str(actually_sent),
                    "latency_sec": f"{latency:.4f}",
                    "response_len": len(response),
                }
                _append_result(output_csv, result_record)

                # ---- 진행 상황 출력 ----
                msg_short = msg[:30] + ("..." if len(msg) > 30 else "")
                resp_short = response[:30] + ("..." if len(response) > 30 else "")
                if not response:
                    resp_short = "(empty)"
                sent_mark = "SENT" if actually_sent else "----"
                print(
                    f"[{current_seq}] [{sent_mark}] "
                    f"latency={latency:.3f}s "
                    f'msg="{msg_short}" '
                    f'-> resp="{resp_short}"'
                )
                sys.stdout.flush()

                # ---- 최대 처리 수 도달 시 종료 ----
                if max_messages > 0 and total_processed >= max_messages:
                    print(f"\n[INFO] Reached --max-messages limit ({max_messages})")
                    _print_summary(
                        total_seen, total_processed,
                        total_nonempty, total_sent,
                        latencies, model_name,
                    )
                    return 0

            # ---- TTL prune ----
            if dedup_ttl_prune_sec > 0.0:
                _prune_ttl_map(sent_ttl, now_ts, ttl_sec=dedup_ttl_prune_sec)

            # 메인 루프 간격 (run_realtime_focus_csv.py 와 동일: 0.01s)
            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user (Ctrl+C)")

    # ---- 종료 시 요약 통계 출력 ----
    _print_summary(
        total_seen, total_processed,
        total_nonempty, total_sent,
        latencies, model_name,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

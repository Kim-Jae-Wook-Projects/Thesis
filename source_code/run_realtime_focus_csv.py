# run_realtime_focus_csv.py
# -*- coding: utf-8 -*-

from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from chat_sender_focus import FocusChatSender, FocusSenderConfig
from chat_storage_monitor import is_system_saved_after_message

from pipeline import Pipeline, PipelineConfig, RouterConfig, Track1Config, Track2Config, Track3Config

# SSOT lexicon
try:
    from resources import DEFAULT_LEXICON  # type: ignore
except Exception:  # pragma: no cover
    DEFAULT_LEXICON = None

# ----------------------------
# Utilities
# ----------------------------

def _now_ts() -> float:
    return time.time()

def _parse_ts_any(ts_raw: str) -> float:
    if ts_raw is None:
        return _now_ts()
    s = str(ts_raw).strip()
    if not s:
        return _now_ts()
    try:
        return float(s)
    except Exception:
        pass
    try:
        dt = datetime.fromisoformat(s)
        return dt.timestamp()
    except Exception:
        return _now_ts()

def _safe_norm_text(s: str) -> str:
    if s is None:
        return ""
    return str(s).replace("\u200b", "").strip()

def _prune_ttl_map(m: Dict[str, float], now_ts: float, ttl_sec: float) -> None:
    if not m:
        return
    dead = [k for k, t in m.items() if (now_ts - t) >= ttl_sec]
    for k in dead:
        m.pop(k, None)

def _is_gate_exempt(out_text: str) -> bool:
    t = _safe_norm_text(out_text)
    if not t:
        return False
    if t == "ㅇㅇㄱ":
        return True
    if "ㅋ" in t:
        return True
    return False

def _is_blocked_single_char(out_text: str) -> bool:
    t = _safe_norm_text(out_text)
    return t == "ㅍ"

# ----------------------------
# Tail CSV (binary-safe) [rotation/truncation-aware + START_AT_END]
# ----------------------------

@dataclass
class TailState:
    last_pos: int = 0
    header: Optional[List[str]] = None
    partial: bytes = b""
    inode: Optional[int] = None
    last_size: int = 0
    start_at_end: bool = True
    initialized: bool = False

def _get_inode_and_size(path: str) -> Tuple[Optional[int], int]:
    try:
        st = os.stat(path)
        return getattr(st, "st_ino", None), int(st.st_size)
    except Exception:
        return None, 0

def _reset_tail_state(state: TailState) -> None:
    state.last_pos = 0
    state.header = None
    state.partial = b""
    state.last_size = 0
    state.initialized = False

def _decode_line(raw: bytes) -> str:
    try:
        return raw.decode("utf-8-sig", errors="replace")
    except Exception:
        return raw.decode("utf-8", errors="replace")

def tail_csv_append_lines(
    csv_path: str,
    state: TailState,
    poll_sec: float = 0.5,
) -> List[Dict[str, str]]:
    if not os.path.exists(csv_path):
        time.sleep(poll_sec)
        return []

    inode, size = _get_inode_and_size(csv_path)

    if state.inode is not None and inode is not None and inode != state.inode:
        _reset_tail_state(state)
    if state.last_pos > 0 and size < state.last_pos:
        _reset_tail_state(state)

    state.inode = inode

    with open(csv_path, "rb") as f:
        if not state.initialized:
            f.seek(0, os.SEEK_SET)
            first = f.readline()
            if first:
                s = _decode_line(first)
                try:
                    reader = csv.reader([s])
                    row = next(reader)
                    state.header = [c.strip() for c in row]
                except Exception:
                    state.header = None

            if state.start_at_end:
                f.seek(0, os.SEEK_END)
                state.last_pos = f.tell()
                state.initialized = True
                state.last_size = size
                time.sleep(poll_sec)
                return []

            state.last_pos = f.tell()
            state.initialized = True
            state.last_size = size

        f.seek(state.last_pos, os.SEEK_SET)
        data = f.read()
        state.last_pos = f.tell()
        state.last_size = size

        if not data:
            time.sleep(poll_sec)
            return []

        buf = state.partial + data
        lines = buf.split(b"\n")

        if not buf.endswith(b"\n"):
            state.partial = lines[-1]
            lines = lines[:-1]
        else:
            state.partial = b""

        out_rows: List[Dict[str, str]] = []
        for raw in lines:
            if not raw.strip():
                continue
            s = _decode_line(raw)

            if state.header is None:
                try:
                    reader = csv.reader([s])
                    row = next(reader)
                    state.header = [c.strip() for c in row]
                    continue
                except Exception:
                    continue

            try:
                reader = csv.reader([s])
                row = next(reader)
            except Exception:
                continue

            if state.header and len(row) < len(state.header):
                row = row + [""] * (len(state.header) - len(row))

            rdict = {state.header[i]: row[i] for i in range(min(len(state.header or []), len(row)))}
            out_rows.append(rdict)

        return out_rows

# ----------------------------
# Context Scheduler (track3 trigger + delayed drain)
# ----------------------------

@dataclass
class ContextSchedulerConfig:
    window_sec: float = 20.0
    context_k: int = 1
    drain_every_sec: float = 0.6
    drain_batch: int = 1

class ContextScheduler:
    def __init__(self, cfg: ContextSchedulerConfig) -> None:
        self.cfg = cfg
        self.buf: Deque[Tuple[float, str]] = deque()
        self.last_drain_ts: float = 0.0

    def observe(self, ts: float, message: str) -> None:
        self.buf.append((float(ts), str(message)))
        self._prune(ts)

    def _prune(self, now_ts: float) -> None:
        w = float(self.cfg.window_sec)
        while self.buf and (float(now_ts) - float(self.buf[0][0])) > w:
            self.buf.popleft()

    def build_context_text(self) -> str:
        k = max(1, int(self.cfg.context_k))
        items = list(self.buf)[-k:]
        parts = []
        for _ts, msg in items:
            t = _safe_norm_text(msg)
            if t:
                parts.append(t)
        return " / ".join(parts).strip()

    def should_drain(self, now_ts: float) -> bool:
        return (float(now_ts) - float(self.last_drain_ts)) >= float(self.cfg.drain_every_sec)

    def mark_drained(self, now_ts: float) -> None:
        self.last_drain_ts = float(now_ts)

# ----------------------------
# Output Gate: "10 chats -> max 1 output"
# ----------------------------

@dataclass
class OutputGateConfig:
    chats_per_output: int = 10

class OutputGate:
    def __init__(self, cfg: OutputGateConfig) -> None:
        self.cfg = cfg
        self._msg_in_window: int = 0
        self._sent_in_window: bool = False

    def observe_chat(self) -> None:
        self._msg_in_window += 1
        if self._msg_in_window >= max(1, int(self.cfg.chats_per_output)):
            self._msg_in_window = 0
            self._sent_in_window = False

    def can_send(self) -> bool:
        return not self._sent_in_window

    def mark_sent(self) -> None:
        self._sent_in_window = True

    def debug_state(self) -> Tuple[int, bool]:
        return self._msg_in_window, self._sent_in_window

# ----------------------------
# 문맥 버퍼 (결과 CSV 기록용)
# ----------------------------

CONTEXT_SIZE = 5

class ContextBuffer:
    def __init__(self, size: int = CONTEXT_SIZE) -> None:
        self._size = max(1, int(size))
        self._buf: Deque[str] = deque(maxlen=self._size)

    def observe(self, message: str) -> None:
        t = _safe_norm_text(message)
        if t:
            self._buf.append(t)

    def snapshot(self) -> List[str]:
        items = list(self._buf)
        while len(items) < self._size:
            items.insert(0, "")
        return items

# ----------------------------
# 결과 CSV 관리 (덮어쓰기 방지 + 자동 백업 + seq 이어쓰기)
# ----------------------------

RESULT_FIELDS = [
    "seq", "msg_id", "ts_original", "ts_response", "nickname",
    "context_1", "context_2", "context_3", "context_4", "context_5",
    "message", "response", "track", "sent", "latency_sec", "response_len",
]

def _init_result_csv(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    if os.path.exists(path) and os.path.getsize(path) > 0:
        print(f"[INFO] 기존 결과 파일 발견, 이어쓰기 모드: {path}")
        return
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
    print(f"[INFO] 새 결과 파일 생성: {path}")

def _backup_result_csv(path: str) -> None:
    if not os.path.exists(path) or os.path.getsize(path) == 0:
        return
    base, ext = os.path.splitext(path)
    backup = f"{base}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
    shutil.copy2(path, backup)
    print(f"[INFO] 기존 결과 백업 완료: {backup}")

def _get_last_seq(path: str) -> int:
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
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writerow(record)

# ----------------------------
# 요약 통계
# ----------------------------

def _print_summary(
    total_seen: int,
    total_processed: int,
    total_sent: int,
    t12_count: int,
    t3_count: int,
    t3_latencies: List[float],
) -> None:
    print("\n" + "=" * 60)
    print("[SUMMARY]")
    print(f"  Total messages seen        : {total_seen}")
    print(f"  Total outputs produced     : {total_processed}")
    print(f"  Actually sent to chat      : {total_sent}")
    print(f"  Track1/2 outputs           : {t12_count}")
    print(f"  Track3 outputs (LLM)       : {t3_count}")
    if t3_latencies:
        avg_lat = sum(t3_latencies) / len(t3_latencies)
        sorted_lat = sorted(t3_latencies)
        n = len(sorted_lat)
        mid = n // 2
        median_lat = sorted_lat[mid] if n % 2 == 1 else (sorted_lat[mid - 1] + sorted_lat[mid]) / 2.0
        print(f"  Track3 avg  latency (sec)  : {avg_lat:.4f}")
        print(f"  Track3 median latency (sec): {median_lat:.4f}")
        print(f"  Track3 min  latency (sec)  : {sorted_lat[0]:.4f}")
        print(f"  Track3 max  latency (sec)  : {sorted_lat[-1]:.4f}")
    else:
        print("  (no Track3 latency data)")
    print("=" * 60)
    sys.stdout.flush()

# ----------------------------
# Build Pipeline
# ----------------------------

def build_pipeline(track3_model: str = None, track3_temperature: float = None) -> Pipeline:
    pcfg = PipelineConfig()
    pcfg.router = RouterConfig(
        trigger_threshold=2,
        trigger_regex=r"(어때\??|어떰\??|ㅇㄸ\??|어떤\s*데|어떤\s*가|어떤\s*거|어떤\s*거야|어떤\s*지|어떤\s*것|ㅈㅉㅇㅇ|진짜|탕핑|핑핑이|시진핑|중국|ㅇㅇ|ㄱㄱ|ㅇㅋ|맞아|맞아요|ㄴㄴ|어떻게 보|어떻게 해야)",
        trigger_window_sec=60.0,
        track3_cooldown_sec=120.0,
        track3_max_output_chars=60,
    )
    pcfg.track1 = Track1Config()
    pcfg.track2 = Track2Config(enabled=False)
    pcfg.track3 = Track3Config(
        enabled=True, forbidden_chars="·", max_chars=60, p_pos=0.5, p_neg=0.5,
    )
    # [v3] 터미널에서 Track3 모델 지정 시 기본값 덮어쓰기
    if track3_model:
        pcfg.exaone.model_name_or_path = track3_model
    # [v4] 터미널에서 Track3 temperature 지정 시 기본값 덮어쓰기
    if track3_temperature is not None:
        pcfg.exaone.temperature = float(track3_temperature)
    return Pipeline(pcfg)

# ----------------------------
# Main Runner
# ----------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", dest="csv_path", default="chat.csv", help="Path to chat CSV (collector output)")
    ap.add_argument("--bot-nick", dest="bot_nick", required=True)
    ap.add_argument("--ctx-window-sec", dest="ctx_window_sec", type=float, default=20.0)
    ap.add_argument("--context-k", dest="context_k", type=int, default=1)
    ap.add_argument("--min-interval-sec", dest="min_interval_sec", type=float, default=0.0)
    ap.add_argument("--dedup-cache-size", dest="dedup_cache_size", type=int, default=3)
    ap.add_argument("--dedup-ttl-sec", dest="dedup_ttl_sec", type=float, default=0.0)
    ap.add_argument("--dedup-ttl-prune-sec", dest="dedup_ttl_prune_sec", type=float, default=20.0)
    ap.add_argument("--chats-per-output", dest="chats_per_output", type=int, default=10)
    ap.add_argument("--output", dest="output_csv", default="result_multitrack.csv",
                    help="결과 CSV 저장 경로 (기본: result_multitrack.csv)")
    # [v2] --max-messages 추가
    ap.add_argument("--max-messages", dest="max_messages", type=int, default=0,
                    help="최대 처리 메시지 수 (0 = 무제한)")
    ap.add_argument("--debug-stats", dest="debug_stats", action="store_true", help="Print STAT lines every 10s")
    # [v3] Track3 모델 터미널 지정
    ap.add_argument("--track3-model", dest="track3_model", default=None,
                    help="Track3 LLM 모델 지정 (미지정 시 backends.py 기본값 사용). "
                         "예: LGAI-EXAONE/EXAONE-3.5-7.8B-Instruct")
    # [v4] Track3 temperature 터미널 지정
    ap.add_argument("--track3-temperature", dest="track3_temperature", type=float, default=None,
                    help="Track3 LLM temperature 지정 (미지정 시 backends.py 기본값 0.9 사용). "
                         "예: 0.5, 0.9, 1.2")

    args = ap.parse_args()

    csv_path = os.path.expanduser(str(args.csv_path))
    csv_path = os.path.abspath(csv_path)
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    bot_nick = str(args.bot_nick).strip()
    if not bot_nick:
        raise ValueError("--bot-nick is required and must be non-empty")

    output_csv = os.path.expanduser(str(args.output_csv))
    output_csv = os.path.abspath(output_csv)

    max_messages = max(0, int(args.max_messages))

    sender_cfg = FocusSenderConfig(
        min_interval_sec=float(args.min_interval_sec),
        hotkey_inter_key_sec=0.1,
        pre_paste_delay_sec=0.1,
        post_paste_delay_sec=0.08,
    )
    sender = FocusChatSender(sender_cfg)

    pipeline = build_pipeline(
        track3_model=args.track3_model,
        track3_temperature=args.track3_temperature,
    )

    ctx = ContextScheduler(
        ContextSchedulerConfig(
            window_sec=float(args.ctx_window_sec),
            context_k=int(args.context_k),
            drain_every_sec=0.6,
            drain_batch=1,
        )
    )

    gate = OutputGate(OutputGateConfig(chats_per_output=max(1, int(args.chats_per_output))))

    dedup_n = max(1, int(args.dedup_cache_size))
    sent_recent: Deque[str] = deque(maxlen=dedup_n)
    sent_ttl: Dict[str, float] = {}
    dedup_ttl_sec = max(0.0, float(args.dedup_ttl_sec))
    dedup_ttl_prune_sec = max(1.0, float(args.dedup_ttl_prune_sec))

    tail = TailState(start_at_end=True)
    last_stat_ts = 0.0

    # [v2] 기존 결과 파일 자동 백업
    _backup_result_csv(output_csv)

    # [v2] 결과 CSV 초기화 (기존 파일이 있으면 이어쓰기)
    _init_result_csv(output_csv)

    # [v2] 기존 seq 번호 이어받기
    seq_offset = _get_last_seq(output_csv)
    if seq_offset > 0:
        print(f"[INFO] 기존 데이터 {seq_offset}건 발견, seq={seq_offset + 1} 부터 이어쓰기")

    # 문맥 버퍼 (결과 CSV 기록용)
    ctx_buf = ContextBuffer(size=CONTEXT_SIZE)

    # 통계 변수
    total_seen = 0
    total_processed = 0
    total_sent = 0
    t12_count = 0
    t3_count = 0
    t3_latencies: List[float] = []

    # Track3 트리거 정보 임시 저장 (drain 시 결과 CSV 기록용)
    t3_trigger_info: Optional[Dict] = None

    print(f"[INFO] tailing: {csv_path}")
    print(f"[INFO] bot nick: {bot_nick}")
    print(f"[INFO] output: {output_csv}")
    print(f"[INFO] dedup_recent_n: {dedup_n}")
    print(f"[INFO] dedup_ttl_sec: {dedup_ttl_sec}")
    print(f"[INFO] chats_per_output: {gate.cfg.chats_per_output}")
    print(f"[INFO] max_messages: {max_messages if max_messages > 0 else 'unlimited'}")
    print(f"[INFO] seq_offset: {seq_offset}")
    print(f"[INFO] sender timing: inter_key={sender_cfg.hotkey_inter_key_sec}s, pre_paste={sender_cfg.pre_paste_delay_sec}s")
    sys.stdout.flush()

    try:
        while True:
            rows = tail_csv_append_lines(csv_path, tail, poll_sec=0.1)
            now_ts = _now_ts()

            if args.debug_stats and (now_ts - last_stat_ts) >= 10.0:
                last_stat_ts = now_ts
                pending = 1 if pipeline.track3.has_pending() else 0
                win_cnt, win_sent = gate.debug_state()
                print(
                    f"[STAT] buf={len(ctx.buf)} pending_track3={pending} "
                    f"sent_recent={len(sent_recent)} gate_win_cnt={win_cnt} gate_sent={int(win_sent)}"
                )
                sys.stdout.flush()

            # read new rows
            for r in rows:
                nickname = _safe_norm_text(r.get("nickname", ""))
                msg = _safe_norm_text(r.get("message", ""))
                msg_id = _safe_norm_text(r.get("msg_id", ""))
                ts_original = _safe_norm_text(r.get("ts", ""))

                if not msg:
                    continue

                total_seen += 1

                # skip own messages
                if nickname and bot_nick and nickname == bot_nick:
                    continue

                ts = _parse_ts_any(ts_original)

                # 문맥 스냅샷 (기록 전 현재 버퍼 캡처)
                ctx_snapshot = ctx_buf.snapshot()

                # record context
                ctx.observe(ts, msg)

                # 문맥 버퍼에 현재 메시지 추가
                ctx_buf.observe(msg)

                # (2) 입력 채팅 1개 관측 (10개 window)
                gate.observe_chat()

                # Track1/2 immediate
                outs = pipeline.process_message(msg, ts=ts)
                for out in outs:
                    out2 = _safe_norm_text(out)
                    if not out2:
                        continue

                    if _is_blocked_single_char(out2):
                        continue

                    if (not gate.can_send()) and (not _is_gate_exempt(out2)):
                        continue

                    if out2 in sent_recent:
                        continue

                    if dedup_ttl_sec > 0.0:
                        if out2 in sent_ttl and (now_ts - sent_ttl[out2]) < dedup_ttl_sec:
                            continue

                    sender.send(out2)
                    sent_recent.append(out2)
                    sent_ttl[out2] = now_ts

                    if not _is_gate_exempt(out2):
                        gate.mark_sent()

                    # [v2] Track1/2 결과 CSV 기록 (seq_offset 반영)
                    total_processed += 1
                    total_sent += 1
                    t12_count += 1
                    current_seq = seq_offset + total_processed
                    _append_result(output_csv, {
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
                        "response": out2,
                        "track": "T1T2",
                        "sent": "True",
                        "latency_sec": "0.0000",
                        "response_len": len(out2),
                    })

                    # [v2] max-messages 체크 (Track1/2)
                    if max_messages > 0 and total_processed >= max_messages:
                        print(f"\n[INFO] Reached --max-messages limit ({max_messages})")
                        _print_summary(total_seen, total_processed, total_sent, t12_count, t3_count, t3_latencies)
                        return 0

                # Track3 request check (based on router)
                req, _reason = pipeline.should_request_track3(now_ts)
                if req:
                    context_text = ctx.build_context_text()
                    if args.debug_stats:
                        print(f"[TRACK3_REQ] reason={_reason} ctx='{context_text}'")
                        sys.stdout.flush()
                    if context_text:
                        pipeline.submit_track3(context_text, ts=now_ts)
                        # Track3 트리거 정보 저장
                        t3_trigger_info = {
                            "msg_id": msg_id,
                            "ts_original": ts_original,
                            "nickname": nickname,
                            "message": context_text,
                            "ctx_snapshot": list(ctx_snapshot),
                        }

            # drain pending track3 outputs
            if ctx.should_drain(now_ts):
                ctx.mark_drained(now_ts)

                # Track3 latency 측정
                t3_start = time.time()
                out3s = pipeline.drain_pending(limit=1)
                t3_latency = time.time() - t3_start

                if args.debug_stats and out3s:
                    print(f"[TRACK3_DRAIN] out3s={out3s}")
                    sys.stdout.flush()

                for out3 in out3s:
                    out3 = _safe_norm_text(out3)
                    if not out3:
                        continue

                    if _is_blocked_single_char(out3):
                        continue

                    if out3 in sent_recent:
                        continue

                    if dedup_ttl_sec > 0.0:
                        if out3 in sent_ttl and (now_ts - sent_ttl[out3]) < dedup_ttl_sec:
                            continue

                    # LLM 연산 직후 CPU 포화 → Cmd+V 미스파이어 방지
                    time.sleep(3.0)
                    sender.send(out3)
                    sent_recent.append(out3)
                    sent_ttl[out3] = now_ts
                    total_sent += 1

                    # [v2] Track3 결과 CSV 기록 (seq_offset 반영)
                    total_processed += 1
                    t3_count += 1
                    t3_latencies.append(t3_latency)

                    current_seq = seq_offset + total_processed
                    ti = t3_trigger_info or {}
                    ti_snap = ti.get("ctx_snapshot", ["", "", "", "", ""])
                    _append_result(output_csv, {
                        "seq": current_seq,
                        "msg_id": ti.get("msg_id", ""),
                        "ts_original": ti.get("ts_original", ""),
                        "ts_response": datetime.now().isoformat(timespec="seconds"),
                        "nickname": ti.get("nickname", ""),
                        "context_1": ti_snap[0] if len(ti_snap) > 0 else "",
                        "context_2": ti_snap[1] if len(ti_snap) > 1 else "",
                        "context_3": ti_snap[2] if len(ti_snap) > 2 else "",
                        "context_4": ti_snap[3] if len(ti_snap) > 3 else "",
                        "context_5": ti_snap[4] if len(ti_snap) > 4 else "",
                        "message": ti.get("message", ""),
                        "response": out3,
                        "track": "T3",
                        "sent": "True",
                        "latency_sec": f"{t3_latency:.4f}",
                        "response_len": len(out3),
                    })

                    # [v2] max-messages 체크 (Track3)
                    if max_messages > 0 and total_processed >= max_messages:
                        print(f"\n[INFO] Reached --max-messages limit ({max_messages})")
                        _print_summary(total_seen, total_processed, total_sent, t12_count, t3_count, t3_latencies)
                        return 0

            # TTL prune
            if dedup_ttl_prune_sec > 0.0:
                _prune_ttl_map(sent_ttl, now_ts, ttl_sec=dedup_ttl_prune_sec)

            time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n[INFO] Interrupted by user (Ctrl+C)")

    # 종료 시 요약 통계 출력
    _print_summary(
        total_seen, total_processed, total_sent,
        t12_count, t3_count, t3_latencies,
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

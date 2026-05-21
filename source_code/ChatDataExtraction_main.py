# ChatDataExtraction_main.py
# -*- coding: utf-8 -*-

import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.color import Color

from chat_collector_main import ChatCSVCollector
from chat_storage_monitor import ChatStorageMonitor, is_system_saved_after_message

CHROMEDRIVER_PATH = "/usr/local/bin/chromedriver"
CHAT_POPUP_URL = "https://vod.sooplive.com/player/161303645"    # specific channel


POLL_INTERVAL = 2.0
CLEANUP_INTERVAL = 60.0

# CSV 저장(collector 모듈이 담당)
CSV_PATH = "chat.csv"
CSV_FIELDS = ["ts", "rank", "nickname", "message", "msg_id"]

# 점검/스냅샷
STATUS_DIR = "status"
SNAPSHOT_DIR = "snapshots"

REPORT_INTERVAL_SEC = 60   # 1분
WINDOW_SEC = 60            # 최근 1분


def main():
    opts = Options()
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    driver = webdriver.Chrome(service=Service(CHROMEDRIVER_PATH), options=opts)

    try:
        driver.get(CHAT_POPUP_URL)
        time.sleep(3)

        seen = set()
        print("=== Start Real-Time CHAT extracting !! (Ctrl+C to stop) ===")

        # collector / monitor 객체를 여기서 1번만 생성
        collector = ChatCSVCollector(
            csv_path=CSV_PATH,
            fieldnames=CSV_FIELDS,
            snapshot_dir=SNAPSHOT_DIR,
            snapshot_interval_sec=REPORT_INTERVAL_SEC,
            enable_snapshot=True,        # 원하면 False로
        )
        monitor = ChatStorageMonitor(
            window_sec=WINDOW_SEC,
            report_interval_sec=REPORT_INTERVAL_SEC,
            status_dir=STATUS_DIR,
        )

        next_poll = time.monotonic()
        next_cleanup = next_poll + CLEANUP_INTERVAL

        while True:
            items = driver.find_elements(By.CSS_SELECTOR, ".chatting-list-item")

            for el in items:
                msg_id_attr = el.get_attribute("data-message-id")
                el_text_content = el.text.strip()

                if msg_id_attr:
                    msg_id = msg_id_attr
                elif el_text_content:
                    msg_id = el_text_content[:50] + str(len(el_text_content)) + str(time.time())
                else:
                    driver.execute_script("arguments[0].remove();", el)
                    continue

                if msg_id in seen:
                    driver.execute_script("arguments[0].remove();", el)
                    continue
                seen.add(msg_id)

                rank_str = ""
                nickname_str = ""
                message_str = ""

                sub_spans_with_text = el.find_elements(By.XPATH, ".//span[normalize-space(.)]")
                effective_elements_for_grouping = sub_spans_with_text if sub_spans_with_text else ([el] if el_text_content else [])

                color_groups = []
                current_color_key = None
                current_texts_for_group = []
                for span_idx, span_element in enumerate(effective_elements_for_grouping):
                    text = span_element.text.strip()
                    if not text:
                        continue
                    try:
                        color_str = span_element.value_of_css_property("color")
                        col_obj = Color.from_string(color_str)
                        color_key = col_obj.rgba
                    except Exception:
                        color_key = f"__error_color_{span_idx}_{id(span_element)}__"

                    if current_color_key is None:
                        current_color_key = color_key
                        current_texts_for_group = [text]
                    elif color_key == current_color_key:
                        current_texts_for_group.append(text)
                    else:
                        color_groups.append({"color_key": current_color_key, "texts": list(current_texts_for_group)})
                        current_color_key = color_key
                        current_texts_for_group = [text]
                if current_texts_for_group:
                    color_groups.append({"color_key": current_color_key, "texts": list(current_texts_for_group)})

                message_from_g2_plus_spans = []

                if not color_groups:
                    if el_text_content:
                        parts_fallback = el_text_content.split(None, 2)
                        if len(parts_fallback) == 3:
                            rank_str, nickname_str, message_str = parts_fallback
                        elif len(parts_fallback) == 2:
                            rank_str, nickname_str = parts_fallback
                        elif len(parts_fallback) == 1:
                            message_str = parts_fallback[0]

                elif len(color_groups) == 1:
                    nickname_str = " ".join(color_groups[0]["texts"]).strip()

                else:
                    rank_str = " ".join(color_groups[0]["texts"]).strip()
                    nickname_str = " ".join(color_groups[1]["texts"]).strip()
                    if len(color_groups) >= 3:
                        for i in range(2, len(color_groups)):
                            message_from_g2_plus_spans.extend(color_groups[i]["texts"])

                if message_from_g2_plus_spans:
                    message_str = " ".join(message_from_g2_plus_spans).strip()
                else:
                    if el_text_content:
                        temp_message = el_text_content
                        if rank_str and temp_message.startswith(rank_str):
                            temp_message = temp_message[len(rank_str):].strip()
                        if nickname_str and temp_message.startswith(nickname_str):
                            temp_message = temp_message[len(nickname_str):].strip()
                        if temp_message:
                            message_str = temp_message

                if not rank_str and not nickname_str and not message_str and el_text_content:
                    message_str = el_text_content

                # -----------------------------
                # CSV 저장/점검용 필터링 + dict 생성 + 모듈 호출
                # -----------------------------
                rank_out = rank_str.strip() if rank_str.strip() else "[NONE]"
                nick_out = nickname_str.strip() if nickname_str.strip() else "[NONE]"
                msg_out = message_str.strip() if message_str.strip() else "[NONE]"

                #  "This chat was saved after HH:MM:SS." 라인 제외
                if is_system_saved_after_message(rank_out, nick_out, msg_out):
                    monitor.bump_filtered(1)
                    driver.execute_script("arguments[0].remove();", el)
                    continue

                record = {
                    "ts": datetime.now().isoformat(timespec="seconds"),
                    "rank": rank_out,
                    "nickname": nick_out,
                    "message": msg_out,
                    "msg_id": msg_id,
                }

                # (CSV 저장)
                collector.append(record)
                monitor.bump_written_csv(1)

                # (10분 점검 누적)
                now_mono = time.monotonic()
                monitor.feed(now_mono, record)
                monitor.bump_seen(len(seen))

                # (10분마다 TXT 리포트 파일 생성)
                report_path = monitor.maybe_write_report(now_mono)
                if report_path:
                    print(f"[MONITOR] status report saved: {report_path}")

                # (10분마다 CSV 스냅샷 새 파일 생성)
                snap_path = collector.maybe_snapshot(now_mono)
                if snap_path:
                    print(f"[SNAPSHOT] csv snapshot saved: {snap_path}")

                # 기존 출력은 유지하되, CSV에는 Start/END가 안 들어가므로 신경 X
                print(f"Rank: {rank_out} / NickName: {nick_out} / Message: {msg_out}")

                driver.execute_script("arguments[0].remove();", el)

            now = time.monotonic()
            if now >= next_cleanup:
                driver.execute_script("document.querySelectorAll('.chatting-list-item').forEach(el => el.remove());")
                next_cleanup += CLEANUP_INTERVAL

            next_poll += POLL_INTERVAL
            sleep_dur = next_poll - time.monotonic()
            if sleep_dur > 0:
                time.sleep(sleep_dur)

    except KeyboardInterrupt:
        print("\nEND")
    except Exception as e:
        print(f"ERROR Executing Program : {e}")
    finally:
        if "driver" in locals() and driver:
            driver.quit()


if __name__ == "__main__":
    main()

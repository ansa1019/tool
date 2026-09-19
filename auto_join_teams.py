import os
import re
import time
import datetime
import requests
import threading
from pyngrok import ngrok
from dotenv import load_dotenv
from selenium import webdriver
from flask import Flask, request
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC


# ============================================================
#               ⭐⭐ 自訂區 ⭐⭐
# ============================================================
load_dotenv()

# 這裡填你的 LINE Messaging API Channel access token
LINE_TOKEN = os.getenv("TEAMS_LINE_TOKEN")

# 這裡填你的 LINE User ID（要推播給自己的那個 ID）
USER_ID = os.getenv("TEAMS_USER_ID")

# 會議顯示的訪客名稱
GUEST_NAME = os.getenv("TEAMS_GUEST_NAME")

# 預設參數
WAIT_BEFORE_JOIN = 5  # 進入預加入畫面後，給頁面一些時間載入（秒）
MAX_WAIT_HOST = 600  # 等待主持人允許進入會議的最長時間（秒）→ 10 分鐘
RETRY_LIMIT = 2  # 自動重試次數（例如：按鈕找不到時）

# ⭐ 你的排程（可以有多筆）
#   date：YYYY-MM-DD
#   time：HH:MM（24小時制）
#   url：Teams 連結（可以先填空字串，之後用 LINE 補）
REMIND_OFFSETS = [120, 60, 30, 15, 5]  # 提前提醒時間（分鐘）
SCHEDULES = [
    {"date": "2025-11-21", "time": "17:25", "url": ""},
    {"date": "2025-11-24", "time": "17:25", "url": ""},
    {"date": "2025-11-25", "time": "17:25", "url": ""},
    {"date": "2025-11-26", "time": "17:25", "url": ""},
    {"date": "2025-11-27", "time": "17:25", "url": ""},
    {"date": "2025-11-28", "time": "17:25", "url": ""},
    {"date": "2025-12-01", "time": "17:25", "url": ""},
    {"date": "2025-12-02", "time": "17:25", "url": ""},
    {"date": "2025-12-03", "time": "17:25", "url": ""},
    {"date": "2025-12-04", "time": "17:25", "url": ""},
]


# ============================================================
#                 Flask & ngrok 啟動
# ============================================================

app = Flask(__name__)
lock = threading.Lock()


def start_ngrok():
    """啟動 ngrok，取得公開網址（HTTPS）"""
    ngrok.kill()
    public_url = ngrok.connect(5000, bind_tls=True).public_url
    print("🌍 ngrok 公開網址：", public_url)
    print(f"➡️ 請在 LINE Developers Webhook URL 填入：{public_url}/linebot")
    return public_url


def run_flask():
    app.run(port=5000, debug=False, use_reloader=False)


public_url = start_ngrok()
threading.Thread(target=run_flask, daemon=True).start()


# ============================================================
#                LINE 傳訊息封裝
# ============================================================


def send_line_message(text: str):
    headers = {
        "Authorization": f"Bearer {LINE_TOKEN}",
        "Content-Type": "application/json",
    }
    body = {"to": USER_ID, "messages": [{"type": "text", "text": text}]}

    try:
        res = requests.post(
            "https://api.line.me/v2/bot/message/push",
            headers=headers,
            json=body,
            timeout=10,
        )
        print("📨 LINE 回應：", res.status_code, res.text)
    except Exception as e:
        print("❌ LINE 傳送錯誤：", e)


# ============================================================
#            🔧 排程相關：修改時間 & URL
# ============================================================


def update_schedule_time_by_day(day_str: str, new_time: str):
    """
    使用者輸入：16 20:00 → 修改「本月 16 號」的排程時間
    """
    global SCHEDULES
    today = datetime.datetime.now()
    year = today.year
    month = today.month
    target_date = f"{year}-{month:02d}-{int(day_str):02d}"

    found = False
    for item in SCHEDULES:
        if item["date"] == target_date:
            item["time"] = new_time
            found = True
            break

    if found:
        send_line_message(f"🕒 已更新排程時間：{target_date} → {new_time}")
        print(f"✅ 更新排程時間：{target_date} → {new_time}")
    else:
        send_line_message(f"⚠️ 找不到 {target_date} 的排程")


def update_schedule_url_by_day(day_str: str, url: str):
    """
    使用者輸入：16 https://teams... → 修改「本月 16 號」的 URL
    """
    global SCHEDULES
    today = datetime.datetime.now()
    year = today.year
    month = today.month
    target_date = f"{year}-{month:02d}-{int(day_str):02d}"

    found = False
    for item in SCHEDULES:
        if item["date"] == target_date:
            item["url"] = url
            found = True
            break

    if found:
        send_line_message(f"🔗 已更新 {target_date} 會議連結")
        print(f"✅ 更新會議連結：{target_date} → {url}")
    else:
        send_line_message(f"⚠️ 找不到 {target_date} 的排程")


def update_next_schedule_url(url: str):
    """
    使用者傳純 URL（https://teams...）→ 更新「下一場尚未開始」的排程 URL
    """
    global SCHEDULES
    now = datetime.datetime.now()

    # 找出所有「尚未開始」的排程
    future_events = []
    for s in SCHEDULES:
        dt = datetime.datetime.strptime(f"{s['date']} {s['time']}", "%Y-%m-%d %H:%M")
        if dt >= now:
            future_events.append((dt, s))

    if not future_events:
        send_line_message("⚠️ 找不到未來的排程，無法更新 URL")
        return

    # 依時間排序，取最近的一場
    future_events.sort(key=lambda x: x[0])
    nearest = future_events[0][1]
    nearest["url"] = url

    send_line_message(f"🔗 已更新會議連結：{nearest['date']} {nearest['time']}")
    print(f"✅ 更新會議連結：{nearest['date']} {nearest['time']} → {url}")
        

def update_remind_offsets_from_line(text):
    """
    接收 LINE 傳來的 [120, 60, 30, 15, 5] 形式，更新 REMIND_OFFSETS。
    """
    global REMIND_OFFSETS

    try:
        # 去除空白
        cleaned = text.replace(" ", "")

        # 必須是 [xxx,yyy] 形式
        if not (cleaned.startswith("[") and cleaned.endswith("]")):
            return False, "格式錯誤，需像 [120,60,30,15,5]"

        # 去掉 [] 再切割
        inner = cleaned[1:-1]

        # 避免空白內容
        if inner.strip() == "":
            return False, "陣列為空"

        # 分割成數字陣列
        parts = inner.split(",")
        offsets = []

        for p in parts:
            if not p.isdigit():
                return False, f"無法解析 '{p}'，請確保所有項目都是數字"
            offsets.append(int(p))

        # 排序（從大到小或小到大皆可，你喜歡）
        offsets = sorted(offsets, reverse=True)

        REMIND_OFFSETS = offsets

        return True, f"已更新提醒點：{REMIND_OFFSETS}"

    except Exception as e:
        return False, str(e)


def check_countdown_reminders():
    """
    只在「該排程的 URL 缺失」時觸發倒數提醒。
    使用 REMIND_OFFSETS（例如[120,60,30,15,5]）
    來判斷何時提醒一次。
    """
    now = datetime.datetime.now()

    for item in SCHEDULES:
        event_dt = datetime.datetime.strptime(
            f"{item['date']} {item['time']}", "%Y-%m-%d %H:%M"
        )

        # 已過時間的會議不提醒
        if event_dt <= now:
            continue

        # ⭐ 只有 URL 空缺時才提醒
        if item.get("url") is not None and item["url"].strip() != "":
            continue  # 有 URL → 不提醒

        # 與現在差距（分鐘）
        diff_min = int((event_dt - now).total_seconds() / 60)

        for offset in REMIND_OFFSETS:
            if diff_min == offset and offset not in item["reminded"]:
                day = int(item["date"][-2:])
                send_line_message(
                    f"⚠️ 距離會議還有 {offset} 分鐘，請盡快設定會議連結！"
                )
                print(f"🔔 URL 缺失提醒：{item['date']} {item['time']}（{offset} 分鐘）")
                item["reminded"].append(offset)


# ============================================================
#             LINE webhook：解析指令
# ============================================================


@app.route("/linebot", methods=["POST"])
def linebot():
    try:
        data = request.get_json()
        print("📥 收到 LINE webhook：", data)

        if not data or "events" not in data:
            return {"error": "Invalid payload"}, 400

        for event in data["events"]:
            if event.get("type") != "message":
                continue

            text = event["message"].get("text", "").strip()
            print("📩 使用者輸入：", text)

            # 1) 修改時間：格式「DD HH:MM」→ 例如 "16 20:00"
            m_time = re.match(r"^(\d{1,2})\s+(\d{2}:\d{2})$", text)
            if m_time and not text.lower().startswith("http"):
                day_str, hm = m_time.groups()
                update_schedule_time_by_day(day_str, hm)
                continue

            # 2) 修改指定日期的 URL：格式「DD URL」
            m_url_day = re.match(
                r"^(\d{1,2})\s+(https://teams\.microsoft\.com/\S+)$", text
            )
            if m_url_day:
                day_str, url = m_url_day.groups()
                update_schedule_url_by_day(day_str, url)
                continue

            # 3) 單純是 URL → 更新下一場排程
            if text.startswith("https://teams.microsoft.com/"):
                update_next_schedule_url(text)
                continue

            # 4）判斷是否為提醒陣列 [120,60,30...]
            if text.startswith("[") and text.endswith("]"):
                ok, msg = update_remind_offsets_from_line(text)
                send_line_message(("✅ " if ok else "⚠️ ") + msg)
                continue

            # 5) 手動重試（立即執行 auto_join_meeting，使用「下一場」URL）
            if text in ["重試", "retry", "再試一次", "再來一次", "重新加入"]:
                send_line_message("🔄 正在重新嘗試加入會議...")
                threading.Thread(target=auto_join_meeting, daemon=True).start()
                continue

            send_line_message(
                "❓ 可用指令：\n"
                "・修改時間： 16 20:00\n"
                "・修改 URL： 16 https://teams...\n"
                "・更新下一場 URL： 直接貼上 https://teams...\n"
                "・重試：重試 / 再試一次 / 重新加入"
            )

        return {"status": "ok"}, 200

    except Exception as e:
        print("❌ LINE webhook error:", e)
        return {"error": str(e)}, 500


# ============================================================
#                Selenium 自動加入 Teams
# ============================================================


def wait_for_meeting_entry(driver, max_wait_minutes=5):
    """
    等待被允許進入會議。
    若成功進入回傳 True，
    若超時回傳 False。
    """
    print(f"⌛ 等待主持人允許中...")
    send_line_message(f"⌛ 等待主持人允許中...")

    start = time.time()

    while True:
        # 若 URL 改變或出現「離開」按鈕 → 成功進入
        if "meetingStage" in driver.current_url:
            print("✅ 已進入會議！")
            return True

        if driver.find_elements(By.XPATH, "//button[contains(., '離開') or contains(., 'Leave')]"):
            print("✅ 已進入會議！")
            return True

        # 若畫面包含「讓你進入」提示 → 持續等待
        if driver.find_elements(By.XPATH,
            "//*[contains(text(), '讓你進入') or "
            "contains(text(), 'Someone in the meeting') or "
            "contains(text(), 'We’ll let you in')]"
        ):
            time.sleep(5)

        # 超時判斷
        if (time.time() - start) > max_wait_minutes * 60:
            print("⚠️ 等待主持人允許超時")
            return False

        time.sleep(5)


def auto_join_meeting(override_url: str = None):
    """
    自動加入 Teams 會議：
    - override_url 有值：直接用這個 URL
    - 否則：選「下一場尚未開始的排程」的 URL
    - 自動重試 RETRY_LIMIT 次
    """

    def report_error(msg: str):
        send_line_message(f"❌ 自動加入失敗：{msg}\n⚠️ 請手動加入會議")
        print("❌", msg)

    # 取得要使用的 URL
    url = override_url
    if not url:
        # 從 SCHEDULES 選「下一場」
        now = datetime.datetime.now()
        future_events = []
        for s in SCHEDULES:
            dt = datetime.datetime.strptime(
                f"{s['date']} {s['time']}", "%Y-%m-%d %H:%M"
            )
            if dt >= now:
                future_events.append((dt, s))
        if not future_events:
            return report_error("⚠️ 找不到未來的排程，無法自動加入")
        future_events.sort(key=lambda x: x[0])
        nearest = future_events[0][1]
        if not nearest.get("url"):
            return report_error(
                f"⚠️ {nearest['date']} {nearest['time']} 會議連結尚未設定"
            )
        url = nearest["url"]

    for attempt in range(1, RETRY_LIMIT + 1):
        print(f"🔁 嘗試加入會議（第 {attempt} 次） → {url}")

        try:
            options = Options()
            options.add_argument("--disable-notifications")
            options.add_argument("--disable-infobars")
            options.add_argument("--use-fake-ui-for-media-stream")
            options.add_argument("--start-maximized")

            driver = webdriver.Chrome(
                service=Service(ChromeDriverManager().install()),
                options=options,
            )
            wait = WebDriverWait(driver, 30)

            # 開啟 URL
            try:
                driver.get(url)
            except Exception:
                if attempt == RETRY_LIMIT:
                    driver.quit()
                    return report_error("⚠️ 無法開啟 Teams URL")
                driver.quit()
                continue

            # 「從這個瀏覽器加入會議」
            try:
                btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//button[@aria-label="從這個瀏覽器加入會議"]')
                    )
                )
                btn.click()
            except Exception:
                if attempt == RETRY_LIMIT:
                    driver.quit()
                    return report_error("⚠️ 找不到『從這個瀏覽器加入會議』按鈕")
                driver.quit()
                continue

            # 「在無音訊或視訊的情況下繼續」
            try:
                continue_btn = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//button[@data-focus-target="gum-continue"]')
                    )
                )
                continue_btn.click()
            except Exception:
                # 若找不到此按鈕不視為錯誤（Teams 不一定每次會出現這個畫面）
                print("⚠️ 找不到『在無音訊或視訊的情況下繼續』按鈕，略過")

            time.sleep(WAIT_BEFORE_JOIN)

            # 輸入名稱
            try:
                name_input = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//input[@data-tid="prejoin-display-name-input"]')
                    )
                )
                name_input.clear()
                name_input.send_keys(GUEST_NAME)
            except Exception:
                if attempt == RETRY_LIMIT:
                    driver.quit()
                    return report_error("⚠️ 找不到『輸入名稱』欄位")
                driver.quit()
                continue

            # 不使用音訊
            try:
                no_audio = wait.until(
                    EC.element_to_be_clickable(
                        (
                            By.XPATH,
                            '//input[@aria-label="不使用音訊"]/following-sibling::label',
                        )
                    )
                )
                no_audio.click()
            except Exception:
                if attempt == RETRY_LIMIT:
                    driver.quit()
                    return report_error("⚠️ 找不到『不使用音訊』按鈕")
                driver.quit()
                continue

            # 「立即加入」
            try:
                join = wait.until(
                    EC.element_to_be_clickable(
                        (By.XPATH, '//button[@aria-label="立即加入"]')
                    )
                )
                join.click()
            except Exception:
                if attempt == RETRY_LIMIT:
                    driver.quit()
                    return report_error("⚠️ 找不到『立即加入』按鈕")
                driver.quit()
                continue

            # 等待主持人允許
            send_line_message("⌛ 等待主持人允許")
            print("⌛ 等待主持人允許")
            start_wait = time.time()

            entered = wait_for_meeting_entry(driver, MAX_WAIT_HOST / 60)

            if entered:
                send_line_message("✅ 已成功進入會議！")
                print("🎉 成功進入會議")
                return
            else:
                driver.quit()
                return report_error("⚠️ 等待主持人允許超時")

        except Exception as e:
            if attempt == RETRY_LIMIT:
                return report_error(f"⚠️ 程式錯誤：{e}")
            continue


# ============================================================
#               排程執行器（多筆排程）
# ============================================================


def schedule_runner():
    print("⏰ 排程執行器啟動")

    last_date = None

    while True:
        now = datetime.datetime.now()
        now_str = now.strftime("%Y-%m-%d %H:%M")
        today_date = now.date()

        # ================
        #   🔔 倒數提醒
        # ================
        if last_date is None or today_date != last_date:
            for item in SCHEDULES:
                item["reminded"] = []   # 清空該天所有提醒記錄
            last_date = today_date
        check_countdown_reminders()

        # ================
        #   ⏰ 排程觸發  
        # ================
        for item in SCHEDULES:
            run_at = f"{item['date']} {item['time']}"
            if now_str == run_at:
                if not item.get("url"):
                    send_line_message(
                        f"⚠️ {run_at} 會議連結尚未設定，無法自動加入會議"
                    )
                    continue

                send_line_message(f"⏰ 觸發排程：{run_at}，開始加入會議")
                threading.Thread(
                    target=auto_join_meeting,
                    args=(item["url"],),
                    daemon=True,
                ).start()

        time.sleep(20)


# ============================================================
#                      程式入口
# ============================================================

if __name__ == "__main__":
    threading.Thread(target=schedule_runner, daemon=True).start()
    send_line_message("✅ 系統啟動中...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        ngrok.kill()
        print("🛑 手動中止程式")

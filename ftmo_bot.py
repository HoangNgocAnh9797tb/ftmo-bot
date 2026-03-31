import sys
import io
import json
import os
import schedule
import time
from datetime import datetime, timedelta

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# ─── CẤU HÌNH ────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
CHAT_ID   = os.getenv("CHAT_ID", "")
SEEN_FILE = "seen_articles.json"
CHECK_INTERVAL_MINUTES = 30

# ─── TELEGRAM ────────────────────────────────────────────────────────────────
def send_telegram(message: str):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML", "disable_web_page_preview": True}
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            print(f"[{_now()}] Đã gửi Telegram OK")
        else:
            print(f"[{_now()}] Gửi thất bại: {r.status_code} — {r.text}")
    except Exception as e:
        print(f"[{_now()}] Lỗi Telegram: {e}")

# ─── SEEN (tránh gửi trùng) ──────────────────────────────────────────────────
def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)

# ─── PLAYWRIGHT: lấy HTML sau khi JS render xong ─────────────────────────────
def get_rendered_html(url: str, wait_selector: str = None, timeout: int = 20000) -> str:
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        # Chờ network idle để API calls hoàn tất
        try:
            page.wait_for_load_state("networkidle", timeout=timeout)
        except Exception:
            page.wait_for_timeout(5000)
        if wait_selector:
            try:
                page.wait_for_selector(wait_selector, timeout=timeout)
            except Exception:
                pass
        html = page.content()
        browser.close()
    return html

# ─── 1. FTMO TRADING UPDATES ─────────────────────────────────────────────────
def fetch_article_content(url: str) -> str:
    """Đọc nội dung đầy đủ từ trang bài viết."""
    try:
        html = get_rendered_html(url)
    except Exception as e:
        print(f"[{_now()}] Lỗi đọc bài: {e}")
        return ""
    soup = BeautifulSoup(html, "html.parser")
    # Xóa nav, header, footer, script
    for tag in soup(["nav", "header", "footer", "script", "style", "noscript"]):
        tag.decompose()
    # Lấy phần nội dung chính
    body = (
        soup.find("article") or
        soup.find(class_=lambda c: c and "content" in c.lower()) or
        soup.find("main") or
        soup.body
    )
    if not body:
        return ""
    return body.get_text("\n", strip=True)

def fetch_trading_updates() -> list[dict]:
    try:
        html = get_rendered_html("https://ftmo.com/vi/trading-updates/")
    except Exception as e:
        print(f"[{_now()}] Trading Updates lỗi: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    items = []

    # Lấy bài mới nhất — link có text dạng "Thông tin cập nhật – DD/MM/YYYY"
    latest = soup.find("a", string=lambda t: t and "cập nhật" in t.lower())
    if not latest:
        print(f"[{_now()}] Trading Updates: không tìm thấy link")
        return []

    link = latest["href"]
    if not link.startswith("http"):
        link = "https://ftmo.com" + link
    title = latest.get_text(strip=True)
    print(f"[{_now()}] Trading Updates latest: {title}")
    items.append({"title": title, "link": link})
    return items

# ─── 2. FTMO CALENDAR ────────────────────────────────────────────────────────
def get_calendar_url() -> str:
    today = datetime.now()
    start = today - timedelta(days=today.weekday())
    end   = start + timedelta(days=6)
    return (
        f"https://ftmo.com/en/calendar/"
        f"?dateFrom={start.strftime('%Y-%m-%d')}"
        f"&dateTo={end.strftime('%Y-%m-%d')}"
        f"&timezone=Asia%2FBangkok"
    )

def fetch_calendar_events() -> list[dict]:
    url = get_calendar_url()
    print(f"[{_now()}] Calendar URL: {url}")
    try:
        html = get_rendered_html(url, wait_selector="table, .calendar, tr.event, [class*='calendar']")
    except Exception as e:
        print(f"[{_now()}] Calendar lỗi: {e}")
        return []

    soup = BeautifulSoup(html, "html.parser")
    events = []

    # Thử tìm table rows
    rows = soup.find_all("tr")
    print(f"[{_now()}] Calendar: tìm thấy {len(rows)} rows")

    # Từ khóa liên quan XAUUSD: USD news ảnh hưởng giá vàng
    XAUUSD_KEYWORDS = ["XAU", "Gold", "XAUUSD"]

    import re as _re

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 3:
            continue

        texts = []
        for c in cells:
            t = c.get_text(" ", strip=True)
            # Bỏ countdown dạng HH:MM:SS (vd: 73:46:07)
            t = _re.sub(r"\b\d{1,3}:\d{2}:\d{2}\b", "", t).strip()
            if t:
                texts.append(t)

        row_text = " ".join(texts)
        if not any(kw.lower() in row_text.lower() for kw in XAUUSD_KEYWORDS):
            continue
        if "restricted event" not in row_text.lower():
            continue

        events.append({"raw": " | ".join(texts)})

    print(f"[{_now()}] Calendar XAUUSD: tìm thấy {len(events)} sự kiện")
    return events[:30]


# ─── JOB CHÍNH ───────────────────────────────────────────────────────────────
def check_ftmo():
    seen = load_seen()
    new_count = 0

    # Trading Updates
    print(f"[{_now()}] Kiểm tra Trading Updates...")
    for item in fetch_trading_updates():
        key = "update:" + item["link"]
        if key not in seen:
            content = fetch_article_content(item["link"])
            # Gửi theo từng đoạn 3800 ký tự (giới hạn Telegram 4096)
            header = f"🔔 <b>FTMO TRADING UPDATES</b>\n🔗 {item['link']}\n\n"
            full = header + content
            for i in range(0, len(full), 3800):
                chunk = full[i:i+3800]
                send_telegram(chunk)
                time.sleep(1)
            seen.add(key)
            new_count += 1

    # Calendar
    print(f"[{_now()}] Kiểm tra Calendar...")
    for event in fetch_calendar_events():
        key = "cal:" + event["raw"][:80]
        if key not in seen:
            send_telegram(f"📅 <b>FTMO CALENDAR — XAUUSD</b>\n\n{event['raw']}")
            seen.add(key)
            new_count += 1
            time.sleep(1)

    save_seen(seen)
    print(f"[{_now()}] Đã gửi {new_count} tin mới." if new_count else f"[{_now()}] Không có gì mới.")

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[{_now()}] FTMO Bot khởi động — kiểm tra mỗi {CHECK_INTERVAL_MINUTES} phút")
    check_ftmo()
    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_ftmo)
    while True:
        schedule.run_pending()
        time.sleep(60)

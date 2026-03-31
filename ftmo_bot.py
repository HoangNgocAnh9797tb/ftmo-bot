import sys
import io
import requests
import json
import os
import schedule
import time
from datetime import datetime, timedelta
from bs4 import BeautifulSoup

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── CẤU HÌNH ────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8210159742:AAEDGW7GstEmrDOJRyQIGWY91Jgd0aDCdbs")
CHAT_ID   = os.getenv("CHAT_ID", "-5294816070")
SEEN_FILE = "seen_articles.json"
CHECK_INTERVAL_MINUTES = 30

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}

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
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)

# ─── 1. FTMO TRADING UPDATES ─────────────────────────────────────────────────
def fetch_trading_updates() -> list[dict]:
    try:
        r = requests.get("https://ftmo.com/en/trading-updates/", headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[{_now()}] Trading Updates lỗi: {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    # Debug lần đầu để xem cấu trúc HTML
    print(f"[{_now()}] Trading Updates HTML snippet:\n{r.text[:800]}")

    items = []
    seen_links = set()
    cards = soup.find_all("article") or soup.find_all(class_=lambda c: c and "post" in c.lower())

    for card in cards:
        title_tag = card.find(["h2", "h3", "h4"])
        title = title_tag.get_text(strip=True) if title_tag else ""
        link_tag = card.find("a", href=True)
        link = link_tag["href"] if link_tag else ""
        if link and not link.startswith("http"):
            link = "https://ftmo.com" + link
        date_tag = card.find("time")
        date = date_tag.get_text(strip=True) if date_tag else ""

        if not title or not link or link in seen_links:
            continue
        seen_links.add(link)
        items.append({"title": title, "link": link, "date": date})
        if len(items) >= 10:
            break

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
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[{_now()}] Calendar lỗi: {e}")
        return []

    # Debug HTML
    print(f"[{_now()}] Calendar HTML snippet:\n{r.text[:800]}")

    soup = BeautifulSoup(r.text, "html.parser")
    events = []

    # Thử các selector phổ biến cho calendar
    rows = (
        soup.find_all("tr", class_=lambda c: c and "event" in c.lower()) or
        soup.find_all("div", class_=lambda c: c and "event" in c.lower()) or
        soup.find_all("li",  class_=lambda c: c and "event" in c.lower()) or
        soup.find_all("tr")[1:]  # bỏ header row
    )

    for row in rows[:30]:
        cells = row.find_all(["td", "th"])
        texts = [c.get_text(strip=True) for c in cells if c.get_text(strip=True)]
        if len(texts) >= 2:
            events.append({"raw": " | ".join(texts)})

    # Nếu không thấy, tìm JSON trong script tags
    if not events:
        for script in soup.find_all("script"):
            content = script.string or ""
            if "event" in content.lower() and len(content) > 100:
                print(f"[{_now()}] Script tag snippet: {content[:400]}")
                break

    return events

# ─── JOB CHÍNH ───────────────────────────────────────────────────────────────
def check_ftmo():
    seen = load_seen()
    new_count = 0

    # Trading Updates
    print(f"[{_now()}] Kiểm tra Trading Updates...")
    for item in fetch_trading_updates():
        key = "update:" + item["link"]
        if key not in seen:
            lines = ["🔔 <b>FTMO TRADING UPDATES</b>", "", f"📌 <b>{item['title']}</b>"]
            if item["date"]:
                lines.append(f"🗓 {item['date']}")
            lines.append(f"\n🔗 <a href=\"{item['link']}\">Đọc thêm</a>")
            send_telegram("\n".join(lines))
            seen.add(key)
            new_count += 1
            time.sleep(1)

    # Calendar
    print(f"[{_now()}] Kiểm tra Calendar...")
    for event in fetch_calendar_events():
        key = "cal:" + event["raw"][:80]
        if key not in seen:
            send_telegram(f"📅 <b>FTMO ECONOMIC CALENDAR</b>\n\n{event['raw']}")
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

import sys
import io
import requests
import json
import os
import schedule
import time
from datetime import datetime
from bs4 import BeautifulSoup

# Fix encoding cho Windows terminal
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# ─── CẤU HÌNH ────────────────────────────────────────────────────────────────
BOT_TOKEN = os.getenv("BOT_TOKEN", "8210159742:AAEDGW7GstEmrDOJRyQIGWY91Jgd0aDCdbs")
CHAT_ID   = os.getenv("CHAT_ID", "-5294816070")
SEEN_FILE = "seen_articles.json"
CHECK_INTERVAL_MINUTES = 30

FTMO_BLOG_URL = "https://ftmo.com/en/blog/"
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
    payload = {
        "chat_id": CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    try:
        r = requests.post(url, data=payload, timeout=10)
        if r.status_code == 200:
            print(f"[{_now()}] Đã gửi Telegram OK")
        else:
            print(f"[{_now()}] Gửi thất bại: {r.status_code} — {r.text}")
    except Exception as e:
        print(f"[{_now()}] Lỗi kết nối Telegram: {e}")

# ─── SEEN ARTICLES (tránh gửi trùng) ────────────────────────────────────────
def load_seen() -> set:
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE, "r", encoding="utf-8") as f:
            return set(json.load(f))
    return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w", encoding="utf-8") as f:
        json.dump(list(seen), f, ensure_ascii=False, indent=2)

# ─── SCRAPE FTMO BLOG ────────────────────────────────────────────────────────
def fetch_ftmo_articles() -> list[dict]:
    try:
        r = requests.get(FTMO_BLOG_URL, headers=HEADERS, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"[{_now()}] Không lấy được FTMO (sẽ hoạt động khi deploy): {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    articles = []
    seen_links = set()

    cards = soup.find_all("article")
    if not cards:
        cards = soup.find_all(class_=lambda c: c and "post" in c.lower())

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
        articles.append({"title": title, "link": link, "date": date})

        if len(articles) >= 10:
            break

    return articles

# ─── FORMAT TIN NHẮN ─────────────────────────────────────────────────────────
def format_article(article: dict) -> str:
    lines = ["📰 <b>CẬP NHẬT MỚI TỪ FTMO</b>", "", f"📌 <b>{article['title']}</b>"]
    if article["date"]:
        lines.append(f"🗓 {article['date']}")
    lines.append(f"\n🔗 <a href=\"{article['link']}\">Đọc thêm</a>")
    return "\n".join(lines)

# ─── JOB CHÍNH ───────────────────────────────────────────────────────────────
def check_ftmo():
    print(f"[{_now()}] Đang kiểm tra FTMO blog...")
    seen = load_seen()
    articles = fetch_ftmo_articles()

    new_count = 0
    for article in articles:
        key = article["link"]
        if key not in seen:
            send_telegram(format_article(article))
            seen.add(key)
            new_count += 1
            time.sleep(1)

    save_seen(seen)
    if new_count == 0:
        print(f"[{_now()}] Không có bài mới.")
    else:
        print(f"[{_now()}] Đã gửi {new_count} bài mới.")

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

# ─── MAIN ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"[{_now()}] FTMO Bot khởi động — kiểm tra mỗi {CHECK_INTERVAL_MINUTES} phút")
    send_telegram("🤖 <b>FTMO Bot đã khởi động!</b>\nSẽ thông báo khi có bài viết mới từ FTMO.")

    check_ftmo()

    schedule.every(CHECK_INTERVAL_MINUTES).minutes.do(check_ftmo)

    while True:
        schedule.run_pending()
        time.sleep(60)

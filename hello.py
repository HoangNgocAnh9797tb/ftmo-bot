import requests

def send_telegram_message(message):
    # Thay thế các thông số bên dưới
    token = "8210159742:AAEDGW7GstEmrDOJRyQIGWY91Jgd0aDCdbs"
    chat_id = "6129301511"
    
    # API URL của Telegram
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    
    # Dữ liệu gửi đi
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML" # Giúp bạn có thể dùng thẻ <b>, <i>...
    }

    try:
        response = requests.post(url, data=payload)
        # Kiểm tra nếu gửi thành công
        if response.status_code == 200:
            print("✅ Tin nhắn đã được gửi đi thành công!")
        else:
            print(f"❌ Thất bại. Mã lỗi: {response.status_code}")
            print(f"Chi tiết: {response.text}")
    except Exception as e:
        print(f"⚠️ Có lỗi xảy ra khi kết nối: {e}")

# --- Chạy thử ---
nd = "<b>THÔNG BÁO MỚI</b>\n🚀 Hệ thống vừa hoàn thành tác vụ lúc 15:30."
send_telegram_message(nd)
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

# SỬA 2 DÒNG NÀY BẰNG INFO CỦA BẠN
API_ID = 27615626 
API_HASH = "bba8d22dd8ba68463a621fcc7fb1ca5d"

print("Đang chạy... Vui lòng nhập số điện thoại và code khi được hỏi.")

with TelegramClient(StringSession(), API_ID, API_HASH) as client:
    session_string = client.session.save()
    print("\n\nĐĂNG NHẬP THÀNH CÔNG!")
    print("=========================================================")
    print("Chuỗi Session của bạn là (SAO CHÉP TOÀN BỘ CÁC DÒNG NÀY):")
    print(session_string)
    print("=========================================================")
    print("Lưu kỹ chuỗi này. Bạn sẽ cần nó cho Bước 2.")

import os
import datetime
from datetime import timezone, timedelta
from collections import Counter
import re
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from telethon.sessions import StringSession

# ====== CẤU HÌNH CỦA BẠN (Sửa tại đây) ======
API_ID = int(os.environ.get("TG_API_ID") or 27615626) # Sửa ID của bạn
API_HASH = os.environ.get("TG_API_HASH") or "bba8d22dd8ba68463a621fcc7fb1ca5d" # Sửa HASH của bạn
TELETHON_SESSION = os.environ.get("1BVtsOJgBu5mDHa63_0ZoWAOQmkXbJmL75QYrhIXXIlwa469Hn6R1MvPSn3q5VFrTeBm3GdE7cRMOGQcsnr9Onybc10liJa2M2kD4YGawzJcnD87xmjO7KpzxkzELOJ61zlbQ0Xjg_DA_gu_Wr5EpZbLCS1tvNI4JGafDJa1oV3MsvUmIgU633bxbzqlsu4AdQiOq0avTQqFKa8Wyze7qihFWjS2OzkxM7Jbc1xOAFucj6NySNkM0JprD4eAD643qxDLhNcrVbzvc8WRiQR2RxSojldlwOk73piXzPDF3zocyOe1tgMMdqgmlnKa3710Y6kRRxxFTNm2pF4ipcQc83sVTWukpVhE=")

GROUP_SOURCES = {
    -1003037580357: "Hẻm Gaming",
    -1003157457932: "Tổ Đội Gaming"
}
# ============================================

# Khởi tạo API
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Cấu hình CORS (Cho phép Mini App gọi)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Cho phép tất cả (sẽ sửa sau)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Khởi tạo Client (Giống như code cũ)
tele_client = TelegramClient(StringSession(1BVtsOJgBu5mDHa63_0ZoWAOQmkXbJmL75QYrhIXXIlwa469Hn6R1MvPSn3q5VFrTeBm3GdE7cRMOGQcsnr9Onybc10liJa2M2kD4YGawzJcnD87xmjO7KpzxkzELOJ61zlbQ0Xjg_DA_gu_Wr5EpZbLCS1tvNI4JGafDJa1oV3MsvUmIgU633bxbzqlsu4AdQiOq0avTQqFKa8Wyze7qihFWjS2OzkxM7Jbc1xOAFucj6NySNkM0JprD4eAD643qxDLhNcrVbzvc8WRiQR2RxSojldlwOk73piXzPDF3zocyOe1tgMMdqgmlnKa3710Y6kRRxxFTNm2pF4ipcQc83sVTWukpVhE=), 27615626, bba8d22dd8ba68463a621fcc7fb1ca5d)

# ====== CÁC HÀM UTILS (Giống code cũ) ======
def escape_md(text: str):
    return re.sub(r'([_*\[\]()~`>#+\-=|{}.!])', r'\\\1', str(text))

def parse_vn_date(s: str) -> datetime.datetime:
    d = datetime.datetime.strptime(s, "%d/%m/%Y")
    start_local = d.replace(hour=0, minute=0, second=0, microsecond=0)
    class GMT7(datetime.tzinfo):
        def utcoffset(self, dt): return timedelta(hours=7)
        def tzname(self, dt): return "GMT+7"
        def dst(self, dt): return timedelta(0)
    gmt7 = GMT7()
    start_local = start_local.replace(tzinfo=gmt7)
    start_utc = start_local.astimezone(timezone.utc)
    end_utc = (start_local + timedelta(days=1)).astimezone(timezone.utc)
    return start_utc, end_utc

async def resolve_chat_entity(raw: str):
    raw = raw.strip()
    if raw.startswith("https://t.me/") or raw.startswith("t.me/"):
        return await tele_client.get_entity(raw)
    try:
        cid = int(raw)
        if cid < -1000000000000:
            cid = int(str(cid)[4:])
        return await tele_client.get_entity(PeerChannel(cid))
    except Exception:
        return await tele_client.get_entity(raw)

async def human_name_for_user(user):
    uname = getattr(user, "username", None)
    if uname:
        return f"@{uname}"
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    full = (first + " " + last).strip()
    return full or f"id:{user.id}"

# ====== CÁC HÀM QUÉT LỊCH SỬ (Sửa để trả về JSON) ======

async def get_rankmem_data(target, date_str_start, date_str_end):
    """Quét top member và trả về dữ liệu (JSON)"""
    try:
        start_utc, _ = parse_vn_date(date_str_start)
        _, end_utc = parse_vn_date(date_str_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ngày không hợp lệ. Định dạng DD/MM/YYYY")

    async with tele_client:
        try:
            entity = await resolve_chat_entity(target)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy nhóm {target}: {e}")

        counter = Counter()
        scanned = 0
        LIMIT = 10000

        try:
            async for msg in tele_client.iter_messages(entity, limit=LIMIT, offset_date=end_utc):
                scanned += 1
                if not msg.date: continue
                msg_dt_utc = msg.date.astimezone(timezone.utc)
                if msg_dt_utc < start_utc: break
                if hasattr(msg, "action") and msg.action is not None: continue
                uid = getattr(msg, "sender_id", None)
                if uid: counter[uid] += 1
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi khi quét tin nhắn: {e}")

        if not counter:
            return {"scanned": scanned, "top": []} # Trả về mảng rỗng

        topn = 10
        rows = counter.most_common(topn)
        results = []
        for i, (uid, cnt) in enumerate(rows, start=1):
            try:
                user = await tele_client.get_entity(uid)
                name = await human_name_for_user(user)
            except Exception:
                name = f"id:{uid}"
            results.append({"rank": i, "name": name, "messages": cnt})
        
        return {"scanned": scanned, "top": results, "group_title": getattr(entity, "title", str(target))}

async def get_checkgroup_data(target, date_str_start, date_str_end):
    """Quét join/leave và trả về dữ liệu (JSON)"""
    try:
        start_utc, _ = parse_vn_date(date_str_start)
        _, end_utc = parse_vn_date(date_str_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ngày không hợp lệ. Định dạng DD/MM/YYYY")

    async with tele_client:
        try:
            entity = await resolve_chat_entity(target)
        except Exception as e:
            raise HTTPException(status_code=404, detail=f"Không tìm thấy nhóm {target}: {e}")

        joins, leaves = [], []
        scanned = 0
        LIMIT = 50000

        try:
            async for msg in tele_client.iter_messages(entity, limit=LIMIT, offset_date=end_utc):
                scanned += 1
                if not msg.date: continue
                msg_dt = msg.date.astimezone(datetime.timezone.utc)
                if msg_dt < start_utc: break
                if hasattr(msg, "action") and msg.action is not None:
                    action = msg.action
                    if hasattr(action, "users"):
                        if "ChatAddUser" in action.__class__.__name__: joins.extend(action.users)
                        elif "ChatJoinedByLink" in action.__class__.__name__: joins.extend(action.users)
                    elif "ChatDeleteUser" in action.__class__.__name__:
                        leaves.append(getattr(action, "user_id", None))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Lỗi khi quét tin nhắn: {e}")

        # (Phần resolve tên không cần thiết cho API, chỉ cần số lượng)
        
        return {
            "scanned": scanned,
            "joins": len(set(joins)),
            "leaves": len(set(leaves)),
            "group_title": getattr(entity, "title", str(target))
        }

# ====== CÁC ĐIỂM CUỐI API (API Endpoints) ======
# Đây là các URL mà Mini App sẽ gọi

@app.get("/")
def read_root():
    return {"message": "Chào mừng đến với API Bot!"}

@app.get("/api/groups")
def get_groups_list():
    """Trả về danh sách nhóm từ cấu hình"""
    return GROUP_SOURCES

@app.get("/api/rankmem")
async def api_rankmem(target: str, start_date: str, end_date: str):
    """Endpoint cho /rankmem"""
    data = await get_rankmem_data(target, start_date, end_date)
    return data

@app.get("/api/checkgroup")
async def api_checkgroup(target: str, start_date: str, end_date: str):
    """Endpoint cho /checkgroup"""
    data = await get_checkgroup_data(target, start_date, end_date)
    return data

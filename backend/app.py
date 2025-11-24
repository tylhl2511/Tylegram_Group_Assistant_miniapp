import os
import datetime
from datetime import timezone, timedelta
from collections import Counter
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from telethon import TelegramClient
from telethon.tl.types import PeerChannel
from telethon.sessions import StringSession
from contextlib import asynccontextmanager
from dotenv import load_dotenv

# ====== CẤU HÌNH ======
load_dotenv() # Load .env cho Local

API_ID_STR = os.getenv("TG_API_ID") or os.environ.get("TG_API_ID")
API_HASH = os.getenv("TG_API_HASH") or os.environ.get("TG_API_HASH")
TELETHON_SESSION = os.getenv("TG_SESSION") or os.environ.get("TG_SESSION")

API_ID = 0
if API_ID_STR:
    try:
        API_ID = int(API_ID_STR)
    except ValueError:
        print(f"❌ LỖI: API_ID '{API_ID_STR}' không hợp lệ")

GROUP_SOURCES = {
    -1003037580357: "Hẻm Gaming",
    -1003157457932: "Tổ Đội Gaming",
    -1002903068231: "Check VAR Banh Bóng",
    -1002445361342: "Kèo là phải thơm",
    -1003159720348: "Lăn bóng cùng Mie",
    -1002268148846: "Quay Đầu Là Bờ - Bỏ Cờ Bạc"
}

tele_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global tele_client
    print("🚀 Ứng dụng đang khởi động...")
    
    if not API_ID or not API_HASH or not TELETHON_SESSION:
        print("❌ LỖI NGHIÊM TRỌNG: Thiếu biến môi trường (TG_API_ID, TG_API_HASH, TG_SESSION).")
        print("Server vẫn chạy để trả về lỗi, nhưng Telegram sẽ không hoạt động.")
        yield
        return

    try:
        tele_client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH)
        print("⏳ Đang kết nối Telegram...")
        await tele_client.connect()
        
        if not await tele_client.is_user_authorized():
            print("⚠️ LỖI: Session String hết hạn hoặc không hợp lệ!")
        else:
            me = await tele_client.get_me()
            print(f"✅ Đã kết nối Telegram thành công! (User: {me.first_name})")
    except Exception as e:
        print(f"❌ LỖI kết nối Telegram: {e}")

    yield

    print("🛑 Ứng dụng đang tắt...")
    if tele_client and tele_client.is_connected():
        await tele_client.disconnect()

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== UTILS ======
def parse_vn_date(s: str) -> datetime.datetime:
    try:
        d = datetime.datetime.strptime(s, "%d/%m/%Y")
    except ValueError:
        # Fallback cho định dạng khác nếu cần
        d = datetime.datetime.strptime(s, "%Y-%m-%d")
        
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
    raw = str(raw).strip()
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
    if not user: return "Unknown User"
    uname = getattr(user, "username", None)
    if uname: return f"@{uname}"
    first = getattr(user, "first_name", "") or ""
    last = getattr(user, "last_name", "") or ""
    full = (first + " " + last).strip()
    return full or f"id:{getattr(user, 'id', 'unknown')}"

# ====== ROUTES ======
@app.get("/")
def read_root(): return {"message": "API is Running!"}

@app.get("/api/groups")
def get_groups_list(): return GROUP_SOURCES

@app.get("/api/rankmem")
async def api_rankmem(target: str, start_date: str, end_date: str):
    if not tele_client or not tele_client.is_connected():
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")
    try:
        start_utc, _ = parse_vn_date(start_date)
        _, end_utc = parse_vn_date(end_date)
        entity = await resolve_chat_entity(target)
        
        counter = Counter()
        scanned = 0
        async for msg in tele_client.iter_messages(entity, limit=10000, offset_date=end_utc):
            scanned += 1
            if not msg.date: continue
            if msg.date.astimezone(timezone.utc) < start_utc: break
            if not msg.action and msg.sender_id: counter[msg.sender_id] += 1
            
        results = []
        for i, (uid, cnt) in enumerate(counter.most_common(10), 1):
            try:
                u = await tele_client.get_entity(uid)
                name = await human_name_for_user(u)
            except: name = f"id:{uid}"
            results.append({"rank": i, "name": name, "messages": cnt})
            
        return {"scanned": scanned, "top": results, "group_title": getattr(entity, "title", str(target))}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/checkgroup")
async def api_checkgroup(target: str, start_date: str, end_date: str):
    return {"message": "Deprecated. Use checkgroup_hidden"}

@app.get("/api/checkgroup_hidden")
async def api_checkgroup_hidden(target: str, start_date: str, end_date: str):
    if not tele_client or not tele_client.is_connected():
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")

    try:
        start_utc, _ = parse_vn_date(start_date)
        _, end_utc = parse_vn_date(end_date)
        entity = await resolve_chat_entity(target)
        
        join_names, leave_names = [], []
        scanned_events = 0
        
        async for event in tele_client.iter_admin_log(entity, limit=None):
            if not event.date: continue
            event_dt = event.date.astimezone(timezone.utc)
            if event_dt > end_utc: continue
            if event_dt < start_utc: break 

            scanned_events += 1
            action = event.action
            # Kỹ thuật string matching an toàn cho mọi version
            action_str = str(action) # Chuyển action thành chuỗi để kiểm tra
            
            is_join = 'ParticipantJoin' in action_str
            is_leave = 'ParticipantLeave' in action_str or 'ChatDeleteUser' in action_str

            if is_join or is_leave:
                # Dùng getattr để tránh lỗi AttributeError nếu 'target' không tồn tại
                target_user = getattr(event, 'target', None)
                user_obj = getattr(event, 'user', None)
                
                user_peer = target_user if target_user else user_obj
                
                if user_peer:
                    try:
                        # Luôn lấy full info
                        u_entity = await tele_client.get_entity(user_peer)
                        name = await human_name_for_user(u_entity)
                    except: 
                        name = f"id:{getattr(user_peer, 'id', 'unknown')}"
                    
                    if is_join: join_names.append(name)
                    if is_leave: leave_names.append(name)

        return {
            "group_title": getattr(entity, "title", str(target)) + " (Admin Log)",
            "scanned": scanned_events,
            "joins": len(join_names),
            "leaves": len(leave_names),
            "joins_list": join_names,
            "leaves_list": leave_names
        }
        
    except Exception as e:
        if "ChatAdminLogInvalidError" in str(e):
             raise HTTPException(status_code=403, detail="Cần quyền ADMIN để xem log!")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/dashboard")
async def api_dashboard(target: str, start_date: str, end_date: str):
    if not tele_client or not tele_client.is_connected():
        raise HTTPException(status_code=503, detail="Telegram chưa kết nối")
    try:
        start_utc, _ = parse_vn_date(start_date)
        _, end_utc = parse_vn_date(end_date)
        entity = await resolve_chat_entity(target)
        
        total_posts = 0
        active_users = Counter()
        hourly_density = Counter()
        
        class GMT7(datetime.tzinfo):
            def utcoffset(self, dt): return timedelta(hours=7)
        gmt7 = GMT7()

        async for msg in tele_client.iter_messages(entity, limit=50000, offset_date=end_utc):
            if not msg.date: continue
            if msg.date.astimezone(timezone.utc) < start_utc: break 
            if msg.action: continue

            total_posts += 1
            if msg.sender_id: active_users[msg.sender_id] += 1
            hourly_density[msg.date.astimezone(gmt7).hour] += 1
            
        total_members = 0
        try:
            total_members = (await tele_client.get_participants(entity, limit=0)).total
        except: pass

        return {
            "group_title": getattr(entity, "title", str(target)),
            "total_members": total_members,
            "total_posts": total_posts,
            "total_active_users": len(active_users),
            "hourly_data": dict(hourly_density.most_common()),
            "scanned": total_posts
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
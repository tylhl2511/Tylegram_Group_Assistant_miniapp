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
from contextlib import asynccontextmanager

# ====== CẤU HÌNH (SỬA LẠI KIỂM TRA LỖI) ======
API_ID_STR = os.environ.get("TG_API_ID")
API_HASH = os.environ.get("TG_API_HASH")
TELETHON_SESSION = os.environ.get("TG_SESSION")

# Kiểm tra xem các biến môi trường đã được set hay chưa
if not API_ID_STR or not API_HASH or not TELETHON_SESSION:
    raise ValueError("LỖI KHỞI ĐỘNG: Vui lòng set các biến môi trường TG_API_ID, TG_API_HASH, và TG_SESSION trên Render.com")
else:
    try:
        API_ID = int(API_ID_STR)
    except ValueError:
        raise ValueError(f"LỖI KHỞI ĐỘNG: TG_API_ID '{API_ID_STR}' không phải là một con số.")

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
    print("Ứng dụng đang khởi động...")
    tele_client = TelegramClient(StringSession(TELETHON_SESSION), API_ID, API_HASH)
    print("Đang kết nối đến Telegram...")
    
    try:
        await tele_client.connect()
        if not await tele_client.is_user_authorized():
            print("⚠️  LỖI: Session không hợp lệ hoặc đã hết hạn!")
            print("Vui lòng tạo session string mới và update TG_SESSION environment variable.")
        else:
            print("✅ Đã kết nối Telegram thành công!")
    except Exception as e:
        print(f"❌ LỖI không thể kết nối Telegram: {e}")
        print(f"Kiểm tra các biến môi trường: TG_API_ID, TG_API_HASH, TG_SESSION")

    yield

    print("Ứng dụng đang tắt...")
    if tele_client and tele_client.is_connected():
        await tele_client.disconnect()
    print("Đã ngắt kết nối Telegram.")

app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ====== CÁC HÀM UTILS ======
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

# ====== 1. HÀM QUÉT TIN NHẮN (CŨ - Dành cho group thường) ======
async def get_rankmem_data(target, date_str_start, date_str_end):
    try:
        start_utc, _ = parse_vn_date(date_str_start)
        _, end_utc = parse_vn_date(date_str_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ngày không hợp lệ.")
    
    if not tele_client or not tele_client.is_connected():
        raise HTTPException(status_code=503, detail="Lỗi: Telegram client chưa sẵn sàng.")

    try:
        entity = await resolve_chat_entity(target)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy nhóm: {e}")
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
        raise HTTPException(status_code=500, detail=f"Lỗi quét tin: {e}")
    
    results = []
    for i, (uid, cnt) in enumerate(counter.most_common(10), start=1):
        try:
            user = await tele_client.get_entity(uid)
            name = await human_name_for_user(user)
        except:
            name = f"id:{uid}"
        results.append({"rank": i, "name": name, "messages": cnt})
    return {"scanned": scanned, "top": results, "group_title": getattr(entity, "title", str(target))}

async def get_checkgroup_data(target, date_str_start, date_str_end):
    try:
        start_utc, _ = parse_vn_date(date_str_start)
        _, end_utc = parse_vn_date(date_str_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ngày không hợp lệ.")
    
    if not tele_client or not tele_client.is_connected():
        raise HTTPException(status_code=503, detail="Lỗi: Telegram client chưa sẵn sàng.")

    try:
        entity = await resolve_chat_entity(target)
    except Exception:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhóm.")

    joins, leaves = [], []
    scanned = 0
    LIMIT = 50000

    try:
        async for msg in tele_client.iter_messages(entity, limit=LIMIT, offset_date=end_utc):
            scanned += 1
            if not msg.date: continue
            msg_dt = msg.date.astimezone(timezone.utc)
            if msg_dt < start_utc: break
            if hasattr(msg, "action") and msg.action is not None:
                action = msg.action
                if hasattr(action, "users"):
                    if "ChatAddUser" in action.__class__.__name__: joins.extend(action.users)
                    elif "ChatJoinedByLink" in action.__class__.__name__: joins.extend(action.users)
                elif "ChatDeleteUser" in action.__class__.__name__:
                    leaves.append(getattr(action, "user_id", None))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi quét: {e}")

    join_names = []
    for uid in set(joins):
        try:
            u = await tele_client.get_entity(uid)
            join_names.append(await human_name_for_user(u))
        except: join_names.append(f"id:{uid}")

    leave_names = []
    for uid in set(leaves):
        try:
            u = await tele_client.get_entity(uid)
            leave_names.append(await human_name_for_user(u))
        except: leave_names.append(f"id:{uid}")

    return {
        "scanned": scanned,
        "joins": len(join_names),
        "leaves": len(leave_names),
        "joins_list": join_names,
        "leaves_list": leave_names, 
        "group_title": getattr(entity, "title", str(target))
    }

# ====== 2. HÀM QUÉT GROUP ẨN (SỬA LỖI LẤY TÊN) ======
async def get_hidden_group_data(target, date_str_start, date_str_end):
    try:
        start_utc, _ = parse_vn_date(date_str_start)
        _, end_utc = parse_vn_date(date_str_end)
    except ValueError:
        raise HTTPException(status_code=400, detail="Ngày không hợp lệ.")

    if not tele_client or not tele_client.is_connected():
        raise HTTPException(status_code=503, detail="Lỗi: Telegram client chưa sẵn sàng.")

    try:
        entity = await resolve_chat_entity(target)
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy nhóm: {e}")

    join_names, leave_names = [], []
    scanned_events = 0
    
    try:
        async for event in tele_client.iter_admin_log(entity, limit=None):
            if not event.date: continue
            event_dt = event.date.astimezone(timezone.utc)
            
            if event_dt > end_utc: continue
            if event_dt < start_utc: break 

            scanned_events += 1
            
            action = event.action
            user_affected_peer = None

            # === SỬA LOGIC LỌC: Dùng string matching để tương thích với các version Telethon ===
            action_class_name = action.__class__.__name__
            
            # Trường hợp: User bị kick hoặc tự leave
            if 'Leave' in action_class_name or 'ChatDeleteUser' in action_class_name:
                if hasattr(event, 'target') and event.target: user_affected_peer = event.target
                else: user_affected_peer = event.user
                    
                if user_affected_peer:
                    try:
                        user_entity = await tele_client.get_entity(user_affected_peer)
                        name = await human_name_for_user(user_entity) 
                        leave_names.append(name)
                    except Exception:
                        uid = getattr(user_affected_peer, 'id', 'unknown')
                        leave_names.append(f"id:{uid}")
            
            # Trường hợp: User join (cả tự join bằng link hoặc được thêm)
            elif 'Join' in action_class_name or 'Participant' in action_class_name:
                if hasattr(event, 'target') and event.target: user_affected_peer = event.target
                else: user_affected_peer = event.user
                    
                if user_affected_peer:
                    try:
                        user_entity = await tele_client.get_entity(user_affected_peer)
                        name = await human_name_for_user(user_entity) 
                        join_names.append(name)
                    except Exception:
                        uid = getattr(user_affected_peer, 'id', 'unknown')
                        join_names.append(f"id:{uid}")
                 
    except Exception as e:
        if "ChatAdminLogInvalidError" in str(e):
             raise HTTPException(status_code=403, detail=f"Lỗi: Bạn cần quyền ADMIN để quét Log!")
        raise HTTPException(status_code=500, detail=f"Lỗi: {str(e)}")

    return {
        "group_title": getattr(entity, "title", str(target)) + " (Admin Log)",
        "scanned": scanned_events,
        "joins": len(join_names),
        "leaves": len(leave_names),
        "joins_list": join_names,
        "leaves_list": leave_names
    }

# ====== 3. DASHBOARD (Giữ nguyên) ======
async def get_dashboard_data(target, date_str_start, date_str_end):
    try:
        start_utc, _ = parse_vn_date(date_str_start)
        _, end_utc = parse_vn_date(date_str_end)
        class GMT7(datetime.tzinfo):
            def utcoffset(self, dt): return timedelta(hours=7)
            def tzname(self, dt): return "GMT+7"
            def dst(self, dt): return timedelta(0)
        gmt7 = GMT7()
    except ValueError:
        raise HTTPException(status_code=400, detail="Ngày lỗi.")

    if not tele_client or not tele_client.is_connected():
        raise HTTPException(status_code=503, detail="Lỗi: Telegram client chưa sẵn sàng.")

    try:
        entity = await resolve_chat_entity(target)
    except:
        raise HTTPException(status_code=404, detail="Không tìm thấy nhóm.")

    total_posts = 0
    active_users = Counter()
    hourly_density = Counter()
    scanned = 0
    LIMIT = 50000

    try:
        async for msg in tele_client.iter_messages(entity, limit=LIMIT, offset_date=end_utc):
            scanned += 1
            if not msg.date: continue
            msg_dt_utc = msg.date.astimezone(timezone.utc)
            if msg_dt_utc < start_utc: break 
            if hasattr(msg, "action") and msg.action is not None: continue

            total_posts += 1
            uid = getattr(msg, "sender_id", None)
            if uid: active_users[uid] += 1
            msg_hour_vn = msg.date.astimezone(gmt7).hour
            hourly_density[msg_hour_vn] += 1
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi: {e}")

    total_members = 0
    try:
        participants = await tele_client.get_participants(entity, limit=0)
        total_members = participants.total
    except: pass

    return {
        "group_title": getattr(entity, "title", str(target)),
        "total_members": total_members,
        "total_posts": total_posts,
        "total_active_users": len(active_users),
        "hourly_data": dict(hourly_density.most_common()),
        "scanned": scanned
    }

# ====== ROUTERS ======
@app.get("/")
def read_root(): return {"message": "API Running"}
@app.get("/api/groups")
def get_groups_list(): return GROUP_SOURCES
@app.get("/api/rankmem")
async def api_rankmem(target: str, start_date: str, end_date: str):
    return await get_rankmem_data(target, start_date, end_date)
@app.get("/api/checkgroup")
async def api_checkgroup(target: str, start_date: str, end_date: str):
    return await get_checkgroup_data(target, start_date, end_date)
@app.get("/api/dashboard")
async def api_dashboard(target: str, start_date: str, end_date: str):
    return await get_dashboard_data(target, start_date, end_date)
@app.get("/api/checkgroup_hidden")
async def api_checkgroup_hidden(target: str, start_date: str, end_date: str):
    return await get_hidden_group_data(target, start_date, end_date)

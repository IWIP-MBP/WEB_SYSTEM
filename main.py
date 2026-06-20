# ============================================
# 后勤三部人事管理系统 - 后端（最终修正版）
# 修复：劳保报表去重、身份证清洗、车间-班组-国籍矩阵
# ============================================
from fastapi import FastAPI, HTTPException, Depends, Request, UploadFile, File, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy import create_engine, text, MetaData, Table, Column, Integer, String, select, insert, update, delete, or_, desc, func, UniqueConstraint
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime, timedelta, date
from pydantic import BaseModel
from typing import Optional
import os, io, shutil, logging, json, subprocess, re
import pandas as pd
from urllib.parse import urlparse

import bcrypt
from jose import jwt
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# ---------- 配置 ----------
class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://admin:iwip123@db:5432/hr_system")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    SECRET_KEY = os.getenv("SECRET_KEY", "iwip-secret-key-change-in-production")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS = 24
    UPLOAD_DIR = "uploads"
    EXPORT_DIR = os.path.join(UPLOAD_DIR, "exports")
    LOGO_DIR = os.path.join(UPLOAD_DIR, "logos")

settings = Settings()

os.makedirs(settings.EXPORT_DIR, exist_ok=True)
os.makedirs(settings.LOGO_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def run_postgres_command(command, db_info, stdout_path=None):
    env = os.environ.copy()
    if db_info.get("password"):
        env["PGPASSWORD"] = db_info["password"]
    args = [
        command,
        "-h", db_info["host"],
        "-p", str(db_info["port"]),
        "-U", db_info["user"],
        "-d", db_info["dbname"],
    ]
    stdout_handle = open(stdout_path, "wb") if stdout_path else subprocess.PIPE
    try:
        return subprocess.run(
            args,
            stdout=stdout_handle,
            stderr=subprocess.PIPE,
            text=False,
            check=True,
            env=env,
        )
    finally:
        if stdout_path:
            stdout_handle.close()

def command_error_message(exc):
    stderr = exc.stderr.decode("utf-8", errors="replace") if exc.stderr else str(exc)
    return stderr.strip() or str(exc)

# ---------- 数据库 ----------
engine = create_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
metadata = MetaData()

# 员工表
employees = Table("employees", metadata,
    Column("id", Integer, primary_key=True),
    Column("ws_bengkel", String, index=True),
    Column("id_nomor", String, unique=True, nullable=False, index=True),
    Column("name_nama", String, nullable=False, index=True),
    Column("team_grup", String),
    Column("gender_jk", String),
    Column("pos_cn_jabatan", String),
    Column("pos_id_jabatan", String),
    Column("nat_negara", String),
    Column("rel_agama", String),
    Column("status_status", String, default="在职 / Aktif"),
    Column("resign_date", String),
    Column("remark_ket", String),
    Column("created_at", String),
    Column("updated_at", String),
    Column("birth_date", String),
    Column("id_card", String),
    Column("hire_date", String),
    Column("contract_end", String),
    Column("custom_fields", String, default="{}"),
    Column("company", String),
)

# 配置表
config_meta = Table("config_meta", metadata,
    Column("id", Integer, primary_key=True),
    Column("meta_type", String),
    Column("meta_value", String)
)

# 审计日志
log_audit = Table("log_audit", metadata,
    Column("id", Integer, primary_key=True),
    Column("op_date", String),
    Column("id_nomor", String),
    Column("name_nama", String),
    Column("type_tipe", String),
    Column("old_payload", String),
    Column("new_payload", String),
    Column("reason_alasan", String),
    Column("operator", String),
    Column("ip_address", String)
)

# 用户表
users = Table("users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String, unique=True, nullable=False),
    Column("hashed_password", String, nullable=False),
    Column("role", String, default="viewer"),
    Column("ws_scope", String, nullable=True)
)

# 在线会话
active_sessions = Table("active_sessions", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String),
    Column("ip_address", String),
    Column("mac_address", String),
    Column("last_seen", String),
    UniqueConstraint("username", "ip_address", name="uq_username_ip")
)

# 劳保用品
labor_items = Table("labor_items", metadata,
    Column("id", Integer, primary_key=True),
    Column("item_name", String, nullable=False),
    Column("item_spec", String),
    Column("unit", String),
    Column("default_cycle_days", Integer, default=90),
    Column("safety_stock", Integer, default=0),
)

labor_inventory = Table("labor_inventory", metadata,
    Column("id", Integer, primary_key=True),
    Column("item_id", Integer, nullable=False),
    Column("change_type", String),
    Column("quantity", Integer),
    Column("change_date", String),
    Column("remark", String)
)

labor_assignments = Table("labor_assignments", metadata,
    Column("id", Integer, primary_key=True),
    Column("id_nomor", String, nullable=False, index=True),
    Column("item_id", Integer, nullable=False),
    Column("last_issue_date", String),
    Column("cycle_days", Integer),
    Column("next_issue_date", String),
    Column("status", String, default="有效"),
    Column("quantity", Integer, default=0),  # 新增
)

employee_transfers = Table("employee_transfers", metadata,
    Column("id", Integer, primary_key=True),
    Column("transfer_date", String),
    Column("id_nomor", String),
    Column("name", String),
    Column("change_type", String),
    Column("old_value", String),
    Column("new_value", String),
    Column("operator", String)
)

# 创建表
metadata.create_all(bind=engine)
# 在 metadata.create_all(bind=engine) 之后添加
with engine.begin() as conn:
    try:
        conn.execute(text("ALTER TABLE active_sessions DROP CONSTRAINT IF EXISTS active_sessions_username_key"))
        conn.execute(text("ALTER TABLE active_sessions DROP CONSTRAINT IF EXISTS uq_username_ip"))
        conn.execute(text("DROP INDEX IF EXISTS active_sessions_username_key"))
        conn.execute(text("ALTER TABLE active_sessions ADD CONSTRAINT uq_username_ip UNIQUE (username, ip_address)"))
        logger.info("Migrated active_sessions to composite unique constraint")
    except Exception as e:
        logger.warning(f"Error migrating active_sessions constraint: {e}")

with engine.begin() as conn:
    try:
        existing_cols = [row[0] for row in conn.execute(text(
            "SELECT column_name FROM information_schema.columns WHERE table_name='active_sessions'"
        )).fetchall()]
        if 'mac_address' not in existing_cols:
            conn.execute(text("ALTER TABLE active_sessions ADD COLUMN mac_address VARCHAR"))
            logger.info("Added mac_address column to active_sessions")
    except Exception as e:
        logger.warning(f"Error adding mac_address column to active_sessions: {e}")

with engine.connect() as conn:
    # 检查列是否存在
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='labor_assignments' AND column_name='quantity'
    """)).fetchone()
    if not result:
        # 添加 quantity 列，默认为 1
        conn.execute(text("ALTER TABLE labor_assignments ADD COLUMN quantity INTEGER DEFAULT 1"))
        logger.info("Added quantity column to labor_assignments")
# 自动补列
with engine.begin() as conn:
    existing = [row[0] for row in conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='employees'"
    )).fetchall()]
    for col, col_type in [
        ('created_at', 'VARCHAR'),
        ('updated_at', 'VARCHAR'),
        ('birth_date', 'VARCHAR'),
        ('id_card', 'VARCHAR'),
        ('hire_date', 'VARCHAR'),
        ('contract_end', 'VARCHAR'),
        ('custom_fields', 'VARCHAR'),
        ('company', 'VARCHAR'),
    ]:
        if col not in existing:
            conn.execute(text(f"ALTER TABLE employees ADD COLUMN {col} {col_type}"))

with engine.begin() as conn:
    existing_users = [row[0] for row in conn.execute(text(
        "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
    )).fetchall()]
    if 'role' not in existing_users:
        conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'viewer'"))
    if 'ws_scope' not in existing_users:
        conn.execute(text("ALTER TABLE users ADD COLUMN ws_scope VARCHAR"))

with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS employee_transfers (
            id SERIAL PRIMARY KEY,
            transfer_date VARCHAR,
            id_nomor VARCHAR,
            name VARCHAR,
            change_type VARCHAR,
            old_value VARCHAR,
            new_value VARCHAR,
            operator VARCHAR
        )
    """))
# 迁移：为 labor_assignments 添加 quantity 列并回填数据
with engine.connect() as conn:
    # 检查列是否存在
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='labor_assignments' AND column_name='quantity'
    """)).fetchone()
    if not result:
        conn.execute(text("ALTER TABLE labor_assignments ADD COLUMN quantity INTEGER DEFAULT 0"))
        # 从 labor_inventory 中汇总每个发放记录的数量（假设 change_date = last_issue_date）
        conn.execute(text("""
            UPDATE labor_assignments la
            SET quantity = (
                SELECT COALESCE(SUM(li.quantity), 1)
                FROM labor_inventory li
                WHERE li.item_id = la.item_id 
                  AND li.change_type = 'out'
                  AND li.change_date = la.last_issue_date
                  AND li.remark LIKE '%发放给 %' || la.id_nomor || '%'
            )
            WHERE la.quantity = 0
        """))
        # 对于无法匹配的历史记录，默认设置为 1
        conn.execute(text("UPDATE labor_assignments SET quantity = 1 WHERE quantity = 0"))
        conn.commit()
        logger.info("Added quantity column to labor_assignments and backfilled data")
# ---------- 身份证清洗 ----------
def clean_id_card(id_card):
    if not id_card:
        return None
    id_str = str(id_card).strip().strip("'\"")
    # 移除非数字和非X字符
    id_str = re.sub(r"[^0-9X]", "", id_str.upper())
    return id_str if id_str else None

def extract_birth_date_from_id_card(id_card, nationality=None):
    """
    从身份证号提取出生日期，仅根据长度判断：
    - 18位：中国身份证规则（前17位数字，末尾数字或X），取第7-14位 YYYYMMDD
    - 16位：印尼身份证规则（纯数字），出生日期在第7-12位 DDMMYY，动态推断世纪
    - 第二个参数 nationality 被忽略，仅保留用于兼容旧调用
    """
    if not id_card:
        return None
    id_str = clean_id_card(id_card)
    if not id_str:
        return None

    # 中国身份证：18位，前17位数字，最后一位数字或X
    if len(id_str) == 18 and id_str[:17].isdigit():
        try:
            birth_str = id_str[6:14]  # YYYYMMDD
            year = int(birth_str[0:4])
            month = int(birth_str[4:6])
            day = int(birth_str[6:8])
            if 1900 <= year <= datetime.now().year and 1 <= month <= 12 and 1 <= day <= 31:
                return datetime.strptime(birth_str, "%Y%m%d").date().strftime("%Y-%m-%d")
        except:
            pass
        return None

    # 印尼身份证：16位纯数字，出生日期在第7-12位（DDMMYY）
    if len(id_str) == 16 and id_str.isdigit():
        try:
            dd = int(id_str[6:8])
            mm = int(id_str[8:10])
            yy = int(id_str[10:12])
            if not (1 <= mm <= 12 and 1 <= dd <= 31):
                return None
            current_year = datetime.now().year
            century_base = (current_year // 100) * 100
            year = century_base + yy
            if year > current_year:
                year -= 100
            if year < 1900 or year > current_year:
                year = 1900 + yy
            return date(year, mm, dd).strftime("%Y-%m-%d")
        except:
            pass
        return None

    return None

# ---------- 初始化 admin ----------
def init_admin():
    with SessionLocal() as db:
        user = db.execute(select(users).where(users.c.username == "admin")).first()
        if not user:
            hashed = bcrypt.hashpw(b"iwip123", bcrypt.gensalt()).decode('utf-8')
            db.execute(insert(users).values(username="admin", hashed_password=hashed, role="admin"))
            db.commit()
init_admin()

limiter = Limiter(key_func=get_remote_address)
app = FastAPI(title="后勤三部人事管理系统")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(CORSMiddleware, allow_origins=settings.CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

def is_real_ip(ip: str) -> bool:
    if not ip:
        return False
    ip = ip.strip()
    if ip in ("127.0.0.1", "::1", "localhost", "unknown", "UNKNOWN", ""):
        return False
    if ip.startswith("172.16.") or ip.startswith("172.17.") or ip.startswith("172.18.") or ip.startswith("172.19.") or \
       ip.startswith("172.20.") or ip.startswith("172.21.") or ip.startswith("172.22.") or ip.startswith("172.23.") or \
       ip.startswith("172.24.") or ip.startswith("172.25.") or ip.startswith("172.26.") or ip.startswith("172.27.") or \
       ip.startswith("172.28.") or ip.startswith("172.29.") or ip.startswith("172.30.") or ip.startswith("172.31."):
        return False
    if ip.startswith("169.254."):
        return False
    return True

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, user_key: str):
        await websocket.accept()
        if user_key not in self.active_connections:
            self.active_connections[user_key] = []
        self.active_connections[user_key].append(websocket)

    def disconnect(self, websocket: WebSocket, user_key: str) -> bool:
        if user_key in self.active_connections:
            if websocket in self.active_connections[user_key]:
                self.active_connections[user_key].remove(websocket)
            if not self.active_connections[user_key]:
                del self.active_connections[user_key]
                return True
        return False

    async def broadcast(self, message: dict):
        for connections in list(self.active_connections.values()):
            for ws in list(connections):
                try:
                    await ws.send_json(message)
                except Exception:
                    pass

manager = ConnectionManager()

async def broadcast_online_users():
    with SessionLocal() as db:
        clean_sessions(db, 60)
        rows = db.execute(select(active_sessions.c.username, active_sessions.c.ip_address)).fetchall()
        users_list = []
        for r in rows:
            ip = r[1]
            display_ip = ip if is_real_ip(ip) else ""
            users_list.append({"user": r[0], "ip": display_ip})
    
    await manager.broadcast({"type": "online_users", "data": users_list})

@app.websocket("/ws/sessions")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    if not token:
        await websocket.close(code=1008)
        return
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=1008)
        return
    
    username = payload.get("sub")
    
    forwarded = websocket.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        real_ip = websocket.headers.get("X-Real-IP")
        if real_ip:
            client_ip = real_ip
        else:
            client_ip = websocket.client.host if websocket.client else "unknown"

    user_key = f"{username}@{client_ip}"
    await manager.connect(websocket, user_key)
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with SessionLocal() as db:
        db.execute(text("""
            INSERT INTO active_sessions (username, ip_address, mac_address, last_seen)
            VALUES (:u, :ip, :mac, :now)
            ON CONFLICT (username, ip_address) DO UPDATE
            SET last_seen = :now
        """), {"u": username, "ip": client_ip, "mac": "WS_CONN", "now": now})
        db.commit()
    
    await broadcast_online_users()
    
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        is_last = manager.disconnect(websocket, user_key)
        if is_last:
            with SessionLocal() as db:
                db.execute(text("""
                    DELETE FROM active_sessions 
                    WHERE username = :u AND ip_address = :ip
                """), {"u": username, "ip": client_ip})
                db.commit()
            await broadcast_online_users()
    except Exception as e:
        logger.warning(f"WebSocket error for {user_key}: {e}")
        is_last = manager.disconnect(websocket, user_key)
        if is_last:
            with SessionLocal() as db:
                db.execute(text("""
                    DELETE FROM active_sessions 
                    WHERE username = :u AND ip_address = :ip
                """), {"u": username, "ip": client_ip})
                db.commit()
            await broadcast_online_users()

@app.get("/api/health")
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(503, "Database unavailable")

# ---------- 工具函数 ----------
def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    data.update({"exp": expire})
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def verify_token(token: str):
    try: return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except: return None

def get_current_user(request: Request, db=Depends(get_db)):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "): raise HTTPException(401, detail="Missing token")
    payload = verify_token(auth.split(" ")[1])
    if not payload: raise HTTPException(401, detail="Invalid token")
    user = db.execute(select(users).where(users.c.username == payload.get("sub"))).first()
    if not user: raise HTTPException(401, detail="User not found")
    return dict(user._mapping)

def get_employee(db, id_nomor):
    res = db.execute(select(employees).where(employees.c.id_nomor == id_nomor)).first()
    return dict(res._mapping) if res else None

def write_audit(db, id_nomor, name, op_type, old="{}", new="{}", reason="", operator="", ip=""):
    db.execute(insert(log_audit).values(
        op_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        id_nomor=id_nomor, name_nama=name, type_tipe=op_type,
        old_payload=old, new_payload=new, reason_alasan=reason,
        operator=operator, ip_address=ip))
    db.commit()

def get_mac_address_from_arp(ip):
    if not ip or ip in ("127.0.0.1", "localhost", "::1"):
        return "Local Loopback"
    try:
        if os.path.exists("/proc/net/arp"):
            with open("/proc/net/arp", "r") as f:
                lines = f.readlines()
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 4 and parts[0] == ip:
                        mac = parts[3]
                        if mac and mac != "00:00:00:00:00:00":
                            return mac.upper()
        if re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", ip):
            cmd = ["arp", "-a", ip]
            out = subprocess.check_output(cmd, text=True, timeout=2)
            match = re.search(r"([0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}", out)
            if match:
                return match.group(0).replace("-", ":").upper()
    except Exception as e:
        logger.warning(f"Failed to get MAC from ARP for {ip}: {e}")
    return None

def clean_sessions(db, max_age_seconds=60):
    threshold = (datetime.now() - timedelta(seconds=max_age_seconds)).strftime("%Y-%m-%d %H:%M:%S")
    db.execute(delete(active_sessions).where(active_sessions.c.last_seen < threshold))
    db.commit()

def parse_db_url():
    url = urlparse(settings.DATABASE_URL)
    return {"host": url.hostname, "port": url.port or 5432, "user": url.username, "password": url.password, "dbname": url.path.lstrip('/')}

def add_meta_if_not_exists(db, meta_type, value):
    if not value or value.strip() == "":
        return
    exists = db.execute(select(config_meta).where(config_meta.c.meta_type == meta_type, config_meta.c.meta_value == value.strip())).first()
    if not exists:
        db.execute(insert(config_meta).values(meta_type=meta_type, meta_value=value.strip()))
        db.commit()

def record_transfer(db, id_nomor, name, change_type, old_value, new_value, operator):
    db.execute(insert(employee_transfers).values(
        transfer_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        id_nomor=id_nomor, name=name, change_type=change_type,
        old_value=old_value, new_value=new_value, operator=operator))
    db.commit()

def get_item_stock(db, item_id):
    in_qty = db.execute(select(func.sum(labor_inventory.c.quantity)).where(
        labor_inventory.c.item_id == item_id,
        labor_inventory.c.change_type == "in"
    )).scalar() or 0
    out_qty = db.execute(select(func.sum(labor_inventory.c.quantity)).where(
        labor_inventory.c.item_id == item_id,
        labor_inventory.c.change_type == "out"
    )).scalar() or 0
    return in_qty - out_qty

def load_org_layout(db):
    raw = db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == "org_layout")).scalar()
    if not raw:
        return {}
    try:
        saved = json.loads(raw)
    except Exception:
        logger.warning("Invalid org_layout JSON ignored")
        return {}
    if isinstance(saved, dict) and "nodes" in saved:
        saved = saved["nodes"]
    if not isinstance(saved, list):
        return {}
    result = {}
    for item in saved:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        result[item["key"]] = {
            "display_name": item.get("display_name") or item.get("name") or item["key"],
            "type": item.get("type") or "",
            "parent": item.get("parent") or "",
            "sort": int(item.get("sort") or 0),
        }
    return result

def build_org_chart(db, current_user=None):
    stmt = select(
        employees.c.ws_bengkel,
        employees.c.team_grup,
        employees.c.nat_negara,
        func.count().label("cnt")
    ).where(employees.c.status_status.contains("在职"))
    if current_user:
        ws_scope_str = current_user.get("ws_scope")
        if ws_scope_str:
            try:
                allowed = json.loads(ws_scope_str)
                if isinstance(allowed, list) and len(allowed) > 0:
                    stmt = stmt.where(employees.c.ws_bengkel.in_(allowed))
            except:
                pass
    rows = db.execute(stmt.group_by(employees.c.ws_bengkel, employees.c.team_grup, employees.c.nat_negara)).fetchall()

    nodes = {
        "root": {
            "key": "root", "name": "后勤三部", "display_name": "后勤三部",
            "type": "部门", "parent": "", "level": 0, "total": 0, "nations": {}, "sort": 0
        }
    }

    for row in rows:
        ws = (row.ws_bengkel or "未分配车间").strip() or "未分配车间"
        team = (row.team_grup or "未分配班组").strip() or "未分配班组"
        nat = (row.nat_negara or "未知").strip() or "未知"
        cnt = int(row.cnt or 0)
        ws_key = f"ws::{ws}"
        team_key = f"team::{ws}::{team}"

        if ws_key not in nodes:
            nodes[ws_key] = {
                "key": ws_key, "name": ws, "display_name": ws,
                "type": "车间", "parent": "root", "level": 1,
                "total": 0, "nations": {}, "sort": len(nodes)
            }
        if team_key not in nodes:
            nodes[team_key] = {
                "key": team_key, "name": team, "display_name": team,
                "type": "班组", "parent": ws_key, "level": 2,
                "total": 0, "nations": {}, "sort": len(nodes)
            }

        for key in ("root", ws_key, team_key):
            nodes[key]["total"] += cnt
            nodes[key]["nations"][nat] = nodes[key]["nations"].get(nat, 0) + cnt

    saved = load_org_layout(db)
    valid_keys = set(nodes.keys())
    for key, override in saved.items():
        if key not in nodes:
            continue
        parent = override.get("parent", nodes[key]["parent"])
        if key == "root":
            parent = ""
        elif parent not in valid_keys or parent == key:
            parent = nodes[key]["parent"]
        nodes[key]["display_name"] = override.get("display_name") or nodes[key]["display_name"]
        nodes[key]["type"] = override.get("type") or nodes[key]["type"]
        nodes[key]["parent"] = parent
        nodes[key]["sort"] = override.get("sort", nodes[key]["sort"])

    ordered = sorted(nodes.values(), key=lambda n: (n.get("level", 9), n.get("sort", 0), n["display_name"]))
    name_map = {n["key"]: n["display_name"] for n in ordered}
    for node in ordered:
        node["parent_name"] = name_map.get(node["parent"], "")

    edges = [{"from": n["parent"], "to": n["key"]} for n in ordered if n["parent"]]
    nations = sorted({nat for n in ordered for nat in n.get("nations", {})})
    return {"nodes": ordered, "edges": edges, "nations": nations}

def validate_org_nodes(nodes):
    if not isinstance(nodes, list) or not nodes:
        raise HTTPException(400, "组织架构数据不能为空")
    keys = [n.get("key") for n in nodes if isinstance(n, dict)]
    if len(keys) != len(set(keys)):
        raise HTTPException(400, "节点 ID 重复，请刷新后重试")
    key_set = set(keys)
    if "root" not in key_set:
        raise HTTPException(400, "缺少根节点 root")
    parent_map = {}
    for node in nodes:
        key = node.get("key")
        parent = node.get("parent") or ""
        if key == "root":
            parent = ""
        elif parent not in key_set:
            raise HTTPException(400, f"节点 {node.get('display_name') or key} 的父级无效")
        if parent == key:
            raise HTTPException(400, f"节点 {node.get('display_name') or key} 不能选择自己作为父级")
        parent_map[key] = parent

    for key in key_set:
        seen = set()
        cursor = key
        while parent_map.get(cursor):
            cursor = parent_map[cursor]
            if cursor in seen:
                raise HTTPException(400, "父级关系形成循环，请重新选择")
            seen.add(cursor)

# ---------- 元数据接口 ----------
@app.get("/api/meta/国籍")
def get_nationalities(db=Depends(get_db)):
    rows = db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == "国籍")).fetchall()
    if rows:
        return [r[0] for r in rows]
    rows = db.execute(select(employees.c.nat_negara).distinct()).fetchall()
    return [r[0] for r in rows if r[0] and r[0].strip()]

def add_nationality_if_not_exists(db, value):
    if not value or value.strip() == "":
        return
    exists = db.execute(select(config_meta).where(config_meta.c.meta_type == "国籍", config_meta.c.meta_value == value.strip())).first()
    if not exists:
        db.execute(insert(config_meta).values(meta_type="国籍", meta_value=value.strip()))
        db.commit()

@app.get("/api/meta/性别")
def get_genders(db=Depends(get_db)):
    rows = db.execute(select(employees.c.gender_jk).distinct()).fetchall()
    return [r[0] for r in rows if r[0] and r[0].strip()]

@app.get("/api/meta/宗教")
def get_religions(db=Depends(get_db)):
    rows = db.execute(select(employees.c.rel_agama).distinct()).fetchall()
    return [r[0] for r in rows if r[0] and r[0].strip()]

# ---------- 员工生日提醒 ----------
@app.get("/api/employees/birthday_reminders")
def get_birthday_reminders(days: int = 7, db=Depends(get_db), current_user=Depends(get_current_user)):
    today = date.today()
    reminders = []
    stmt = select(employees).where(employees.c.status_status.contains("在职"))
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                stmt = stmt.where(employees.c.ws_bengkel.in_(allowed))
            else:
                stmt = stmt.where(employees.c.ws_bengkel == "__NONE__")
        except:
            pass
    rows = db.execute(stmt).fetchall()
    for row in rows:
        emp = dict(row._mapping)
        bd_str = None
        if emp.get("id_card"):
            bd_str = extract_birth_date_from_id_card(emp["id_card"], emp.get("nat_negara", ""))
        if bd_str:
            try:
                bd = datetime.strptime(bd_str, "%Y-%m-%d").date()
                this_year_birthday = bd.replace(year=today.year)
                if this_year_birthday < today:
                    this_year_birthday = this_year_birthday.replace(year=today.year + 1)
                diff = (this_year_birthday - today).days
                if 0 <= diff <= days:
                    reminders.append({"id_nomor": emp["id_nomor"], "name": emp["name_nama"], "birth_date": bd_str, "days_left": diff})
            except:
                continue
    return reminders

# ---------- 通知历史 ----------
@app.get("/api/notifications/history")
def get_notification_history(days: int = 7, db=Depends(get_db), current_user=Depends(get_current_user)):
    result = []
    today = date.today()
    for i in range(days):
        target_date = today - timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")
        logs = db.execute(select(log_audit).where(log_audit.c.op_date.like(f"{date_str}%")).order_by(desc(log_audit.c.op_date)).limit(10)).fetchall()
        logs_detail = []
        for log in logs:
            logs_detail.append({
                "time": log.op_date,
                "type": log.type_tipe,
                "operator": log.operator,
                "id_nomor": log.id_nomor,
                "name": log.name_nama,
                "old": (log.old_payload[:50] + "...") if log.old_payload and len(log.old_payload) > 50 else log.old_payload,
                "new": (log.new_payload[:50] + "...") if log.new_payload and len(log.new_payload) > 50 else log.new_payload,
            })
        labor_reminders = db.execute(select(labor_assignments).where(labor_assignments.c.next_issue_date == date_str)).fetchall()
        labor_list = []
        for r in labor_reminders:
            emp = get_employee(db, r.id_nomor)
            item = db.execute(select(labor_items).where(labor_items.c.id == r.item_id)).first()
            labor_list.append({
                "id_nomor": r.id_nomor,
                "name": emp["name_nama"] if emp else "",
                "item": item.item_name if item else "",
                "next_issue_date": r.next_issue_date
            })
        birthday_list = []
        all_active = db.execute(select(employees).where(employees.c.status_status.contains("在职"))).fetchall()
        for emp in all_active:
            bd_str = None
            if emp.id_card:
                bd_str = extract_birth_date_from_id_card(emp.id_card, emp.nat_negara or "")
            if bd_str:
                try:
                    bd = datetime.strptime(bd_str, "%Y-%m-%d").date()
                    if bd.month == target_date.month and bd.day == target_date.day:
                        birthday_list.append({
                            "id_nomor": emp.id_nomor,
                            "name": emp.name_nama,
                            "birth_date": bd_str
                        })
                except:
                    pass
        result.append({
            "date": date_str,
            "log_count": len(logs),
            "logs_detail": logs_detail,
            "labor_reminders": labor_list,
            "birthday_reminders": birthday_list
        })
    return result
@app.get("/api/org_chart_data")
def get_org_chart_data(db=Depends(get_db), current_user=Depends(get_current_user)):
    """获取组织架构数据，人数始终来自在职员工实时统计。"""
    return build_org_chart(db, current_user)
@app.get("/api/org_chart_editable")
def get_org_chart_editable(db=Depends(get_db), current_user=Depends(get_current_user)):
    # 查询所有在职员工的车间、班组、国籍人数
    stmt = select(
        employees.c.ws_bengkel,
        employees.c.team_grup,
        employees.c.nat_negara,
        func.count().label("cnt")
    ).where(employees.c.status_status.contains("在职"))
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                stmt = stmt.where(employees.c.ws_bengkel.in_(allowed))
        except:
            pass
            
    rows = db.execute(stmt.group_by(employees.c.ws_bengkel, employees.c.team_grup, employees.c.nat_negara)).fetchall()
    
    # 构建节点列表：每个车间和班组为一个节点
    nodes = {}
    # 根节点
    nodes["后勤三部"] = {"id": "root", "parent": "", "name": "后勤三部", "type": "root", "total": 0}
    
    for row in rows:
        ws = row.ws_bengkel or "未分配车间"
        team = row.team_grup or "未分配班组"
        cnt = row.cnt
        # 确保车间节点存在
        if ws not in nodes:
            nodes[ws] = {"id": ws, "parent": "后勤三部", "name": ws, "type": "workshop", "total": 0}
        # 确保班组节点存在
        if team not in nodes:
            nodes[team] = {"id": team, "parent": ws, "name": team, "type": "team", "total": 0}
        nodes[ws]["total"] += cnt
        nodes[team]["total"] += cnt
    
    # 转换为列表格式供前端 data_editor 使用
    node_list = []
    for name, info in nodes.items():
        node_list.append({
            "ID": info["id"],
            "名称": info["name"],
            "类型": info["type"],
            "父级": info["parent"],
            "人数": info["total"]
        })
    return node_list
@app.get("/api/org_graph")
def get_org_graph(db=Depends(get_db), current_user=Depends(get_current_user)):
    """生成组织架构树形数据（经理 → 车间 → 班组），包含各国籍人数"""
    stmt = select(
        employees.c.ws_bengkel,
        employees.c.team_grup,
        employees.c.nat_negara,
        func.count().label("cnt")
    ).where(employees.c.status_status.contains("在职"))
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                stmt = stmt.where(employees.c.ws_bengkel.in_(allowed))
        except:
            pass
            
    rows = db.execute(stmt.group_by(employees.c.ws_bengkel, employees.c.team_grup, employees.c.nat_negara)).fetchall()
    
    # 构建树结构
    root = {"key": "root", "name": "经理", "type": "经理", "children": [], "total": 0, "nations": {}}
    # 用于存储车间节点
    workshops = {}
    
    for row in rows:
        ws = row.ws_bengkel or "未分配车间"
        team = row.team_grup or "未分配班组"
        nat = row.nat_negara or "未知"
        cnt = row.cnt
        
        if ws not in workshops:
            workshops[ws] = {"key": f"ws_{ws}", "name": ws, "type": "主任", "children": [], "total": 0, "nations": {}}
        ws_node = workshops[ws]
        ws_node["total"] += cnt
        ws_node["nations"][nat] = ws_node["nations"].get(nat, 0) + cnt
        
        # 找班组
        team_node = next((c for c in ws_node["children"] if c["name"] == team), None)
        if not team_node:
            team_node = {"key": f"team_{ws}_{team}", "name": team, "type": "班长", "children": [], "total": 0, "nations": {}}
            ws_node["children"].append(team_node)
        team_node["total"] += cnt
        team_node["nations"][nat] = team_node["nations"].get(nat, 0) + cnt
    
    # 将车间添加到根节点
    root["children"] = list(workshops.values())
    # 根节点总人数
    root["total"] = sum(w["total"] for w in workshops.values())
    # 根节点国籍汇总
    for w in workshops.values():
        for nat, cnt in w["nations"].items():
            root["nations"][nat] = root["nations"].get(nat, 0) + cnt
    
    # 获取所有国籍列表（用于下拉选择）
    all_nations = db.execute(select(employees.c.nat_negara).distinct()).fetchall()
    all_nations = [n[0] for n in all_nations if n[0]]
    
    return {"tree": root, "nations": all_nations}
@app.post("/org_chart/save_layout")
def save_org_layout(data: dict, db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can save layout")
    nodes = data.get("nodes", [])
    validate_org_nodes(nodes)
    payload = []
    for idx, node in enumerate(nodes):
        payload.append({
            "key": node.get("key"),
            "display_name": (node.get("display_name") or node.get("name") or node.get("key") or "").strip(),
            "type": (node.get("type") or "").strip(),
            "parent": node.get("parent") or "",
            "sort": int(node.get("sort") if node.get("sort") is not None else idx),
        })
    existing = db.execute(select(config_meta).where(config_meta.c.meta_type == "org_layout")).first()
    if existing:
        db.execute(update(config_meta).where(config_meta.c.id == existing.id).values(meta_value=json.dumps(payload, ensure_ascii=False)))
    else:
        db.execute(insert(config_meta).values(meta_type="org_layout", meta_value=json.dumps(payload, ensure_ascii=False)))
    db.commit()
    return {"status": "success"}

@app.post("/api/org_chart/reset_layout")
def reset_org_layout(db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can reset layout")
    db.execute(delete(config_meta).where(config_meta.c.meta_type == "org_layout"))
    db.commit()
    return {"status": "success"}

@app.get("/api/org_chart/quota")
def get_org_quota(db=Depends(get_db)):
    raw = db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == "org_quota")).scalar()
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except:
        return {}

@app.post("/api/org_chart/quota")
def save_org_quota(data: dict, db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can save quota")
    existing = db.execute(select(config_meta).where(config_meta.c.meta_type == "org_quota")).first()
    if existing:
        db.execute(update(config_meta).where(config_meta.c.id == existing.id).values(meta_value=json.dumps(data, ensure_ascii=False)))
    else:
        db.execute(insert(config_meta).values(meta_type="org_quota", meta_value=json.dumps(data, ensure_ascii=False)))
    db.commit()
    return {"status": "success"}
# ---------- 员工恢复 ----------
@app.post("/api/employees/restore")
def restore_employee(request: Request, db=Depends(get_db), current_user=Depends(get_current_user), id_nomor: str = ""):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can restore employees")
    emp = get_employee(db, id_nomor)
    if not emp: raise HTTPException(404, "Employee not found")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and emp.get("ws_bengkel") not in allowed:
                raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass
            
    if "在职" in emp["status_status"]:
        raise HTTPException(400, "Employee is already active")
    db.execute(update(employees).where(employees.c.id_nomor == id_nomor).values(
        status_status="在职 / Aktif", resign_date=None, remark_ket=None))
    db.commit()
    write_audit(db, id_nomor, emp["name_nama"], "恢复在职",
                old=json.dumps({"status": emp["status_status"], "resign_date": emp["resign_date"], "reason": emp["remark_ket"]}),
                new=json.dumps({"status": "在职"}), operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

# ---------- 认证 ----------
@app.post("/api/auth/login")
@limiter.limit("10/minute")
def login(username: str, password: str, request: Request, db=Depends(get_db)):
    user = db.execute(select(users).where(users.c.username == username)).first()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.hashed_password.encode('utf-8')):
        raise HTTPException(401, detail="用户名或密码错误")
    token = create_token({"sub": username, "role": user.role})
    write_audit(db, "", "", "登录", old="{}", new=json.dumps({"username": username, "role": user.role}), reason="用户登录成功", operator=username, ip=request.client.host)
    return {"access_token": token, "token_type": "bearer", "username": username, "role": user.role, "ws_scope": user.ws_scope}


# ---------- 员工花名册 ----------
@app.get("/api/employees")
def get_employees(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    status: str = "在职",
    search: str = "",
    ws: str = "",
    team: str = "",
    nation: str = "",
    gender: str = "",
    page: int = 1,
    page_size: int = 20
):
    query = select(employees).where(employees.c.status_status.contains(status))
    if search:
        query = query.where(or_(employees.c.name_nama.ilike(f"%{search}%"), employees.c.id_nomor.ilike(f"%{search}%")))
    if ws: query = query.where(employees.c.ws_bengkel == ws)
    if team: query = query.where(employees.c.team_grup == team)
    if nation: query = query.where(employees.c.nat_negara == nation)
    if gender: query = query.where(employees.c.gender_jk == gender)
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.where(employees.c.ws_bengkel.in_(allowed))
            else:
                query = query.where(employees.c.ws_bengkel == "__NONE__")
        except:
            pass

    total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = db.execute(query.order_by(desc(employees.c.id)).offset((page-1)*page_size).limit(page_size)).fetchall()
    return {"data": [dict(r._mapping) for r in rows], "total": total}

@app.get("/api/employees/query")
def get_employee_by_id(id_nomor: str, db=Depends(get_db), current_user=Depends(get_current_user)):
    emp = get_employee(db, id_nomor)
    if not emp: raise HTTPException(404, "Employee not found")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and emp.get("ws_bengkel") not in allowed:
                raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass
    return emp

class EmployeeSave(BaseModel):
    ws_bengkel: Optional[str] = None
    id_nomor: str
    name_nama: str
    team_grup: Optional[str] = None
    gender_jk: Optional[str] = None
    pos_cn_jabatan: Optional[str] = None
    pos_id_jabatan: Optional[str] = None
    nat_negara: Optional[str] = None
    rel_agama: Optional[str] = None
    id_card: Optional[str] = None
    hire_date: Optional[str] = None
    contract_end: Optional[str] = None
    custom_fields: Optional[str] = "{}"
    company: Optional[str] = None

@app.post("/api/employees/save")
def save_employee(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    data: EmployeeSave = None,
    is_update: bool = False
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can modify employee data")
    try:
        payload = data.dict(exclude_unset=True)
        if payload.get("id_card"):
            payload["id_card"] = clean_id_card(payload["id_card"])
        emp = get_employee(db, payload["id_nomor"])
        
        ws_scope_str = current_user.get("ws_scope")
        if ws_scope_str:
            try:
                allowed = json.loads(ws_scope_str)
                if isinstance(allowed, list):
                    target_ws = payload.get("ws_bengkel")
                    if target_ws not in allowed:
                        raise HTTPException(403, f"Permission denied: Workshop '{target_ws}' is not in your allowed workshops")
                    if is_update and emp:
                        if emp.get("ws_bengkel") not in allowed:
                            raise HTTPException(403, f"Permission denied: Employee is currently in restricted workshop '{emp.get('ws_bengkel')}'")
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(400, f"Permission verification failed: {str(e)}")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if is_update and emp:
            old_ws = emp.get("ws_bengkel")
            new_ws = payload.get("ws_bengkel")
            if old_ws != new_ws and new_ws:
                record_transfer(db, payload["id_nomor"], payload["name_nama"], "车间变更", old_ws or "", new_ws, current_user["username"])
            old_team = emp.get("team_grup")
            new_team = payload.get("team_grup")
            if old_team != new_team and new_team:
                record_transfer(db, payload["id_nomor"], payload["name_nama"], "班组变更", old_team or "", new_team, current_user["username"])
        if payload.get("ws_bengkel"):
            add_meta_if_not_exists(db, "车间", payload["ws_bengkel"])
        if payload.get("team_grup"):
            add_meta_if_not_exists(db, "班组", payload["team_grup"])
        if payload.get("nat_negara"):
            add_nationality_if_not_exists(db, payload["nat_negara"])
        if is_update:
            if not emp: raise HTTPException(404, "Employee not found")
            old = json.dumps({k: emp.get(k) for k in payload.keys()}, default=str)
            db.execute(update(employees).where(employees.c.id_nomor == payload["id_nomor"]).values(**payload, updated_at=now))
            db.commit()
            write_audit(db, payload["id_nomor"], payload.get("name_nama", emp["name_nama"]), "修改", old=old, new=json.dumps(payload, default=str), operator=current_user["username"], ip=request.client.host)
            return {"status": "success"}
        else:
            if emp: raise HTTPException(400, "ID already exists")
            db.execute(insert(employees).values(**payload, created_at=now, updated_at=now))
            db.commit()
            write_audit(db, payload["id_nomor"], payload.get("name_nama", ""), "入职", old="{}", new=json.dumps(payload, default=str), operator=current_user["username"], ip=request.client.host)
            return {"status": "success"}
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(500, str(e))

@app.post("/api/employees/resign")
def resign(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    id_nomor: str = "",
    reason: str = "",
    resign_date: str = None
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can resign employees")
    emp = get_employee(db, id_nomor)
    if not emp: raise HTTPException(404, "Employee not found")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and emp.get("ws_bengkel") not in allowed:
                raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass
    if resign_date:
        try:
            datetime.strptime(resign_date, "%Y-%m-%d")
        except:
            raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")
    else:
        resign_date = datetime.now().strftime("%Y-%m-%d")
    db.execute(update(employees).where(employees.c.id_nomor == id_nomor).values(status_status="离职 / Resign", resign_date=resign_date, remark_ket=reason))
    db.commit()
    write_audit(db, id_nomor, emp["name_nama"], "离职",
                old=json.dumps({"status": emp["status_status"]}),
                new=json.dumps({"status": "离职", "reason": reason, "resign_date": resign_date}),
                operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.post("/api/employees/permanent_delete")
def permanent_delete_employee(
    request: Request,
    id_nomor: str,
    admin_password: str,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can permanently delete employees")
    
    # 验证管理员密码 (支持大小写容错)
    user_db = db.execute(select(users).where(users.c.username == current_user["username"])).first()
    pw_ok = False
    if user_db:
        if bcrypt.checkpw(admin_password.encode('utf-8'), user_db.hashed_password.encode('utf-8')):
            pw_ok = True
        elif bcrypt.checkpw(admin_password.lower().encode('utf-8'), user_db.hashed_password.encode('utf-8')):
            pw_ok = True
        elif bcrypt.checkpw(admin_password.upper().encode('utf-8'), user_db.hashed_password.encode('utf-8')):
            pw_ok = True
    if not pw_ok:
        raise HTTPException(400, "密码错误，验证失败")
        
    emp = get_employee(db, id_nomor)
    if not emp:
        raise HTTPException(404, "Employee not found")
        
    if "离职" not in emp["status_status"]:
        raise HTTPException(400, "Only resigned employees can be permanently deleted")
        
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and emp.get("ws_bengkel") not in allowed:
                raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass
            
    db.execute(delete(employees).where(employees.c.id_nomor == id_nomor))
    db.execute(delete(labor_assignments).where(labor_assignments.c.id_nomor == id_nomor))
    db.commit()
    
    write_audit(db, id_nomor, emp["name_nama"], "彻底删除员工",
                old=json.dumps(emp),
                new="{}",
                reason="管理员验证密码后彻底删除离职员工",
                operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.get("/api/employees/export")
def export_employees(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    status: str = "在职",
    ws: str = "",
    team: str = "",
    nation: str = "",
    lang: str = "zh"
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Only admin can export data")
    query = select(employees).where(employees.c.status_status.contains(status))
    if ws: query = query.where(employees.c.ws_bengkel == ws)
    if team: query = query.where(employees.c.team_grup == team)
    if nation: query = query.where(employees.c.nat_negara == nation)
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.where(employees.c.ws_bengkel.in_(allowed))
            else:
                query = query.where(employees.c.ws_bengkel == "__NONE__")
        except:
            pass

    rows = db.execute(query).fetchall()
    df = pd.DataFrame([dict(r._mapping) for r in rows])
    
    rename_zh = {
        "id_nomor": "工号", "name_nama": "姓名", "company": "归属公司", "ws_bengkel": "车间", "team_grup": "班组",
        "gender_jk": "性别", "pos_cn_jabatan": "岗位(中)", "pos_id_jabatan": "岗位(印)",
        "nat_negara": "国籍", "rel_agama": "宗教", "id_card": "身份证号",
        "hire_date": "入职日期", "contract_end": "合同到期日", "status_status": "状态",
        "resign_date": "离职日期", "remark_ket": "备注"
    }
    rename_id = {
        "id_nomor": "ID", "name_nama": "Nama", "company": "Perusahaan", "ws_bengkel": "Bengkel", "team_grup": "Grup",
        "gender_jk": "JK", "pos_cn_jabatan": "Jabatan (CN)", "pos_id_jabatan": "Jabatan (ID)",
        "nat_negara": "Kewarganegaraan", "rel_agama": "Agama", "id_card": "Nomor KTP",
        "hire_date": "Tgl Masuk", "contract_end": "Kontrak Berakhir", "status_status": "Status",
        "resign_date": "Tgl Resign", "remark_ket": "Keterangan"
    }
    rename = rename_id if lang == "id" else rename_zh
    df.rename(columns=rename, inplace=True)
    if "出生日期" in df.columns:
        df.drop(columns=["出生日期"], inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=employees_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"}
    )

# ---------- 成本报表导出 ----------
@app.get("/api/employees/cost_report_export")
def cost_report_export(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    start_date: str = "",
    end_date: str = "",
    fields: str = "",
    field_labels: str = "{}"
):
    if current_user.get("role") != "admin":
        raise HTTPException(403, "Only admin can export data")
    try:
        if start_date:
            datetime.strptime(start_date, "%Y-%m-%d")
        if end_date:
            datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "日期格式错误，请使用 YYYY-MM-DD")

    query = select(employees)
    if end_date:
        query = query.where(
            or_(employees.c.hire_date == None, employees.c.hire_date <= end_date)
        )
    if start_date:
        query = query.where(
            or_(
                employees.c.status_status.contains("在职"),
                employees.c.resign_date == None,
                employees.c.resign_date >= start_date
            )
        )

    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.where(employees.c.ws_bengkel.in_(allowed))
            else:
                query = query.where(employees.c.ws_bengkel == "__NONE__")
        except:
            pass

    rows = db.execute(query.order_by(employees.c.hire_date, employees.c.id_nomor)).fetchall()
    df = pd.DataFrame([dict(r._mapping) for r in rows])

    all_available = [
        "id_nomor", "name_nama", "company", "ws_bengkel", "team_grup",
        "gender_jk", "pos_cn_jabatan", "pos_id_jabatan", "nat_negara",
        "rel_agama", "id_card", "hire_date", "contract_end",
        "status_status", "resign_date", "remark_ket"
    ]
    if fields:
        selected_fields = [f.strip() for f in fields.split(",") if f.strip() in all_available]
    else:
        selected_fields = all_available

    try:
        custom_labels = json.loads(field_labels) if field_labels else {}
    except:
        custom_labels = {}

    default_labels = {
        "id_nomor": "工号", "name_nama": "姓名", "company": "归属公司",
        "ws_bengkel": "车间", "team_grup": "班组", "gender_jk": "性别",
        "pos_cn_jabatan": "岗位(中)", "pos_id_jabatan": "岗位(印)",
        "nat_negara": "国籍", "rel_agama": "宗教", "id_card": "身份证号",
        "hire_date": "入职日期", "contract_end": "合同到期日",
        "status_status": "状态", "resign_date": "离职日期", "remark_ket": "备注"
    }

    # 获取自定义列名（保留换行符）
    headers = []
    for field in selected_fields:
        lbl = custom_labels.get(field) or default_labels.get(field, field)
        headers.append(lbl)

    cn_export_df = pd.DataFrame(columns=headers)
    id_export_df = pd.DataFrame(columns=headers)

    if not df.empty:
        # 分流：包含“中国籍”或“China”或“CN”的定义为中国籍，其他为印尼籍
        is_china = pd.Series(False, index=df.index)
        if "nat_negara" in df.columns:
            is_china = df["nat_negara"].fillna("").astype(str).str.contains("中国籍|China|CN", case=False, na=False)
        cn_df = df[is_china]
        id_df = df[~is_china]

        for field, col_label in zip(selected_fields, headers):
            if field in df.columns:
                cn_export_df[col_label] = cn_df[field].fillna("").astype(str).replace("nan", "")
                id_export_df[col_label] = id_df[field].fillna("").astype(str).replace("nan", "")

    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        cn_export_df.to_excel(writer, index=False, sheet_name="中国籍")
        id_export_df.to_excel(writer, index=False, sheet_name="印尼籍")
        
        # 针对导出的工作表第一行（表头）启用自动换行，以便展示自定义列名中的回车换行
        from openpyxl.styles import Alignment
        workbook = writer.book
        for sheet_name in ["中国籍", "印尼籍"]:
            worksheet = workbook[sheet_name]
            for cell in worksheet[1]:
                cell.alignment = Alignment(wrap_text=True, vertical="center", horizontal="center")
    output.seek(0)
    filename = f"cost_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/employees/import")
def import_excel(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can import data")
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(400, "Excel file required")
    df = pd.read_excel(io.BytesIO(file.file.read()))
    col_map = {
        "工号": "id_nomor", "ID": "id_nomor",
        "姓名": "name_nama", "Nama": "name_nama",
        "车间": "ws_bengkel", "Bengkel": "ws_bengkel",
        "班组": "team_grup", "Grup": "team_grup",
        "性别": "gender_jk", "JK": "gender_jk",
        "岗位(中)": "pos_cn_jabatan", "Jabatan (CN)": "pos_cn_jabatan",
        "岗位(印)": "pos_id_jabatan", "Jabatan (ID)": "pos_id_jabatan",
        "国籍": "nat_negara", "Negara": "nat_negara", "Kewarganegaraan": "nat_negara",
        "宗教": "rel_agama", "Agama": "rel_agama",
        "身份证号": "id_card", "ID Card": "id_card", "Nomor KTP": "id_card",
        "入职日期": "hire_date", "Tgl Masuk": "hire_date", "Tanggal Masuk": "hire_date",
        "合同到期日": "contract_end", "Kontrak Berakhir": "contract_end",
        "出生日期": "birth_date",
        "归属公司": "company", "Perusahaan": "company",
    }
    df.rename(columns=col_map, inplace=True)
    success = 0
    updated = 0
    errors = []
    skipped = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    workshops = set()
    teams = set()
    nationalities = set()
    
    for idx, row in df.iterrows():
        data = row.to_dict()
        id_num = str(data.get("id_nomor", "")).strip() if not pd.isna(data.get("id_nomor")) else ""
        name = str(data.get("name_nama", "")).strip() if not pd.isna(data.get("name_nama")) else ""
        if not id_num and not name:
            skipped.append(f"第{idx+2}行：工号和姓名均为空")
            continue
        if not id_num:
            skipped.append(f"第{idx+2}行：工号为空")
            continue
        if not name:
            skipped.append(f"第{idx+2}行：姓名为空 (工号={id_num})")
            continue
        ws = data.get("ws_bengkel")
        if ws and not pd.isna(ws) and str(ws).strip():
            workshops.add(str(ws).strip())
        team = data.get("team_grup")
        if team and not pd.isna(team) and str(team).strip():
            teams.add(str(team).strip())
        nat = data.get("nat_negara")
        if nat and not pd.isna(nat) and str(nat).strip():
            nationalities.add(str(nat).strip())
        id_card_val = data.get("id_card")
        if id_card_val and not pd.isna(id_card_val):
            data["id_card"] = clean_id_card(str(id_card_val))
        # 处理出生日期
        birth_val = data.get("birth_date")
        if birth_val and not pd.isna(birth_val):
            try:
                if isinstance(birth_val, str):
                    data["birth_date"] = datetime.strptime(birth_val, "%Y-%m-%d").date().strftime("%Y-%m-%d")
                else:
                    data["birth_date"] = birth_val.strftime("%Y-%m-%d")
            except:
                pass
        try:
            clean_data = {k: (None if pd.isna(v) else str(v)) for k, v in data.items()}
            
            ws_scope_str = current_user.get("ws_scope")
            if ws_scope_str:
                allowed = json.loads(ws_scope_str)
                if isinstance(allowed, list) and len(allowed) > 0:
                    ws_val = clean_data.get("ws_bengkel")
                    if ws_val not in allowed:
                        errors.append(f"第{idx+2}行 (工号={id_num}): 车间 '{ws_val}' 不在您允许的操作范围内")
                        continue
                    existing_check = get_employee(db, id_num)
                    if existing_check and existing_check.get("ws_bengkel") not in allowed:
                        errors.append(f"第{idx+2}行 (工号={id_num}): 员工当前属于受限车间 '{existing_check.get('ws_bengkel')}'，无权修改")
                        continue

            existing = get_employee(db, id_num)
            if existing:
                clean_data.pop('updated_at', None)
                clean_data.pop('created_at', None)
                db.execute(
                    update(employees)
                    .where(employees.c.id_nomor == id_num)
                    .values(**clean_data, updated_at=now)
                )
                updated += 1
            else:
                clean_data["created_at"] = now
                clean_data["updated_at"] = now
                db.execute(insert(employees).values(**clean_data))
            db.commit()
            success += 1
        except Exception as e:
            db.rollback()
            errors.append(f"第{idx+2}行 (工号={id_num}): {str(e)}")
    # 保存元数据 ...
    write_audit(db, "", "", "批量导入", old="", new=f"成功{success}条（新增{success-updated}，更新{updated}），跳过{len(skipped)}条，失败{len(errors)}条", operator=current_user["username"], ip=request.client.host)
    return {"imported": success, "updated": updated, "errors": errors, "skipped": skipped, "total_rows": len(df)}

@app.get("/api/employee/transfers")
def get_transfers(db=Depends(get_db), current_user=Depends(get_current_user)):
    stmt = select(employee_transfers)
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                stmt = stmt.select_from(
                    employee_transfers.join(employees, employee_transfers.c.id_nomor == employees.c.id_nomor)
                ).where(employees.c.ws_bengkel.in_(allowed))
        except:
            pass
    rows = db.execute(stmt.order_by(desc(employee_transfers.c.id))).fetchall()
    return [dict(r._mapping) for r in rows]

# Bulk delete transfer records
from typing import List
from fastapi import HTTPException, status, Query

@app.delete("/api/employee/transfers")
def delete_transfers(ids: List[int] = Query([]), db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied")
    if not ids:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No IDs provided")

    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                records = db.execute(
                    select(employee_transfers.c.id, employees.c.ws_bengkel)
                    .select_from(employee_transfers.outerjoin(employees, employee_transfers.c.id_nomor == employees.c.id_nomor))
                    .where(employee_transfers.c.id.in_(ids))
                ).fetchall()
                for r in records:
                    if r.ws_bengkel not in allowed:
                        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Permission denied: transfer record is for a workshop not in your scope")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Permission check failed: {str(e)}")

    try:
        del_stmt = delete(employee_transfers).where(employee_transfers.c.id.in_(ids))
        result = db.execute(del_stmt)
        db.commit()
        # Audit log
        write_audit(db, "employee_transfers", "", "Bulk delete transfer records", old="", new=f"Deleted IDs: {ids}", operator=current_user["username"], ip="")
        return {"deleted": result.rowcount}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

# 仪表盘
@app.get("/api/dashboard")
def dashboard(db=Depends(get_db), current_user=Depends(get_current_user)):
    ws_scope_str = current_user.get("ws_scope")
    allowed = []
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
        except:
            pass

    def apply_ws_filter(stmt, col=employees.c.ws_bengkel):
        if allowed:
            return stmt.where(col.in_(allowed))
        return stmt

    active = db.execute(apply_ws_filter(select(func.count()).where(employees.c.status_status.contains("在职")))).scalar()
    resigned = db.execute(apply_ws_filter(select(func.count()).where(employees.c.status_status.contains("离职")))).scalar()
    ws_dist = db.execute(apply_ws_filter(select(employees.c.ws_bengkel, func.count()).where(employees.c.status_status.contains("在职")).group_by(employees.c.ws_bengkel))).fetchall()
    nation_dist = db.execute(apply_ws_filter(select(employees.c.nat_negara, func.count()).where(employees.c.status_status.contains("在职")).group_by(employees.c.nat_negara))).fetchall()
    gender_dist = db.execute(apply_ws_filter(select(employees.c.gender_jk, func.count()).where(employees.c.status_status.contains("在职")).group_by(employees.c.gender_jk))).fetchall()
    
    age_groups = {"<20":0, "20-30":0, "30-40":0, "40-50":0, ">50":0, "UNKNOWN":0}
    today = date.today()
    rows = db.execute(apply_ws_filter(select(employees.c.id_card, employees.c.nat_negara).where(employees.c.status_status.contains("在职")))).fetchall()
    for row in rows:
        birth = None
        if row.id_card:
            birth_str = extract_birth_date_from_id_card(row.id_card, row.nat_negara or "")
            if birth_str:
                try:
                    birth = datetime.strptime(birth_str, "%Y-%m-%d").date()
                except:
                    pass
        if not birth:
            age_groups["UNKNOWN"] += 1
            continue
        age = today.year - birth.year - ((today.month, today.day) < (birth.month, birth.day))
        if age < 20: age_groups["<20"] += 1
        elif age < 30: age_groups["20-30"] += 1
        elif age < 40: age_groups["30-40"] += 1
        elif age < 50: age_groups["40-50"] += 1
        else: age_groups[">50"] += 1
    
    workshop_team_nation = db.execute(
        apply_ws_filter(
            select(
                employees.c.ws_bengkel,
                employees.c.team_grup,
                employees.c.nat_negara,
                func.count().label("count")
            )
            .where(employees.c.status_status.contains("在职"))
            .group_by(employees.c.ws_bengkel, employees.c.team_grup, employees.c.nat_negara)
        )
    ).fetchall()
    
    monthly_resign = []
    for i in range(11, -1, -1):
        month = (datetime.now().replace(day=1) - timedelta(days=i*30)).strftime("%Y-%m")
        cnt = db.execute(apply_ws_filter(select(func.count()).where(employees.c.status_status.contains("离职"), employees.c.resign_date.like(f"{month}%")))).scalar()
        monthly_resign.append({"month": month, "count": cnt})
    
    resign_ws_dist = db.execute(
        apply_ws_filter(
            select(employees.c.ws_bengkel, func.count())
            .where(employees.c.status_status.contains("离职"))
            .group_by(employees.c.ws_bengkel)
        )
    ).fetchall()
    
    resign_nation_dist = db.execute(
        apply_ws_filter(
            select(employees.c.nat_negara, func.count())
            .where(employees.c.status_status.contains("离职"))
            .group_by(employees.c.nat_negara)
        )
    ).fetchall()
    
    resign_team_dist = db.execute(
        apply_ws_filter(
            select(employees.c.team_grup, func.count())
            .where(employees.c.status_status.contains("离职"))
            .group_by(employees.c.team_grup)
        )
    ).fetchall()
    
    return {
        "total_active": active, "total_resigned": resigned,
        "workshop_distribution": [{"name": r[0] or "未知", "count": r[1]} for r in ws_dist],
        "nation_distribution": [{"name": r[0] or "未知", "count": r[1]} for r in nation_dist],
        "gender_distribution": [{"name": r[0] or "未知", "count": r[1]} for r in gender_dist],
        "age_distribution": [{"name": k, "count": v} for k, v in age_groups.items()],
        "monthly_resign": monthly_resign,
        "workshop_team_nation_matrix": [
            {"workshop": r[0] or "未知", "team": r[1] or "未知", "nation": r[2] or "未知", "count": r[3]} for r in workshop_team_nation
        ],
        "resign_workshop_distribution": [{"name": r[0] or "未知", "count": r[1]} for r in resign_ws_dist],
        "resign_nation_distribution": [{"name": r[0] or "未知", "count": r[1]} for r in resign_nation_dist],
        "resign_team_distribution": [{"name": r[0] or "未知", "count": r[1]} for r in resign_team_dist]
    }


# ========== 劳保用品 API ==========
@app.get("/api/labor/items")
def get_labor_items(db=Depends(get_db)):
    return [dict(r._mapping) for r in db.execute(select(labor_items)).fetchall()]

@app.post("/api/labor/items")
def add_labor_item(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    item_name: str = "",
    spec: str = "",
    unit: str = "件",
    default_cycle_days: int = 90,
    safety_stock: int = 0
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can add items")
    db.execute(insert(labor_items).values(item_name=item_name, item_spec=spec, unit=unit, default_cycle_days=default_cycle_days, safety_stock=safety_stock))
    db.commit()
    write_audit(db, "", "", "新增物品", old="", new=f"{item_name} (周期:{default_cycle_days},安全库存:{safety_stock})", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}
class AssignmentUpdate(BaseModel):
    last_issue_date: Optional[str] = None
    cycle_days: Optional[int] = None
    status: Optional[str] = None
@app.put("/api/labor/items/{item_id}")
def update_labor_item(
    item_id: int,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    item_name: str = "",
    spec: str = "",
    unit: str = "件",
    default_cycle_days: int = 90,
    safety_stock: int = 0
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can update items")
    old = db.execute(select(labor_items).where(labor_items.c.id==item_id)).first()
    db.execute(update(labor_items).where(labor_items.c.id==item_id).values(item_name=item_name, item_spec=spec, unit=unit, default_cycle_days=default_cycle_days, safety_stock=safety_stock))
    db.commit()
    write_audit(db, "", "", "修改物品", old=json.dumps(dict(old._mapping)), new=f"{item_name}", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.delete("/api/labor/items/{item_id}")
def delete_labor_item(
    item_id: int,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can delete items")
    assign_cnt = db.execute(select(func.count()).where(labor_assignments.c.item_id == item_id)).scalar()
    if assign_cnt > 0:
        raise HTTPException(400, f"该物品有 {assign_cnt} 条领用记录，请先删除相关领用记录")
    inv_cnt = db.execute(select(func.count()).where(labor_inventory.c.item_id == item_id)).scalar()
    if inv_cnt > 0:
        raise HTTPException(400, f"该物品有 {inv_cnt} 条库存记录，请先处理库存")
    item = db.execute(select(labor_items).where(labor_items.c.id==item_id)).first()
    db.execute(delete(labor_items).where(labor_items.c.id == item_id))
    db.commit()
    write_audit(db, "", "", "删除物品", old=json.dumps(dict(item._mapping)), new="", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.get("/api/labor/inventory")
def get_inventory(db=Depends(get_db), item_id: int = None):
    items = db.execute(select(labor_items)).fetchall()
    result = []
    for item in items:
        if item_id and item.id != item_id: continue
        result.append({"item": dict(item._mapping), "stock": get_item_stock(db, item.id)})
    return result

@app.post("/api/labor/inventory/in")
def stock_in(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    item_id: int = 0,
    quantity: int = 1,
    remark: str = ""
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can adjust inventory")
    db.execute(insert(labor_inventory).values(item_id=item_id, change_type="in", quantity=quantity, change_date=datetime.now().strftime("%Y-%m-%d"), remark=remark))
    db.commit()
    write_audit(db, "", "", "入库", old="", new=f"物品ID:{item_id},数量:{quantity},备注:{remark}", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.post("/api/labor/inventory/out")
def stock_out(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    item_id: int = 0,
    quantity: int = 1,
    remark: str = ""
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can adjust inventory")
    if quantity <= 0:
        raise HTTPException(400, "数量必须大于 0")
    stock = get_item_stock(db, item_id)
    if stock < quantity:
        raise HTTPException(400, f"库存不足，当前库存 {stock}，本次出库 {quantity}")
    db.execute(insert(labor_inventory).values(item_id=item_id, change_type="out", quantity=quantity, change_date=datetime.now().strftime("%Y-%m-%d"), remark=remark))
    db.commit()
    write_audit(db, "", "", "出库", old="", new=f"物品ID:{item_id},数量:{quantity},备注:{remark}", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.get("/api/labor/assignments")
def get_assignments(db=Depends(get_db), id_nomor: str = "", current_user=Depends(get_current_user)):
    query = select(labor_assignments)
    if id_nomor: query = query.where(labor_assignments.c.id_nomor == id_nomor)
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.select_from(
                    labor_assignments.join(employees, labor_assignments.c.id_nomor == employees.c.id_nomor)
                ).where(employees.c.ws_bengkel.in_(allowed))
        except:
            pass

    rows = db.execute(query).fetchall()
    result = []
    for r in rows:
        d = dict(r._mapping)
        item = db.execute(select(labor_items).where(labor_items.c.id==d["item_id"])).first()
        d["item"] = dict(item._mapping) if item else {}
        result.append(d)
    return result

@app.get("/api/labor/assignments/report")
def get_assignments_report(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    start_date: str = None,
    end_date: str = None,
    item_id: int = None,
    workshop: str = None,
    team: str = None
):
    # 直接使用 labor_assignments.quantity 字段，避免关联 labor_inventory 导致的重复
    query = select(
        labor_assignments.c.id_nomor,
        employees.c.name_nama,
        employees.c.ws_bengkel,
        employees.c.team_grup,
        labor_items.c.item_name,
        labor_items.c.item_spec,
        labor_assignments.c.last_issue_date,
        labor_assignments.c.next_issue_date,
        labor_assignments.c.cycle_days,
        labor_assignments.c.status,
        labor_assignments.c.quantity   # 新增字段，直接取发放数量
    ).select_from(
        labor_assignments
        .join(employees, labor_assignments.c.id_nomor == employees.c.id_nomor)
        .join(labor_items, labor_assignments.c.item_id == labor_items.c.id)
    )
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.where(employees.c.ws_bengkel.in_(allowed))
        except:
            pass
    if start_date:
        try:
            datetime.strptime(start_date, "%Y-%m-%d")
            query = query.where(labor_assignments.c.last_issue_date >= start_date)
        except:
            pass
    if end_date:
        try:
            datetime.strptime(end_date, "%Y-%m-%d")
            query = query.where(labor_assignments.c.last_issue_date <= end_date)
        except:
            pass
    if item_id:
        query = query.where(labor_assignments.c.item_id == item_id)
    if workshop:
        query = query.where(employees.c.ws_bengkel == workshop)
    if team:
        query = query.where(employees.c.team_grup == team)
    rows = db.execute(query.order_by(desc(labor_assignments.c.last_issue_date))).fetchall()
    result = []
    for r in rows:
        result.append({
            "id_nomor": r.id_nomor,
            "name": r.name_nama,
            "workshop": r.ws_bengkel,
            "team": r.team_grup,
            "item_name": r.item_name,
            "item_spec": r.item_spec,
            "last_issue_date": r.last_issue_date,
            "next_issue_date": r.next_issue_date,
            "cycle_days": r.cycle_days,
            "status": r.status,
            "quantity": r.quantity or 0
        })
    return result

@app.post("/api/labor/assignments/issue")
def issue_item(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    id_nomor: str = "",
    item_id: int = 0,
    quantity: int = 1,
    cycle_days: Optional[int] = None,
    issue_date: Optional[str] = None
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can issue items")
    if quantity <= 0:
        raise HTTPException(400, "发放数量必须大于 0")

    emp = get_employee(db, id_nomor)
    if not emp:
        raise HTTPException(404, "Employee not found")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and emp.get("ws_bengkel") not in allowed:
                raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass

    item = db.execute(select(labor_items).where(labor_items.c.id == item_id)).first()
    if not item:
        raise HTTPException(404, "Item not found")
    stock = get_item_stock(db, item_id)
    if stock < quantity:
        raise HTTPException(400, f"库存不足，当前库存 {stock}，本次发放 {quantity}")

    if cycle_days is None:
        cycle_days = item.default_cycle_days

    if issue_date:
        try:
            dt = datetime.strptime(issue_date, "%Y-%m-%d")
        except:
            raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")
    else:
        dt = datetime.now()

    next_dt = dt + timedelta(days=cycle_days)

    db.execute(update(labor_assignments).where(
        labor_assignments.c.id_nomor == id_nomor,
        labor_assignments.c.item_id == item_id,
        labor_assignments.c.status == "有效"
    ).values(status="已换发"))

    db.execute(insert(labor_assignments).values(
        id_nomor=id_nomor,
        item_id=item_id,
        last_issue_date=dt.strftime("%Y-%m-%d"),
        cycle_days=cycle_days,
        next_issue_date=next_dt.strftime("%Y-%m-%d"),
        quantity=quantity,
        status="有效"
    ))

    # 记录库存出库（用于库存统计）
    db.execute(insert(labor_inventory).values(
        item_id=item_id,
        change_type="out",
        quantity=quantity,
        change_date=dt.strftime("%Y-%m-%d"),
        remark=f"发放给 {id_nomor} (数量{quantity})"
    ))

    db.commit()
    write_audit(db, id_nomor, emp["name_nama"], "发放劳保",
                old="", new=f"物品:{item.item_name},数量:{quantity},周期:{cycle_days}",
                operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.post("/api/labor/assignments/{assignment_id}/cancel")
def cancel_assignment(
    assignment_id: int,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    reason: str = ""
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can cancel assignments")
    assign = db.execute(select(labor_assignments).where(labor_assignments.c.id == assignment_id)).first()
    if not assign:
        raise HTTPException(404, "Assignment not found")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list):
                emp = get_employee(db, assign.id_nomor)
                if emp and emp.get("ws_bengkel") not in allowed:
                    raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass
    if assign.status == "已撤销":
        raise HTTPException(400, "该记录已经撤销")
    qty = int(assign.quantity or 1)
    item = db.execute(select(labor_items).where(labor_items.c.id == assign.item_id)).first()
    db.execute(update(labor_assignments).where(labor_assignments.c.id == assignment_id).values(status="已撤销"))
    db.execute(insert(labor_inventory).values(
        item_id=assign.item_id,
        change_type="in",
        quantity=qty,
        change_date=datetime.now().strftime("%Y-%m-%d"),
        remark=f"撤销发放记录 #{assignment_id}，回补库存，原因:{reason or '填写错误'}"
    ))
    db.commit()
    write_audit(
        db, assign.id_nomor, "", "撤销劳保发放",
        old=json.dumps(dict(assign._mapping), ensure_ascii=False),
        new=f"物品:{item.item_name if item else assign.item_id},回补数量:{qty},原因:{reason or '填写错误'}",
        operator=current_user["username"], ip=request.client.host
    )
    return {"status": "success"}

@app.put("/api/labor/assignments/{assignment_id}")
def update_assignment(
    assignment_id: int,
    data: AssignmentUpdate,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can update assignments")
    assign = db.execute(select(labor_assignments).where(labor_assignments.c.id == assignment_id)).first()
    if not assign: raise HTTPException(404, "Assignment not found")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list):
                emp = get_employee(db, assign.id_nomor)
                if emp and emp.get("ws_bengkel") not in allowed:
                    raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass
    update_data = {}
    if data.last_issue_date is not None:
        try:
            dt = datetime.strptime(data.last_issue_date, "%Y-%m-%d")
            update_data["last_issue_date"] = dt.strftime("%Y-%m-%d")
            cycle = data.cycle_days if data.cycle_days is not None else assign.cycle_days
            update_data["next_issue_date"] = (dt + timedelta(days=cycle)).strftime("%Y-%m-%d")
        except:
            raise HTTPException(400, "Invalid date format")
    if data.cycle_days is not None:
        update_data["cycle_days"] = data.cycle_days
        if "last_issue_date" in update_data:
            last = datetime.strptime(update_data["last_issue_date"], "%Y-%m-%d")
            update_data["next_issue_date"] = (last + timedelta(days=data.cycle_days)).strftime("%Y-%m-%d")
        elif assign.last_issue_date:
            last = datetime.strptime(assign.last_issue_date, "%Y-%m-%d")
            update_data["next_issue_date"] = (last + timedelta(days=data.cycle_days)).strftime("%Y-%m-%d")
    if data.status is not None:
        update_data["status"] = data.status
    if update_data:
        db.execute(update(labor_assignments).where(labor_assignments.c.id == assignment_id).values(**update_data))
        db.commit()
        write_audit(db, assign.id_nomor, "", "编辑领用记录", old=json.dumps(dict(assign._mapping)), new=json.dumps(update_data), operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.delete("/api/labor/assignments/{assignment_id}")
def delete_assignment(
    assignment_id: int,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can delete assignments")
    assign = db.execute(select(labor_assignments).where(labor_assignments.c.id == assignment_id)).first()
    if not assign: raise HTTPException(404, "Assignment not found")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list):
                emp = get_employee(db, assign.id_nomor)
                if emp and emp.get("ws_bengkel") not in allowed:
                    raise HTTPException(403, "Permission denied for this workshop")
        except HTTPException:
            raise
        except:
            pass
    write_audit(db, assign.id_nomor, "", "删除领用记录", old=json.dumps(dict(assign._mapping)), new="", operator=current_user["username"], ip=request.client.host)
    db.execute(delete(labor_assignments).where(labor_assignments.c.id == assignment_id))
    db.commit()
    return {"status": "success"}

@app.get("/api/labor/reminders")
def labor_reminders(db=Depends(get_db), current_user=Depends(get_current_user)):
    today = date.today()
    stmt = select(labor_assignments).where(labor_assignments.c.status=="有效")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                stmt = stmt.select_from(
                    labor_assignments.join(employees, labor_assignments.c.id_nomor == employees.c.id_nomor)
                ).where(employees.c.ws_bengkel.in_(allowed))
        except:
            pass

    rows = db.execute(stmt).fetchall()
    reminders = []
    for r in rows:
        d = dict(r._mapping)
        if d["next_issue_date"]:
            try:
                next_date = datetime.strptime(d["next_issue_date"], "%Y-%m-%d").date()
                diff = (next_date - today).days
                if diff <= 15:
                    emp = get_employee(db, d["id_nomor"])
                    item = db.execute(select(labor_items).where(labor_items.c.id==d["item_id"])).first()
                    reminders.append({
                        "id_nomor": d["id_nomor"],
                        "name": emp["name_nama"] if emp else "",
                        "item": item.item_name if item else "",
                        "next_issue_date": d["next_issue_date"],
                        "days_left": diff,
                        "overdue": diff < 0
                    })
            except: pass
    return sorted(reminders, key=lambda x: x["days_left"])

# ---------- 日志 ----------
@app.get("/api/logs/summary")
def get_log_summary(db=Depends(get_db), current_user=Depends(get_current_user), date_str: str = None):
    if not date_str:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except:
            raise HTTPException(400, "Invalid date format")
    query = select(log_audit).where(log_audit.c.op_date.like(f"{date_str}%"))
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.select_from(
                    log_audit.outerjoin(employees, log_audit.c.id_nomor == employees.c.id_nomor)
                ).where(or_(employees.c.ws_bengkel.in_(allowed), log_audit.c.id_nomor == ""))
        except:
            pass
    logs = db.execute(query).fetchall()
    return [dict(r._mapping) for r in logs]

@app.get("/api/logs/report")
def export_log_report(db=Depends(get_db), current_user=Depends(get_current_user), lang: str = "zh"):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can export logs")
    query = select(log_audit).order_by(desc(log_audit.c.id))
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.select_from(
                    log_audit.outerjoin(employees, log_audit.c.id_nomor == employees.c.id_nomor)
                ).where(or_(employees.c.ws_bengkel.in_(allowed), log_audit.c.id_nomor == ""))
        except:
            pass
    rows = db.execute(query).fetchall()
    df = pd.DataFrame([dict(r._mapping) for r in rows])
    rename_zh = {
        "op_date": "操作时间", "id_nomor": "工号", "name_nama": "姓名",
        "type_tipe": "操作类型", "old_payload": "原数据", "new_payload": "新数据",
        "reason_alasan": "原因", "operator": "操作人", "ip_address": "IP"
    }
    rename_id = {
        "op_date": "Waktu Operasi", "id_nomor": "ID Karyawan", "name_nama": "Nama Karyawan",
        "type_tipe": "Tipe Operasi", "old_payload": "Data Lama", "new_payload": "Data Baru",
        "reason_alasan": "Alasan", "operator": "Operator", "ip_address": "IP"
    }
    rename = rename_id if lang == "id" else rename_zh
    df.rename(columns=rename, inplace=True)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename=log_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"}
    )

# ---------- 元数据维护 ----------
@app.get("/api/meta/{m_type}")
def get_meta(m_type: str, db=Depends(get_db)):
    return [v[0] for v in db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == m_type)).fetchall()]

@app.post("/api/meta/add")
def add_meta(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    m_type: str = "",
    value: str = ""
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can modify metadata")

    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                if m_type == "车间" and value.strip() not in allowed:
                    raise HTTPException(403, "Permission denied: you can only add workshops within your scope")
        except HTTPException:
            raise
        except:
            pass

    if not value.strip(): raise HTTPException(400)
    db.execute(insert(config_meta).values(meta_type=m_type, meta_value=value.strip()))
    db.commit()
    write_audit(db, "", "", f"新增{m_type}", old="", new=value.strip(), operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.post("/api/meta/update")
def update_meta(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    m_type: str = "",
    old_val: str = "",
    new_val: str = ""
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can modify metadata")

    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                if m_type == "车间" and old_val.strip() not in allowed:
                    raise HTTPException(403, "Permission denied: you can only update workshops within your scope")
        except HTTPException:
            raise
        except:
            pass

    if not new_val.strip(): raise HTTPException(400)
    db.execute(update(config_meta).where(config_meta.c.meta_type==m_type, config_meta.c.meta_value==old_val).values(meta_value=new_val.strip()))
    if m_type == "车间":
        db.execute(update(employees).where(employees.c.ws_bengkel == old_val).values(ws_bengkel=new_val))
    elif m_type == "班组":
        db.execute(update(employees).where(employees.c.team_grup == old_val).values(team_grup=new_val))
    db.commit()
    write_audit(db, "", "", f"修改{m_type}", old=old_val, new=new_val, operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.post("/api/meta/delete")
def delete_meta(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    m_type: str = "",
    value: str = ""
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can modify metadata")

    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                if m_type == "车间" and value.strip() not in allowed:
                    raise HTTPException(403, "Permission denied: you can only delete workshops within your scope")
        except HTTPException:
            raise
        except:
            pass
    if m_type == "车间":
        ref = db.execute(select(func.count()).where(employees.c.ws_bengkel == value)).scalar()
    elif m_type == "班组":
        ref = db.execute(select(func.count()).where(employees.c.team_grup == value)).scalar()
    else:
        ref = 0
    if ref > 0:
        raise HTTPException(400, f"{ref} employees using this")
    db.execute(delete(config_meta).where(config_meta.c.meta_type==m_type, config_meta.c.meta_value==value))
    db.commit()
    write_audit(db, "", "", f"删除{m_type}", old=value, new="", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

# ---------- 用户管理 ----------
class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    ws_scope: Optional[str] = None

@app.get("/api/users")
def get_users(db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can list users")
    rows = db.execute(select(users.c.id, users.c.username, users.c.role, users.c.ws_scope)).fetchall()
    return {"users": [{"id": r.id, "username": r.username, "role": r.role, "ws_scope": r.ws_scope} for r in rows]}

@app.post("/api/users")
def create_user(
    request: Request,
    user: UserCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can create users")
    existing = db.execute(select(users).where(users.c.username == user.username)).first()
    if existing:
        raise HTTPException(400, "Username already exists")
    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.execute(insert(users).values(username=user.username, hashed_password=hashed, role=user.role, ws_scope=user.ws_scope))
    db.commit()
    write_audit(db, "", "", "新增用户", old="", new=f"{user.username} ({user.role}), ws_scope: {user.ws_scope}", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.put("/api/users/{user_id}/role")
def update_user_role(
    user_id: int,
    role: str,
    request: Request,
    ws_scope: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can change roles/permissions")
    if role not in ["viewer", "admin"]:
        raise HTTPException(400, "Invalid role")
    target = db.execute(select(users).where(users.c.id == user_id)).first()
    if not target:
        raise HTTPException(404, "User not found")
    if target.username == current_user["username"]:
        raise HTTPException(400, "Cannot change your own role/permissions")
    old_role = target.role
    old_scope = target.ws_scope
    db.execute(update(users).where(users.c.id == user_id).values(role=role, ws_scope=ws_scope))
    db.commit()
    write_audit(db, "", "", "修改用户角色和权限", old=f"role: {old_role}, scope: {old_scope}", new=f"role: {role}, scope: {ws_scope}", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@app.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can delete users")
    target = db.execute(select(users).where(users.c.id == user_id)).first()
    if not target:
        raise HTTPException(404, "User not found")
    if target.username == current_user["username"]:
        raise HTTPException(400, "Cannot delete yourself")
    db.execute(delete(users).where(users.c.id == user_id))
    db.commit()
    write_audit(db, "", "", "删除用户", old=target.username, new="", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

# ---------- Logo ----------
@app.post("/api/settings/logo")
async def upload_logo(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can upload logo")
    if not file or not file.filename:
        raise HTTPException(400, "No file uploaded")
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.bmp']:
        raise HTTPException(400, "Only image files (png, jpg, jpeg, gif, bmp) are allowed")
    filepath = os.path.join(settings.LOGO_DIR, "logo.png")
    try:
        with open(filepath, "wb") as f:
            shutil.copyfileobj(file.file, f)
        return {"status": "success", "path": "/uploads/logos/logo.png"}
    except Exception as e:
        logger.error(f"Logo upload failed: {e}")
        raise HTTPException(500, f"Upload failed: {e}")

@app.get("/api/settings/logo")
def get_logo():
    filepath = os.path.join(settings.LOGO_DIR, "logo.png")
    if os.path.exists(filepath):
        return FileResponse(filepath, media_type="image/png")
    else:
        raise HTTPException(404, "Logo not found")

# ---------- 心跳 ----------
@app.post("/api/sessions/heartbeat")
def heartbeat(request: Request, mac: Optional[str] = None, db=Depends(get_db), current_user=Depends(get_current_user)):
    # Get real client IP from proxy headers
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        # X-Forwarded-For may contain multiple IPs: "client, proxy1, proxy2"
        # The first one is the real client IP
        client_ip = forwarded.split(",")[0].strip()
    else:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            client_ip = real_ip
        else:
            client_ip = request.client.host
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Try ARP first
    detected_mac = get_mac_address_from_arp(client_ip)
    if not detected_mac or detected_mac == "00:00:00:00:00:00":
        detected_mac = mac or "UNKNOWN"
        
    db.execute(text("""
        INSERT INTO active_sessions (username, ip_address, mac_address, last_seen)
        VALUES (:u, :ip, :mac, :now)
        ON CONFLICT (username, ip_address) DO UPDATE
        SET last_seen = :now, mac_address = :mac
    """), {"u": current_user["username"], "ip": client_ip, "mac": detected_mac, "now": now})
    db.commit()
    clean_sessions(db, 60)
    rows = db.execute(select(active_sessions.c.username, active_sessions.c.ip_address)).fetchall()
    return [{"user": r[0], "ip": r[1] if is_real_ip(r[1]) else ""} for r in rows]

@app.get("/api/logs")
def get_logs(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    page: int = 1,
    page_size: int = 50,
    date_from: str = "",
    date_to: str = "",
    op_type: str = "",
    search: str = ""
):
    query = select(log_audit).order_by(desc(log_audit.c.id))
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                query = query.select_from(
                    log_audit.outerjoin(employees, log_audit.c.id_nomor == employees.c.id_nomor)
                ).where(or_(employees.c.ws_bengkel.in_(allowed), log_audit.c.id_nomor == "", log_audit.c.id_nomor.is_(None)))
        except:
            pass
    if date_from:
        query = query.where(log_audit.c.op_date >= f"{date_from} 00:00:00")
    if date_to:
        query = query.where(log_audit.c.op_date <= f"{date_to} 23:59:59")
    if op_type:
        query = query.where(log_audit.c.type_tipe == op_type)
    if search:
        like = f"%{search}%"
        query = query.where(or_(
            log_audit.c.id_nomor.ilike(like),
            log_audit.c.name_nama.ilike(like),
            log_audit.c.operator.ilike(like),
            log_audit.c.type_tipe.ilike(like),
            log_audit.c.new_payload.ilike(like),
            log_audit.c.old_payload.ilike(like),
        ))
    total = db.execute(select(func.count()).select_from(query.subquery())).scalar()
    rows = db.execute(query.offset((page-1)*page_size).limit(page_size)).fetchall()
    type_rows = db.execute(select(log_audit.c.type_tipe).distinct().order_by(log_audit.c.type_tipe)).fetchall()
    return {
        "data": [dict(r._mapping) for r in rows],
        "total": total,
        "types": [r[0] for r in type_rows if r[0]]
    }

@app.delete("/api/logs")
def delete_logs(
    op_type: str = "",
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can delete logs")
    
    query = delete(log_audit)
    if op_type and op_type not in ["全部", "All"]:
        query = query.where(log_audit.c.type_tipe == op_type)
        
    db.execute(query)
    db.commit()
    
    write_audit(db, "", "", "删除操作日志", 
                old="", new=json.dumps({"deleted_category": op_type or "全部"}),
                reason="管理员清空指定类别的操作日志", 
                operator=current_user["username"], ip="")
    return {"status": "success"}

class BatchDeleteLogsRequest(BaseModel):
    ids: list

@app.post("/api/logs/batch-delete")
def batch_delete_logs(
    request: Request,
    body: BatchDeleteLogsRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can delete logs")
    ids = [int(i) for i in body.ids if str(i).isdigit()]
    if not ids:
        raise HTTPException(400, "No valid IDs provided")
    db.execute(delete(log_audit).where(log_audit.c.id.in_(ids)))
    db.commit()
    write_audit(db, "", "", "批量删除操作日志",
                old="", new=json.dumps({"deleted_ids": ids}),
                reason="管理员批量删除选定日志条目",
                operator=current_user["username"], ip=request.client.host)
    return {"status": "success", "deleted_count": len(ids)}

@app.get("/api/db/backup")
def backup(current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(403)
    db_info = parse_db_url()
    backup_file = f"backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql"
    filepath = os.path.join(settings.EXPORT_DIR, backup_file)
    try:
        run_postgres_command("pg_dump", db_info, stdout_path=filepath)
        return FileResponse(filepath, filename=backup_file)
    except subprocess.CalledProcessError as e:
        msg = command_error_message(e)
        logger.error(f"Backup failed: {msg}")
        raise HTTPException(500, f"Backup failed: {msg}")

@app.post("/api/db/restore")
async def restore(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(403)
    db_info = parse_db_url()
    path = os.path.join(settings.EXPORT_DIR, "restore_temp.sql")
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        args = [
            "psql",
            "-h", db_info["host"],
            "-p", str(db_info["port"]),
            "-U", db_info["user"],
            "-d", db_info["dbname"],
            "-f", path,
        ]
        env = os.environ.copy()
        if db_info.get("password"):
            env["PGPASSWORD"] = db_info["password"]
        subprocess.run(args, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=False, env=env)
        return {"status": "success"}
    except subprocess.CalledProcessError as e:
        msg = command_error_message(e)
        logger.error(f"Restore failed: {msg}")
        raise HTTPException(500, f"Restore failed: {msg}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

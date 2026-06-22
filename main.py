# ============================================
# 后勤三部人事管理系统 - 后端入口点
# ============================================
import os
import logging
import bcrypt
from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text, select, insert

from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

# ---------- 配置与数据库 ----------
from database import settings, engine, SessionLocal, metadata, get_db
from models import users

# ---------- 路由导入 ----------
from routers import auth, employees, labor, logs, backup
from services.backup_service import init_backup_scheduler
from services.limiter import limiter

os.makedirs(settings.EXPORT_DIR, exist_ok=True)
os.makedirs(settings.LOGO_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

# 创建表
metadata.create_all(bind=engine)

# 自动数据库结构检查与迁移
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
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='labor_assignments' AND column_name='quantity'
    """)).fetchone()
    if not result:
        conn.execute(text("ALTER TABLE labor_assignments ADD COLUMN quantity INTEGER DEFAULT 1"))
        logger.info("Added quantity column to labor_assignments")

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

with engine.connect() as conn:
    result = conn.execute(text("""
        SELECT column_name 
        FROM information_schema.columns 
        WHERE table_name='labor_assignments' AND column_name='quantity'
    """)).fetchone()
    if not result:
        conn.execute(text("ALTER TABLE labor_assignments ADD COLUMN quantity INTEGER DEFAULT 0"))
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
        conn.execute(text("UPDATE labor_assignments SET quantity = 1 WHERE quantity = 0"))
        conn.commit()
        logger.info("Added quantity column to labor_assignments and backfilled data")

# ---------- 初始化 admin ----------
def init_admin():
    with SessionLocal() as db:
        user = db.execute(select(users).where(users.c.username == "admin")).first()
        if not user:
            hashed = bcrypt.hashpw(b"iwip123", bcrypt.gensalt()).decode('utf-8')
            db.execute(insert(users).values(username="admin", hashed_password=hashed, role="admin"))
            db.commit()
init_admin()

app = FastAPI(title="后勤三部人事管理系统")
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
app.mount("/uploads", StaticFiles(directory=settings.UPLOAD_DIR), name="uploads")

@app.on_event("startup")
def startup_validation():
    logger.info("Running startup environment and database validation...")
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Database connection validated successfully.")
        init_backup_scheduler()
    except Exception as e:
        logger.critical(f"Database connection validation failed: {e}")
        raise RuntimeError(f"CRITICAL ERROR: Database connection failed during startup: {e}")

@app.get("/api/health")
def health_check():
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return {"status": "ok", "database": "ok"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(503, "Database unavailable")

# ---------- 注册路由 ----------
app.include_router(auth.router)
app.include_router(employees.router)
app.include_router(labor.router)
app.include_router(logs.router)
app.include_router(backup.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

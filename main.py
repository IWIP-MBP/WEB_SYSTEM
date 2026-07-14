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
from routers import auth, employees, labor, logs, backup, attendance
from services.backup_service import init_backup_scheduler
from services.limiter import limiter

os.makedirs(settings.EXPORT_DIR, exist_ok=True)
os.makedirs(settings.LOGO_DIR, exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("uvicorn.error")

from services.migration import run_db_migrations
run_db_migrations()

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
app.include_router(attendance.router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

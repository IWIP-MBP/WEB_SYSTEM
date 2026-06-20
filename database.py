import os
import logging
from sqlalchemy import create_engine, MetaData
from sqlalchemy.orm import sessionmaker

# ---------- 配置 ----------
class Settings:
    DATABASE_URL = os.getenv("DATABASE_URL")
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "*").split(",")
    SECRET_KEY = os.getenv("SECRET_KEY")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_HOURS = 24
    UPLOAD_DIR = "uploads"
    EXPORT_DIR = os.path.join(UPLOAD_DIR, "exports")
    LOGO_DIR = os.path.join(UPLOAD_DIR, "logos")

    @classmethod
    def validate(cls):
        if not cls.DATABASE_URL:
            raise RuntimeError("CRITICAL ERROR: Environment variable 'DATABASE_URL' is required but not configured.")
        if not cls.SECRET_KEY:
            raise RuntimeError("CRITICAL ERROR: Environment variable 'SECRET_KEY' is required but not configured.")
        if cls.SECRET_KEY == "iwip-secret-key-change-in-production":
            logging.warning("WARNING: 'SECRET_KEY' is using an insecure default value. Please change it in production!")

Settings.validate()
settings = Settings()

# ---------- 数据库 ----------
engine = create_engine(settings.DATABASE_URL, pool_size=10, max_overflow=20, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
metadata = MetaData()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

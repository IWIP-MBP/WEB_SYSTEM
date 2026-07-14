import os
import logging
import json
import bcrypt
from datetime import datetime
from sqlalchemy import text, select, insert, update
from database import engine, metadata, SessionLocal
from models import users, employees

logger = logging.getLogger("uvicorn.error")

def run_db_migrations():
    logger.info("开始执行数据库结构检查与自动迁移...")
    # 1. 创建表结构
    metadata.create_all(bind=engine)

    # 2. 自动数据库结构检查与迁移
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
        try:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='labor_assignments' AND column_name='quantity'
            """)).fetchone()
            if not result:
                conn.execute(text("ALTER TABLE labor_assignments ADD COLUMN quantity INTEGER DEFAULT 1"))
                logger.info("Added quantity column to labor_assignments")
        except Exception as e:
            logger.warning(f"Error adding quantity column to labor_assignments: {e}")

    with engine.begin() as conn:
        try:
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
                ('resign_operator', 'VARCHAR'),
                ('resign_op_date', 'VARCHAR'),
            ]:
                if col not in existing:
                    conn.execute(text(f"ALTER TABLE employees ADD COLUMN {col} {col_type}"))
            logger.info("Checked/migrated employees table columns")
        except Exception as e:
            logger.warning(f"Error migrating employees table: {e}")

    with engine.begin() as conn:
        try:
            conn.execute(text("""
                UPDATE employees e
                SET resign_op_date = COALESCE(
                    (
                        SELECT LEFT(la.op_date, 10)
                        FROM log_audit la
                        WHERE la.id_nomor = e.id_nomor AND la.type_tipe = '离职'
                        ORDER BY la.id DESC
                        LIMIT 1
                    ),
                    e.resign_date
                )
                WHERE e.status_status LIKE '%离职%' AND e.resign_op_date IS NULL
            """))
            logger.info("Backfilled resign_op_date for existing resigned employees")
        except Exception as ex:
            logger.warning(f"Error backfilling resign_op_date: {ex}")

    with engine.begin() as conn:
        try:
            existing_users = [row[0] for row in conn.execute(text(
                "SELECT column_name FROM information_schema.columns WHERE table_name='users'"
            )).fetchall()]
            if 'role' not in existing_users:
                conn.execute(text("ALTER TABLE users ADD COLUMN role VARCHAR DEFAULT 'viewer'"))
            if 'ws_scope' not in existing_users:
                conn.execute(text("ALTER TABLE users ADD COLUMN ws_scope VARCHAR"))
            logger.info("Checked/migrated users table columns")
        except Exception as e:
            logger.warning(f"Error migrating users table: {e}")

    with engine.connect() as conn:
        try:
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
            conn.commit()
            logger.info("Ensured employee_transfers table exists")
        except Exception as e:
            logger.warning(f"Error creating employee_transfers table: {e}")

    with engine.connect() as conn:
        try:
            result = conn.execute(text("""
                SELECT column_name 
                FROM information_schema.columns 
                WHERE table_name='labor_assignments' AND column_name='quantity'
            """)).fetchone()
            # Double check backfill condition
            # If the column has just been added, or has values that are 0
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
            logger.info("Backfilled labor_assignments quantity data")
        except Exception as e:
            logger.warning(f"Error backfilling labor_assignments quantity data: {e}")

    # 3. 初始化 admin 用户
    with SessionLocal() as db:
        try:
            user = db.execute(select(users).where(users.c.username == "admin")).first()
            if not user:
                hashed = bcrypt.hashpw(b"iwip123", bcrypt.gensalt()).decode('utf-8')
                db.execute(insert(users).values(username="admin", hashed_password=hashed, role="admin"))
                db.commit()
                logger.info("Initialized admin user successfully")
        except Exception as e:
            logger.error(f"Error initializing admin user: {e}")

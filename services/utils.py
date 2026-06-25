import os
import re
import subprocess
import logging
from datetime import datetime, timedelta, date
from urllib.parse import urlparse
from sqlalchemy import select, insert, delete
from models import active_sessions, config_meta, employee_transfers, employees
from database import settings

logger = logging.getLogger(__name__)

def is_real_ip(ip: str) -> bool:
    if not ip:
        return False
    ip = ip.strip()
    if ip in ("127.0.0.1", "::1", "localhost", "unknown", "UNKNOWN", ""):
        return False
    if ip.startswith("172.16.") or ip.startswith("172.17.") or ip.startswith("172.18.") or ip.startswith("172.19.") or \
       ip.startswith("172.20.") or ip.startswith("172.21.") or ip.startswith("172.22.") or ip.startswith("172.23.") or \
       ip.startswith("172.24.") or ip.startswith("172.25.") or ip.startswith("172.26.") or ip.startswith("172.27.") or \
       ip.startswith("172.28.") or ip.startswith("172.29.") or ip.startswith("172.30.") or ip.startswith("172.31.") or \
       ip.startswith("192.168.") or ip.startswith("10."):
        return False
    return True

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

def get_employee(db, id_nomor):
    res = db.execute(select(employees).where(employees.c.id_nomor == id_nomor)).first()
    return dict(res._mapping) if res else None

def clean_id_card(id_card):
    if not id_card:
        return None
    # 处理科学计数法（如 Excel 导入的 3.17e+15 → 3170000000000000）
    raw = str(id_card).strip().strip("'\"")
    try:
        if 'e' in raw.lower() or 'E' in raw:
            raw = str(int(float(raw)))
    except:
        pass
    # 移除非数字和非X字符
    id_str = re.sub(r"[^0-9X]", "", raw.upper())
    return id_str if id_str else None

def extract_birth_date_from_id_card(id_card, nationality=None):
    """
    从身份证号提取出生日期，仅根据长度判断：
    - 18位：中国身份证规则（前17位数字，末尾数字或X），取第7-14位 YYYYMMDD
    - 16位：印尼身份证规则（纯数字），出生日期在第7-12位 DDMMYY，动态推断世纪
      ※ 印尼女性：出生日 DD 加 40 存储（如1日→41），提取时自动还原
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
            # 印尼女性：出生日 dd 加 40（如1日 → 41），需还原为真实日期
            if 41 <= dd <= 71:
                dd -= 40
            if not (1 <= mm <= 12 and 1 <= dd <= 31):
                return None
            current_year = datetime.now().year
            century_base = (current_year // 100) * 100
            year = century_base + yy
            # 若推断年份超出当前年份，退回上一世纪
            if year > current_year:
                year -= 100
            # 兜底：结果仍不合理时，对 yy >= 50 使用 1900s，yy < 50 使用 2000s
            if year < 1900 or year > current_year:
                year = (1900 if yy >= 50 else 2000) + yy
            return date(year, mm, dd).strftime("%Y-%m-%d")
        except:
            pass
        return None

    return None

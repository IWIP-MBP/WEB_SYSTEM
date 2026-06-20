import os
import json
import logging
import subprocess
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from services.utils import parse_db_url

logger = logging.getLogger(__name__)

BACKUP_DIR = "/app/backups"
CONFIG_FILE = os.path.join(BACKUP_DIR, "config.json")
os.makedirs(BACKUP_DIR, exist_ok=True)

# 默认配置：每天凌晨 2:00 自动备份，保留 7 天
DEFAULT_CONFIG = {
    "hour": 2,
    "minute": 0,
    "retention_days": 7
}

scheduler = BackgroundScheduler(timezone="Asia/Tokyo")

def load_backup_config():
    """
    从本地持久化 JSON 文件中读取备份策略配置
    """
    if not os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(DEFAULT_CONFIG, f, indent=4)
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"读取备份配置失败，使用默认配置: {e}")
        return DEFAULT_CONFIG

def save_backup_config(config):
    """
    将备份策略保存到本地 JSON 配置文件中
    """
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
    except Exception as e:
        logger.error(f"保存备份配置失败: {e}")

def create_db_backup() -> str:
    """
    执行 pg_dump 并以自定义时间戳生成自定义压缩格式（-Fc）备份文件。
    """
    db_info = parse_db_url()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_{timestamp}.dump"
    filepath = os.path.join(BACKUP_DIR, filename)
    
    # pg_dump 命令参数，使用 -F c 输出自定义压缩包，利于 pg_restore 高效还原
    args = [
        "pg_dump",
        "-h", db_info["host"],
        "-p", str(db_info["port"]),
        "-U", db_info["user"],
        "-F", "c",
        "-f", filepath,
        db_info["dbname"]
    ]
    
    env = os.environ.copy()
    if db_info.get("password"):
        env["PGPASSWORD"] = db_info["password"]
        
    try:
        logger.info(f"正在启动数据库自动/手动备份至 {filepath}...")
        subprocess.run(args, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f"数据库备份创建成功: {filename}")
        return filepath
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        logger.error(f"数据库备份失败: {stderr_msg}")
        raise RuntimeError(f"数据库备份失败: {stderr_msg}")

def restore_db_backup(filename: str):
    """
    使用 pg_restore 结合 --clean 清除原库结构后，还原数据库。
    """
    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        raise FileNotFoundError(f"未找到指定的备份文件: {filename}")
        
    db_info = parse_db_url()
    
    # pg_restore 参数：使用 --clean (-c) 清除已有对象，确保还原干净
    args = [
        "pg_restore",
        "-h", db_info["host"],
        "-p", str(db_info["port"]),
        "-U", db_info["user"],
        "-d", db_info["dbname"],
        "-c",
        filepath
    ]
    
    env = os.environ.copy()
    if db_info.get("password"):
        env["PGPASSWORD"] = db_info["password"]
        
    try:
        logger.info(f"正在从备份文件 {filename} 还原数据库...")
        subprocess.run(args, env=env, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logger.info(f"数据库已成功从备份 {filename} 还原！")
    except subprocess.CalledProcessError as e:
        stderr_msg = e.stderr.decode("utf-8", errors="replace") if e.stderr else str(e)
        logger.error(f"数据库还原失败: {stderr_msg}")
        raise RuntimeError(f"数据库还原失败: {stderr_msg}")

def clean_old_backups(retention_days: int):
    """
    根据配置，自动清理 N 天前生成的旧备份文件
    """
    logger.info(f"开始自动清理超过 {retention_days} 天的旧备份...")
    now = datetime.now()
    count = 0
    try:
        for file in os.listdir(BACKUP_DIR):
            if file.startswith("backup_") and file.endswith(".dump"):
                filepath = os.path.join(BACKUP_DIR, file)
                file_time = datetime.fromtimestamp(os.path.getmtime(filepath))
                if now - file_time > timedelta(days=retention_days):
                    os.remove(filepath)
                    logger.info(f"已删除过期备份文件: {file}")
                    count += 1
        logger.info(f"备份文件清理完成，共删除 {count} 个文件。")
    except Exception as e:
        logger.error(f"清理过期备份文件失败: {e}")

def scheduled_backup_job():
    """
    定时任务执行函数：创建备份并清理过期备份
    """
    try:
        create_db_backup()
        config = load_backup_config()
        clean_old_backups(config.get("retention_days", 7))
    except Exception as e:
        logger.error(f"定时备份任务执行异常: {e}")

def init_backup_scheduler():
    """
    初始化并启动 BackgroundScheduler，动态添加/重置定时任务
    """
    config = load_backup_config()
    hour = config.get("hour", 2)
    minute = config.get("minute", 0)
    
    # 启动调度器
    if not scheduler.running:
        scheduler.start()
        logger.info("备份 BackgroundScheduler 已成功启动。")
        
    # 清理已有的同名任务
    if scheduler.get_job("auto_backup"):
        scheduler.remove_job("auto_backup")
        
    trigger = CronTrigger(hour=hour, minute=minute, timezone="Asia/Tokyo")
    scheduler.add_job(
        scheduled_backup_job,
        trigger=trigger,
        id="auto_backup",
        replace_existing=True
    )
    logger.info(f"自动备份任务 'auto_backup' 已配置为每天 {hour:02d}:{minute:02d} (Tokyo 时间) 自动运行。")

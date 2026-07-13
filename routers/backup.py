import os
import json
import logging
from datetime import datetime
from typing import List
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel, Field

from database import get_db
from services.auth import get_current_user, ensure_super_admin
from services.audit import write_audit
from services.backup_service import (
    BACKUP_DIR,
    load_backup_config,
    save_backup_config,
    create_db_backup,
    restore_db_backup,
    scheduler,
    init_backup_scheduler
)
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)
router = APIRouter()

class BackupConfigSchema(BaseModel):
    hour: int = Field(..., ge=0, le=23, description="备份触发小时数 (0-23)")
    minute: int = Field(..., ge=0, le=59, description="备份触发分钟数 (0-59)")
    retention_days: int = Field(..., ge=1, le=365, description="备份保留天数 (1-365)")

class BackupFileSchema(BaseModel):
    filename: str
    size_bytes: int
    created_at: str

class RestoreRequestSchema(BaseModel):
    filename: str

@router.get("/api/system/backup/config")
def get_backup_config(current_user=Depends(get_current_user)):
    """
    获取当前自动备份策略配置
    """
    ensure_super_admin(current_user, "只有管理员可以查看备份配置")
    return load_backup_config()



@router.get("/api/system/backups", response_model=List[BackupFileSchema])
def get_backups(current_user=Depends(get_current_user)):
    """
    列出所有现存备份文件（按创建时间倒序排序）
    """
    ensure_super_admin(current_user, "只有管理员有权限查看备份列表")
        
    backups = []
    if not os.path.exists(BACKUP_DIR):
        return backups
        
    for file in os.listdir(BACKUP_DIR):
        if file.startswith("backup_") and file.endswith(".dump"):
            filepath = os.path.join(BACKUP_DIR, file)
            stat = os.stat(filepath)
            created_time = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
            backups.append(BackupFileSchema(
                filename=file,
                size_bytes=stat.st_size,
                created_at=created_time
            ))
            
    # 按文件名倒序，由于包含时间戳，恰好也是时间倒序
    backups.sort(key=lambda x: x.filename, reverse=True)
    return backups

@router.post("/api/system/backup/create")
def trigger_backup(request: Request, db=Depends(get_db), current_user=Depends(get_current_user)):
    """
    立即手动触发一次异步/同步数据库备份
    """
    ensure_super_admin(current_user, "只有管理员可以手动触发备份")
        
    try:
        filepath = create_db_backup()
        filename = os.path.basename(filepath)
        write_audit(db, "", "", "手动备份数据库", old="", new=filename, reason="管理员手动触发数据库备份成功", operator=current_user["username"], ip=request.client.host)
        return {"status": "success", "filename": filename}
    except Exception as e:
        raise HTTPException(500, f"创建备份失败: {str(e)}")

def bg_restore_task(filename: str, username: str, ip: str):
    """
    还原任务后台执行线程，防止长连接 HTTP 请求超时
    """
    try:
        restore_db_backup(filename)
        from database import SessionLocal
        with SessionLocal() as db:
            write_audit(db, "", "", "还原数据库", old="", new=filename, reason="管理员后台还原数据库成功", operator=username, ip=ip)
    except Exception as e:
        logger.error(f"后台还原数据库任务失败: {e}")

@router.post("/api/system/backup/restore")
def restore_backup(
    body: RestoreRequestSchema,
    background_tasks: BackgroundTasks,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    接收文件名，通过 FastAPI BackgroundTasks 在后台异步执行还原，保证高可用性
    """
    ensure_super_admin(current_user, "只有管理员可以执行还原操作")
        
    filename = body.filename
    filepath = os.path.join(BACKUP_DIR, filename)
    if not os.path.exists(filepath):
        raise HTTPException(404, "未找到指定的备份文件")
        
    # 写入审计日志记录触发动作
    write_audit(db, "", "", "触发还原数据库", old="", new=filename, reason="管理员触发数据库还原动作，提交后台异步执行", operator=current_user["username"], ip=request.client.host)
    
    # 提交后台任务
    background_tasks.add_task(bg_restore_task, filename, current_user["username"], request.client.host)
    return {"status": "success", "message": "还原任务已在后台排队执行，请稍后检查系统日志"}

@router.post("/api/system/backup/config")
def update_backup_config(
    body: BackupConfigSchema,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    """
    接收参数，保存新配置，并动态重置 APScheduler 中的任务，不重启服务即时生效
    """
    ensure_super_admin(current_user, "只有管理员可以修改备份配置")
        
    config = {
        "hour": body.hour,
        "minute": body.minute,
        "retention_days": body.retention_days
    }
    
    old_config = load_backup_config()
    save_backup_config(config)
    
    # 动态 reschedule APScheduler 定时任务
    try:
        init_backup_scheduler()
        logger.info(f"备份定时任务重构成功，运行时间已变更为 每天 {body.hour:02d}:{body.minute:02d}")
    except Exception as e:
        logger.error(f"重构备份定时任务失败: {e}")
            
    write_audit(db, "", "", "更新自动备份配置", old=json.dumps(old_config), new=json.dumps(config), reason="管理员修改自动备份周期及保留天数", operator=current_user["username"], ip="")
    return {"status": "success", "config": config}

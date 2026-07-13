import os
import io
import json
import shutil
import logging
import subprocess
from datetime import datetime, timedelta, date
from typing import Optional, List
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Response
from fastapi.responses import FileResponse
from sqlalchemy import select, insert, update, delete, or_, desc, func, text
from pydantic import BaseModel

from database import get_db, settings
from models import log_audit, employees, labor_assignments, labor_items
from services.auth import get_current_user
from services.audit import write_audit
from services.utils import get_employee, extract_birth_date_from_id_card, parse_db_url, parse_ws_scope

logger = logging.getLogger(__name__)
router = APIRouter()

class BatchDeleteLogsRequest(BaseModel):
    ids: list

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

# ---------- 日志/系统接口 ----------
@router.get("/api/logs/summary")
def get_log_summary(db=Depends(get_db), current_user=Depends(get_current_user), date_str: str = None):
    if not date_str:
        date_str = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    else:
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(400, "Invalid date format")
    query = select(log_audit).where(log_audit.c.op_date.like(f"{date_str}%"))
    allowed = parse_ws_scope(current_user.get("ws_scope"))
    if allowed is not None and len(allowed) > 0:
        query = query.select_from(
            log_audit.outerjoin(employees, log_audit.c.id_nomor == employees.c.id_nomor)
        ).where(or_(employees.c.ws_bengkel.in_(allowed), log_audit.c.id_nomor == ""))
    logs = db.execute(query).fetchall()
    return [dict(r._mapping) for r in logs]

@router.get("/api/logs/report")
def export_log_report(db=Depends(get_db), current_user=Depends(get_current_user), lang: str = "zh"):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can export logs")
    query = select(log_audit).order_by(desc(log_audit.c.id))
    allowed = parse_ws_scope(current_user.get("ws_scope"))
    if allowed is not None and len(allowed) > 0:
        query = query.select_from(
            log_audit.outerjoin(employees, log_audit.c.id_nomor == employees.c.id_nomor)
        ).where(or_(employees.c.ws_bengkel.in_(allowed), log_audit.c.id_nomor == ""))
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

@router.get("/api/logs")
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
    allowed = parse_ws_scope(current_user.get("ws_scope"))
    if allowed is not None and len(allowed) > 0:
        query = query.select_from(
            log_audit.outerjoin(employees, log_audit.c.id_nomor == employees.c.id_nomor)
        ).where(or_(employees.c.ws_bengkel.in_(allowed), log_audit.c.id_nomor == "", log_audit.c.id_nomor.is_(None)))
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

@router.delete("/api/logs")
def delete_logs(
    op_type: str = "",
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.get("username") != "admin":
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

@router.post("/api/logs/batch-delete")
def batch_delete_logs(
    request: Request,
    body: BatchDeleteLogsRequest,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user.get("username") != "admin":
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

# ---------- 数据库备份与恢复 ----------
@router.get("/api/db/backup")
def backup(current_user=Depends(get_current_user)):
    if current_user.get("username") != "admin":
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

@router.post("/api/db/restore")
async def restore(file: UploadFile = File(...), current_user=Depends(get_current_user)):
    if current_user.get("username") != "admin":
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

# ---------- 通知历史 ----------
@router.get("/api/notifications/history")
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
                except (ValueError, TypeError):
                    pass
        result.append({
            "date": date_str,
            "log_count": len(logs),
            "logs_detail": logs_detail,
            "labor_reminders": labor_list,
            "birthday_reminders": birthday_list
        })
    return result

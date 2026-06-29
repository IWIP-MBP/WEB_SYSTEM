import os
import io
import json
import logging
import bcrypt
from datetime import datetime, timedelta, date
from typing import Optional, List
import pandas as pd
from openpyxl.styles import Alignment
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Response, Query
from sqlalchemy import select, insert, update, delete, or_, desc, func, text
from sqlalchemy.orm import Session
from pydantic import BaseModel

from database import get_db, settings
from models import employees, config_meta, users, employee_transfers, labor_assignments, log_audit
from services.auth import get_current_user
from services.audit import write_audit
from services.org_chart import build_org_chart, validate_org_nodes
from services.utils import (
    get_employee,
    clean_id_card,
    extract_birth_date_from_id_card,
    add_meta_if_not_exists,
    record_transfer
)

logger = logging.getLogger(__name__)
router = APIRouter()

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

# ---------- 员工恢复 ----------
@router.post("/api/employees/restore")
def restore_employee(request: Request, db=Depends(get_db), current_user=Depends(get_current_user), id_nomor: str = ""):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can restore employees")
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
            
    if "在职" in emp["status_status"]:
        raise HTTPException(400, "Employee is already active")
    db.execute(update(employees).where(employees.c.id_nomor == id_nomor).values(
        status_status="在职 / Aktif", resign_date=None, remark_ket=None, resign_operator=None))
    db.commit()
    write_audit(db, id_nomor, emp["name_nama"], "恢复在职",
                old=json.dumps({"status": emp["status_status"], "resign_date": emp["resign_date"], "reason": emp["remark_ket"]}),
                new=json.dumps({"status": "在职"}), operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

# ---------- 员工花名册 ----------
@router.get("/api/employees")
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

@router.get("/api/employees/query")
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

@router.post("/api/employees/save")
def save_employee(
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    data: EmployeeSave = None,
    is_update: bool = False,
    original_id: Optional[str] = Query(None)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can modify employee data")
    try:
        payload = data.dict(exclude_unset=True)
        if payload.get("id_card"):
            payload["id_card"] = clean_id_card(payload["id_card"])
            
        old_id = original_id if original_id else payload.get("id_nomor")
        emp = get_employee(db, old_id)
        
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
            # 添加国籍元数据
            exists = db.execute(select(config_meta).where(config_meta.c.meta_type == "国籍", config_meta.c.meta_value == payload["nat_negara"].strip())).first()
            if not exists:
                db.execute(insert(config_meta).values(meta_type="国籍", meta_value=payload["nat_negara"].strip()))
                db.commit()
                
        if is_update:
            if not emp: raise HTTPException(404, "Employee not found")
            
            # Check if id_nomor is being modified and new ID already exists
            if payload.get("id_nomor") and payload["id_nomor"] != old_id:
                existing_new = get_employee(db, payload["id_nomor"])
                if existing_new:
                    raise HTTPException(400, "New employee ID already exists / 新工号已存在")
                    
            old = json.dumps({k: emp.get(k) for k in payload.keys()}, default=str)
            db.execute(update(employees).where(employees.c.id_nomor == old_id).values(**payload, updated_at=now))
            db.commit()
            
            # Cascade updates to other tables
            if payload.get("id_nomor") and payload["id_nomor"] != old_id:
                db.execute(update(labor_assignments).where(labor_assignments.c.id_nomor == old_id).values(id_nomor=payload["id_nomor"]))
                db.execute(update(employee_transfers).where(employee_transfers.c.id_nomor == old_id).values(id_nomor=payload["id_nomor"]))
                db.execute(update(log_audit).where(log_audit.c.id_nomor == old_id).values(id_nomor=payload["id_nomor"]))
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

@router.post("/api/employees/resign")
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
    db.execute(update(employees).where(employees.c.id_nomor == id_nomor).values(status_status="离职 / Resign", resign_date=resign_date, remark_ket=reason, resign_operator=current_user["username"]))
    db.commit()
    write_audit(db, id_nomor, emp["name_nama"], "离职",
                old=json.dumps({"status": emp["status_status"]}),
                new=json.dumps({"status": "离职", "reason": reason, "resign_date": resign_date}),
                operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@router.post("/api/employees/permanent_delete")
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

@router.get("/api/employees/export")
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
@router.get("/api/employees/cost_report_export")
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

@router.post("/api/employees/import")
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
            
    # 批量保存元数据到 config_meta
    for ws in workshops:
        add_meta_if_not_exists(db, "车间", ws)
    for team in teams:
        add_meta_if_not_exists(db, "班组", team)
    for nat in nationalities:
        # 添加国籍元数据
        exists = db.execute(select(config_meta).where(config_meta.c.meta_type == "国籍", config_meta.c.meta_value == nat.strip())).first()
        if not exists:
            db.execute(insert(config_meta).values(meta_type="国籍", meta_value=nat.strip()))
            db.commit()

    write_audit(db, "", "", "批量导入", old="", new=f"成功{success}条（新增{success-updated}，更新{updated}），跳过{len(skipped)}条，失败{len(errors)}条", operator=current_user["username"], ip=request.client.host)
    return {"imported": success, "updated": updated, "errors": errors, "skipped": skipped, "total_rows": len(df)}

@router.get("/api/employee/transfers")
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

@router.delete("/api/employee/transfers")
def delete_transfers(ids: List[int] = Query([]), db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Permission denied")
    if not ids:
        raise HTTPException(status_code=400, detail="No IDs provided")

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
                        raise HTTPException(status_code=403, detail="Permission denied: transfer record is for a workshop not in your scope")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Permission check failed: {str(e)}")

    try:
        del_stmt = delete(employee_transfers).where(employee_transfers.c.id.in_(ids))
        result = db.execute(del_stmt)
        db.commit()
        write_audit(db, "employee_transfers", "", "Bulk delete transfer records", old="", new=f"Deleted IDs: {ids}", operator=current_user["username"], ip="")
        return {"deleted": result.rowcount}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

# 仪表盘
@router.get("/api/dashboard")
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
    rows = db.execute(apply_ws_filter(
        select(employees.c.id_card, employees.c.nat_negara, employees.c.birth_date)
        .where(employees.c.status_status.contains("在职"))
    )).fetchall()
    for row in rows:
        birth = None
        # 优先从 id_card 提取出生日期
        if row.id_card:
            birth_str = extract_birth_date_from_id_card(row.id_card, row.nat_negara or "")
            if birth_str:
                try:
                    birth = datetime.strptime(birth_str, "%Y-%m-%d").date()
                except:
                    pass
        # 后备：id_card 无法解析时，使用 birth_date 字段
        if not birth and row.birth_date:
            try:
                birth = datetime.strptime(str(row.birth_date)[:10], "%Y-%m-%d").date()
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
    # Load and filter quota for the dashboard
    quota_raw = db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == "org_quota")).scalar()
    quota_total = 0
    quota_by_ws = {}
    if quota_raw:
        try:
            quota_data = json.loads(quota_raw)
            for k, v in quota_data.items():
                parts = k.split("::")
                if len(parts) >= 2:
                    ws = parts[1]
                    if not allowed or ws in allowed:
                        sum_val = sum(int(x) for x in v.values())
                        quota_total += sum_val
                        quota_by_ws[ws] = quota_by_ws.get(ws, 0) + sum_val
        except Exception as e:
            logger.error(f"Dashboard quota calculation failed: {e}")

    return {
        "total_active": active, "total_resigned": resigned,
        "total_quota": quota_total,
        "quota_by_ws": quota_by_ws,
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

# ---------- 员工生日提醒 ----------
@router.get("/api/employees/birthday_reminders")
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

# ---------- 组织架构接口 ----------
@router.get("/api/org_chart_data")
def get_org_chart_data(db=Depends(get_db), current_user=Depends(get_current_user)):
    """获取组织架构数据，人数始终来自在职员工实时统计。"""
    return build_org_chart(db, current_user)

@router.get("/api/org_chart_editable")
def get_org_chart_editable(db=Depends(get_db), current_user=Depends(get_current_user)):
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
    
    nodes = {}
    nodes["后勤三部"] = {"id": "root", "parent": "", "name": "后勤三部", "type": "root", "total": 0}
    
    for row in rows:
        ws = row.ws_bengkel or "未分配车间"
        team = row.team_grup or "未分配班组"
        cnt = row.cnt
        if ws not in nodes:
            nodes[ws] = {"id": ws, "parent": "后勤三部", "name": ws, "type": "workshop", "total": 0}
        if team not in nodes:
            nodes[team] = {"id": team, "parent": ws, "name": team, "type": "team", "total": 0}
        nodes[ws]["total"] += cnt
        nodes[team]["total"] += cnt
    
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

@router.get("/api/org_graph")
def get_org_graph(db=Depends(get_db), current_user=Depends(get_current_user)):
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
    
    root = {"key": "root", "name": "经理", "type": "经理", "children": [], "total": 0, "nations": {}}
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
        
        team_node = next((c for c in ws_node["children"] if c["name"] == team), None)
        if not team_node:
            team_node = {"key": f"team_{ws}_{team}", "name": team, "type": "班长", "children": [], "total": 0, "nations": {}}
            ws_node["children"].append(team_node)
        team_node["total"] += cnt
        team_node["nations"][nat] = team_node["nations"].get(nat, 0) + cnt
    
    root["children"] = list(workshops.values())
    root["total"] = sum(w["total"] for w in workshops.values())
    for w in workshops.values():
        for nat, cnt in w["nations"].items():
            root["nations"][nat] = root["nations"].get(nat, 0) + cnt
            
    all_nations = db.execute(select(employees.c.nat_negara).distinct()).fetchall()
    all_nations = [n[0] for n in all_nations if n[0]]
    
    return {"tree": root, "nations": all_nations}

@router.post("/org_chart/save_layout")
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

@router.post("/api/org_chart/reset_layout")
def reset_org_layout(db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can reset layout")
    db.execute(delete(config_meta).where(config_meta.c.meta_type == "org_layout"))
    db.commit()
    return {"status": "success"}

@router.get("/api/org_chart/quota")
def get_org_quota(db=Depends(get_db), current_user=Depends(get_current_user)):
    raw = db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == "org_quota")).scalar()
    if not raw:
        return {}
    try:
        quota_data = json.loads(raw)
    except:
        return {}
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                filtered_quota = {}
                for k, v in quota_data.items():
                    parts = k.split("::")
                    if len(parts) >= 2:
                        ws = parts[1]
                        if ws in allowed:
                            filtered_quota[k] = v
                return filtered_quota
        except Exception as e:
            logger.error(f"Error filtering quota: {e}")
    return quota_data

@router.post("/api/org_chart/quota")
def save_org_quota(data: dict, db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can save quota")
    
    ws_scope_str = current_user.get("ws_scope")
    if ws_scope_str:
        try:
            allowed = json.loads(ws_scope_str)
            if isinstance(allowed, list) and len(allowed) > 0:
                existing = db.execute(select(config_meta).where(config_meta.c.meta_type == "org_quota")).first()
                existing_data = {}
                if existing and existing.meta_value:
                    existing_data = json.loads(existing.meta_value)
                
                final_quota = {}
                # Keep keys outside the user's allowed scope
                for k, v in existing_data.items():
                    parts = k.split("::")
                    if len(parts) >= 2:
                        ws = parts[1]
                        if ws not in allowed:
                            final_quota[k] = v
                            
                # Merge user's updated keys within their allowed scope
                for k, v in data.items():
                    parts = k.split("::")
                    if len(parts) >= 2:
                        ws = parts[1]
                        if ws in allowed:
                            if any(int(val) > 0 for val in v.values()):
                                final_quota[k] = {nat: int(val) for nat, val in v.items() if int(val) > 0}
                data = final_quota
        except Exception as e:
            logger.error(f"Error merging quota on save: {e}")
            raise HTTPException(400, f"Error saving quota: {str(e)}")

    existing = db.execute(select(config_meta).where(config_meta.c.meta_type == "org_quota")).first()
    if existing:
        db.execute(update(config_meta).where(config_meta.c.id == existing.id).values(meta_value=json.dumps(data, ensure_ascii=False)))
    else:
        db.execute(insert(config_meta).values(meta_type="org_quota", meta_value=json.dumps(data, ensure_ascii=False)))
    db.commit()
    return {"status": "success"}

# ---------- 元数据维护接口 ----------
@router.get("/api/meta/国籍")
def get_nationalities(db=Depends(get_db)):
    rows = db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == "国籍")).fetchall()
    if rows:
        return [r[0] for r in rows]
    rows = db.execute(select(employees.c.nat_negara).distinct()).fetchall()
    return [r[0] for r in rows if r[0] and r[0].strip()]

@router.get("/api/meta/性别")
def get_genders(db=Depends(get_db)):
    rows = db.execute(select(employees.c.gender_jk).distinct()).fetchall()
    return [r[0] for r in rows if r[0] and r[0].strip()]

@router.get("/api/meta/宗教")
def get_religions(db=Depends(get_db)):
    rows = db.execute(select(employees.c.rel_agama).distinct()).fetchall()
    return [r[0] for r in rows if r[0] and r[0].strip()]

@router.get("/api/meta/{m_type}")
def get_meta(m_type: str, db=Depends(get_db)):
    return [v[0] for v in db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == m_type)).fetchall()]

@router.post("/api/meta/add")
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

@router.post("/api/meta/update")
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

@router.post("/api/meta/delete")
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

# ---------- Logo ----------
@router.post("/api/settings/logo")
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
            shutil = __import__("shutil")
            shutil.copyfileobj(file.file, f)
        return {"status": "success", "path": "/uploads/logos/logo.png"}
    except Exception as e:
        logger.error(f"Logo upload failed: {e}")
        raise HTTPException(500, f"Upload failed: {e}")

@router.get("/api/settings/logo")
def get_logo():
    filepath = os.path.join(settings.LOGO_DIR, "logo.png")
    if os.path.exists(filepath):
        return Response(content=open(filepath, "rb").read(), media_type="image/png")
    else:
        raise HTTPException(404, "Logo not found")

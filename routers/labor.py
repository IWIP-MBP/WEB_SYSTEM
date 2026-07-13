import json
import logging
from datetime import datetime, timedelta, date
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select, insert, update, delete, func, desc
from pydantic import BaseModel

from database import get_db
from models import labor_items, labor_inventory, labor_assignments, employees
from services.auth import get_current_user
from services.audit import write_audit
from services.labor_service import get_item_stock
from services.utils import get_employee

logger = logging.getLogger(__name__)
router = APIRouter()

class AssignmentUpdate(BaseModel):
    last_issue_date: Optional[str] = None
    cycle_days: Optional[int] = None
    status: Optional[str] = None

# ========== 劳保用品 API ==========
@router.get("/api/labor/items")
def get_labor_items(db=Depends(get_db), current_user=Depends(get_current_user)):
    return [dict(r._mapping) for r in db.execute(select(labor_items)).fetchall()]

@router.post("/api/labor/items")
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

@router.put("/api/labor/items/{item_id}")
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

@router.delete("/api/labor/items/{item_id}")
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

@router.get("/api/labor/inventory")
def get_inventory(db=Depends(get_db), item_id: int = None, current_user=Depends(get_current_user)):
    items = db.execute(select(labor_items)).fetchall()
    result = []
    for item in items:
        if item_id and item.id != item_id: continue
        result.append({"item": dict(item._mapping), "stock": get_item_stock(db, item.id)})
    return result

@router.post("/api/labor/inventory/in")
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

@router.post("/api/labor/inventory/out")
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

@router.get("/api/labor/assignments")
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

@router.get("/api/labor/assignments/report")
def get_assignments_report(
    db=Depends(get_db),
    current_user=Depends(get_current_user),
    start_date: str = None,
    end_date: str = None,
    item_id: int = None,
    workshop: str = None,
    team: str = None
):
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
        labor_assignments.c.quantity
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

@router.post("/api/labor/assignments/issue")
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

@router.post("/api/labor/assignments/{assignment_id}/cancel")
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

@router.put("/api/labor/assignments/{assignment_id}")
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

@router.delete("/api/labor/assignments/{assignment_id}")
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

@router.get("/api/labor/reminders")
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

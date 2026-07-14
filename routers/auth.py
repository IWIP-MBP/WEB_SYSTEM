import os
import json
import bcrypt
import asyncio
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from sqlalchemy import select, insert, update, delete, text
from database import get_db, SessionLocal
from models import users, active_sessions
from services.auth import create_token, get_current_user, verify_token
from services.audit import write_audit
from services.utils import get_mac_address_from_arp, clean_sessions, is_real_ip
from services.websocket_manager import manager, broadcast_online_users
from services.limiter import limiter
from pydantic import BaseModel
from typing import Optional

router = APIRouter()

class UserCreate(BaseModel):
    username: str
    password: str
    role: str = "viewer"
    ws_scope: Optional[str] = None

@router.post("/api/auth/login")
@limiter.limit("10/minute")
def login(username: str, password: str, request: Request, db=Depends(get_db)):
    user = db.execute(select(users).where(users.c.username == username)).first()
    if not user or not bcrypt.checkpw(password.encode('utf-8'), user.hashed_password.encode('utf-8')):
        raise HTTPException(401, detail="用户名或密码错误")
    token = create_token({"sub": username, "role": user.role})
    write_audit(db, "", "", "登录", old="{}", new=json.dumps({"username": username, "role": user.role}), reason="用户登录成功", operator=username, ip=request.client.host)
    return {"access_token": token, "token_type": "bearer", "username": username, "role": user.role, "ws_scope": user.ws_scope}

@router.get("/api/users")
def get_users(db=Depends(get_db), current_user=Depends(get_current_user)):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can list users")
    rows = db.execute(select(users.c.id, users.c.username, users.c.role, users.c.ws_scope)).fetchall()
    return {"users": [{"id": r.id, "username": r.username, "role": r.role, "ws_scope": r.ws_scope} for r in rows]}

@router.post("/api/users")
def create_user(
    request: Request,
    user: UserCreate,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can create users")
    existing = db.execute(select(users).where(users.c.username == user.username)).first()
    if existing:
        raise HTTPException(400, "Username already exists")
    hashed = bcrypt.hashpw(user.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    db.execute(insert(users).values(username=user.username, hashed_password=hashed, role=user.role, ws_scope=user.ws_scope))
    db.commit()
    write_audit(db, "", "", "新增用户", old="", new=f"{user.username} ({user.role}), ws_scope: {user.ws_scope}", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@router.put("/api/users/{user_id}/role")
def update_user_role(
    user_id: int,
    role: str,
    request: Request,
    ws_scope: Optional[str] = None,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can change roles/permissions")
    if role not in ["viewer", "admin"]:
        raise HTTPException(400, "Invalid role")
    target = db.execute(select(users).where(users.c.id == user_id)).first()
    if not target:
        raise HTTPException(404, "User not found")
    if target.username == current_user["username"]:
        raise HTTPException(400, "Cannot change your own role/permissions")
    old_role = target.role
    old_scope = target.ws_scope
    db.execute(update(users).where(users.c.id == user_id).values(role=role, ws_scope=ws_scope))
    db.commit()
    write_audit(db, "", "", "修改用户角色和权限", old=f"role: {old_role}, scope: {old_scope}", new=f"role: {role}, scope: {ws_scope}", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@router.delete("/api/users/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db=Depends(get_db),
    current_user=Depends(get_current_user)
):
    if current_user["role"] != "admin":
        raise HTTPException(403, "Only admin can delete users")
    target = db.execute(select(users).where(users.c.id == user_id)).first()
    if not target:
        raise HTTPException(404, "User not found")
    if target.username == current_user["username"]:
        raise HTTPException(400, "Cannot delete yourself")
    db.execute(delete(users).where(users.c.id == user_id))
    db.commit()
    write_audit(db, "", "", "删除用户", old=target.username, new="", operator=current_user["username"], ip=request.client.host)
    return {"status": "success"}

@router.post("/api/sessions/heartbeat")
def heartbeat(request: Request, mac: Optional[str] = None, db=Depends(get_db), current_user=Depends(get_current_user)):
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            client_ip = real_ip
        else:
            client_ip = request.client.host
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    detected_mac = get_mac_address_from_arp(client_ip)
    if not detected_mac or detected_mac == "00:00:00:00:00:00":
        detected_mac = mac or "UNKNOWN"
        
    db.execute(text("""
        INSERT INTO active_sessions (username, ip_address, mac_address, last_seen)
        VALUES (:u, :ip, :mac, :now)
        ON CONFLICT (username, ip_address) DO UPDATE
        SET last_seen = :now, mac_address = :mac
    """), {"u": current_user["username"], "ip": client_ip, "mac": detected_mac, "now": now})
    db.commit()
    clean_sessions(db, 3600)
    rows = db.execute(select(active_sessions.c.username, active_sessions.c.ip_address)).fetchall()
    return [{"user": r[0], "ip": r[1] if is_real_ip(r[1]) else ""} for r in rows]

@router.websocket("/ws/sessions")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    if not token:
        await websocket.close(code=1008)
        return
    payload = verify_token(token)
    if not payload:
        await websocket.close(code=1008)
        return
    
    username = payload.get("sub")
    
    forwarded = websocket.headers.get("X-Forwarded-For")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()
    else:
        real_ip = websocket.headers.get("X-Real-IP")
        if real_ip:
            client_ip = real_ip
        else:
            client_ip = websocket.client.host if websocket.client else "unknown"

    user_key = f"{username}@{client_ip}"
    await manager.connect(websocket, user_key)
    
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with SessionLocal() as db:
        db.execute(text("""
            INSERT INTO active_sessions (username, ip_address, mac_address, last_seen)
            VALUES (:u, :ip, :mac, :now)
            ON CONFLICT (username, ip_address) DO UPDATE
            SET last_seen = :now
        """), {"u": username, "ip": client_ip, "mac": "UNKNOWN", "now": now})
        db.commit()
    
    await broadcast_online_users()
    
    async def keep_alive():
        try:
            while True:
                await asyncio.sleep(20)
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                with SessionLocal() as db:
                    db.execute(text("""
                        UPDATE active_sessions 
                        SET last_seen = :now 
                        WHERE username = :u AND ip_address = :ip
                    """), {"u": username, "ip": client_ip, "now": now})
                    db.commit()
        except asyncio.CancelledError:
            pass
        except Exception:
            pass

    keep_alive_task = asyncio.create_task(keep_alive())

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        keep_alive_task.cancel()
        if manager.disconnect(websocket, user_key):
            with SessionLocal() as db:
                db.execute(text("""
                    DELETE FROM active_sessions 
                    WHERE username = :u AND ip_address = :ip
                """), {"u": username, "ip": client_ip})
                db.commit()
        await broadcast_online_users()

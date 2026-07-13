import logging

from fastapi import WebSocket
from starlette.websockets import WebSocketDisconnect
from sqlalchemy import select
from database import SessionLocal
from models import active_sessions
from services.utils import clean_sessions, is_real_ip

logger = logging.getLogger("uvicorn.error")

class ConnectionManager:
    def __init__(self):
        self.active_connections = {}

    async def connect(self, websocket: WebSocket, user_key: str):
        await websocket.accept()
        if user_key not in self.active_connections:
            self.active_connections[user_key] = []
        self.active_connections[user_key].append(websocket)

    def disconnect(self, websocket: WebSocket, user_key: str) -> bool:
        if user_key in self.active_connections:
            if websocket in self.active_connections[user_key]:
                self.active_connections[user_key].remove(websocket)
            if not self.active_connections[user_key]:
                del self.active_connections[user_key]
                return True
        return False

    async def broadcast(self, message: dict):
        for user_key, connections in list(self.active_connections.items()):
            for ws in list(connections):
                try:
                    await ws.send_json(message)
                except (WebSocketDisconnect, RuntimeError):
                    # 连接已断开：移除失效的 socket，避免其永久滞留在连接表中。
                    self.disconnect(ws, user_key)
                except Exception as e:
                    # 非预期的推送错误应记录下来，同时移除该连接以防阻塞后续广播。
                    logger.warning(f"向 WebSocket 推送消息失败，已移除该连接: {e}")
                    self.disconnect(ws, user_key)

manager = ConnectionManager()

async def broadcast_online_users():
    with SessionLocal() as db:
        clean_sessions(db, 60)
        rows = db.execute(select(active_sessions.c.username, active_sessions.c.ip_address)).fetchall()
        users_list = []
        for r in rows:
            ip = r[1]
            display_ip = ip if is_real_ip(ip) else ""
            users_list.append({"user": r[0], "ip": display_ip})
    
    await manager.broadcast({"type": "online_users", "data": users_list})

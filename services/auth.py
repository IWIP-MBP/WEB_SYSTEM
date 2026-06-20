from datetime import datetime, timedelta
from jose import jwt
from fastapi import Request, Depends, HTTPException
from sqlalchemy import select
from database import settings, get_db
from models import users

def verify_token(token: str):
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except:
        return None

def create_token(data: dict):
    expire = datetime.utcnow() + timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)
    data.update({"exp": expire})
    return jwt.encode(data, settings.SECRET_KEY, algorithm=settings.ALGORITHM)

def get_current_user(request: Request, db=Depends(get_db)):
    auth = request.headers.get("Authorization")
    if not auth or not auth.startswith("Bearer "):
        raise HTTPException(401, detail="Missing token")
    payload = verify_token(auth.split(" ")[1])
    if not payload:
        raise HTTPException(401, detail="Invalid token")
    user = db.execute(select(users).where(users.c.username == payload.get("sub"))).first()
    if not user:
        raise HTTPException(401, detail="User not found")
    return dict(user._mapping)

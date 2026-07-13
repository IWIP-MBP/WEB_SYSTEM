import json
from typing import Optional, List
from fastapi import HTTPException

# 车间数据权限（ws_scope）统一处理工具
# ws_scope 存储为 JSON 字符串，形如 '["车间A", "车间B"]'
# 语义约定：
#   - None            ：未配置或无法解析 → 不做任何车间过滤（拥有全部权限）
#   - []              ：空列表 → 无任何可见车间
#   - ["A", "B", ...] ：仅可见列表内的车间


def parse_ws_scope(current_user) -> Optional[List[str]]:
    """解析当前用户的车间权限范围。

    返回允许的车间列表；若未配置或解析失败则返回 None（视为不受限）。
    """
    if not current_user:
        return None
    ws_scope_str = current_user.get("ws_scope")
    if not ws_scope_str:
        return None
    try:
        allowed = json.loads(ws_scope_str)
    except Exception:
        return None
    if not isinstance(allowed, list):
        return None
    return allowed


def apply_ws_scope_filter(query, column, current_user, restrict_when_empty: bool = False):
    """将车间权限过滤应用到 SQLAlchemy 查询上。

    - 允许列表非空：追加 column.in_(allowed)
    - 允许列表为空且 restrict_when_empty=True：追加 column == "__NONE__"（隐藏全部）
    - 不受限（None）：原样返回
    """
    allowed = parse_ws_scope(current_user)
    if allowed:
        return query.where(column.in_(allowed))
    if restrict_when_empty and allowed is not None:
        return query.where(column == "__NONE__")
    return query


def ensure_workshop_in_scope(current_user, workshop, detail: str = "Permission denied for this workshop"):
    """校验指定车间是否在当前用户的权限范围内，越权时抛出 403。"""
    allowed = parse_ws_scope(current_user)
    if allowed is not None and workshop not in allowed:
        raise HTTPException(403, detail)

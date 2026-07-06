import json
import logging
from sqlalchemy import select, func
from fastapi import HTTPException
from models import employees, config_meta, employee_transfers

logger = logging.getLogger(__name__)

def load_org_layout(db):
    raw = db.execute(select(config_meta.c.meta_value).where(config_meta.c.meta_type == "org_layout")).scalar()
    if not raw:
        return {}
    try:
        saved = json.loads(raw)
    except Exception:
        logger.warning("Invalid org_layout JSON ignored")
        return {}
    if isinstance(saved, dict) and "nodes" in saved:
        saved = saved["nodes"]
    if not isinstance(saved, list):
        return {}
    result = {}
    for item in saved:
        if not isinstance(item, dict) or not item.get("key"):
            continue
        result[item["key"]] = {
            "display_name": item.get("display_name") or item.get("name") or item["key"],
            "type": item.get("type") or "",
            "parent": item.get("parent") or "",
            "sort": int(item.get("sort") or 0),
        }
    return result

def build_org_chart(db, current_user=None, query_date=None):
    if query_date:
        try:
            from datetime import datetime
            datetime.strptime(query_date, "%Y-%m-%d")
        except Exception:
            raise HTTPException(400, "Invalid query date format. Use YYYY-MM-DD.")
        
        query_datetime = query_date + " 23:59:59"
        from sqlalchemy import or_
        
        hired_before = or_(employees.c.hire_date == None, employees.c.hire_date <= query_date)
        not_resigned_yet = or_(~employees.c.status_status.contains("离职"), employees.c.resign_date > query_date)
        
        emp_stmt = select(
            employees.c.id_nomor,
            employees.c.name_nama,
            employees.c.ws_bengkel,
            employees.c.team_grup,
            employees.c.nat_negara
        ).where(hired_before).where(not_resigned_yet)
        
        emp_rows = db.execute(emp_stmt).fetchall()
        active_emps = [dict(r._mapping) for r in emp_rows]
        
        # Get transfers after query_datetime
        transfer_stmt = select(employee_transfers).where(employee_transfers.c.transfer_date > query_datetime)
        transfer_rows = db.execute(transfer_stmt).fetchall()
        
        # Sort ascending by transfer_date
        transfers = sorted([dict(r._mapping) for r in transfer_rows], key=lambda x: x["transfer_date"])
        
        earliest_ws_transfer = {}
        earliest_team_transfer = {}
        for t in transfers:
            id_num = t["id_nomor"]
            change_type = t["change_type"]
            old_val = t["old_value"]
            if change_type == "车间变更":
                if id_num not in earliest_ws_transfer:
                    earliest_ws_transfer[id_num] = old_val
            elif change_type == "班组变更":
                if id_num not in earliest_team_transfer:
                    earliest_team_transfer[id_num] = old_val
                    
        resolved_emps = []
        allowed_workshops = None
        if current_user:
            ws_scope_str = current_user.get("ws_scope")
            if ws_scope_str:
                try:
                    allowed_workshops = json.loads(ws_scope_str)
                    if not isinstance(allowed_workshops, list):
                        allowed_workshops = None
                except:
                    pass
                    
        for emp in active_emps:
            id_num = emp["id_nomor"]
            ws = earliest_ws_transfer.get(id_num, emp["ws_bengkel"])
            team = earliest_team_transfer.get(id_num, emp["team_grup"])
            
            # Apply ws_scope filter if configured
            if allowed_workshops is not None:
                if ws not in allowed_workshops:
                    continue
                    
            resolved_emps.append({
                "ws_bengkel": ws,
                "team_grup": team,
                "nat_negara": emp["nat_negara"]
            })
            
        counts = {}
        for emp in resolved_emps:
            ws = (emp["ws_bengkel"] or "未分配车间").strip() or "未分配车间"
            team = (emp["team_grup"] or "未分配班组").strip() or "未分配班组"
            nat = (emp["nat_negara"] or "未知").strip() or "未知"
            key = (ws, team, nat)
            counts[key] = counts.get(key, 0) + 1
            
        class PythonRow:
            def __init__(self, ws_bengkel, team_grup, nat_negara, cnt):
                self.ws_bengkel = ws_bengkel
                self.team_grup = team_grup
                self.nat_negara = nat_negara
                self.cnt = cnt
                
        rows = [PythonRow(k[0], k[1], k[2], v) for k, v in counts.items()]
    else:
        stmt = select(
            employees.c.ws_bengkel,
            employees.c.team_grup,
            employees.c.nat_negara,
            func.count().label("cnt")
        ).where(employees.c.status_status.contains("在职"))
        
        if current_user:
            ws_scope_str = current_user.get("ws_scope")
            if ws_scope_str:
                try:
                    allowed = json.loads(ws_scope_str)
                    if isinstance(allowed, list) and len(allowed) > 0:
                        stmt = stmt.where(employees.c.ws_bengkel.in_(allowed))
                except:
                    pass
        rows = db.execute(stmt.group_by(employees.c.ws_bengkel, employees.c.team_grup, employees.c.nat_negara)).fetchall()

    nodes = {
        "root": {
            "key": "root", "name": "后勤三部", "display_name": "后勤三部",
            "type": "部门", "parent": "", "level": 0, "total": 0, "nations": {}, "sort": 0
        }
    }

    for row in rows:
        ws = (row.ws_bengkel or "未分配车间").strip() or "未分配车间"
        team = (row.team_grup or "未分配班组").strip() or "未分配班组"
        nat = (row.nat_negara or "未知").strip() or "未知"
        cnt = int(row.cnt or 0)
        ws_key = f"ws::{ws}"
        team_key = f"team::{ws}::{team}"

        if ws_key not in nodes:
            nodes[ws_key] = {
                "key": ws_key, "name": ws, "display_name": ws,
                "type": "车间", "parent": "root", "level": 1,
                "total": 0, "nations": {}, "sort": len(nodes)
            }
        if team_key not in nodes:
            nodes[team_key] = {
                "key": team_key, "name": team, "display_name": team,
                "type": "班组", "parent": ws_key, "level": 2,
                "total": 0, "nations": {}, "sort": len(nodes)
            }

        for key in ("root", ws_key, team_key):
            nodes[key]["total"] += cnt
            nodes[key]["nations"][nat] = nodes[key]["nations"].get(nat, 0) + cnt

    saved = load_org_layout(db)
    valid_keys = set(nodes.keys())
    for key, override in saved.items():
        if key not in nodes:
            continue
        parent = override.get("parent", nodes[key]["parent"])
        if key == "root":
            parent = ""
        elif parent not in valid_keys or parent == key:
            parent = nodes[key]["parent"]
        nodes[key]["display_name"] = override.get("display_name") or nodes[key]["display_name"]
        nodes[key]["type"] = override.get("type") or nodes[key]["type"]
        nodes[key]["parent"] = parent
        nodes[key]["sort"] = override.get("sort", nodes[key]["sort"])

    for node in nodes.values():
        china_count = 0
        non_china_count = 0
        for nat, cnt in node.get("nations", {}).items():
            is_cn = any(x in nat.lower() for x in ["中国籍", "china", "cn"])
            if is_cn:
                china_count += cnt
            else:
                non_china_count += cnt
        if china_count > 0:
            val = non_china_count / china_count
            if val.is_integer():
                node["localization_rate"] = f"1:{int(val)}"
            else:
                node["localization_rate"] = f"1:{val:.1f}"
        else:
            node["localization_rate"] = "N/A"

    ordered = sorted(nodes.values(), key=lambda n: (n.get("level", 9), n.get("sort", 0), n["display_name"]))
    name_map = {n["key"]: n["display_name"] for n in ordered}
    for node in ordered:
        node["parent_name"] = name_map.get(node["parent"], "")

    edges = [{"from": n["parent"], "to": n["key"]} for n in ordered if n["parent"]]
    nations = sorted({nat for n in ordered for nat in n.get("nations", {})})
    return {"nodes": ordered, "edges": edges, "nations": nations}

def validate_org_nodes(nodes):
    if not isinstance(nodes, list) or not nodes:
        raise HTTPException(400, "组织架构数据不能为空")
    keys = [n.get("key") for n in nodes if isinstance(n, dict)]
    if len(keys) != len(set(keys)):
        raise HTTPException(400, "节点 ID 重复，请刷新后重试")
    key_set = set(keys)
    if "root" not in key_set:
        raise HTTPException(400, "缺少根节点 root")
    parent_map = {}
    for node in nodes:
        key = node.get("key")
        parent = node.get("parent") or ""
        if key == "root":
            parent = ""
        elif parent not in key_set:
            raise HTTPException(400, f"节点 {node.get('display_name') or key} 的父级无效")
        if parent == key:
            raise HTTPException(400, f"节点 {node.get('display_name') or key} 不能选择自己作为父级")
        parent_map[key] = parent

    for key in key_set:
        seen = set()
        cursor = key
        while parent_map.get(cursor):
            cursor = parent_map[cursor]
            if cursor in seen:
                raise HTTPException(400, "父级关系形成循环，请重新选择")
            seen.add(cursor)

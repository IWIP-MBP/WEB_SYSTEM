from sqlalchemy import Table, Column, Integer, String, UniqueConstraint
from database import metadata

# 员工表
employees = Table("employees", metadata,
    Column("id", Integer, primary_key=True),
    Column("ws_bengkel", String, index=True),
    Column("id_nomor", String, unique=True, nullable=False, index=True),
    Column("name_nama", String, nullable=False, index=True),
    Column("team_grup", String),
    Column("gender_jk", String),
    Column("pos_cn_jabatan", String),
    Column("pos_id_jabatan", String),
    Column("nat_negara", String),
    Column("rel_agama", String),
    Column("status_status", String, default="在职 / Aktif"),
    Column("resign_date", String),
    Column("remark_ket", String),
    Column("created_at", String),
    Column("updated_at", String),
    Column("birth_date", String),
    Column("id_card", String),
    Column("hire_date", String),
    Column("contract_end", String),
    Column("custom_fields", String, default="{}"),
    Column("company", String),
)

# 配置表
config_meta = Table("config_meta", metadata,
    Column("id", Integer, primary_key=True),
    Column("meta_type", String),
    Column("meta_value", String)
)

# 审计日志
log_audit = Table("log_audit", metadata,
    Column("id", Integer, primary_key=True),
    Column("op_date", String),
    Column("id_nomor", String),
    Column("name_nama", String),
    Column("type_tipe", String),
    Column("old_payload", String),
    Column("new_payload", String),
    Column("reason_alasan", String),
    Column("operator", String),
    Column("ip_address", String)
)

# 用户表
users = Table("users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String, unique=True, nullable=False),
    Column("hashed_password", String, nullable=False),
    Column("role", String, default="viewer"),
    Column("ws_scope", String, nullable=True)
)

# 在线会话
active_sessions = Table("active_sessions", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String),
    Column("ip_address", String),
    Column("mac_address", String),
    Column("last_seen", String),
    UniqueConstraint("username", "ip_address", name="uq_username_ip")
)

# 劳保用品
labor_items = Table("labor_items", metadata,
    Column("id", Integer, primary_key=True),
    Column("item_name", String, nullable=False),
    Column("item_spec", String),
    Column("unit", String),
    Column("default_cycle_days", Integer, default=90),
    Column("safety_stock", Integer, default=0),
)

# 劳保库存明细
labor_inventory = Table("labor_inventory", metadata,
    Column("id", Integer, primary_key=True),
    Column("item_id", Integer, nullable=False),
    Column("change_type", String),
    Column("quantity", Integer),
    Column("change_date", String),
    Column("remark", String)
)

# 劳保发放记录
labor_assignments = Table("labor_assignments", metadata,
    Column("id", Integer, primary_key=True),
    Column("id_nomor", String, nullable=False, index=True),
    Column("item_id", Integer, nullable=False),
    Column("last_issue_date", String),
    Column("cycle_days", Integer),
    Column("next_issue_date", String),
    Column("status", String, default="有效"),
    Column("quantity", Integer, default=0),
)

# 员工异动记录
employee_transfers = Table("employee_transfers", metadata,
    Column("id", Integer, primary_key=True),
    Column("transfer_date", String),
    Column("id_nomor", String),
    Column("name", String),
    Column("change_type", String),
    Column("old_value", String),
    Column("new_value", String),
    Column("operator", String)
)

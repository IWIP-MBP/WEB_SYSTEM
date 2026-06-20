from datetime import datetime
from sqlalchemy import insert
from models import log_audit

def write_audit(db, id_nomor, name, op_type, old="{}", new="{}", reason="", operator="", ip=""):
    db.execute(insert(log_audit).values(
        op_date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        id_nomor=id_nomor,
        name_nama=name,
        type_tipe=op_type,
        old_payload=old,
        new_payload=new,
        reason_alasan=reason,
        operator=operator,
        ip_address=ip
    ))
    db.commit()

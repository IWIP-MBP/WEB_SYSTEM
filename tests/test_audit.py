from sqlalchemy import select

import services.audit as audit
from models import log_audit


class TestWriteAudit:
    def test_writes_all_fields(self, db):
        audit.write_audit(
            db, "E1", "Alice", "UPDATE",
            old='{"a": 1}', new='{"a": 2}', reason="fix", operator="admin", ip="8.8.8.8",
        )
        rows = db.execute(select(log_audit)).fetchall()
        assert len(rows) == 1
        r = rows[0]
        assert (r.id_nomor, r.name_nama, r.type_tipe) == ("E1", "Alice", "UPDATE")
        assert (r.old_payload, r.new_payload, r.reason_alasan) == ('{"a": 1}', '{"a": 2}', "fix")
        assert (r.operator, r.ip_address) == ("admin", "8.8.8.8")
        assert r.op_date is not None

    def test_defaults(self, db):
        audit.write_audit(db, "E2", "Bob", "DELETE")
        r = db.execute(select(log_audit)).first()
        assert r.old_payload == "{}"
        assert r.new_payload == "{}"
        assert r.reason_alasan == ""
        assert r.operator == ""
        assert r.ip_address == ""

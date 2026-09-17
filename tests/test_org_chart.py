import json

import pytest
from fastapi import HTTPException
from sqlalchemy import insert

import services.org_chart as org
from models import config_meta, employee_transfers, employees


def _add_employee(db, id_nomor, ws, team, nat, status="在职 / Aktif", **extra):
    db.execute(insert(employees).values(
        id_nomor=id_nomor, name_nama=f"name-{id_nomor}",
        ws_bengkel=ws, team_grup=team, nat_negara=nat, status_status=status, **extra,
    ))


def _add_transfer(db, id_nomor, change_type, old_value, new_value, transfer_date):
    db.execute(insert(employee_transfers).values(
        id_nomor=id_nomor, name=f"name-{id_nomor}", change_type=change_type,
        old_value=old_value, new_value=new_value, transfer_date=transfer_date, operator="admin",
    ))


def _set_layout(db, layout):
    db.execute(insert(config_meta).values(meta_type="org_layout", meta_value=json.dumps(layout)))
    db.commit()


class TestValidateOrgNodes:
    def test_empty_rejected(self):
        with pytest.raises(HTTPException) as e:
            org.validate_org_nodes([])
        assert e.value.status_code == 400

    def test_not_a_list_rejected(self):
        with pytest.raises(HTTPException):
            org.validate_org_nodes({"key": "root"})

    def test_missing_root_rejected(self):
        with pytest.raises(HTTPException):
            org.validate_org_nodes([{"key": "a", "parent": ""}])

    def test_duplicate_keys_rejected(self):
        nodes = [{"key": "root", "parent": ""}, {"key": "a", "parent": "root"}, {"key": "a", "parent": "root"}]
        with pytest.raises(HTTPException):
            org.validate_org_nodes(nodes)

    def test_invalid_parent_rejected(self):
        nodes = [{"key": "root", "parent": ""}, {"key": "a", "parent": "ghost"}]
        with pytest.raises(HTTPException):
            org.validate_org_nodes(nodes)

    def test_self_parent_rejected(self):
        nodes = [{"key": "root", "parent": ""}, {"key": "a", "parent": "a"}]
        with pytest.raises(HTTPException):
            org.validate_org_nodes(nodes)

    def test_cycle_rejected(self):
        # root plus a->b->a cycle
        nodes = [
            {"key": "root", "parent": ""},
            {"key": "a", "parent": "b"},
            {"key": "b", "parent": "a"},
        ]
        with pytest.raises(HTTPException):
            org.validate_org_nodes(nodes)

    def test_valid_tree_passes(self):
        nodes = [
            {"key": "root", "parent": ""},
            {"key": "a", "parent": "root"},
            {"key": "b", "parent": "a"},
        ]
        # returns None without raising
        assert org.validate_org_nodes(nodes) is None


class TestLoadOrgLayout:
    def test_no_row_returns_empty(self, db):
        assert org.load_org_layout(db) == {}

    def test_invalid_json_returns_empty(self, db):
        db.execute(insert(config_meta).values(meta_type="org_layout", meta_value="{not valid"))
        db.commit()
        assert org.load_org_layout(db) == {}

    def test_list_of_nodes(self, db):
        _set_layout(db, [{"key": "ws::A", "display_name": "Workshop A", "type": "车间", "parent": "root", "sort": 3}])
        result = org.load_org_layout(db)
        assert result["ws::A"] == {
            "display_name": "Workshop A", "type": "车间", "parent": "root", "sort": 3,
        }

    def test_nodes_wrapped_in_dict(self, db):
        _set_layout(db, {"nodes": [{"key": "ws::A"}]})
        result = org.load_org_layout(db)
        assert result["ws::A"]["display_name"] == "ws::A"

    def test_items_without_key_skipped(self, db):
        _set_layout(db, [{"display_name": "no key"}, {"key": "ws::A"}])
        result = org.load_org_layout(db)
        assert list(result.keys()) == ["ws::A"]


class TestBuildOrgChart:
    def test_basic_hierarchy_and_totals(self, db):
        _add_employee(db, "E1", "WS1", "T1", "中国籍")
        _add_employee(db, "E2", "WS1", "T1", "印尼籍")
        _add_employee(db, "E3", "WS1", "T2", "中国籍")
        db.commit()

        chart = org.build_org_chart(db)
        by_key = {n["key"]: n for n in chart["nodes"]}

        assert by_key["root"]["total"] == 3
        assert by_key["ws::WS1"]["total"] == 3
        assert by_key["team::WS1::T1"]["total"] == 2
        assert by_key["team::WS1::T2"]["total"] == 1

    def test_localization_rate(self, db):
        # 2 non-chinese to 1 chinese -> 1:2
        _add_employee(db, "E1", "WS1", "T1", "中国籍")
        _add_employee(db, "E2", "WS1", "T1", "印尼籍")
        _add_employee(db, "E3", "WS1", "T1", "印尼籍")
        db.commit()

        chart = org.build_org_chart(db)
        root = next(n for n in chart["nodes"] if n["key"] == "root")
        assert root["localization_rate"] == "1:2"

    def test_localization_rate_na_without_chinese(self, db):
        _add_employee(db, "E1", "WS1", "T1", "印尼籍")
        db.commit()
        chart = org.build_org_chart(db)
        root = next(n for n in chart["nodes"] if n["key"] == "root")
        assert root["localization_rate"] == "N/A"

    def test_resigned_excluded(self, db):
        _add_employee(db, "E1", "WS1", "T1", "中国籍", status="离职 / Resign")
        db.commit()
        chart = org.build_org_chart(db)
        root = next(n for n in chart["nodes"] if n["key"] == "root")
        assert root["total"] == 0

    def test_ws_scope_filter(self, db):
        _add_employee(db, "E1", "WS1", "T1", "中国籍")
        _add_employee(db, "E2", "WS2", "T1", "中国籍")
        db.commit()
        chart = org.build_org_chart(db, current_user={"ws_scope": json.dumps(["WS1"])})
        keys = {n["key"] for n in chart["nodes"]}
        assert "ws::WS1" in keys
        assert "ws::WS2" not in keys

    def test_blank_workshop_defaults(self, db):
        _add_employee(db, "E1", "", "", "中国籍")
        db.commit()
        chart = org.build_org_chart(db)
        keys = {n["key"] for n in chart["nodes"]}
        assert "ws::未分配车间" in keys
        assert "team::未分配车间::未分配班组" in keys

    def test_invalid_query_date_raises(self, db):
        with pytest.raises(HTTPException) as e:
            org.build_org_chart(db, query_date="2024/01/01")
        assert e.value.status_code == 400

    def test_edges_reference_parents(self, db):
        _add_employee(db, "E1", "WS1", "T1", "中国籍")
        db.commit()
        chart = org.build_org_chart(db)
        edges = {(e["from"], e["to"]) for e in chart["edges"]}
        assert ("root", "ws::WS1") in edges
        assert ("ws::WS1", "team::WS1::T1") in edges


class TestBuildOrgChartHistorical:
    def test_query_date_uses_current_state_without_transfers(self, db):
        _add_employee(db, "E1", "WS1", "T1", "中国籍", hire_date="2024-01-01")
        db.commit()
        chart = org.build_org_chart(db, query_date="2024-06-01")
        by_key = {n["key"]: n for n in chart["nodes"]}
        assert by_key["ws::WS1"]["total"] == 1

    def test_query_date_resolves_historical_workshop(self, db):
        # Employee currently in WS2, but a workshop change happened after the
        # query date (moving from WS1 -> WS2), so historically they were in WS1.
        _add_employee(db, "E1", "WS2", "T1", "中国籍", hire_date="2024-01-01")
        _add_transfer(db, "E1", "车间变更", "WS1", "WS2", "2024-07-01 10:00:00")
        db.commit()
        chart = org.build_org_chart(db, query_date="2024-06-01")
        keys = {n["key"] for n in chart["nodes"]}
        assert "ws::WS1" in keys
        assert "ws::WS2" not in keys

    def test_query_date_excludes_not_yet_hired(self, db):
        _add_employee(db, "E1", "WS1", "T1", "中国籍", hire_date="2024-09-01")
        db.commit()
        chart = org.build_org_chart(db, query_date="2024-06-01")
        root = next(n for n in chart["nodes"] if n["key"] == "root")
        assert root["total"] == 0

    def test_query_date_excludes_already_resigned(self, db):
        _add_employee(
            db, "E1", "WS1", "T1", "中国籍",
            status="离职 / Resign", hire_date="2024-01-01", resign_date="2024-03-01",
        )
        db.commit()
        chart = org.build_org_chart(db, query_date="2024-06-01")
        root = next(n for n in chart["nodes"] if n["key"] == "root")
        assert root["total"] == 0

    def test_query_date_applies_ws_scope(self, db):
        _add_employee(db, "E1", "WS1", "T1", "中国籍", hire_date="2024-01-01")
        _add_employee(db, "E2", "WS2", "T1", "中国籍", hire_date="2024-01-01")
        db.commit()
        chart = org.build_org_chart(
            db, current_user={"ws_scope": json.dumps(["WS1"])}, query_date="2024-06-01",
        )
        keys = {n["key"] for n in chart["nodes"]}
        assert "ws::WS1" in keys
        assert "ws::WS2" not in keys

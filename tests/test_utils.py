from datetime import datetime, timedelta

import pytest
from sqlalchemy import insert, select

import services.utils as utils
from models import active_sessions, config_meta, employee_transfers, employees


class TestIsRealIp:
    @pytest.mark.parametrize("ip", ["", None, "   "])
    def test_empty_is_not_real(self, ip):
        assert utils.is_real_ip(ip) is False

    @pytest.mark.parametrize("ip", ["127.0.0.1", "::1", "localhost", "unknown", "UNKNOWN"])
    def test_loopback_and_placeholders_not_real(self, ip):
        assert utils.is_real_ip(ip) is False

    @pytest.mark.parametrize("ip", ["192.168.1.1", "10.0.0.5", "172.16.0.1", "172.31.255.255", "172.20.10.3"])
    def test_private_ranges_not_real(self, ip):
        assert utils.is_real_ip(ip) is False

    @pytest.mark.parametrize("ip", ["8.8.8.8", "203.0.113.5", "172.32.0.1", "172.15.0.1"])
    def test_public_ip_is_real(self, ip):
        assert utils.is_real_ip(ip) is True

    def test_surrounding_whitespace_is_stripped(self):
        assert utils.is_real_ip("  8.8.8.8  ") is True
        assert utils.is_real_ip("  127.0.0.1  ") is False


class TestCleanIdCard:
    def test_none_and_empty(self):
        assert utils.clean_id_card(None) is None
        assert utils.clean_id_card("") is None

    def test_strips_quotes_and_whitespace(self):
        assert utils.clean_id_card(" '110101199003070011' ") == "110101199003070011"

    def test_scientific_notation_from_excel(self):
        assert utils.clean_id_card("3.17e+15") == "3170000000000000"

    def test_removes_non_digit_non_x_chars(self):
        assert utils.clean_id_card("1101-0119 9003 07001X") == "11010119900307001X"

    def test_keeps_trailing_x_uppercased(self):
        assert utils.clean_id_card("11010119900307001x") == "11010119900307001X"

    def test_all_non_numeric_returns_none(self):
        assert utils.clean_id_card("abc-def") is None


class TestExtractBirthDateFromIdCard:
    def test_none_input(self):
        assert utils.extract_birth_date_from_id_card(None) is None

    def test_chinese_18_digit(self):
        assert utils.extract_birth_date_from_id_card("11010119900307001X") == "1990-03-07"

    def test_chinese_invalid_month_returns_none(self):
        assert utils.extract_birth_date_from_id_card("110101199013070011") is None

    def test_indonesian_16_digit_male(self):
        # DDMMYY = 070588 -> 1988-05-07 (assuming past century)
        assert utils.extract_birth_date_from_id_card("3201230705880001") == "1988-05-07"

    def test_indonesian_female_day_plus_40(self):
        # female day offset: 47 -> day 7
        result = utils.extract_birth_date_from_id_card("3201234705880002")
        assert result == "1988-05-07"

    def test_unrecognized_length_returns_none(self):
        assert utils.extract_birth_date_from_id_card("12345") is None

    def test_nationality_arg_is_ignored(self):
        a = utils.extract_birth_date_from_id_card("11010119900307001X")
        b = utils.extract_birth_date_from_id_card("11010119900307001X", nationality="中国籍")
        assert a == b == "1990-03-07"


class TestParseDbUrl:
    def test_parses_components(self, monkeypatch):
        monkeypatch.setattr(utils.settings, "DATABASE_URL", "postgresql://admin:secret@dbhost:6543/hr_system")
        parsed = utils.parse_db_url()
        assert parsed == {
            "host": "dbhost",
            "port": 6543,
            "user": "admin",
            "password": "secret",
            "dbname": "hr_system",
        }

    def test_default_port(self, monkeypatch):
        monkeypatch.setattr(utils.settings, "DATABASE_URL", "postgresql://admin:secret@dbhost/hr_system")
        assert utils.parse_db_url()["port"] == 5432


class TestCleanSessions:
    def test_removes_only_stale_sessions(self, db):
        now = datetime.now()
        fresh = now.strftime("%Y-%m-%d %H:%M:%S")
        stale = (now - timedelta(seconds=120)).strftime("%Y-%m-%d %H:%M:%S")
        db.execute(insert(active_sessions).values(username="fresh", ip_address="1.1.1.1", last_seen=fresh))
        db.execute(insert(active_sessions).values(username="stale", ip_address="2.2.2.2", last_seen=stale))
        db.commit()

        utils.clean_sessions(db, max_age_seconds=60)

        remaining = [r.username for r in db.execute(select(active_sessions.c.username)).fetchall()]
        assert remaining == ["fresh"]


class TestAddMetaIfNotExists:
    def test_inserts_new_value(self, db):
        utils.add_meta_if_not_exists(db, "workshop", "  Assembly  ")
        rows = db.execute(select(config_meta)).fetchall()
        assert len(rows) == 1
        assert rows[0].meta_value == "Assembly"

    def test_does_not_duplicate(self, db):
        utils.add_meta_if_not_exists(db, "workshop", "Assembly")
        utils.add_meta_if_not_exists(db, "workshop", "Assembly")
        assert len(db.execute(select(config_meta)).fetchall()) == 1

    @pytest.mark.parametrize("value", [None, "", "   "])
    def test_ignores_empty(self, db, value):
        utils.add_meta_if_not_exists(db, "workshop", value)
        assert db.execute(select(config_meta)).fetchall() == []


class TestRecordTransfer:
    def test_writes_transfer_row(self, db):
        utils.record_transfer(db, "E1", "Alice", "车间变更", "old_ws", "new_ws", "admin")
        rows = db.execute(select(employee_transfers)).fetchall()
        assert len(rows) == 1
        r = rows[0]
        assert (r.id_nomor, r.name, r.change_type, r.old_value, r.new_value, r.operator) == (
            "E1", "Alice", "车间变更", "old_ws", "new_ws", "admin",
        )
        assert r.transfer_date is not None


class TestGetEmployee:
    def test_returns_dict_when_found(self, db):
        db.execute(insert(employees).values(id_nomor="E1", name_nama="Alice", ws_bengkel="A"))
        db.commit()
        emp = utils.get_employee(db, "E1")
        assert emp["name_nama"] == "Alice"
        assert emp["ws_bengkel"] == "A"

    def test_returns_none_when_missing(self, db):
        assert utils.get_employee(db, "NOPE") is None


class TestGetMacAddressFromArp:
    def test_loopback_returns_local(self):
        assert utils.get_mac_address_from_arp("127.0.0.1") == "Local Loopback"
        assert utils.get_mac_address_from_arp(None) == "Local Loopback"

    def test_parses_mac_from_arp_command_output(self, monkeypatch):
        monkeypatch.setattr(utils.os.path, "exists", lambda p: False)
        monkeypatch.setattr(
            utils.subprocess,
            "check_output",
            lambda *a, **k: "? (9.9.9.9) at aa-bb-cc-dd-ee-ff [ether] on eth0",
        )
        assert utils.get_mac_address_from_arp("9.9.9.9") == "AA:BB:CC:DD:EE:FF"

    def test_returns_none_on_lookup_failure(self, monkeypatch):
        monkeypatch.setattr(utils.os.path, "exists", lambda p: False)

        def boom(*a, **k):
            raise OSError("arp not available")

        monkeypatch.setattr(utils.subprocess, "check_output", boom)
        assert utils.get_mac_address_from_arp("9.9.9.9") is None

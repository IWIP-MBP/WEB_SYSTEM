import io
from datetime import date, datetime

import pytest
from openpyxl import Workbook

import services.attendance_service as att


def _workbook_bytes(build):
    wb = Workbook()
    build(wb)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _write_rows(ws, rows):
    for r, row in enumerate(rows, start=1):
        for c, val in enumerate(row, start=1):
            ws.cell(row=r, column=c, value=val)


class TestParseOtHours:
    @pytest.mark.parametrize("val", ["", "-", "0", "0.0", "0h", None, float("nan")])
    def test_zero_like_values(self, val):
        assert att.parse_ot_hours(val) == 0.0

    def test_hours_only(self):
        assert att.parse_ot_hours("4h") == 4.0

    def test_hours_and_minutes(self):
        assert att.parse_ot_hours("8h30m") == pytest.approx(8.5)

    def test_minutes_only(self):
        assert att.parse_ot_hours("45m") == pytest.approx(0.75)

    def test_plain_float(self):
        assert att.parse_ot_hours("4.5") == pytest.approx(4.5)

    def test_numeric_input(self):
        assert att.parse_ot_hours(6) == 6.0

    def test_garbage_returns_zero(self):
        assert att.parse_ot_hours("abc") == 0.0


class TestCheckResignedLastMonth:
    def test_unknown_employee(self):
        assert att.check_resigned_last_month("E1", 2024, 6, {}) is False

    def test_no_resign_date(self):
        info = {"E1": {"earliest_resign": None}}
        assert att.check_resigned_last_month("E1", 2024, 6, info) is False

    def test_resigned_previous_year(self):
        info = {"E1": {"earliest_resign": date(2023, 12, 1)}}
        assert att.check_resigned_last_month("E1", 2024, 6, info) is True

    def test_resigned_earlier_this_year(self):
        info = {"E1": {"earliest_resign": date(2024, 3, 1)}}
        assert att.check_resigned_last_month("E1", 2024, 6, info) is True

    def test_resigned_current_month_not_before(self):
        info = {"E1": {"earliest_resign": date(2024, 6, 15)}}
        assert att.check_resigned_last_month("E1", 2024, 6, info) is False


class TestCompileEmpInfo:
    def test_computes_extremes(self):
        events = {
            "E1": {
                "out": {date(2024, 6, 10), date(2024, 6, 5)},
                "in": {date(2024, 6, 20), date(2024, 6, 25)},
                "resign": {date(2024, 7, 1), date(2024, 6, 30)},
                "leave": {date(2024, 6, 12)},
            }
        }
        info = att.compile_emp_info(events)["E1"]
        assert info["earliest_out"] == date(2024, 6, 5)
        assert info["latest_in"] == date(2024, 6, 25)
        assert info["earliest_resign"] == date(2024, 6, 30)
        assert info["leave_dates"] == {date(2024, 6, 12)}

    def test_empty_sets_yield_none(self):
        events = {"E1": {"out": set(), "in": set(), "resign": set(), "leave": set()}}
        info = att.compile_emp_info(events)["E1"]
        assert info["earliest_out"] is None
        assert info["latest_in"] is None
        assert info["earliest_resign"] is None


class TestCheckInactiveOrLeave:
    def _info(self, **overrides):
        base = {
            "earliest_resign": None,
            "earliest_out": None,
            "latest_in": None,
            "leave_dates": set(),
            "out_dates": set(),
            "in_dates": set(),
            "resign_dates": set(),
        }
        base.update(overrides)
        return {"E1": base}

    def test_unknown_employee(self):
        assert att.check_inactive_or_leave("E1", date(2024, 6, 1), {}) is False

    def test_on_or_after_resign(self):
        info = self._info(earliest_resign=date(2024, 6, 10))
        assert att.check_inactive_or_leave("E1", date(2024, 6, 10), info) is True
        assert att.check_inactive_or_leave("E1", date(2024, 6, 9), info) is False

    def test_within_out_in_window(self):
        info = self._info(earliest_out=date(2024, 6, 5), latest_in=date(2024, 6, 15))
        assert att.check_inactive_or_leave("E1", date(2024, 6, 10), info) is True
        assert att.check_inactive_or_leave("E1", date(2024, 6, 20), info) is False

    def test_only_in_date_means_inactive_before(self):
        info = self._info(latest_in=date(2024, 6, 15))
        assert att.check_inactive_or_leave("E1", date(2024, 6, 10), info) is True
        assert att.check_inactive_or_leave("E1", date(2024, 6, 16), info) is False

    def test_only_out_date_means_inactive_after(self):
        info = self._info(earliest_out=date(2024, 6, 15))
        assert att.check_inactive_or_leave("E1", date(2024, 6, 16), info) is True
        assert att.check_inactive_or_leave("E1", date(2024, 6, 14), info) is False

    def test_explicit_leave_day(self):
        info = self._info(leave_dates={date(2024, 6, 12)})
        assert att.check_inactive_or_leave("E1", date(2024, 6, 12), info) is True
        assert att.check_inactive_or_leave("E1", date(2024, 6, 13), info) is False


class TestExtractAttendanceEvents:
    def test_log_sheet_row_based(self):
        def build(wb):
            ws = wb.active
            _write_rows(ws, [
                ["工号", "日期", "状态"],
                ["1001", datetime(2024, 6, 5), "出园回国"],
                ["1001", datetime(2024, 6, 20), "出境入园"],
                ["1002", datetime(2024, 6, 10), "已离职"],
                ["1002", datetime(2024, 6, 8), "休假"],
            ])

        events = att.extract_attendance_events([_workbook_bytes(build)], 2024)
        assert events["1001"]["out"] == {date(2024, 6, 5)}
        assert events["1001"]["in"] == {date(2024, 6, 20)}
        assert events["1002"]["resign"] == {date(2024, 6, 10)}
        assert events["1002"]["leave"] == {date(2024, 6, 8)}

    def test_summary_sheet_column_based(self):
        def build(wb):
            ws = wb.active
            _write_rows(ws, [
                ["工号", "06-05", "06-20"],
                ["1001", "出园回国", "出境入园"],
            ])

        events = att.extract_attendance_events([_workbook_bytes(build)], 2024)
        assert events["1001"]["out"] == {date(2024, 6, 5)}
        assert events["1001"]["in"] == {date(2024, 6, 20)}

    def test_float_employee_id_normalized(self):
        def build(wb):
            ws = wb.active
            _write_rows(ws, [
                ["工号", "日期", "状态"],
                [1001.0, datetime(2024, 6, 5), "出园回国"],
            ])

        events = att.extract_attendance_events([_workbook_bytes(build)], 2024)
        assert "1001" in events

    def test_sheet_without_header_skipped(self):
        def build(wb):
            ws = wb.active
            _write_rows(ws, [["random", "data"], ["foo", "bar"]])

        events = att.extract_attendance_events([_workbook_bytes(build)], 2024)
        assert events == {}

    def test_placeholder_ids_ignored(self):
        def build(wb):
            ws = wb.active
            _write_rows(ws, [
                ["工号", "日期", "状态"],
                ["序号", datetime(2024, 6, 5), "出园回国"],
            ])

        events = att.extract_attendance_events([_workbook_bytes(build)], 2024)
        assert events == {}

    def test_corrupt_file_is_skipped(self):
        events = att.extract_attendance_events([b"not an excel file"], 2024)
        assert events == {}

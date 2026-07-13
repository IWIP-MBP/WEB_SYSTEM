import io
from datetime import datetime
import pandas as pd
from fastapi import Response

# Excel 导出通用工具与双语列名映射

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 员工花名册 / 成本报表字段的双语列名
EMPLOYEE_LABELS_ZH = {
    "id_nomor": "工号", "name_nama": "姓名", "company": "归属公司", "ws_bengkel": "车间", "team_grup": "班组",
    "gender_jk": "性别", "pos_cn_jabatan": "岗位(中)", "pos_id_jabatan": "岗位(印)",
    "nat_negara": "国籍", "rel_agama": "宗教", "id_card": "身份证号",
    "hire_date": "入职日期", "contract_end": "合同到期日", "status_status": "状态",
    "resign_date": "离职日期", "remark_ket": "备注", "resign_operator": "操作人", "resign_op_date": "操作日期"
}
EMPLOYEE_LABELS_ID = {
    "id_nomor": "ID", "name_nama": "Nama", "company": "Perusahaan", "ws_bengkel": "Bengkel", "team_grup": "Grup",
    "gender_jk": "JK", "pos_cn_jabatan": "Jabatan (CN)", "pos_id_jabatan": "Jabatan (ID)",
    "nat_negara": "Kewarganegaraan", "rel_agama": "Agama", "id_card": "Nomor KTP",
    "hire_date": "Tgl Masuk", "contract_end": "Kontrak Berakhir", "status_status": "Status",
    "resign_date": "Tgl Resign", "remark_ket": "Keterangan", "resign_operator": "Operator", "resign_op_date": "Tanggal Operasi"
}

# 审计日志字段的双语列名
LOG_LABELS_ZH = {
    "op_date": "操作时间", "id_nomor": "工号", "name_nama": "姓名",
    "type_tipe": "操作类型", "old_payload": "原数据", "new_payload": "新数据",
    "reason_alasan": "原因", "operator": "操作人", "ip_address": "IP"
}
LOG_LABELS_ID = {
    "op_date": "Waktu Operasi", "id_nomor": "ID Karyawan", "name_nama": "Nama Karyawan",
    "type_tipe": "Tipe Operasi", "old_payload": "Data Lama", "new_payload": "Data Baru",
    "reason_alasan": "Alasan", "operator": "Operator", "ip_address": "IP"
}


def timestamped_filename(prefix: str, ext: str = "xlsx") -> str:
    """生成带时间戳的文件名，如 employees_20240101_120000.xlsx。"""
    return f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"


def dataframe_to_xlsx_bytes(df: pd.DataFrame) -> bytes:
    """将 DataFrame 序列化为 xlsx 字节流。"""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return output.getvalue()


def xlsx_response(content: bytes, filename: str) -> Response:
    """构造下载 xlsx 文件的 FastAPI Response。"""
    return Response(
        content=content,
        media_type=XLSX_MEDIA_TYPE,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

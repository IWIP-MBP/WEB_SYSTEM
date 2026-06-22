import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Response
from sqlalchemy.orm import Session

from database import get_db
from services.auth import get_current_user
from services.audit import write_audit
from services.attendance_service import convert_attendance

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/api/attendance/convert")
def convert_attendance_endpoint(
    request: Request,
    files: List[UploadFile] = File(...),
    template: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    # 限制只有管理员角色（admin）能够进行考勤排休转换
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="您当前权限不足，无法执行此操作。")

    try:
        # 读取上传的文件字节
        attendance_files_bytes = []
        for file in files:
            content = file.file.read()
            if content:
                attendance_files_bytes.append(content)
        
        template_bytes = template.file.read()

        if not attendance_files_bytes:
            raise HTTPException(status_code=400, detail="没有上传任何有效的出勤明细文件")
        if not template_bytes:
            raise HTTPException(status_code=400, detail="没有上传有效的排休模板文件")

        # 将上传的文件保存到本地目录以进行容器内诊断
        import os
        os.makedirs("uploads", exist_ok=True)
        try:
            with open("uploads/received_template.xlsx", "wb") as f:
                f.write(template_bytes)
            for idx, content in enumerate(attendance_files_bytes):
                with open(f"uploads/received_log_{idx}.xlsx", "wb") as f:
                    f.write(content)
            logger.info("已成功在容器中保存上传的调试副本。")
        except Exception as save_err:
            logger.error(f"保存调试文件副本失败: {save_err}")

        # 调用核心算法进行转换
        out_bytes, year, month, updated_count = convert_attendance(
            attendance_files_bytes, template_bytes
        )

        # 写入系统审计日志
        try:
            write_audit(
                db=db,
                id_nomor="",
                name="",
                op_type="考勤排休转换",
                old="{}",
                new="{}",
                reason=f"转换【{year}年{month}月】调休排班数据，覆盖 {updated_count} 人",
                operator=current_user["username"],
                ip=request.client.host
            )
        except Exception as audit_err:
            logger.error(f"写入审计日志失败: {audit_err}")

        # 返回生成的 Excel 文件
        filename = f"attendance_converted_{year}_{month}.xlsx"
        return Response(
            content=out_bytes,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except ValueError as val_err:
        logger.warning(f"考勤转换参数校验失败: {val_err}")
        raise HTTPException(status_code=400, detail=str(val_err))
    except Exception as e:
        logger.error(f"考勤转换执行中发生未知异常: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"转换服务发生未知内部错误: {str(e)}")

import os
import sys
import openpyxl
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.drawing.image import Image
from PIL import Image as PILImage

# Set stdout encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PIC_DIR = r"d:\WEB_SYSTEM\PIC"
TEMPLATE_PATH = os.path.join(PIC_DIR, "模板.xlsx")
OUTPUT_PATH = os.path.join(PIC_DIR, "后勤三部精益管理降本增效提案汇总表.xlsx")

def fill_excel_template():
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "精益管理降本增效提案表"

    # Define headers matching user's template
    headers = [
        "序号", 
        "车间", 
        "提案名称", 
        "提案分类", 
        "提案人/负责人", 
        "改善前现状及存在的问题", 
        "改善思路与方案", 
        "改善预期目标", 
        "改善前照片"
    ]

    # Header styling
    header_fill = PatternFill(start_color="0F766E", end_color="0F766E", fill_type="solid") # Dark teal
    header_font = Font(name="Microsoft YaHei", size=11, bold=True, color="FFFFFF")
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    border_thin = Border(
        left=Side(style='thin', color='CBD5E1'),
        right=Side(style='thin', color='CBD5E1'),
        top=Side(style='thin', color='CBD5E1'),
        bottom=Side(style='thin', color='CBD5E1')
    )

    ws.append(headers)
    ws.row_dimensions[1].height = 28

    for col_idx in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=col_idx)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = border_thin

    # Proposal data rows
    proposals = [
        {
            "seq": 1,
            "workshop": "后勤三部（综合办）",
            "name": "人事花名册全流程数字化与秒级全局检索改善",
            "category": "流程优化 / 消除等待浪费",
            "owner": "后勤三部 / 张金刚",
            "problem": "1. 过去依赖多个Excel手工台账分散维护2000+名员工花名册，跨部门查询耗时数小时；\n2. 传统输入法存在中断、光标丢失、高页码结果空白等严重缺陷；\n3. 岗位与员工状态多语言未标准化，易引发对账错误。",
            "solution": "1. 研发上线 Web 数字化花名册，优化原生输入法与光标融合，实现中文回车提交与极速筛选；\n2. 增加按车间、归属公司、员工状态多维筛选与一键 Excel 导出；\n3. 后端集成多语言规范词典，支持中印双语一键无缝切换。",
            "target": "1. 花名册查询响应时间从数小时缩短至 1秒内（效率提升95%）；\n2. 消除手工台账版本混乱与录报错漏，数据准确率达到 100%。",
            "img": "03_员工花名册全局检索.png"
        },
        {
            "seq": 2,
            "workshop": "后勤三部（人力运营）",
            "name": "入职与离职双趋势同屏对比及用工平稳度精益调控",
            "category": "目视化管理 / 用工成本控制",
            "owner": "后勤三部 / 人力资源组",
            "problem": "1. 过去仅有单向离职统计，无法同屏对比流入与流出走势；\n2. 用工波动缺乏预警，人员大批流失后才紧急招聘，增加高昂溢价招聘与培训成本；\n3. 离职办理缺乏操作人跟踪，存在误注销风险。",
            "solution": "1. 数据看板上线“入职与离职双趋势”动态折线图，同屏直观展现人员流动走势；\n2. 实时聚合各车间/归属公司人数分布与定编人数（Active vs Quota）对比图；\n3. 离职办理增加操作人（resign_operator）自动追溯留痕。",
            "target": "1. 提前1-2个月预判用工缺口，平抑用工波动，降低紧急招聘溢价成本 15%+；\n2. 离职办理全流程透明留痕，误操作与违规注销率降至 0%。",
            "img": "02_数据看板与双趋势图.png"
        },
        {
            "seq": 3,
            "workshop": "后勤三部（组织合规）",
            "name": "动态组织架构图谱渲染与本土化率合规指标监控",
            "category": "风险防控 / 合规管理",
            "owner": "后勤三部 / 组织合规组",
            "problem": "1. 印尼项目部中籍与非中籍（印尼籍）员工比例受当地劳工法严格监管，过去人工月底倒推计算费时且滞后；\n2. 架构图更新困难，无法查询历史某节点的架构演变。",
            "solution": "1. 研发前端动态渲染多层级组织架构树状图/烈日图；\n2. 顶部显著卡片新增“本土化率”核心指标，算法基于国籍自动秒级计算；\n3. 支持“历史组织架构查询”，任意日期一键回溯并演算历史本土化率。",
            "target": "1. 跨国用工本土化率计算由月底倒推升级为毫秒级实时监控；\n2. 确保园区用工 100% 符合当地法律监管要求，规避合规诉讼与罚款风险。",
            "img": "04_组织架构与本土化率.png"
        },
        {
            "seq": 4,
            "workshop": "后勤三部（物资仓储）",
            "name": "劳保用品到期自动预警与领用配额全生命周期管理",
            "category": "物资零浪费 / 降本增效",
            "owner": "后勤三部 / 劳保物资组",
            "problem": "1. 劳保用品（安全帽、防护服、劳保鞋）依赖纸质签单，易出现超领、重复领用或离职未交旧领新；\n2. 缺乏到期预警机制，容易造成物料死库存或安全隐患。",
            "solution": "1. 建立劳保出入库、发放登记与撤销数据库全生命周期履历；\n2. 上线“到期未换发自动提醒看板”，按默认使用周期自动计算剩余天数并预警提示；\n3. 嵌入同员工同物品“旧记录自动标记已换发”与库存校验锁。",
            "target": "1. 杜绝无序超领与重复领用，预计降低劳保耗材年度损耗 15%-25%（年节约约 8万-10万元）；\n2. 劳保物资周转效率提升 50%，实现精准按需领用。",
            "img": "06_劳保用品全生命周期管理.png"
        },
        {
            "seq": 5,
            "workshop": "后勤三部（考勤结算）",
            "name": "考勤日志与排休模板自动化解析比对与极速导出",
            "category": "流程自动化 / 消除重工浪费",
            "owner": "后勤三部 / 考勤组",
            "problem": "1. 每月人工核对数千名员工原始打卡日志与排休模板极其繁重，需耗费2-3名专员连续工作3天；\n2. 手工对账容易看错漏看，引发薪酬计算争议。",
            "solution": "1. 后端编写考勤自动解析算法引擎，支持多月份原始日志批量上传与模板自动匹配；\n2. 秒级输出转换结果，对异常打卡、缺卡与排休不符自动标红；\n3. 极速生成并提供一键可下载的 Excel 对账报表。",
            "target": "1. 考勤结算工时从 3天（24小时）缩短至 15分钟（效率提升97%）；\n2. 考勤计算零差错，薪酬争议发生率降至 0%。",
            "img": "07_考勤自动对账与转换.png"
        },
        {
            "seq": 6,
            "workshop": "后勤三部（信息运维）",
            "name": "操作全流程审计留痕与 PostgreSQL 每日自动化灾备体系",
            "category": "IT安全与运维降本 / 风险防范",
            "owner": "后勤三部 / 系统管理员",
            "problem": "1. 缺乏敏感操作审计留痕，误删误改无法追溯；\n2. 依赖人工手动备份，存在磁盘损坏或容器重建导致数据丢失隐患；\n3. 采购商业灾备软件需要昂贵额外预算。",
            "solution": "1. 系统引入全动作审计日志，严格隔离日志清空与恢复权限（仅 admin 可用）；\n2. 后台集成调度器，每日 02:00 全自动导出加密备份至本地硬盘并自动清理过期文件；\n3. 集成编码智能检测转码（GBK/UTF-8）与数据库模式自动升级。",
            "target": "1. 彻底防范数据丢失风险，备份恢复成功率达到 100%；\n2. 零专职 DBA 运维成本，节省商业灾备预算约 15万元/年。",
            "img": "08_系统审计日志与安全管控.png"
        }
    ]

    font_data = Font(name="Microsoft YaHei", size=10)
    font_bold = Font(name="Microsoft YaHei", size=10, bold=True)
    align_center = Alignment(horizontal="center", vertical="center", wrap_text=True)
    align_left = Alignment(horizontal="left", vertical="center", wrap_text=True)
    fill_zebra = PatternFill(start_color="F8FAFC", end_color="F8FAFC", fill_type="solid")

    row_start = 2
    for idx, p in enumerate(proposals):
        row_num = row_start + idx
        ws.row_dimensions[row_num].height = 140 # High row to fit thumbnail image

        ws.cell(row=row_num, column=1, value=p["seq"]).alignment = align_center
        ws.cell(row=row_num, column=2, value=p["workshop"]).alignment = align_center
        ws.cell(row=row_num, column=3, value=p["name"]).alignment = align_left
        ws.cell(row=row_num, column=4, value=p["category"]).alignment = align_center
        ws.cell(row=row_num, column=5, value=p["owner"]).alignment = align_center
        ws.cell(row=row_num, column=6, value=p["problem"]).alignment = align_left
        ws.cell(row=row_num, column=7, value=p["solution"]).alignment = align_left
        ws.cell(row=row_num, column=8, value=p["target"]).alignment = align_left
        ws.cell(row=row_num, column=9, value=f"[系统截图: {p['img']}]").alignment = align_center

        for col_idx in range(1, 10):
            cell = ws.cell(row=row_num, column=col_idx)
            cell.font = font_data
            cell.border = border_thin
            if idx % 2 == 1:
                cell.fill = fill_zebra

        ws.cell(row=row_num, column=3).font = font_bold

        # Add image to column I if exists
        img_path = os.path.join(PIC_DIR, p["img"])
        if os.path.exists(img_path):
            try:
                # Resize image for thumbnail insertion
                pil_img = PILImage.open(img_path)
                # Keep aspect ratio, scale width to ~280px
                aspect = pil_img.height / pil_img.width
                new_w = 260
                new_h = int(new_w * aspect)
                
                img_obj = Image(img_path)
                img_obj.width = new_w
                img_obj.height = new_h
                
                # Position image in cell I{row_num}
                cell_address = f"I{row_num}"
                ws.add_image(img_obj, cell_address)
            except Exception as ex:
                print(f"Error adding image {p['img']}: {ex}")

    # Set column widths
    col_widths = {
        "A": 8,
        "B": 18,
        "C": 28,
        "D": 22,
        "E": 18,
        "F": 35,
        "G": 38,
        "H": 35,
        "I": 36
    }
    for col_letter, width in col_widths.items():
        ws.column_dimensions[col_letter].width = width

    # Save to both TEMPLATE_PATH and OUTPUT_PATH
    wb.save(TEMPLATE_PATH)
    print(f"Saved filled template to: {TEMPLATE_PATH}")
    wb.save(OUTPUT_PATH)
    print(f"Saved copy to: {OUTPUT_PATH}")

if __name__ == "__main__":
    fill_excel_template()

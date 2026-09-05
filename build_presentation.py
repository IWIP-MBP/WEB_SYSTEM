import os
import sys
import pptx
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from pptx.dml.color import RGBColor

# Ensure UTF-8 output encoding
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PIC_DIR = r"d:\WEB_SYSTEM\PIC"
PPT_OUTPUT_PATH = os.path.join(PIC_DIR, "后勤三部人事与劳保管理系统功能介绍.pptx")

# Color Palette (Dark Modern Tech Theme)
COLOR_DARK_BG = RGBColor(15, 23, 42)       # Slate 900 #0f172a
COLOR_CARD_BG = RGBColor(30, 41, 59)      # Slate 800 #1e293b
COLOR_PRIMARY = RGBColor(15, 118, 110)    # Teal 700 #0f766e
COLOR_ACCENT = RGBColor(37, 99, 235)      # Blue 600 #2563eb
COLOR_TEXT_MAIN = RGBColor(248, 250, 252) # Slate 50 #f8fafc
COLOR_TEXT_MUTED = RGBColor(148, 163, 184)# Slate 400 #94a3b8
COLOR_GOLD = RGBColor(245, 158, 11)       # Amber 500 #f59e0b
COLOR_WHITE = RGBColor(255, 255, 255)

def add_background(slide, prs, fill_color=COLOR_DARK_BG):
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, prs.slide_width, prs.slide_height)
    bg.fill.solid()
    bg.fill.fore_color.rgb = fill_color
    bg.line.fill.background()
    return bg

def add_header(slide, title_text, category_text="后勤三部人事与劳保管理系统 · 功能汇报"):
    # Header bar text box
    tb = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.733), Inches(0.9))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_top = tf.margin_right = tf.margin_bottom = 0
    
    p_cat = tf.paragraphs[0]
    p_cat.text = category_text.upper()
    p_cat.font.size = Pt(10)
    p_cat.font.bold = True
    p_cat.font.color.rgb = COLOR_GOLD
    p_cat.font.name = "Microsoft YaHei"
    
    p_title = tf.add_paragraph()
    p_title.text = title_text
    p_title.font.size = Pt(22)
    p_title.font.bold = True
    p_title.font.color.rgb = COLOR_TEXT_MAIN
    p_title.font.name = "Microsoft YaHei"
    p_title.space_before = Pt(4)

def build_ppt():
    prs = Presentation()
    prs.slide_width = Inches(13.333) # 16:9 Widescreen
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6] # Blank slide layout

    # ==================== SLIDE 1: Cover Slide ====================
    slide1 = prs.slides.add_slide(blank_layout)
    add_background(slide1, prs, COLOR_DARK_BG)

    # Accent decorative bar
    bar = slide1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(2.2), Inches(0.15), Inches(3.2))
    bar.fill.solid()
    bar.fill.fore_color.rgb = COLOR_PRIMARY
    bar.line.fill.background()

    # Title box
    tb1 = slide1.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(11.0), Inches(3.5))
    tf1 = tb1.text_frame
    tf1.word_wrap = True

    p0 = tf1.paragraphs[0]
    p0.text = "后勤三部精益管理与数字化建设成果"
    p0.font.size = Pt(14)
    p0.font.bold = True
    p0.font.color.rgb = COLOR_GOLD
    p0.font.name = "Microsoft YaHei"

    p1 = tf1.add_paragraph()
    p1.text = "人事与劳保管理系统功能汇报"
    p1.font.size = Pt(36)
    p1.font.bold = True
    p1.font.color.rgb = COLOR_TEXT_MAIN
    p1.font.name = "Microsoft YaHei"
    p1.space_before = Pt(10)

    p2 = tf1.add_paragraph()
    p2.text = "消除管理浪费 · 提升运营效率 · 实时精准掌控 · 保障数据安全"
    p2.font.size = Pt(16)
    p2.font.color.rgb = COLOR_TEXT_MUTED
    p2.font.name = "Microsoft YaHei"
    p2.space_before = Pt(14)

    # Footer presenter info
    tb_foot = slide1.shapes.add_textbox(Inches(1.2), Inches(5.8), Inches(10.0), Inches(1.0))
    tf_foot = tb_foot.text_frame
    pf = tf_foot.paragraphs[0]
    pf.text = "汇报部门：后勤三部  |  汇报人：张金刚  |  版本：V2.0"
    pf.font.size = Pt(12)
    pf.font.color.rgb = COLOR_TEXT_MUTED
    pf.font.name = "Microsoft YaHei"

    # ==================== SLIDE 2: Agenda ====================
    slide2 = prs.slides.add_slide(blank_layout)
    add_background(slide2, prs, COLOR_DARK_BG)
    add_header(slide2, "汇报目录与内容纲要", "AGENDA")

    agenda_items = [
        ("01", "系统研发背景与痛点分析", "手工台账效率低、劳保无到期提醒、合规计算困难、数据存在丢失风险。"),
        ("02", "精益降本与核心价值概览", "围绕效率提升、准确性、实时性与数据安全性四大支柱展开精益改善。"),
        ("03", "核心业务功能与界面实拍", "实拍演示数据看板、花名册检索、组织架构、劳保管理、考勤对账与灾备。"),
        ("04", "降本增效成果与总结建议", "量化效益总结（0软件授权费、节约劳保20%、考勤效率提升97%）。")
    ]

    lefts = [Inches(0.8), Inches(6.8), Inches(0.8), Inches(6.8)]
    tops = [Inches(1.8), Inches(1.8), Inches(4.4), Inches(4.4)]
    widths = Inches(5.7)
    heights = Inches(2.2)

    for i, (num, title, desc) in enumerate(agenda_items):
        card = slide2.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, lefts[i], tops[i], widths, heights)
        card.fill.solid()
        card.fill.fore_color.rgb = COLOR_CARD_BG
        card.line.color.rgb = COLOR_PRIMARY
        
        tb = slide2.shapes.add_textbox(lefts[i] + Inches(0.2), tops[i] + Inches(0.2), widths - Inches(0.4), heights - Inches(0.4))
        tf = tb.text_frame
        tf.word_wrap = True
        
        p_num = tf.paragraphs[0]
        p_num.text = f"{num}. {title}"
        p_num.font.size = Pt(18)
        p_num.font.bold = True
        p_num.font.color.rgb = COLOR_GOLD
        p_num.font.name = "Microsoft YaHei"
        
        p_desc = tf.add_paragraph()
        p_desc.text = desc
        p_desc.font.size = Pt(13)
        p_desc.font.color.rgb = COLOR_TEXT_MUTED
        p_desc.font.name = "Microsoft YaHei"
        p_desc.space_before = Pt(8)

    # Function to create feature slides with text on left and image on right
    def add_feature_slide(title, category, highlights, img_name):
        slide = prs.slides.add_slide(blank_layout)
        add_background(slide, prs, COLOR_DARK_BG)
        add_header(slide, title, category)

        # Left text card
        left_w = Inches(4.6)
        card_l = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(0.8), Inches(1.5), left_w, Inches(5.4))
        card_l.fill.solid()
        card_l.fill.fore_color.rgb = COLOR_CARD_BG
        card_l.line.color.rgb = COLOR_PRIMARY

        tb_l = slide.shapes.add_textbox(Inches(1.0), Inches(1.7), left_w - Inches(0.4), Inches(5.0))
        tf_l = tb_l.text_frame
        tf_l.word_wrap = True

        for idx, (label, val) in enumerate(highlights):
            p_lbl = tf_l.paragraphs[0] if idx == 0 else tf_l.add_paragraph()
            p_lbl.text = f"● {label}"
            p_lbl.font.size = Pt(15)
            p_lbl.font.bold = True
            p_lbl.font.color.rgb = COLOR_GOLD
            p_lbl.font.name = "Microsoft YaHei"
            if idx > 0:
                p_lbl.space_before = Pt(14)

            p_val = tf_l.add_paragraph()
            p_val.text = val
            p_val.font.size = Pt(12)
            p_val.font.color.rgb = COLOR_TEXT_MAIN
            p_val.font.name = "Microsoft YaHei"
            p_val.space_before = Pt(4)

        # Right image card & actual screenshot
        img_path = os.path.join(PIC_DIR, img_name)
        if os.path.exists(img_path):
            img_x = Inches(5.6)
            img_y = Inches(1.5)
            img_w = Inches(6.9)
            img_h = Inches(5.4)

            # Background border frame for image
            frame = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, img_x, img_y, img_w, img_h)
            frame.fill.solid()
            frame.fill.fore_color.rgb = COLOR_CARD_BG
            frame.line.color.rgb = COLOR_ACCENT

            # Insert real image slightly inside frame
            slide.shapes.add_picture(img_path, img_x + Inches(0.1), img_y + Inches(0.1), width=img_w - Inches(0.2))

        return slide

    # ==================== SLIDE 3: Dashboard ====================
    add_feature_slide(
        "用工数据看板与入职/离职双趋势分析",
        "模块01 · 实时用工监控",
        [
            ("使用用途", "同屏直观展现月度新入职与离职人数流动走势，实时监控各车间在职人数与定编对比（Active vs Quota）。"),
            ("精益优点", "提前1-2个月预判用工缺口，平抑用工波动，降低紧急招聘与培训成本15%+。"),
            ("核心指标", "全员流动率、各车间定编达成率、双趋势流动对比秒级动态呈现。")
        ],
        "02_数据看板与双趋势图.png"
    )

    # ==================== SLIDE 4: Employee Roster ====================
    add_feature_slide(
        "员工花名册全局检索与多语言标准词典",
        "模块02 · 极速数据检索",
        [
            ("使用用途", "提供全局模糊检索、车间/公司/状态联合筛选、离职流转办理及标准 Excel 报表一键导出。"),
            ("精益优点", "查询响应时间由数小时缩短至1秒内（效率提升95%），中印双语岗位无缝切换，彻底消除录错。"),
            ("安全保护", "脱敏显示身份证号，离职办理自动追溯记录 `resign_operator` 操作人。")
        ],
        "03_员工花名册全局检索.png"
    )

    # ==================== SLIDE 5: Org Chart ====================
    add_feature_slide(
        "动态组织架构与本土化率指标实时监控",
        "模块03 · 跨国合规管理",
        [
            ("使用用途", "动态渲染多层级树状图/烈日图组织架构，首位高亮卡片实时计算并展示“本土化率”。"),
            ("精益优点", "跨国用工本土化率计算升级为秒级实时监控，确保园区用工100%符合当地法规，规避合规风险。"),
            ("特色功能", "支持“历史组织架构查询”，选择任意历史日期自动回溯架构与历史本土化率。")
        ],
        "04_组织架构与本土化率.png"
    )

    # ==================== SLIDE 6: PPE Management ====================
    add_feature_slide(
        "劳保用品全生命周期管理与到期预警",
        "模块04 · 物资防浪费控成本",
        [
            ("使用用途", "建立劳保出入库台账、个人领用分配及“到期未换发自动提醒看板”，设置领用周期与配额。"),
            ("精益优点", "杜绝无序超领与重复领用，预计降低劳保耗材年度损耗15%-25%（年节约约8万-10万元）。"),
            ("智能锁死", "同员工同物品再次发放自动将旧记录标记为已换发，避免多发漏发。")
        ],
        "06_劳保用品全生命周期管理.png"
    )

    # ==================== SLIDE 7: Attendance Conversion ====================
    add_feature_slide(
        "考勤日志与排休模板自动化解析比对",
        "模块05 · 考勤高效极速对账",
        [
            ("使用用途", "导入原始打卡日志与排休模板，后端算法引擎秒级完成考勤比对、缺卡标红与转换。"),
            ("精益优点", "考勤结算工时从3天（24小时）缩短至15分钟（效率提升97%），考勤核算100%零差错。"),
            ("结果导出", "对账结果一键导出 Excel，消除考勤错算引发的薪酬争议。")
        ],
        "07_考勤自动对账与转换.png"
    )

    # ==================== SLIDE 8: Security & Disaster Recovery ====================
    add_feature_slide(
        "全动作审计留痕与每日全自动加密灾备",
        "模块06 · 数据安全与无人值守",
        [
            ("使用用途", "系统关键新增、修改与删除操作全留痕对比；每日 02:00 全自动导出加密备份至本地硬盘。"),
            ("精益优点", "彻底防范数据丢失风险，数据恢复成功率100%；零专职 DBA 运维成本，节省灾备预算15万元/年。"),
            ("权限隔离", "敏感功能（清空日志、备份恢复）严格限定超级管理员 admin 执行，防范越权。")
        ],
        "08_系统审计日志与安全管控.png"
    )

    # ==================== SLIDE 9: Summary & Benefits ====================
    slide_sum = prs.slides.add_slide(blank_layout)
    add_background(slide_sum, prs, COLOR_DARK_BG)
    add_header(slide_sum, "系统降本增效成果与总结", "EXECUTIVE SUMMARY")

    sum_cards = [
        ("🚀 效率提升 90%+", "花名册查询秒级响应，考勤比对从3天缩短至15分钟，全面消除人工繁重对账。"),
        ("🎯 数据准确率 100%", "标准化多语言词典与自动比对算法，彻底消除人工录入与计算错漏。"),
        ("⚡ 实时动态掌控", "用工趋势、车间定编与印尼籍本土化率秒级监控，提前预判用工缺口。"),
        ("🛡️ 数据安全与零成本", "审计留痕 + 每日全自动加密灾备；全自主研发，软件许可与订阅费用为 ￥0 元。")
    ]

    for i, (stitle, sdesc) in enumerate(sum_cards):
        cx = lefts[i]
        cy = tops[i]
        cw = widths
        ch = heights

        cshape = slide_sum.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, cx, cy, cw, ch)
        cshape.fill.solid()
        cshape.fill.fore_color.rgb = COLOR_CARD_BG
        cshape.line.color.rgb = COLOR_GOLD

        ctb = slide_sum.shapes.add_textbox(cx + Inches(0.2), cy + Inches(0.2), cw - Inches(0.4), ch - Inches(0.4))
        ctf = ctb.text_frame
        ctf.word_wrap = True

        cp0 = ctf.paragraphs[0]
        cp0.text = stitle
        cp0.font.size = Pt(18)
        cp0.font.bold = True
        cp0.font.color.rgb = COLOR_GOLD
        cp0.font.name = "Microsoft YaHei"

        cp1 = ctf.add_paragraph()
        cp1.text = sdesc
        cp1.font.size = Pt(13)
        cp1.font.color.rgb = COLOR_TEXT_MAIN
        cp1.font.name = "Microsoft YaHei"
        cp1.space_before = Pt(8)

    prs.save(PPT_OUTPUT_PATH)
    print(f"PPT Presentation saved successfully at: {PPT_OUTPUT_PATH}")

if __name__ == "__main__":
    build_ppt()

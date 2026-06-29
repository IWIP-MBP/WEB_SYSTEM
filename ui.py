import streamlit as st
import pandas as pd
import requests
from plotly import express as px, graph_objects as go
from datetime import datetime, date, timedelta
import os
import json
import io
import base64
import time
# Monkeypatch requests to support relative paths for server-side requests
_INTERNAL_BACKEND_URL = os.getenv("API_BASE", "http://localhost:8000/api").replace("/api", "").rstrip("/")
_orig_get = requests.get
_orig_post = requests.post
_orig_put = requests.put
_orig_delete = requests.delete

def _resolve_url(url):
    if url.startswith("/api"):
        return f"{_INTERNAL_BACKEND_URL}{url}"
    return url

requests.get = lambda url, *args, **kwargs: _orig_get(_resolve_url(url), *args, **kwargs)
requests.post = lambda url, *args, **kwargs: _orig_post(_resolve_url(url), *args, **kwargs)
requests.put = lambda url, *args, **kwargs: _orig_put(_resolve_url(url), *args, **kwargs)
requests.delete = lambda url, *args, **kwargs: _orig_delete(_resolve_url(url), *args, **kwargs)

API_BASE = "/api"
API_TIMEOUT = int(os.getenv("API_TIMEOUT", "15"))

st.set_page_config(page_title="后勤三部人事管理系统", layout="wide", page_icon="👥")

def init_session_state():
    defaults = {
        "lang": "zh",
        "access_token": None,
        "user_info": None,
        "greeting_shown": False,
        "menu_position": "sidebar",
        "edit_employee_id": None,
        "resign_employee_id": None,
        "edit_assign_id": None,
        "edit_assign_data": None,
        "selected_employee": None,
        "show_edit_form": False,
        "show_resign_form": False,
        "summary_shown_today": False,
        "reminder_shown_today": False,
        "show_history": False,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

init_session_state()

# ---------- Apple Frosted Glass (Glassmorphism) UI Configuration ----------
st.markdown("""
<style>
    :root {
        --app-primary: #0f766e;
        --app-primary-dark: #115e59;
        --app-accent: #2563eb;
        
        /* Light Mode Glassmorphism Tokens */
        --app-bg: #f4f5f7;
        --app-panel: rgba(255, 255, 255, 0.45);
        --app-border: rgba(255, 255, 255, 0.65);
        --app-text: #0f172a;
        --input-bg: rgba(255, 255, 255, 0.85);
        --input-border: rgba(15, 118, 110, 0.35);
        --dropdown-bg: #ffffff;
        --app-bg-radial: radial-gradient(circle at 10% 20%, rgba(15, 118, 110, 0.12) 0%, transparent 45%),
                         radial-gradient(circle at 90% 80%, rgba(37, 99, 235, 0.1) 0%, transparent 45%),
                         radial-gradient(circle at 50% 50%, rgba(219, 39, 119, 0.04) 0%, transparent 50%);
    }

    @media (prefers-color-scheme: dark) {
        :root {
            /* Dark Mode Glassmorphism Tokens */
            --app-bg: #0b0f19;
            --app-panel: rgba(15, 23, 42, 0.45);
            --app-border: rgba(255, 255, 255, 0.2);
            --app-text: #f1f5f9;
            --input-bg: rgba(15, 23, 42, 0.8);
            --input-border: rgba(255, 255, 255, 0.25);
            --dropdown-bg: #1e293b;
            --app-bg-radial: radial-gradient(circle at 10% 20%, rgba(20, 184, 166, 0.15) 0%, transparent 50%),
                             radial-gradient(circle at 90% 80%, rgba(59, 130, 246, 0.12) 0%, transparent 50%),
                             radial-gradient(circle at 50% 50%, rgba(244, 63, 94, 0.05) 0%, transparent 50%);
        }
    }

    .stApp {
        background-attachment: fixed !important;
        background: var(--app-bg-radial), var(--app-bg) !important;
        color: var(--app-text) !important;
    }
</style>
""", unsafe_allow_html=True)


st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
    /* 1. 全局字体设置 */
    html, body, [class*="css"], .stApp, p, h1, h2, h3, h4, h5, h6, span, button, input, select, textarea {
        font-family: 'Plus Jakarta Sans', 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important;
    }
    .stMarkdown, .stText, .stDataframe, .stButton button {
        font-size: 14px !important;
    }
    /* 数据表格（DataFrame）的字体略小，节省空间 */
    .dataframe { 
        font-size: 13px !important; 
    }
    /* 限制主内容区域最大宽度并居中 */
    .main .block-container {
        max-width: 1600px !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        margin: 0 auto !important;
    }

    /* 1. 限制基础表单控件（文本输入、日期、数字、文本域） */
    .stTextInput > div > div > input,
    .stDateInput > div > div > input,
    .stTextArea > div > div > textarea,
    .stNumberInput > div > div > input {
        max-width: 1200px !important;
        width: 100% !important;
        border-radius: 10px !important;
        border: 1.5px solid var(--input-border) !important;
        background-color: var(--input-bg) !important;
        transition: all 0.2s ease !important;
        color: var(--app-text) !important; /* 确保文字颜色可见 */
    }

    /* 2. 专门为 Selectbox 和 Multiselect 设置样式（避免破坏其复杂的内部结构） */
    div[data-baseweb="select"] > div {
        border-radius: 10px !important;
        border: 1.5px solid var(--input-border) !important;
        background-color: var(--input-bg) !important;
        transition: all 0.2s ease !important;
    }

    /* 3. 基础控件的聚焦状态，Selectbox 使用 focus-within */
    .stTextInput > div > div > input:focus,
    .stDateInput > div > div > input:focus,
    .stTextArea > div > div > textarea:focus,
    .stNumberInput > div > div > input:focus,
    div[data-baseweb="select"] > div:focus-within {
        border-color: var(--app-primary) !important;
        box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.25) !important;
    }

    /* 确保 Selectbox 内部的选中文字颜色正常显示 */
    div[data-baseweb="select"] span {
        color: var(--app-text) !important;
    }

    /* 4. 专门为选择下拉框菜单设置样式，增加对比度和颜色差异，防止低对比度字样或半透明叠加造成阅读困难 */
    div[data-baseweb="popover"],
    div[role="listbox"],
    div[data-baseweb="menu"] {
        background-color: var(--dropdown-bg) !important;
        border: 1.5px solid var(--app-border) !important;
        border-radius: 10px !important;
        box-shadow: 0 10px 30px rgba(0,0,0,0.15) !important;
    }
    div[data-baseweb="popover"] li,
    div[role="listbox"] li,
    div[data-baseweb="menu"] li {
        color: var(--app-text) !important;
        transition: background-color 0.15s, color 0.15s !important;
    }
    div[data-baseweb="popover"] li:hover,
    div[role="listbox"] li:hover,
    div[data-baseweb="menu"] li:hover {
        background-color: var(--app-primary) !important;
        color: white !important;
    }
    
    /* 主内容区随侧边栏宽度自动适配，无需额外修改 */
    /* 在表格或复杂布局中，避免控件过宽；但对列内元素保持自适应 */
    div[data-testid="column"] .stTextInput > div > div > input {
        max-width: 100% !important;
    }
    /* 调整侧边栏宽度 */
    section[data-testid="stSidebar"] {
        width: 280px !important;
        min-width: 220px !important;
        background: var(--app-panel) !important;
        backdrop-filter: blur(20px) saturate(190%) !important;
        -webkit-backdrop-filter: blur(20px) saturate(190%) !important;
        border-right: 1px solid var(--app-border) !important;
    }
    section[data-testid="stSidebar"] [data-testid="stMarkdownContainer"] p,
    section[data-testid="stSidebar"] label {
        color: var(--app-text) !important;
        font-weight: 500;
    }
    /* 4. 登录 Logo 样式 */
    .login-logo {
        max-width: 120px;               /* Logo 图片最大宽度 120px */
        margin: 0 auto 20px auto;       /* 水平居中，底部留白 20px */
        border-radius: 50%;             /* 圆形裁剪（如果图片为正方形则成圆） */
        box-shadow: 0 8px 16px rgba(0,0,0,0.08); /* 轻微阴影，提升层次感 */
    }

    .main .block-container {
        padding-top: 2.5rem !important;
        padding-bottom: 2.5rem !important;
    }
    
    /* 使顶部白色条状物透明 */
    [data-testid="stAppViewContainer"],
    [data-testid="stViewerEmbedded"],
    .stAppViewContainer,
    div[data-testid="stHeader"] {
        background: transparent !important;
    }
    
    /* 隐藏或透明化顶部工具栏背景 */
    [class*="css-"] header {
        background: transparent !important;
    }
    h1, h2, h3, h4, h5, h6 {
        letter-spacing: -0.025em !important;
        color: var(--app-text) !important;
        font-weight: 700 !important;
    }
    
    /* 现代高级按钮样式 */
    .stButton > button,
    .stDownloadButton > button {
        border-radius: 10px !important;
        border: 1px solid var(--app-border) !important;
        background: var(--app-panel) !important;
        color: var(--app-text) !important;
        font-weight: 600 !important;
        min-height: 2.5rem;
        padding: 0.5rem 1.2rem !important;
        box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    .stButton > button:hover,
    .stDownloadButton > button:hover {
        border-color: var(--app-primary) !important;
        color: var(--app-primary) !important;
        background: rgba(15, 118, 110, 0.1) !important;
        transform: translateY(-1px);
        box-shadow: 0 4px 12px rgba(15, 118, 110, 0.08);
    }
    .stButton > button:active,
    .stDownloadButton > button:active {
        transform: translateY(0);
    }
    
    /* 提交表单按钮样式 */
    div[data-testid="stFormSubmitButton"] button {
        border-radius: 10px !important;
        background: linear-gradient(135deg, var(--app-primary), var(--app-primary-dark)) !important;
        color: white !important;
        border-color: transparent !important;
        font-weight: 600 !important;
        min-height: 2.5rem;
        padding: 0.5rem 1.2rem !important;
        box-shadow: 0 4px 12px rgba(15, 118, 110, 0.15);
        transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    div[data-testid="stFormSubmitButton"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 6px 16px rgba(15, 118, 110, 0.25);
        background: linear-gradient(135deg, var(--app-primary-dark), #0d5c55) !important;
    }
    
    /* 高级卡片样式 */
    [data-testid="stMetric"] {
        background: var(--app-panel) !important;
        border: 1px solid var(--app-border) !important;
        border-left: 5px solid var(--app-primary) !important;
        border-radius: 12px !important;
        padding: 1.1rem 1.3rem !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.05) !important;
        backdrop-filter: blur(16px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1) !important;
    }
    [data-testid="stMetric"]:hover {
        transform: translateY(-2px);
        box-shadow: 0 12px 40px rgba(15, 23, 42, 0.08) !important;
        border-color: rgba(15, 118, 110, 0.3) !important;
    }
    [data-testid="stMetricLabel"] {
        color: var(--app-text) !important;
        opacity: 0.65;
        font-weight: 600 !important;
        font-size: 0.88rem !important;
        text-transform: uppercase;
        letter-spacing: 0.05em;
    }
    [data-testid="stMetricValue"] {
        color: var(--app-text) !important;
        font-weight: 700 !important;
        font-size: 2rem !important;
    }
    div[data-testid="stDataFrame"],
    div[data-testid="stDataEditor"] {
        background: var(--app-panel) !important;
        border: 1px solid var(--app-border) !important;
        backdrop-filter: blur(16px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
        border-radius: 12px;
        overflow: hidden;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.05) !important;
    }
    div[data-testid="stExpander"] {
        border: 1px solid var(--app-border) !important;
        border-radius: 10px !important;
        background: var(--app-panel) !important;
        backdrop-filter: blur(16px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.05) !important;
        margin-bottom: 0.75rem;
    }
    div[data-testid="stTabs"] button[role="tab"] {
        border-radius: 10px 10px 0 0 !important;
        padding: 0.6rem 1.2rem !important;
        font-weight: 600 !important;
        color: var(--app-text) !important;
        opacity: 0.7;
        transition: all 0.2s ease !important;
    }
    div[data-testid="stTabs"] button[aria-selected="true"] {
        color: var(--app-primary-dark) !important;
        opacity: 1;
        background-color: rgba(15, 118, 110, 0.04) !important;
        border-bottom-color: var(--app-primary) !important;
    }
    .section-note {
        color: var(--app-text) !important;
        opacity: 0.8;
        font-size: 0.92rem;
        margin: -0.5rem 0 1.2rem 0;
        background: rgba(128, 128, 128, 0.1) !important;
        padding: 0.6rem 1rem;
        border-radius: 8px;
        border-left: 3px solid var(--app-primary) !important;
    }
    
    /* 登录面板毛玻璃样式 */
    .login-brand {
        background:
            linear-gradient(135deg, rgba(15,118,110,0.95), rgba(37,99,235,0.92)),
            linear-gradient(180deg, #0f766e, #2563eb);
        color: white;
        padding: 3.5rem 3rem;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
        min-height: 480px;
        border-radius: 16px;
        box-shadow: 0 24px 70px rgba(15,23,42,0.16);
        position: relative;
        overflow: hidden;
    }
    
    .login-brand::before {
        content: '';
        position: absolute;
        width: 300px;
        height: 300px;
        border-radius: 50%;
        background: radial-gradient(circle, rgba(255,255,255,0.15) 0%, transparent 75%);
        top: -100px;
        right: -100px;
        pointer-events: none;
    }
    
    .login-brand h1 {
        color: white !important;
        font-size: 2.5rem !important;
        line-height: 1.2;
        margin: 0 0 1.2rem 0;
        font-weight: 800 !important;
    }
    .login-brand p {
        color: rgba(255,255,255,0.9);
        font-size: 1.05rem;
        line-height: 1.7;
        margin: 0;
    }
    .login-badges {
        display: flex;
        flex-direction: column;
        gap: 0.85rem;
        margin-top: 2.5rem;
    }
    .login-badge {
        border: 1px solid rgba(255,255,255,0.22);
        border-radius: 10px;
        padding: 0.8rem 1.2rem;
        background: rgba(255,255,255,0.08);
        color: white;
        font-weight: 500;
        backdrop-filter: blur(8px);
        transition: all 0.3s ease;
        display: flex;
        align-items: center;
        gap: 10px;
    }
    .login-badge::before {
        content: '✓';
        color: #4ade80;
        font-weight: bold;
    }
    .login-badge:hover {
        background: rgba(255,255,255,0.15);
        border-color: rgba(255,255,255,0.35);
        transform: translateX(5px);
    }
    a.login-badge {
        text-decoration: none !important;
        color: white !important;
    }
    a.login-badge:hover {
        text-decoration: none !important;
        color: white !important;
        background: rgba(255,255,255,0.15) !important;
        border-color: rgba(255,255,255,0.35) !important;
        transform: translateX(5px) !important;
    }
    .login-heading {
        margin: 0 0 1.5rem 0;
        padding: 0.15rem 0 0.35rem 0;
    }
    .login-logo-wrap {
        margin: 0.25rem 0 1.15rem 0;
    }
    .login-logo-wrap img {
        width: 86px;
        max-height: 86px;
        object-fit: contain;
    }
    div[data-testid="stForm"] {
        background: var(--app-panel) !important;
        border: 1px solid var(--app-border) !important;
        border-radius: 16px;
        padding: 1.75rem 1.75rem 2rem 1.75rem;
        box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.08) !important;
        backdrop-filter: blur(16px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
        overflow: visible !important;
    }
    .login-heading h2 {
        margin: 0 0 0.4rem 0;
        font-size: 1.55rem !important;
        color: var(--app-text) !important;
    }
    .login-heading .hint {
        color: var(--app-text) !important;
        opacity: 0.7;
        margin-bottom: 0;
    }
    @media (max-width: 820px) {
        .login-brand { min-height: auto; padding: 2.2rem; }
    }
    
    /* Reposition Streamlit toasts so they sit above the bottom taskbar */
    div[data-testid="stToast"],
    div[data-testid="stToastContainer"],
    [class*="stToast"] {
        bottom: 80px !important;
        z-index: 10000001 !important;
    }

    /* ---------------- 屏幕中间专用弹窗提示 ---------------- */
    /* 背景遮罩层 */
    .custom-modal-backdrop {
        position: fixed !important;
        top: 0 !important;
        left: 0 !important;
        width: 100vw !important;
        height: 100vh !important;
        background-color: rgba(15, 23, 42, 0.45) !important;
        backdrop-filter: blur(5px) !important;
        z-index: 999998 !important;
    }

    /* 弹窗容器 CSS (利用 :has 匹配包含标记的容器) */
    div[data-testid="stVerticalBlock"]:has(> div.element-container .modal-marker) {
        position: fixed !important;
        top: 50% !important;
        left: 50% !important;
        transform: translate(-50%, -50%) !important;
        z-index: 999999 !important;
        background: var(--app-panel) !important;
        backdrop-filter: blur(25px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(25px) saturate(180%) !important;
        padding: 30px !important;
        border-radius: 16px !important;
        box-shadow: 0 20px 50px rgba(0, 0, 0, 0.15) !important;
        border: 1px solid var(--app-border) !important;
        max-width: 420px !important;
        width: 90% !important;
        display: flex !important;
        flex-direction: column !important;
        justify-content: center !important;
        align-items: center !important;
    }

    /* 弹窗内的元素宽度及居中显示 */
    div[data-testid="stVerticalBlock"]:has(> div.element-container .modal-marker) > div.element-container {
        width: 100% !important;
        display: flex !important;
        justify-content: center !important;
    }

    /* 强力修复所有主题模式下 Inactive 文本与 Label 不可见问题 */
    div[data-testid="stTabs"] button[role="tab"] {
        color: var(--app-text) !important;
        opacity: 0.7 !important;
    }
    div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
        color: var(--app-primary) !important;
        opacity: 1 !important;
    }
    div[data-testid="stTabs"] button[role="tab"] p,
    div[data-testid="stTabs"] button[role="tab"] span {
        color: inherit !important;
    }
    
    /* 强力修复 Radio, Select 和 Checkbox Label 不可见问题 */
    div[data-testid="stRadio"] label p,
    div[data-testid="stRadio"] label span,
    div[data-testid="stCheckbox"] label p,
    div[data-testid="stCheckbox"] label span,
    label[data-testid="stWidgetLabel"] p,
    label[data-testid="stWidgetLabel"] span {
        color: var(--app-text) !important;
        opacity: 0.95 !important;
    }
</style>
""", unsafe_allow_html=True)

# ---------- 多语言字典 ----------
LANG = {
    "zh": {
        "actions": "操作",
        "active_status": "有效",
        "add": "添加",
        "add_labor_item": "新增劳保用品",
        "add_user": "添加用户",
        "admin": "管理员",
        "age_dist": "年龄分布",
        "all_items": "全部物品",
        "all_teams": "全部班组",
        "all_workshops": "全部车间",
        "all_nations": "全部国籍",
        "assign_report": "📊 领用报表",
        "back": "返回",
        "backup": "💾 备份数据库",
        "batch_import": "批量导入",
        "birthday_employees": "🎂 生日员工:",
        "birthday_label": "生日",
        "birthday_reminder": "员工生日提醒",
        "birthday_today": "今天是 {name} 的生日！祝生日快乐！",
        "birthday_today_format": "今天是 {name} 的生日！祝生日快乐！",
        "birthday_upcoming": "{name} 的生日将在 {days} 天后，提前祝生日快乐！",
        "birthday_upcoming_format": "{name} 的生日将在 {days} 天后，提前祝生日快乐！",
        "cancel": "取消",
        "cancel_edit_issue": "撤销/编辑发放记录",
        "cancel_issue": "↩️ 撤销发放",
        "cancel_reason": "撤销原因",
        "cancel_reason_default": "填写错误",
        "cancel_success": "已撤销发放并回补库存",
        "cancelled_status": "已撤销",
        "change_arrow": "变更",
        "change_type": "异动类型",
        "choose_record": "选择记录",
        "col_display_name": "显示名称",
        "col_node_id": "节点ID",
        "col_parent": "上级",
        "col_sort": "排序",
        "col_source": "数据来源",
        "col_total": "人数",
        "col_type": "类型",
        "company_logo": "公司 Logo",
        "confirm": "确认",
        "confirm_cancel_required": "请先勾选确认撤销",
        "confirm_cancel_stock": "确认撤销并回补库存",
        "confirm_cancel_success": "已撤销发放并回补库存",
        "confirm_delete": "确认删除此用户？",
        "confirm_delete_labor_item": "确认删除该劳保用品",
        "confirm_delete_labor_item_checkbox": "确认删除该劳保用品",
        "confirm_delete_user": "确认删除用户 {username} 吗？此操作不可恢复。",
        "confirm_delete_user_format": "确认删除用户 {username} 吗？此操作不可恢复。",
        "confirm_issue_format": "确认发放：{emp_id} / {item_name} / 数量 {quantity}",
        "confirm_issue_required": "请先勾选确认发放信息，避免误操作",
        "confirm_issue_text": "确认发放",
        "confirm_password": "确认密码",
        "create_user_failed": "创建失败",
        "current_stock": "库存",
        "current_stock_and_cycle_format": "当前库存：{stock}；默认周期：{cycle} 天。若同员工同物品再次发放，旧有效记录会自动标记为已换发。",
        "current_stock_hint": "当前库存",
        "cycle_days": "领用周期(天)",
        "dashboard": "📊 数据看板",
        "dashboard_note": "快速查看人员总量、分布趋势和车间班组结构。",
        "days_left": "剩余天数",
        "days_left_format": "剩余 {days} 天",
        "db_backing_up": "备份中...",
        "db_maintenance": "数据库维护",
        "db_restore_success": "数据库恢复成功",
        "db_restoring": "恢复中...",
        "default_cycle": "默认周期(天)",
        "default_cycle_hint": "默认周期",
        "delete": "删除",
        "delete_assign": "删除记录",
        "delete_value": "删除值",
        "download_template": "下载模板",
        "edit": "编辑",
        "edit_assign": "编辑领用记录",
        "edit_delete_labor_item": "更新或删除劳保用品",
        "edit_employee": "编辑员工",
        "edit_issue_date_cycle": "编辑日期/周期",
        "employee_form": "✏️ 员工信息表单",
        "employee_not_exist": "员工不存在",
        "employees": "👥 员工花名册",
        "employees_note": "支持筛选、导出、入职登记、资料修改和批量导入。",
        "end_date": "结束日期",
        "error_rows": "失败 {count} 行",
        "error_rows_format": "失败 {count} 行",
        "expired": "已过期",
        "expiry_reminder": "到期提醒",
        "export": "📤 导出Excel",
        "export_generating": "生成导出文件中...",
        "export_logs": "导出日志报表",
        "export_records": "📤 导出领用记录",
        "filter": "🔍 筛选条件",
        "filter_results": "筛选结果",
        "gender_dist": "性别分布",
        "generate_report": "生成报告",
        "generating_report": "生成报表中...",
        "get_online_failed": "获取在线用户失败",
        "history_reminder": "📜 历史提醒",
        "id_card": "身份证号",
        "id_name_required": "工号和姓名必填",
        "import": "📥 批量导入",
        "import_success": "成功导入 {imported} 条 (共 {total} 行数据)",
        "import_success_format": "成功导入 {imported} 条 (共 {total} 行数据)",
        "import_toast_format": "成功导入 {imported} 条 (共 {total} 行数据) (新增: {added}, 更新: {updated})",
        "importing": "导入中...",
        "inactive_status": "已停用",
        "input_error": "填写错误",
        "insufficient_stock": "库存不足，当前库存 {stock}",
        "insufficient_stock_format": "库存不足，当前库存 {stock}",
        "inventory_management": "库存管理",
        "issue_date": "发放日期",
        "issue_management": "领用发放",
        "issue_quantity": "发放数量",
        "item_management": "物品管理",
        "item_name": "物品名称",
        "labor": "🧤 劳保用品",
        "labor_expired_label": "🧤 劳保到期:",
        "labor_note": "管理劳保用品、库存、发放、撤销和到期提醒，所有关键操作会进入日志。",
        "last_issue_date_info": "上次领用日期",
        "last_issue_format": " (上次: {date})",
        "log_all_types": "全部",
        "log_count_format": "操作记录: {count} 条",
        "log_detail_new": "新数据",
        "log_detail_object": "对象：{id} {name}",
        "log_detail_old": "原数据",
        "log_detail_title": "查看变更详情",
        "log_filter_caption": "支持按日期、操作类型、工号、姓名、操作人或变更内容快速筛选。",
        "log_list": "操作日志",
        "log_search_placeholder": "工号 / 姓名 / 操作人 / 内容",
        "log_time": "时间",
        "log_type_label": "操作类型",
        "login": "登录",
        "login_badge1": "人员数据统一维护",
        "login_badge2": "劳保发放可追溯",
        "login_badge3": "操作记录实时审计",
        "login_desc": "集中管理员工花名册、劳保用品、库存发放、组织架构和操作审计，让日常人事工作更清晰、更可靠。同时集成印尼语学习系统，助力员工快速提升语言技能与沟通效率。",
        "indonesian_learning_portal": "印尼语学习系统 (账号是工号，密码是123456，地址是http://10.158.0.185:8080/login，点击可打开)",
        "login_empty": "请输入用户名和密码",
        "login_error": "用户名或密码错误",
        "login_footer": "后勤三部 张金刚 | 版本 2.0",
        "login_hint": "请选择语言并输入账号密码",
        "login_title": "后勤三部人事管理系统",
        "login_welcome": "欢迎登录",
        "logo_empty": "暂无 Logo",
        "logo_get_failed": "无法获取 Logo",
        "logo_select_file": "选择图片文件",
        "logo_upload_btn": "上传 Logo",
        "logo_upload_failed": "上传失败",
        "logo_upload_success": "Logo 上传成功",
        "logo_upload_title": "上传公司 Logo（将在登录页显示）",
        "logout": "退出",
        "logs": "📜 操作日志",
        "logs_note": "按日期、类型和关键词追踪系统内的关键操作。",
        "menu_position": "菜单位置",
        "menu_sidebar": "侧边栏",
        "menu_top": "顶部",
        "meta_maintenance": "基础数据维护",
        "metric_active_total": "在职总人数",
        "metric_nation_count": "国籍数",
        "metric_team_count": "班组数",
        "metric_workshop_count": "车间数",
        "mode": "操作模式",
        "mode_add": "入职登记",
        "mode_edit": "资料修改",
        "nation_dist": "国籍分布",
        "nationality": "国籍",
        "new_name": "新名称",
        "new_password": "新密码",
        "new_username": "新用户名",
        "new_value": "新值",
        "next_issue": "下次发放",
        "next_issue_date_label": "应领日期",
        "no_data": "暂无数据",
        "no_history_records": "暂无历史记录",
        "no_nationality_detail": "暂无国籍明细",
        "no_online_users": "暂无在线用户",
        "no_records": "该员工暂无领用记录",
        "old_value": "原值",
        "online_title": "🌐 在线用户",
        "online_toast_in": "🟢 {user} 上线",
        "online_toast_out": "🔴 {user} 下线",
        "operation_failed": "操作失败",
        "operation_success": "操作成功",
        "operator": "操作人",
        "org_chart": "📊 组织架构图",
        "org_manage_caption": "可调整显示名称、类型、上级和排序；人数来自员工花名册自动统计，不能手动修改。",
        "org_reset": "已恢复默认组织架构",
        "org_saved": "组织架构已保存",
        "overdue": "已超期",
        "page": "页码",
        "page_info_format": "共 {total} 条记录，第 {page} / {max_page} 页",
        "parent_invalid": "的上级无效",
        "parent_self_invalid": "不能选择自己作为上级",
        "password": "密码",
        "password_mismatch": "两次密码输入不一致",
        "please_check_confirm_cancel": "请先勾选确认撤销",
        "please_check_confirm_issue": "请先勾选确认发放信息，避免误操作",
        "please_select_employee": "请选择员工",
        "process_resign": "办理离职",
        "quantity": "数量",
        "readonly_msg": "您当前为只读权限，无法进行此操作。",
        "readonly_org_msg": "当前为只读权限，仅可查看组织架构。",
        "reason_alasan": "原因",
        "record_id": "记录ID",
        "refresh_btn": "刷新在线状态",
        "refresh_failed": "刷新失败: {error}",
        "remark": "备注",
        "reminder_15days": "劳保领用到期提醒",
        "replacement_hint": "若同员工同物品再次发放，旧有效记录会自动标记为已换发。",
        "report_filter": "报表筛选",
        "reset_org": "🔄 恢复默认层级",
        "resign_btn": "确认注销",
        "resign_date": "离职日期",
        "resign_distribution_analysis": "离职人员分布分析",
        "resign_employee": "办理离职",
        "resign_list": "名册",
        "resign_nation_dist": "离职国籍分布",
        "resign_reason": "离职原因",
        "resign_team_dist": "离职班组分布",
        "resign_trend": "离职趋势",
        "resign_workshop_dist": "离职车间分布",
        "resigned": "🚫 离职名册",
        "resigned_note": "集中查看离职员工，并支持恢复在职或办理离职。",
        "restore": "🔄 恢复数据库",
        "restore_btn": "恢复在职",
        "role": "角色",
        "role_updated": "角色已更新",
        "safety_stock": "安全库存",
        "save": "💾 保存",
        "save_org": "💾 保存组织架构",
        "save_success": "保存成功",
        "search": "搜索工号/姓名",
        "search_employee": "搜索员工",
        "select_employee": "选择员工",
        "select_employee_issue": "选择要发放的员工",
        "select_labor_item": "选择劳保用品",
        "select_language": "语言 / Language",
        "seq_no": "序号",
        "settings": "⚙️ 系统设置",
        "settings_note": "维护基础数据、用户权限、数据库备份和系统 Logo。",
        "backup_management": "💾 数据备份与还原",
        "backup_config": "自动备份策略配置",
        "backup_hour": "备份时间(小时)",
        "backup_minute": "备份时间(分钟)",
        "backup_files": "备份文件管理",
        "backup_now": "立即备份",
        "restore_confirm_title": "⚠️ 数据库还原二次确认",
        "restore_confirm_msg": "警告：还原操作将覆盖当前系统中的所有数据库数据！此操作无法撤销。是否确认还原文件 {filename}？",
        "skipped_rows": "跳过了 {count} 行（缺少工号或姓名）",
        "skipped_rows_format": "跳过了 {count} 行（缺少工号或姓名）",
        "spec": "规格",
        "start_date": "开始日期",
        "status": "状态",
        "status_active": "在职",
        "status_inactive": "离职",
        "stock_format": "库存 {stock}",
        "stock_in": "入库",
        "stock_label": "库存",
        "stock_out": "出库",
        "tab_hierarchy": "层级维护",
        "tab_nationality_detail": "国籍明细",
        "tab_overview": "图表总览",
        "team": "班组",
        "team_change": "班组变更",
        "template": "📥 下载模板",
        "top_level": "顶层",
        "total_active": "在职",
        "total_employees": "总人数",
        "total_label": "合计",
        "total_resigned": "离职",
        "total_quota": "总编制人数",
        "quota_label": "编制",
        "quota_num": "编制人数",
        "col_quota": "编制人数",
        "workshop_quota_comparison": "各车间在职与编制对比",
        "transfer_date": "异动日期",
        "transfer_records": "📋 异动记录",
        "transfer_records_note": "自动记录员工车间、班组等组织归属变化。",
        "unassigned_team": "未分配班组",
        "unassigned_workshop": "未分配车间",
        "unit": "单位",
        "unit_pieces": "件",
        "unknown": "未知",
        "unselected_employee": "未选择员工",
        "update": "更新",
        "upload_backup": "上传备份文件 (.sql)",
        "upload_excel": "选择Excel文件",
        "user_created": "用户创建成功",
        "user_deleted": "用户已删除",
        "user_management": "👥 用户管理",
        "username": "用户名",
        "username_password_required": "用户名 and 密码不能为空",
        "treemap_view": "矩形树图",
        "mindmap_view": "思维导图",
        "sunburst_view": "烈日图",
        "view_detail_data": "查看明细数据",
        "view_mode": "显示模式",
        "view": "查看",
        "view_detail_logs": "📋 查看详细操作日志 ({count}条)",
        "view_records": "输入员工工号查看领用记录",
        "viewer": "只读用户",
        "warning_low_stock": "⚠️ 低于安全库存",
        "workshop": "车间",
        "workshop_change": "车间变更",
        "workshop_dist": "车间分布",
        "workshop_nation_matrix": "车间-国籍矩阵",
        "workshop_team_nation": "车间-班组-国籍",
        "yesterday_summary": "昨日操作汇总",
        "yesterday_summary_no_records": "无操作记录",
        "yesterday_summary_records": "{count} 条操作记录",
        "workshop_scope": "车间权限范围",
        "all": "全部",
        "online_status": "在线",
        "messages": "消息",
        "no_notifications": "暂无消息通知",
        "message_notifications": "💬 消息通知",
        "yesterday_summary_desc_format": "昨日共有 <b>{count}</b> 条操作记录",
        "birthday_reminder_title": "🎂 生日提醒 ({name})",
        "labor_expiry_reminder": "⚠️ 劳保到期提醒",
        "labor_expiry_reminder_desc_format": "<b>{name}</b> ({id_nomor}) 的 <b>{item}</b> 已到期或即将到期 ({status})，应领日期: {date}",
        "tab_quota_settings": "定编设置",
        "save_quota": "💾 保存定编",
        "quota_saved": "定编人数已保存",
        "no_teams_found": "未找到班组节点",
        "transfer_workshop_team": "📝 员工异动 (车间/班组)",
        "select_employee_transfer": "选择要异动的员工",
        "please_select_employee_option": "请选择员工",
        "current_assignment": "当前归属",
        "unassigned": "未分配",
        "select_new_workshop": "选择新车间",
        "none_unassigned": "无/未分配",
        "select_new_team": "选择新班组",
        "confirm_transfer": "确认异动",
        "no_change_workshop_team": "车间和班组没有发生任何变化",
        "no_active_employees_to_transfer": "暂无可操作的在职员工数据",
        "select_transfers_to_delete": "选择要删除的异动记录",
        "delete_selected": "删除已选择记录",
        "confirm_delete_transfers": "⚠️ 确认要永久删除选中的异动记录吗？",
        "delete_permanently": "彻底删除",
        "delete_permanently_warning": "⚠️ 警示：彻底删除操作将直接从数据库中删除该员工及其所有相关记录，此操作不可逆，请谨慎操作！",
        "input_admin_password_confirm": "请输入管理员密码以确认删除：",
        "confirm_delete_permanently": "确认彻底删除",
        "confirm_delete_btn": "确认删除",
        "attendance_converter": "📅 考勤排休转换",
        "attendance_converter_note": "### 📅 跨月考勤排休智能转换\n1. **上传出勤明细**：请同时多选并上传<b>上个月</b>和<b>本月</b>的系统原始出勤明细 Excel 文件（支持多选、跨月追踪）。\n2. **上传输出模板**：上传最新的空白排班输出模板 Excel 文件。\n3. **一键智能转换**：系统会自动分析跨月出入园轨迹、自动匹配出入园闭环并生成备注，计算休息日加班高亮并写入模板中。",
        "upload_attendance_logs": "📂 步骤一：上传出勤明细 Excel 文件（可多选，请同时选中上月和本月流水）",
        "upload_attendance_template": "📄 步骤二：上传您的『输出模板.xlsx』",
        "start_conversion": "开始跨月深度追踪与转换",
        "converting_msg": "程序正在全局检索出勤轨迹并重构矩阵，请稍候...",
        "conversion_success": "✨ 转换大功告成！已成功重构调休排班数据。",
        "download_attendance_result": "点击下载更新后的排休表 Excel 附件",
        "id_nomor": "工号",
        "name_nama": "姓名",
        "select": "选择",
        "delete_operation_logs": "🗑️ 删除操作日志",
        "delete_operation_logs_desc": "您可以选择清空特定类别的操作日志。此操作为永久删除，不可恢复。",
        "select_log_category_to_delete": "选择要删除的日志类别",
        "confirm_delete_category_logs_btn": "🚨 确认删除该类别日志",
        "confirm_delete_category_logs_warning": "⚠️ 确认要永久删除类别为 [{category}] 的所有操作日志吗？",
        "confirm_delete_permanently_btn": "确认永久删除",
        "select_all_page": "全选本页",
        "deselect_all_page": "取消全选本页",
        "selected_records_count": "已选 <b style='color:#0f766e'>{count}</b> 条",
        "batch_delete_with_count": "🗑️ 批量删除 ({count})",
        "confirm_batch_delete_warning": "⚠️ 确认要永久删除选中的 **{count}** 条日志记录吗？此操作不可恢复！",
        "confirm_batch_delete_btn": "✅ 确认批量删除",
        "batch_delete_success_format": "已删除 {count} 条日志",
        "request_failed_format": "请求失败: {error}",
        # 操作类型 / Log Types
        "删除操作日志": "删除操作日志",
        "批量删除操作日志": "批量删除操作日志",
        "新增物品": "新增物品",
        "修改物品": "修改物品",
        "删除物品": "删除物品",
        "入库": "入库",
        "出库": "出库",
        "发放劳保": "发放劳保",
        "撤销发放": "撤销发放",
        "编辑领用记录": "编辑领用记录",
        "删除领用记录": "删除领用记录",
        "恢复在职": "恢复在职",
        "修改": "修改",
        "入职": "入职",
        "离职": "离职",
        "彻底删除员工": "彻底删除员工",
        "批量导入": "批量导入",
        "Bulk delete transfer records": "批量删除异动记录",
        "考勤排休转换": "考勤排休转换",
        "手动备份数据库": "手动备份数据库",
        "还原数据库": "还原数据库",
        "触发还原数据库": "触发还原数据库",
        "更新自动备份配置": "更新自动备份配置",
        "登录": "登录",
        "新增用户": "新增用户",
        "修改用户角色和权限": "修改用户角色和权限",
        "删除用户": "删除用户",
        # 动态操作类型
        "新增车间": "新增车间", "修改车间": "修改车间", "删除车间": "删除车间",
        "新增班组": "新增班组", "修改班组": "修改班组", "删除班组": "删除班组",
        "新增国籍": "新增国籍", "修改国籍": "修改国籍", "删除国籍": "删除国籍",
        "新增宗教": "新增宗教", "修改宗教": "修改宗教", "删除宗教": "删除宗教",
        "新增公司": "新增公司", "修改公司": "修改公司", "删除公司": "删除公司",
        "新增性别": "新增性别", "修改性别": "修改性别", "删除性别": "删除性别",
        # 常见日志原因
        "用户登录成功": "用户登录成功",
        "管理员手动触发数据库备份成功": "管理员手动触发数据库备份成功",
        "管理员后台还原数据库成功": "管理员后台还原数据库成功",
        "管理员触发数据库还原动作，提交后台异步执行": "管理员触发数据库还原动作，提交后台异步执行",
        "管理员修改自动备份周期及保留天数": "管理员修改自动备份周期及保留天数",
    },
    "id": {
        "actions": "Aksi",
        "active_status": "Aktif",
        "add": "Tambah",
        "add_labor_item": "Tambah APD",
        "add_user": "Tambah Pengguna",
        "admin": "Administrator",
        "age_dist": "Distribusi Usia",
        "all_items": "Semua Barang",
        "all_teams": "Semua Grup",
        "all_workshops": "Semua Bengkel",
        "all_nations": "Semua Kewarganegaraan",
        "assign_report": "📊 Laporan Pemberian",
        "back": "Kembali",
        "backup": "💾 Cadangkan Database",
        "batch_import": "Impor Massal",
        "birthday_employees": "🎂 Pegawai Ulang Tahun:",
        "birthday_label": "Ulang Tahun",
        "birthday_reminder": "Pengingat Ulang Tahun",
        "birthday_today": "Hari ini ulang tahun {name}! Selamat ulang tahun!",
        "birthday_today_format": "Hari ini ulang tahun {name}! Selamat ulang tahun!",
        "birthday_upcoming": "Ulang tahun {name} dalam {days} hari, selamat ulang tahun!",
        "birthday_upcoming_format": "Ulang tahun {name} dalam {days} hari, selamat ulang tahun!",
        "cancel": "Batal",
        "cancel_edit_issue": "Batalkan / Ubah Riwayat Pemberian",
        "cancel_issue": "↩️ Batalkan pemberian",
        "cancel_reason": "Alasan pembatalan",
        "cancel_reason_default": "Kesalahan input",
        "cancel_success": "Pemberian dibatalkan dan stok dikembalikan",
        "cancelled_status": "Dibatalkan",
        "change_arrow": "Perubahan",
        "change_type": "Jenis Mutasi",
        "choose_record": "Pilih Riwayat",
        "col_display_name": "Nama Tampilan",
        "col_node_id": "ID Node",
        "col_parent": "Atasan",
        "col_sort": "Urutan",
        "col_source": "Sumber Data",
        "col_total": "Jumlah",
        "col_type": "Tipe",
        "company_logo": "Logo Perusahaan",
        "confirm": "Konfirmasi",
        "confirm_cancel_required": "Centang konfirmasi pembatalan terlebih dahulu",
        "confirm_cancel_stock": "Konfirmasi batal dan kembalikan stok",
        "confirm_cancel_success": "Pemberian dibatalkan dan stok dikembalikan",
        "confirm_delete": "Konfirmasi hapus pengguna ini?",
        "confirm_delete_labor_item": "Konfirmasi hapus APD ini",
        "confirm_delete_labor_item_checkbox": "Konfirmasi hapus APD ini",
        "confirm_delete_user": "Konfirmasi hapus pengguna {username}? Operasi ini tidak dapat dibatalkan.",
        "confirm_delete_user_format": "Konfirmasi hapus pengguna {username}? Operasi ini tidak dapat dibatalkan.",
        "confirm_issue_format": "Konfirmasi pemberian: {emp_id} / {item_name} / Jumlah {quantity}",
        "confirm_issue_required": "Centang konfirmasi pemberian terlebih dahulu untuk menghindari kesalahan.",
        "confirm_issue_text": "Konfirmasi pemberian",
        "confirm_password": "Konfirmasi Kata Sandi",
        "create_user_failed": "Gagal membuat pengguna",
        "current_stock": "Stok",
        "current_stock_and_cycle_format": "Stok saat ini: {stock}; Siklus default: {cycle} hari. Jika APD yang sama diberikan lagi kepada pegawai yang sama, riwayat lama akan ditandai diganti.",
        "current_stock_hint": "Stok saat ini",
        "cycle_days": "Siklus (hari)",
        "dashboard": "📊 Dasbor",
        "dashboard_note": "Melihat jumlah karyawan, tren, dan struktur bengkel/grup dengan cepat.",
        "days_left": "Hari Tersisa",
        "days_left_format": "sisa {days} hari",
        "db_backing_up": "Mencadangkan...",
        "db_maintenance": "Pemeliharaan Database",
        "db_restore_success": "Database berhasil dipulihkan",
        "db_restoring": "Memulihkan...",
        "default_cycle": "Siklus Default (hari)",
        "default_cycle_hint": "Siklus default",
        "delete": "Hapus",
        "delete_assign": "Hapus Riwayat",
        "delete_value": "Hapus nilai",
        "download_template": "Unduh Template",
        "edit": "Ubah",
        "edit_assign": "Ubah Riwayat",
        "edit_delete_labor_item": "Ubah atau Hapus APD",
        "edit_employee": "Ubah Pegawai",
        "edit_issue_date_cycle": "Ubah tanggal/siklus",
        "employee_form": "✏️ Form Pegawai",
        "employee_not_exist": "Pegawai tidak ditemukan",
        "employees": "👥 Arsip Pegawai",
        "employees_note": "Mendukung penyaringan, ekspor, pendaftaran, modifikasi data, dan impor massal.",
        "end_date": "Tanggal Akhir",
        "error_rows": "{count} baris gagal",
        "error_rows_format": "{count} baris gagal",
        "expired": "Terlambat",
        "expiry_reminder": "Pengingat Jatuh Tempo",
        "export": "📤 Ekspor Excel",
        "export_generating": "Membuat file ekspor...",
        "export_logs": "Ekspor Log",
        "export_records": "📤 Ekspor Riwayat",
        "filter": "🔍 Filter",
        "filter_results": "Hasil Filter",
        "gender_dist": "Distribusi Gender",
        "generate_report": "Buat Laporan",
        "generating_report": "Membuat laporan...",
        "get_online_failed": "Gagal mendapatkan pengguna online",
        "history_reminder": "📜 Riwayat Peringatan",
        "id_card": "Nomor KTP",
        "id_name_required": "ID dan nama wajib diisi",
        "import": "📥 Impor Massal",
        "import_success": "Berhasil mengimpor {imported} data (dari {total} baris)",
        "import_success_format": "Berhasil mengimpor {imported} data (dari {total} baris)",
        "import_toast_format": "Berhasil mengimpor {imported} data (dari {total} baris) (Baru: {added}, Perbarui: {updated})",
        "importing": "Mengimpor...",
        "inactive_status": "Tidak Aktif",
        "input_error": "Kesalahan input",
        "insufficient_stock": "Stok tidak cukup, stok saat ini {stock}",
        "insufficient_stock_format": "Stok tidak cukup, stok saat ini {stock}",
        "inventory_management": "Manajemen Stok",
        "issue_date": "Tanggal Pemberian",
        "issue_management": "Pemberian",
        "issue_quantity": "Jumlah Diberikan",
        "item_management": "Manajemen Barang",
        "item_name": "Nama Barang",
        "labor": "🧤 Alat Pelindung",
        "labor_expired_label": "🧤 APD Jatuh Tempo:",
        "labor_note": "Mengelola APD, stok, pemberian, pembatalan, dan pengingat jatuh tempo. Semua operasi penting dicatat dalam log.",
        "last_issue_date_info": "Tanggal pemberian terakhir",
        "last_issue_format": " (Terakhir: {date})",
        "log_all_types": "Semua",
        "log_count_format": "Log aktivitas: {count} baris",
        "log_detail_new": "Data Baru",
        "log_detail_object": "Objek: {id} {name}",
        "log_detail_old": "Data Lama",
        "log_detail_title": "Lihat Detail Perubahan",
        "log_filter_caption": "Mendukung penyaringan cepat berdasarkan tanggal, tipe operasi, ID pegawai, nama, operator, atau konten perubahan.",
        "log_list": "Log Aktivitas",
        "log_search_placeholder": "ID / Nama / Operator / Konten",
        "log_time": "Waktu",
        "log_type_label": "Tipe Operasi",
        "login": "Masuk",
        "login_badge1": "Pemeliharaan Data Pegawai Terpadu",
        "login_badge2": "Pemberian APD Dapat Dilacak",
        "login_badge3": "Audit Operasi Real-time",
        "login_desc": "Mengelola data pegawai, alat pelindung diri (APD), stok & distribusi, bagan organisasi, dan audit aktivitas secara terpusat untuk pekerjaan personalia yang lebih teratur dan andal. Terintegrasi dengan sistem pembelajaran bahasa Indonesia untuk membantu meningkatkan keterampilan bahasa.",
        "indonesian_learning_portal": "Sistem Belajar Bahasa Indonesia (Username: ID Karyawan, Password: 123456, Alamat: http://10.158.0.185:8080/login)",
        "login_empty": "Silakan masukkan nama pengguna dan kata sandi",
        "login_error": "Nama pengguna atau kata sandi salah",
        "login_footer": "ACC Departemen 3 Zhang Jingang | Versi 2.0",
        "login_hint": "Silakan pilih bahasa dan masukkan nama pengguna & kata sandi",
        "login_title": "Sistem Manajemen SDM ACC Departemen 3",
        "login_welcome": "Selamat Datang",
        "logo_empty": "Belum ada logo",
        "logo_get_failed": "Gagal mendapatkan logo",
        "logo_select_file": "Pilih file gambar",
        "logo_upload_btn": "Unggah Logo",
        "logo_upload_failed": "Gagal mengunggah logo",
        "logo_upload_success": "Logo berhasil diunggah",
        "logo_upload_title": "Unggah Logo Perusahaan (akan ditampilkan di halaman masuk)",
        "logout": "Keluar",
        "logs": "📜 Log Aktivitas",
        "logs_note": "Melacak operasi penting dalam sistem berdasarkan tanggal, tipe, dan kata kunci.",
        "menu_position": "Posisi Menu",
        "menu_sidebar": "Sidebar",
        "menu_top": "Atas",
        "meta_maintenance": "Pemeliharaan Data Dasar",
        "metric_active_total": "Total Karyawan Aktif",
        "metric_nation_count": "Jumlah Kewarganegaraan",
        "metric_team_count": "Jumlah Grup",
        "metric_workshop_count": "Jumlah Bengkel",
        "mode": "Mode Operasi",
        "mode_add": "Pendaftaran",
        "mode_edit": "Ubah Data",
        "nation_dist": "Distribusi Negara",
        "nationality": "Kewarganegaraan",
        "new_name": "Nama baru",
        "new_password": "Kata Sandi Baru",
        "new_username": "Nama Pengguna Baru",
        "new_value": "Nilai Baru",
        "next_issue": "Pemberian Berikutnya",
        "next_issue_date_label": "Tanggal Pemberian",
        "no_data": "Tidak ada data",
        "no_history_records": "Tidak ada riwayat",
        "no_nationality_detail": "Tidak ada detail kewarganegaraan",
        "no_online_users": "Tidak ada pengguna online",
        "no_records": "Tidak ada riwayat untuk pegawai ini",
        "old_value": "Nilai Lama",
        "online_title": "🌐 Pengguna Online",
        "online_toast_in": "🟢 {user} online",
        "online_toast_out": "🔴 {user} offline",
        "operation_failed": "Operasi gagal",
        "operation_success": "Operasi berhasil",
        "operator": "Operator",
        "org_chart": "📊 Bagan Organisasi",
        "org_manage_caption": "Dapat menyesuaikan nama tampilan, tipe, atasan, dan urutan; Jumlah orang dihitung otomatis dari arsip pegawai dan tidak dapat diubah manual.",
        "org_reset": "Hirarki bagan organisasi diatur ulang",
        "org_saved": "Bagan organisasi berhasil disimpan",
        "overdue": "Terlambat",
        "page": "Halaman",
        "page_info_format": "Total {total} data, Halaman {page} / {max_page}",
        "parent_invalid": "memiliki atasan yang tidak valid",
        "parent_self_invalid": "tidak dapat memilih diri sendiri sebagai atasan",
        "password": "Kata Sandi",
        "password_mismatch": "Kata sandi tidak cocok",
        "please_check_confirm_cancel": "Centang konfirmasi pembatalan terlebih dahulu",
        "please_check_confirm_issue": "Centang konfirmasi pemberian terlebih dahulu untuk menghindari kesalahan.",
        "please_select_employee": "Silakan pilih pegawai",
        "process_resign": "Proses Resign",
        "quantity": "Jumlah",
        "readonly_msg": "Anda dalam mode baca-saja, tidak dapat melakukan operasi ini.",
        "readonly_org_msg": "Anda saat ini memiliki akses baca-saja, hanya dapat melihat bagan organisasi.",
        "reason_alasan": "Alasan",
        "record_id": "ID Riwayat",
        "refresh_btn": "Segarkan status online",
        "refresh_failed": "Gagal menyegarkan: {error}",
        "remark": "Keterangan",
        "reminder_15days": "Pengingat Pemberian APD",
        "replacement_hint": "Jika APD yang sama diberikan lagi kepada pegawai yang sama, riwayat lama akan ditandai diganti.",
        "report_filter": "Filter Laporan",
        "reset_org": "🔄 Atur Ulang Hirarki",
        "resign_btn": "Konfirmasi Resign",
        "resign_date": "Tanggal Resign",
        "resign_distribution_analysis": "Analisis Distribusi Resign",
        "resign_employee": "Resign Pegawai",
        "resign_list": "Daftar Resign",
        "resign_nation_dist": "Distribusi Resign per Kewarganegaraan",
        "resign_reason": "Alasan Resign",
        "resign_team_dist": "Distribusi Resign per Grup",
        "resign_trend": "Tren Resign",
        "resign_workshop_dist": "Distribusi Resign per Bengkel",
        "resigned": "🚫 Daftar Resign",
        "resigned_note": "Melihat pegawai yang resign secara terpusat, mendukung pemulihan atau pemrosesan resign.",
        "restore": "🔄 Pulihkan Database",
        "restore_btn": "Pulihkan",
        "role": "Peran",
        "role_updated": "Peran diperbarui",
        "safety_stock": "Stok Minimum",
        "save": "💾 Simpan",
        "save_org": "💾 Simpan Bagan Organisasi",
        "save_success": "Berhasil disimpan",
        "search": "Cari ID/Nama",
        "search_employee": "Cari Pegawai",
        "select_employee": "Pilih Pegawai",
        "select_employee_issue": "Pilih pegawai untuk diberikan",
        "select_labor_item": "Pilih APD",
        "select_language": "Bahasa / 语言",
        "seq_no": "No",
        "settings": "⚙️ Pengaturan",
        "settings_note": "Memelihara data dasar, hak akses pengguna, cadangan database, dan Logo sistem.",
        "backup_management": "💾 Cadangan & Pemulihan Data",
        "backup_config": "Konfigurasi Strategi Pencadangan Otomatis",
        "backup_hour": "Waktu Pencadangan (Jam)",
        "backup_minute": "Waktu Pencadangan (Menit)",
        "backup_files": "Manajemen File Cadangan",
        "backup_now": "Cadangkan Sekarang",
        "restore_confirm_title": "⚠️ Konfirmasi Pemulihan Database",
        "restore_confirm_msg": "Peringatan: Operasi pemulihan akan menimpa semua data database saat ini di sistem! Operasi ini tidak dapat dibatalkan. Apakah Anda yakin ingin memulihkan file {filename}?",
        "skipped_rows": "{count} baris dilewati (ID atau nama kosong)",
        "skipped_rows_format": "{count} baris dilewati (ID atau nama kosong)",
        "spec": "Spesifikasi",
        "start_date": "Tanggal Mulai",
        "status": "Status",
        "status_active": "Aktif",
        "status_inactive": "Resign",
        "stock_format": "Stok {stock}",
        "stock_in": "Masuk",
        "stock_label": "Stok",
        "stock_out": "Keluar",
        "tab_hierarchy": "Pemeliharaan Hirarki",
        "tab_nationality_detail": "Detail Kewarganegaraan",
        "tab_overview": "Ikhtisar Grafik",
        "team": "Grup",
        "team_change": "Perubahan Grup",
        "template": "📥 Unduh Template",
        "top_level": "Tingkat Teratas",
        "total_active": "Aktif",
        "total_employees": "Total Karyawan",
        "total_label": "Total",
        "total_resigned": "Resign",
        "total_quota": "Total Kuota Staffing",
        "quota_label": "Kuota",
        "quota_num": "Jumlah Kuota",
        "col_quota": "Kuota",
        "workshop_quota_comparison": "Perbandingan Aktif vs Kuota per Bengkel",
        "transfer_date": "Tanggal Mutasi",
        "transfer_records": "📋 Riwayat Mutasi",
        "transfer_records_note": "Mencatat perubahan departemen, bengkel, atau grup pegawai secara otomatis.",
        "unassigned_team": "Grup Belum Dialokasikan",
        "unassigned_workshop": "Bengkel Belum Dialokasikan",
        "unit": "Satuan",
        "unit_pieces": "Pcs",
        "unknown": "Tidak Diketahui",
        "unselected_employee": "Pegawai belum dipilih",
        "update": "Perbarui",
        "upload_backup": "Unggah file cadangan (.sql)",
        "upload_excel": "Pilih file Excel",
        "user_created": "Pengguna berhasil dibuat",
        "user_deleted": "Pengguna dihapus",
        "user_management": "👥 Manajemen Pengguna",
        "username": "Nama Pengguna",
        "username_password_required": "Nama pengguna dan kata sandi wajib diisi",
        "treemap_view": "Treemap",
        "mindmap_view": "Mind Map",
        "sunburst_view": "Diagram Sunburst",
        "view_detail_data": "Lihat Detail Data",
        "view_mode": "Mode Tampilan",
        "view": "Lihat",
        "view_detail_logs": "📋 Lihat log detail ({count} baris)",
        "view_records": "Masukkan ID Pegawai untuk melihat riwayat",
        "viewer": "Hanya Baca",
        "warning_low_stock": "⚠️ Stok di bawah minimum",
        "workshop": "Bengkel",
        "workshop_change": "Perubahan Bengkel",
        "workshop_dist": "Distribusi Bengkel",
        "workshop_nation_matrix": "Matriks Bengkel-Negara",
        "workshop_team_nation": "Bengkel-Grup-Kewarganegaraan",
        "yesterday_summary": "Ringkasan Operasi Kemarin",
        "yesterday_summary_no_records": "Tidak ada log aktivitas",
        "yesterday_summary_records": "{count} log aktivitas",
        "workshop_scope": "Cakupan Bengkel",
        "all": "Semua",
        "online_status": "Online",
        "messages": "Pesan",
        "no_notifications": "Tidak ada notifikasi",
        "message_notifications": "💬 Notifikasi Pesan",
        "yesterday_summary_desc_format": "Kemarin ada <b>{count}</b> log aktivitas",
        "birthday_reminder_title": "🎂 Pengingat Ulang Tahun ({name})",
        "labor_expiry_reminder": "⚠️ Pengingat APD Jatuh Tempo",
        "labor_expiry_reminder_desc_format": "<b>{name}</b> ({id_nomor}) <b>{item}</b> telah jatuh tempo atau akan jatuh tempo ({status}), tanggal pemberian: {date}",
        "tab_quota_settings": "Pengaturan Kuota",
        "save_quota": "💾 Simpan Kuota",
        "quota_saved": "Kuota staffing berhasil disimpan",
        "no_teams_found": "Grup tidak ditemukan",
        "transfer_workshop_team": "📝 Mutasi Karyawan (Bengkel/Grup)",
        "select_employee_transfer": "Pilih karyawan untuk dimutasi",
        "please_select_employee_option": "Silakan pilih karyawan",
        "current_assignment": "Penempatan Saat Ini",
        "unassigned": "Belum Dialokasikan",
        "select_new_workshop": "Pilih Bengkel Baru",
        "none_unassigned": "Tidak ada / Belum dialokasikan",
        "select_new_team": "Pilih Grup Baru",
        "confirm_transfer": "Konfirmasi Mutasi",
        "no_change_workshop_team": "Tidak ada perubahan pada Bengkel dan Grup",
        "no_active_employees_to_transfer": "Tidak ada data karyawan aktif untuk dimutasi",
        "select_transfers_to_delete": "Pilih riwayat mutasi yang ingin dihapus",
        "delete_selected": "Hapus Rekaman Terpilih",
        "confirm_delete_transfers": "⚠️ Konfirmasi untuk menghapus riwayat mutasi yang dipilih secara permanen?",
        "delete_permanently": "Hapus Permanen",
        "delete_permanently_warning": "⚠️ Peringatan: Tindakan hapus permanen akan menghapus karyawan ini beserta semua data terkait dari database secara langsung. Tindakan ini tidak dapat dibatalkan, harap berhati-hati!",
        "input_admin_password_confirm": "Silakan masukkan kata sandi administrator untuk konfirmasi:",
        "confirm_delete_permanently": "Konfirmasi Hapus Permanen",
        "confirm_delete_btn": "Konfirmasi Hapus",
        "attendance_converter": "📅 Konversi Absensi",
        "attendance_converter_note": "### 📅 Konversi Pintar Absensi Lintas Bulan\n1. **Unggah Detail Kehadiran**: Harap pilih dan unggah file Excel detail kehadiran asli sistem untuk **bulan lalu** dan **bulan ini** sekaligus (mendukung pelacakan lintas bulan).\n2. **Unggah Template Output**: Unggah file template output jadwal kerja kosong terbaru.\n3. **Konversi Sekali Klik**: Sistem akan secara otomatis menganalisis riwayat keluar/masuk taman, mencocokkan keluar/masuk taman untuk menghasilkan catatan, menghitung lembur hari libur dan menulis ke template.",
        "upload_attendance_logs": "📂 Langkah 1: Unggah file Excel detail kehadiran (Bisa pilih banyak, harap pilih riwayat bulan lalu dan bulan ini)",
        "upload_attendance_template": "📄 Langkah 2: Unggah file 『output_template.xlsx』 Anda",
        "start_conversion": "Mulai Pelacakan Lintas Bulan & Konversi",
        "converting_msg": "Sistem sedang mencari riwayat kehadiran secara global dan merekonstruksi matriks, harap tunggu...",
        "conversion_success": "✨ Konversi berhasil! Data pengaturan libur dan jadwal kerja berhasil direkonstruksi.",
        "download_attendance_result": "Klik untuk mengunduh lampiran Excel tabel jadwal kerja yang diperbarui",
        "id_nomor": "ID",
        "name_nama": "Nama",
        "select": "Pilih",
        "delete_operation_logs": "🗑️ Hapus Log Aktivitas",
        "delete_operation_logs_desc": "Anda dapat memilih untuk mengosongkan kategori log aktivitas tertentu. Tindakan ini bersifat permanen dan tidak dapat dibatalkan.",
        "select_log_category_to_delete": "Pilih Kategori Log yang Akan Dihapus",
        "confirm_delete_category_logs_btn": "🚨 Konfirmasi Hapus Log Kategori Ini",
        "confirm_delete_category_logs_warning": "⚠️ Konfirmasi hapus permanen semua log aktivitas dengan kategori [{category}]?",
        "confirm_delete_permanently_btn": "Konfirmasi Hapus Permanen",
        "select_all_page": "Pilih Semua Halaman Ini",
        "deselect_all_page": "Batal Pilih Semua Halaman Ini",
        "selected_records_count": "Terpilih <b style='color:#0f766e'>{count}</b> baris",
        "batch_delete_with_count": "🗑️ Hapus Massal ({count})",
        "confirm_batch_delete_warning": "⚠️ Konfirmasi hapus permanen **{count}** log aktivitas terpilih? Tindakan ini tidak dapat dibatalkan!",
        "confirm_batch_delete_btn": "✅ Konfirmasi Hapus Massal",
        "batch_delete_success_format": "{count} log berhasil dihapus",
        "request_failed_format": "Permintaan gagal: {error}",
        # Operasi / Log Types
        "删除操作日志": "Hapus log aktivitas",
        "批量删除操作日志": "Hapus massal log aktivitas",
        "新增物品": "Tambah barang APD",
        "修改物品": "Ubah barang APD",
        "删除物品": "Hapus barang APD",
        "入库": "Stok Masuk",
        "出库": "Stok Keluar",
        "发放劳保": "Pemberian APD",
        "撤销发放": "Pembatalan pemberian APD",
        "编辑领用记录": "Edit rekaman APD",
        "删除领用记录": "Hapus rekaman APD",
        "恢复在职": "Pulihkan status aktif",
        "修改": "Ubah data pegawai",
        "入职": "Pegawai Baru",
        "离职": "Pegawai Resign",
        "彻底删除员工": "Hapus permanen pegawai",
        "批量导入": "Impor massal",
        "Bulk delete transfer records": "Hapus massal riwayat mutasi",
        "考勤排休转换": "Konversi absensi",
        "手动备份数据库": "Cadangkan database secara manual",
        "还原数据库": "Pulihkan database",
        "触发还原数据库": "Picu pemulihan database",
        "更新自动备份配置": "Perbarui konfigurasi cadangan otomatis",
        "登录": "Login",
        "新增用户": "Tambah pengguna",
        "修改用户角色和权限": "Ubah peran dan izin pengguna",
        "删除用户": "Hapus pengguna",
        # Kategori Dinamis
        "新增车间": "Tambah bengkel", "修改车间": "Ubah bengkel", "删除车间": "Hapus bengkel",
        "新增班组": "Tambah grup", "修改班组": "Ubah grup", "删除班组": "Hapus grup",
        "新增国籍": "Tambah kewarganegaraan", "修改国籍": "Ubah kewarganegaraan", "删除国籍": "Hapus kewarganegaraan",
        "新增宗教": "Tambah agama", "修改宗教": "Ubah agama", "删除宗教": "Hapus agama",
        "新增公司": "Tambah perusahaan", "修改公司": "Ubah perusahaan", "删除公司": "Hapus perusahaan",
        "新增性别": "Tambah jenis kelamin", "修改性别": "Ubah jenis kelamin", "删除性别": "Hapus jenis kelamin",
        # Alasan Log Umum
        "用户登录成功": "Login pengguna berhasil",
        "管理员手动触发数据库备份成功": "Administrator berhasil memicu pencadangan database secara manual",
        "管理员后台还原数据库成功": "Administrator berhasil memulihkan database di latar belakang",
        "管理员触发数据库还原动作，提交后台异步执行": "Administrator memicu pemulihan database, dikirim untuk eksekusi asinkron",
        "管理员修改自动备份周期及保留天数": "Administrator mengubah siklus pencadangan otomatis dan hari penyimpanan",
    }
}

def t(key):
    lang = st.session_state.get("lang", "zh")
    return LANG.get(lang, LANG["zh"]).get(key, key)

def t_val(val):
    """
    Display a bilingual database value in the current language.
    
    Database stores values in one of these formats:
      1. "Indonesian Chinese"  e.g. "Kantin VIP VIP食堂", "China 中国籍", "Laki Laki 男"
         Rule: split at the FIRST space-separated word that contains Chinese characters.
         - zh → everything from that word onward  e.g. "VIP食堂", "中国籍", "男"
         - id → everything before that word        e.g. "Kantin VIP", "China", "Laki Laki"
      2. "Chinese / Indonesian"  e.g. "在职 / Aktif"
         Rule: split on " / "
         - zh → left part,  id → right part
      3. Pure Chinese or pure Latin/numeric — returned as-is.
    
    NOTE: The raw database value is always the full bilingual string.
    The UI uses format_func=t_val on selectboxes, so saved values are never the
    translated display text — this keeps data consistent across languages.
    """
    if not val or not isinstance(val, str):
        return val
    val_str = val.strip()
    lang = st.session_state.get("lang", "zh")

    # Format 2: explicit " / " separator
    if " / " in val_str:
        parts = val_str.split(" / ", 1)
        return parts[0].strip() if lang == "zh" else parts[1].strip()

    # Format 1: "Indonesian Chinese" — split at the first word containing Chinese characters
    def has_zh(s):
        return any('\u4e00' <= c <= '\u9fff' for c in s)

    if has_zh(val_str):
        words = val_str.split(" ")
        for i, word in enumerate(words):
            if has_zh(word):
                id_part = " ".join(words[:i]).strip()
                zh_part = " ".join(words[i:]).strip()
                if id_part:
                    return zh_part if lang == "zh" else id_part
                # No Indonesian prefix — return full string for both languages
                return val_str

    # Format 3: pure Latin/numeric — return as-is
    return val_str

FIELD_LABELS = {
    "zh": {
        "id_nomor": "工号", "name_nama": "姓名", "ws_bengkel": "车间",
        "team_grup": "班组", "gender_jk": "性别", "pos_cn_jabatan": "岗位(中)", "pos_id_jabatan": "岗位(印)",
        "nat_negara": "国籍", "rel_agama": "宗教", "status_status": "状态", "resign_date": "离职日期",
        "remark_ket": "原因/备注", "id_card": "身份证号", "hire_date": "入职日期", "contract_end": "合同到期日",
        "company": "归属公司", "resign_operator": "操作人"
    },
    "id": {
        "id_nomor": "ID", "name_nama": "Nama", "ws_bengkel": "Bengkel",
        "team_grup": "Grup", "gender_jk": "JK", "pos_cn_jabatan": "Jabatan (CN)", "pos_id_jabatan": "Jabatan (ID)",
        "nat_negara": "Kewarganegaraan", "rel_agama": "Agama", "status_status": "Status", "resign_date": "Tgl Resign",
        "remark_ket": "Keterangan", "id_card": "Nomor KTP", "hire_date": "Tgl Masuk", "contract_end": "Kontrak Berakhir",
        "company": "Perusahaan", "resign_operator": "Operator"
    }
}

def label(col):
    return FIELD_LABELS.get(st.session_state.get("lang", "zh"), FIELD_LABELS["zh"]).get(col, col)

# ---------- API 辅助 ----------
def auth_h():
    return {"Authorization": f"Bearer {st.session_state.access_token}"} if st.session_state.get("access_token") else {}

def handle_api_response(r, default=None):
    if r.status_code == 401:
        # Prevent infinite rerun loops by checking a flag
        if not st.session_state.get("auth_rerun_flag", False):
            st.session_state.auth_rerun_flag = True
            st.session_state.access_token = None
            st.rerun()
        else:
            # Already attempted rerun, show error and reset flag
            st.session_state.auth_rerun_flag = False
            st.error(t("auth_failed"))
    if not r.ok:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        st.toast(f"{t('operation_failed')}: {str(detail)[:160]}", icon="❌")
        return default
    if not r.text:
        return {"status": "success"} if default is None else default
    try:
        return r.json()
    except ValueError:
        return {"status": "success"} if default is None else default

def api_get(endpoint, params=None):
    try:
        r = requests.get(f"/api{endpoint}", params=params, headers=auth_h(), timeout=API_TIMEOUT)
        return handle_api_response(r, default={})
    except requests.RequestException as e:
        st.toast(f"{t('operation_failed')}: {e}", icon="❌")
        return None

def api_post(endpoint, params=None, json_data=None, files=None):
    try:
        if files:
            r = requests.post(f"/api{endpoint}", params=params, files=files, headers=auth_h(), timeout=max(API_TIMEOUT, 60))
        else:
            r = requests.post(f"/api{endpoint}", params=params, json=json_data, headers=auth_h(), timeout=API_TIMEOUT)
        return handle_api_response(r)
    except requests.RequestException as e:
        st.toast(f"{t('operation_failed')}: {e}", icon="❌")
        return None

def api_put(endpoint, params=None, json_data=None):
    try:
        r = requests.put(f"/api{endpoint}", params=params, json=json_data, headers=auth_h(), timeout=API_TIMEOUT)
        return handle_api_response(r, default={})
    except requests.RequestException as e:
        st.toast(f"{t('operation_failed')}: {e}", icon="❌")
        return None

def api_delete(endpoint, params=None):
    try:
        r = requests.delete(f"/api{endpoint}", params=params, headers=auth_h(), timeout=API_TIMEOUT)
        return handle_api_response(r, default={})
    except requests.RequestException as e:
        st.toast(f"{t('operation_failed')}: {e}", icon="❌")
        return None

def to_date(val):
    if val:
        try:
            return datetime.strptime(val, "%Y-%m-%d").date()
        except:
            return None
    return None

def generate_employee_template():
    col_mapping = {
        "工号": "id_nomor",
        "姓名": "name_nama",
        "归属公司": "company",
        "车间": "ws_bengkel",
        "班组": "team_grup",
        "性别": "gender_jk",
        "岗位(中)": "pos_cn_jabatan",
        "岗位(印)": "pos_id_jabatan",
        "国籍": "nat_negara",
        "宗教": "rel_agama",
        "身份证号": "id_card",
        "入职日期": "hire_date",
        "合同到期日": "contract_end"
    }
    columns = [label(col_mapping[c]) for c in ["工号", "姓名", "归属公司", "车间", "班组", "性别", "岗位(中)", "岗位(印)", "国籍", "宗教", "身份证号", "入职日期", "合同到期日"]]
    df = pd.DataFrame(columns=columns)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()



def custom_toast(msg, icon=None):
    lang = st.session_state.get("lang", "zh")
    if lang == "zh":
        title = "操作成功" if icon == "✅" else ("操作失败" if icon == "❌" else "提示")
    else:
        title = "Berhasil" if icon == "✅" else ("Gagal" if icon == "❌" else "Pemberitahuan")
    st.session_state.modal_message = {
        "title": title,
        "text": msg,
        "icon": icon or "ℹ️"
    }

st.toast = custom_toast

def show_modal_message():
    if "modal_message" in st.session_state:
        msg_info = st.session_state.modal_message
        title = msg_info.get("title", "")
        text = msg_info.get("text", "")
        icon = msg_info.get("icon", "ℹ️")
        
        st.markdown('<div class="custom-modal-backdrop"></div>', unsafe_allow_html=True)
        
        with st.container():
            st.markdown('<div class="modal-marker"></div>', unsafe_allow_html=True)
            st.markdown(f'<div style="font-size: 54px; margin-bottom: 16px; text-align: center;">{icon}</div>', unsafe_allow_html=True)
            st.markdown(f'<h3 style="margin: 0 0 12px 0; color: #0f172a; font-size: 22px; font-weight: 700; text-align: center;">{title}</h3>', unsafe_allow_html=True)
            st.markdown(f'<p style="margin: 0 0 24px 0; color: #475569; font-size: 15px; line-height: 1.6; text-align: center;">{text}</p>', unsafe_allow_html=True)
            
            btn_label = "确定" if st.session_state.get("lang", "zh") == "zh" else "Konfirmasi"
            if st.button(btn_label, key="close_modal_btn", use_container_width=True, type="primary"):
                del st.session_state.modal_message
                st.rerun()



# Display persistent toast message if set in previous run
if "toast_message" in st.session_state:
    msg, icon = st.session_state.toast_message
    st.toast(msg, icon=icon)
    del st.session_state.toast_message

# Sync language toggle state immediately at the start of the rerun to prevent taskbar language lag
if "lang_toggle" in st.session_state:
    st.session_state.lang = "id" if st.session_state.lang_toggle else "zh"

if not st.session_state.access_token:
    brand_col, form_col = st.columns([1.05, 0.95], gap="large")
    with brand_col:
        st.markdown(f"""
        <div class="login-brand">
            <div>
                <h1>{t("login_title")}</h1>
                <p>{t("login_desc")}</p>
                <div class="login-badges">
                    <div class="login-badge">{t("login_badge1")}</div>
                    <div class="login-badge">{t("login_badge2")}</div>
                    <div class="login-badge">{t("login_badge3")}</div>
                    <a href="http://10.158.0.185:8080/login" target="_blank" class="login-badge">
                        {t("indonesian_learning_portal")}
                    </a>
                </div>
            </div>
            <p>{t("login_footer")}</p>
        </div>
        """, unsafe_allow_html=True)
    with form_col:
        st.markdown('<div class="login-form-panel">', unsafe_allow_html=True)
        try:
            logo_resp = requests.get("/api/settings/logo", timeout=3)
            if logo_resp.status_code == 200:
                logo_base64 = base64.b64encode(logo_resp.content).decode()
                st.image(f"data:image/png;base64,{logo_base64}", width=88)
        except:
            pass
        st.markdown(f"<h2>{t('login_welcome')}</h2><div class='hint'>{t('login_hint')}</div>", unsafe_allow_html=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("中文", key="login_zh", use_container_width=True):
                st.session_state.lang = "zh"
                st.rerun()
        with col2:
            if st.button("Bahasa Indonesia", key="login_id", use_container_width=True):
                st.session_state.lang = "id"
                st.rerun()
        with st.form("login_form"):
            u = st.text_input(t("username"), placeholder=t("username"))
            p = st.text_input(t("password"), type="password", placeholder=t("password"))
            submitted = st.form_submit_button(t("login"), use_container_width=True)
            if submitted:
                if not u or not p:
                    st.error(t("login_empty"))
                elif st.session_state.get("_login_done"):
                    # 防止 Streamlit 重渲染时重复发送登录请求
                    st.session_state._login_done = False
                    st.rerun()
                else:
                    try:
                        response = requests.post("/api/auth/login", params={"username": u, "password": p}, timeout=10)
                        if response.status_code == 200:
                            res = response.json()
                            st.session_state._login_done = True
                            st.session_state.access_token = res["access_token"]
                            st.session_state.user_info = {"username": res["username"], "role": res["role"], "ws_scope": res.get("ws_scope")}
                            st.session_state.greeting_shown = False
                            st.rerun()
                        else:
                            st.error(t("login_error"))
                    except Exception as e:
                        st.error(f"{t('login_error')}: {e}")
        st.caption(t("login_footer"))
        st.markdown('</div>', unsafe_allow_html=True)
    st.stop()



# ---------- Windows 任务栏状态栏组件 ----------
import streamlit.components.v1 as components
components.html(
    f"""
    <script>
    const accessToken = "{st.session_state.access_token or ''}";
    
    window.parent._current_access_token = accessToken;
    window.parent._resolved_api_base = "/api";

    const doc = window.parent.document;
    const body = doc.body;

    window.parent.toggleTaskbarPopup = function(id) {{
        let popup = doc.getElementById(id);
        if (!popup) return;
        let isVisible = popup.style.display === 'flex';
        doc.querySelectorAll('.taskbar-popup').forEach(p => p.style.display = 'none');
        if (!isVisible) {{
            popup.style.display = 'flex';
        }}
    }};

    if (!doc.getElementById('taskbar-styles')) {{
        let style = doc.createElement('style');
        style.id = 'taskbar-styles';
        style.innerHTML = `
            .main .block-container {{
                padding-bottom: 80px !important;
            }}
            
            #win-taskbar {{
                position: fixed;
                bottom: 0;
                left: 0;
                right: 0;
                height: 48px;
                background: var(--app-panel) !important;
                backdrop-filter: blur(20px) saturate(180%) !important;
                -webkit-backdrop-filter: blur(20px) saturate(180%) !important;
                border-top: 1px solid var(--app-border) !important;
                z-index: 999990;
                display: none;
                align-items: center;
                justify-content: space-between;
                padding: 0 16px;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
                color: var(--app-text) !important;
                box-sizing: border-box;
                user-select: none;
                box-shadow: 0 -2px 10px rgba(0,0,0,0.05);
            }}
            .taskbar-left {{
                display: flex;
                align-items: center;
                gap: 10px;
            }}
            .taskbar-logo {{
                width: 24px;
                height: 24px;
                object-fit: contain;
                border-radius: 4px;
            }}
            .taskbar-title {{
                font-size: 13.5px;
                font-weight: 600;
                color: var(--app-text) !important;
            }}
            .taskbar-right {{
                display: flex;
                align-items: center;
                gap: 12px;
            }}
            .taskbar-widget {{
                display: flex;
                align-items: center;
                gap: 6px;
                padding: 5px 12px;
                border-radius: 6px;
                cursor: pointer;
                font-size: 13px;
                transition: background-color 0.2s, transform 0.1s;
                position: relative;
                background-color: rgba(255, 255, 255, 0.15) !important;
                border: 1px solid var(--app-border) !important;
                color: var(--app-text) !important;
            }}
            .taskbar-widget:hover {{
                background-color: rgba(255, 255, 255, 0.3) !important;
                transform: translateY(-1px);
            }}
            .taskbar-widget:active {{
                transform: translateY(0);
            }}
            .widget-icon {{
                font-size: 15px;
            }}
            .msg-badge {{
                position: absolute;
                top: -5px;
                right: -5px;
                background-color: #ef4444;
                color: white;
                font-size: 10px;
                font-weight: bold;
                border-radius: 9999px;
                padding: 2px 6px;
                line-height: 1;
                box-shadow: 0 2px 4px rgba(239, 68, 68, 0.2);
            }}
            .taskbar-clock {{
                display: flex;
                flex-direction: column;
                align-items: flex-end;
                font-size: 11px;
                color: var(--app-text) !important;
                opacity: 0.8;
                padding-left: 10px;
                border-left: 1px solid var(--app-border) !important;
            }}
            .taskbar-clock #taskbar-time {{
                font-weight: 600;
                color: var(--app-text) !important;
                font-size: 12px;
            }}
            
            .taskbar-popup {{
                position: fixed;
                bottom: 56px;
                width: 340px;
                max-height: 420px;
                background: var(--app-panel) !important;
                backdrop-filter: blur(25px) saturate(180%) !important;
                -webkit-backdrop-filter: blur(25px) saturate(180%) !important;
                border: 1px solid var(--app-border) !important;
                border-radius: 12px;
                box-shadow: 0 10px 30px rgba(0, 0, 0, 0.15);
                z-index: 1000000;
                display: none;
                flex-direction: column;
                overflow: hidden;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
                animation: slideUp 0.15s cubic-bezier(0.1, 0.9, 0.2, 1);
            }}
            @keyframes slideUp {{
                from {{ transform: translateY(15px); opacity: 0; }}
                to {{ transform: translateY(0); opacity: 1; }}
            }}
            #popup-online {{
                right: 140px;
            }}
            #popup-messages {{
                right: 16px;
            }}
            .popup-header {{
                padding: 12px 16px;
                font-weight: 600;
                font-size: 14px;
                border-bottom: 1px solid var(--border-color, rgba(0, 0, 0, 0.08)) !important;
                background: var(--secondary-background-color, rgba(249, 250, 251, 0.6)) !important;
                display: flex;
                justify-content: space-between;
                align-items: center;
                color: var(--text-color, #111827) !important;
            }}
            .popup-close {{
                cursor: pointer;
                font-size: 14px;
                color: var(--text-color, #9ca3af) !important;
                opacity: 0.6;
            }}
            .popup-close:hover {{
                opacity: 1;
            }}
            .popup-content {{
                padding: 12px;
                overflow-y: auto;
                flex: 1;
                font-size: 12.5px;
                color: var(--text-color, #374151) !important;
            }}
            .popup-item {{
                padding: 10px;
                border-radius: 8px;
                margin-bottom: 8px;
                background: var(--secondary-background-color, rgba(255, 255, 255, 0.7)) !important;
                border: 1px solid var(--border-color, rgba(0, 0, 0, 0.05)) !important;
                box-shadow: 0 2px 4px rgba(0,0,0,0.02);
            }}
            .popup-item:last-child {{
                margin-bottom: 0;
            }}
            .popup-item-title {{
                font-weight: 600;
                color: var(--text-color, #111827) !important;
                margin-bottom: 4px;
                display: flex;
                align-items: center;
                gap: 6px;
            }}
            .popup-item-desc {{
                font-size: 12px;
                color: var(--text-color, #4b5563) !important;
                opacity: 0.85;
                line-height: 1.4;
            }}
            .no-data-msg {{
                text-align: center;
                color: var(--text-color, #9ca3af) !important;
                opacity: 0.6;
                padding: 24px 0;
                font-style: italic;
            }}
        `;
        doc.head.appendChild(style);
    }}

    let container = doc.querySelector('.stApp') || body;

    if (!doc.getElementById('win-taskbar')) {{
        let taskbar = doc.createElement('div');
        taskbar.id = 'win-taskbar';
        taskbar.innerHTML = `
            <div class="taskbar-left">
                <img src="/api/settings/logo" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' viewBox=\\'0 0 24 24\\' fill=\\'%230f766e\\'><path d=\\'M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.53c-.26-.81-1-1.4-1.9-1.4h-1v-3c0-.55-.45-1-1-1h-6v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.4z\\'/></svg>';" class="taskbar-logo">
                <span class="taskbar-title">{t('login_title')}</span>
            </div>
            <div class="taskbar-center">
            </div>
            <div class="taskbar-right">
                <div class="taskbar-widget" id="widget-online" onclick="window.parent.toggleTaskbarPopup('popup-online')">
                    <span class="widget-icon">👥</span>
                    <span id="taskbar-online-count">{t('online_status')}: 0</span>
                </div>
                <div class="taskbar-widget" id="widget-messages" onclick="window.parent.toggleTaskbarPopup('popup-messages')">
                    <span class="widget-icon">💬</span>
                    <span>{t('messages')}</span>
                    <span id="taskbar-msg-badge" class="msg-badge" style="display:none;">0</span>
                </div>
                <div class="taskbar-clock">
                    <div id="taskbar-time">00:00</div>
                    <div id="taskbar-date">2026/01/01</div>
                </div>
            </div>
        `;
        container.appendChild(taskbar);
        
        let popOnline = doc.createElement('div');
        popOnline.id = 'popup-online';
        popOnline.className = 'taskbar-popup';
        popOnline.innerHTML = `
            <div class="popup-header">
                <span>{t('online_title')}</span>
                <span class="popup-close" onclick="window.parent.toggleTaskbarPopup('popup-online')">✕</span>
            </div>
            <div class="popup-content" id="online-users-list">
                <div class="no-data-msg">{t('no_online_users')}</div>
            </div>
        `;
        container.appendChild(popOnline);

        let popMsg = doc.createElement('div');
        popMsg.id = 'popup-messages';
        popMsg.className = 'taskbar-popup';
        popMsg.innerHTML = `
            <div class="popup-header">
                <span>{t('message_notifications')}</span>
                <span class="popup-close" onclick="window.parent.toggleTaskbarPopup('popup-messages')">✕</span>
            </div>
            <div class="popup-content" id="messages-list">
                <div class="no-data-msg">{t('no_notifications')}</div>
            </div>
        `;
        container.appendChild(popMsg);
    }}

    const tb = doc.getElementById('win-taskbar');
    if (!accessToken) {{
        if (tb) tb.style.display = 'none';
        doc.querySelectorAll('.taskbar-popup').forEach(p => p.style.display = 'none');
        if (window.parent._sessions_ws) {{
            window.parent._sessions_ws.close();
            window.parent._sessions_ws = null;
        }}
    }} else {{
        if (tb) tb.style.display = 'flex';
    }}

    if (!window.parent._taskbar_clock_id) {{
        function updateClock() {{
            let now = new Date();
            let hours = String(now.getHours()).padStart(2, '0');
            let minutes = String(now.getMinutes()).padStart(2, '0');
            let timeStr = hours + ':' + minutes;
            
            let year = now.getFullYear();
            let month = String(now.getMonth() + 1).padStart(2, '0');
            let dateVal = String(now.getDate()).padStart(2, '0');
            let dateStr = year + '/' + month + '/' + dateVal;
            
            let tEl = doc.getElementById('taskbar-time');
            let dEl = doc.getElementById('taskbar-date');
            if (tEl) tEl.innerText = timeStr;
            if (dEl) dEl.innerText = dateStr;
        }}
        window.parent._taskbar_clock_id = setInterval(updateClock, 1000);
        updateClock();
    }}

    if (!window.parent._taskbar_click_handler_registered) {{
        doc.addEventListener('click', function(e) {{
            if (!e.target.closest('#win-taskbar') && !e.target.closest('.taskbar-popup')) {{
                doc.querySelectorAll('.taskbar-popup').forEach(p => p.style.display = 'none');
            }}
        }});
        window.parent._taskbar_click_handler_registered = true;
    }}

    window.parent.getOrCreateVirtualMac = function() {{
        let mac = localStorage.getItem('virtual_mac');
        if (!mac) {{
            const hexDigits = "0123456789ABCDEF";
            let parts = ["02"];
            for (let i = 0; i < 5; i++) {{
                parts.push(hexDigits[Math.floor(Math.random() * 16)] + hexDigits[Math.floor(Math.random() * 16)]);
            }}
            mac = parts.join(":");
            localStorage.setItem('virtual_mac', mac);
        }}
        return mac;
    }};

    window.parent.showTaskbarToast = function(message, type='info') {{
        let toastContainer = doc.getElementById('taskbar-toast-container');
        if (!toastContainer) {{
            toastContainer = doc.createElement('div');
            toastContainer.id = 'taskbar-toast-container';
            toastContainer.style.cssText = `
                position: fixed;
                top: 20px;
                right: 20px;
                z-index: 10000000;
                display: flex;
                flex-direction: column;
                gap: 10px;
                font-family: 'Segoe UI', -apple-system, BlinkMacSystemFont, Roboto, sans-serif;
            `;
            body.appendChild(toastContainer);
        }}
        
        const toast = doc.createElement('div');
        toast.style.cssText = `
            padding: 12px 20px;
            border-radius: 8px;
            background: rgba(255, 255, 255, 0.90);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(0,0,0,0.1);
            box-shadow: 0 10px 25px rgba(0,0,0,0.1);
            color: #1f2937;
            font-size: 13.5px;
            font-weight: 500;
            display: flex;
            align-items: center;
            gap: 8px;
            min-width: 200px;
            transform: translateX(120%);
            transition: transform 0.3s cubic-bezier(0.1, 0.9, 0.2, 1);
        `;
        
        let icon = "ℹ️";
        if (type === 'online') {{
            icon = "🟢";
            toast.style.borderLeft = "4px solid #10b981";
        }} else if (type === 'offline') {{
            icon = "🔴";
            toast.style.borderLeft = "4px solid #ef4444";
        }}
        
        toast.innerHTML = `<span>${{icon}}</span><span>${{message}}</span>`;
        toastContainer.appendChild(toast);
        
        toast.offsetHeight; // trigger reflow
        toast.style.transform = "translateX(0)";
        
        setTimeout(() => {{
            toast.style.transform = "translateX(120%)";
            setTimeout(() => {{
                toast.remove();
            }}, 300);
        }}, 4000);
    }};

    if (!window.parent._prev_online_users) {{
        window.parent._prev_online_users = {{}};
    }}

    window.parent.updateOnlineUsersUI = function(users) {{
        let countEl = doc.getElementById('taskbar-online-count');
        if (countEl) countEl.innerText = '{t("online_status")}: ' + users.length;
        
        let listEl = doc.getElementById('online-users-list');
        if (listEl) {{
            if (users.length === 0) {{
                listEl.innerHTML = '<div class="no-data-msg">{t("no_online_users")}</div>';
            }} else {{
                listEl.innerHTML = users.map(u => {{
                    const ipHtml = u.ip ? `<div class="popup-item-desc">IP: ${{u.ip}}</div>` : '';
                    return `
                        <div class="popup-item">
                            <div class="popup-item-title">🟢 ${{u.user}}</div>
                            ${{ipHtml}}
                        </div>
                    `;
                }}).join('');
            }}
        }}

        // Online/Offline alerts logic
        let currentUsers = {{}};
        users.forEach(u => {{
            currentUsers[u.user + '@' + u.ip] = u.user;
        }});
        
        let prevUsers = window.parent._prev_online_users;
        
        // Check offline
        for (let key in prevUsers) {{
            if (!currentUsers[key]) {{
                let username = prevUsers[key];
                let msg = "{t('online_toast_out')}".replace("{{user}}", username);
                window.parent.showTaskbarToast(msg, 'offline');
            }}
        }}
        
        // Check online
        for (let key in currentUsers) {{
            if (!prevUsers[key]) {{
                let username = currentUsers[key];
                let msg = "{t('online_toast_in')}".replace("{{user}}", username);
                if (Object.keys(prevUsers).length > 0) {{
                    window.parent.showTaskbarToast(msg, 'online');
                }}
            }}
        }}
        
        window.parent._prev_online_users = currentUsers;
    }};

    window.parent.updateMessagesUI = function(birthdayList, laborList, summaryData) {{
        let totalMessages = 0;
        let itemsHtml = [];
        
        if (summaryData && summaryData.length > 0) {{
            totalMessages += 1;
            let titleText = "{t('yesterday_summary')}";
            let descText = "{t('yesterday_summary_desc_format')}".replace("{{count}}", summaryData.length);
            itemsHtml.push(`
                <div class="popup-item">
                    <div class="popup-item-title">📋 ${{titleText}}</div>
                    <div class="popup-item-desc">${{descText}}</div>
                </div>
            `);
        }}
        
        if (birthdayList && birthdayList.length > 0) {{
            totalMessages += birthdayList.length;
            birthdayList.forEach(b => {{
                let titleText = "{t('birthday_reminder')}";
                let desc = b.days_left === 0 ? 
                    "{t('birthday_today_format')}".replace("{{name}}", "<b>" + b.name + "</b>") : 
                    "{t('birthday_upcoming_format')}".replace("{{name}}", "<b>" + b.name + "</b>").replace("{{days}}", "<b>" + b.days_left + "</b>");
                itemsHtml.push(`
                    <div class="popup-item">
                        <div class="popup-item-title">🎂 ${{titleText}} (${{b.name}})</div>
                        <div class="popup-item-desc">${{desc}}</div>
                    </div>
                `);
            }});
        }}
        
        if (laborList && laborList.length > 0) {{
            totalMessages += laborList.length;
            laborList.forEach(r => {{
                let titleText = "{t('labor_expiry_reminder')}";
                let statusText = r.overdue ? 
                    '<span style="color:#ef4444;font-weight:bold;">' + "{t('overdue')}" + '</span>' : 
                    "{t('days_left_format')}".replace("{{days}}", "<b>" + r.days_left + "</b>");
                
                let desc = "{t('labor_expiry_reminder_desc_format')}"
                    .replace("{{name}}", "<b>" + r.name + "</b>")
                    .replace("{{id_nomor}}", r.id_nomor)
                    .replace("{{item}}", "<b>" + r.item + "</b>")
                    .replace("{{status}}", statusText)
                    .replace("{{date}}", r.next_issue_date);

                itemsHtml.push(`
                    <div class="popup-item">
                        <div class="popup-item-title">${{titleText}}</div>
                        <div class="popup-item-desc">${{desc}}</div>
                    </div>
                `);
            }});
        }}
        
        let badgeEl = doc.getElementById('taskbar-msg-badge');
        if (badgeEl) {{
            if (totalMessages > 0) {{
                badgeEl.innerText = totalMessages;
                badgeEl.style.display = 'block';
            }} else {{
                badgeEl.style.display = 'none';
            }}
        }}
        
        let listEl = doc.getElementById('messages-list');
        if (listEl) {{
            if (itemsHtml.length === 0) {{
                listEl.innerHTML = '<div class="no-data-msg">{t("no_notifications")}</div>';
            }} else {{
                listEl.innerHTML = itemsHtml.join('');
            }}
        }}
    }};

    window.parent.connectSessionsWS = function() {{
        const token = window.parent._current_access_token;
        if (!token) return;

        if (window.parent._sessions_ws && (window.parent._sessions_ws.readyState === WebSocket.OPEN || window.parent._sessions_ws.readyState === WebSocket.CONNECTING)) {{
            return;
        }}

        let wsProtocol = window.parent.location.protocol === "https:" ? "wss:" : "ws:";
        let wsUrl = wsProtocol + "//" + window.parent.location.host + "/ws/sessions?token=" + encodeURIComponent(token);

        const ws = new WebSocket(wsUrl);
        window.parent._sessions_ws = ws;

        ws.onmessage = function(event) {{
            try {{
                const msg = JSON.parse(event.data);
                if (msg.type === "online_users") {{
                    window.parent.updateOnlineUsersUI(msg.data);
                }}
            }} catch (e) {{
                console.error("WS error parsing message:", e);
            }}
        }};

        ws.onclose = function() {{
            setTimeout(window.parent.connectSessionsWS, 5000);
        }};

        ws.onerror = function(err) {{
            console.error("WS error:", err);
            ws.close();
        }};
    }};

    window.parent.fetchTaskbarData = function() {{
        const token = window.parent._current_access_token;
        const url = window.parent._resolved_api_base;
        if (!token || !url) return;
        
        const yesterdayDate = new Date();
        yesterdayDate.setDate(yesterdayDate.getDate() - 1);
        const yyyy = yesterdayDate.getFullYear();
        const mm = String(yesterdayDate.getMonth() + 1).padStart(2, '0');
        const dd = String(yesterdayDate.getDate()).padStart(2, '0');
        const yesterdayStr = yyyy + "-" + mm + "-" + dd;
        
        let p2 = fetch(url + "/employees/birthday_reminders?days=7", {{
            headers: {{ "Authorization": "Bearer " + token }}
        }}).then(res => res.json()).catch(err => {{ console.log(err); return []; }});

        let p3 = fetch(url + "/labor/reminders", {{
            headers: {{ "Authorization": "Bearer " + token }}
        }}).then(res => res.json()).catch(err => {{ console.log(err); return []; }});

        let p4 = fetch(url + "/logs/summary?date_str=" + yesterdayStr, {{
            headers: {{ "Authorization": "Bearer " + token }}
        }}).then(res => res.json()).catch(err => {{ console.log(err); return null; }});

        Promise.all([p2, p3, p4]).then(([birthdays, labors, summary]) => {{
            window.parent.updateMessagesUI(birthdays, labors, summary);
        }});
    }};

    if (!window.parent._taskbar_poll_id) {{
        window.parent.fetchTaskbarData();
        window.parent.connectSessionsWS();
        window.parent._taskbar_poll_id = setInterval(function() {{
            window.parent.fetchTaskbarData();
        }}, 60000);
    }} else {{
        window.parent.fetchTaskbarData();
        window.parent.connectSessionsWS();
    }}
    </script>
    """,
    height=0,
    width=0
)

# ---------- 登录后提示 ----------
if not st.session_state.greeting_shown:
    st.session_state.greeting_shown = True

# ---------- 菜单 ----------
st.sidebar.title(t("login_title"))
st.sidebar.toggle("Bahasa Indonesia/中文", value=(st.session_state.lang == "id"), key="lang_toggle")
st.session_state.lang = "id" if st.session_state.lang_toggle else "zh"


menu_options = [t("dashboard"), t("org_chart"), t("employees"), t("resigned"), t("labor"), t("logs")]
if st.session_state.user_info.get("role") == "admin":
    menu_options.insert(4, t("transfer_records"))
    menu_options.append("📊 导出成本报表")
    menu_options.append(t("attendance_converter"))
if st.session_state.user_info.get("username") == "admin":
    menu_options.append(t("backup_management"))
    menu_options.append(t("settings"))
menu = st.sidebar.radio("Menu", menu_options, key="menu_radio")

# 历史提醒按钮
if st.sidebar.button(t("history_reminder"), key="history_reminder_btn"):
    st.session_state.show_history = not st.session_state.get("show_history", False)

if st.session_state.get("show_history"):
    with st.sidebar:
        st.subheader(t("history_reminder"))
        history = api_get("/notifications/history", {"days": 7})
        if history:
            for day in history:
                st.markdown(f"**{day['date']}**")
                st.caption(t("log_count_format").format(count=day['log_count']))
                if day.get('logs_detail'):
                    with st.expander(t("view_detail_logs").format(count=len(day['logs_detail']))):
                        for log in day['logs_detail']:
                            st.markdown(f"**{log['time']}** | `{t(log['type'])}` | {log['operator']} | {t('id_nomor')}:{log['id_nomor']} {log['name']}")
                            st.caption(f"{t('change_arrow')}: {log['old']} → {log['new']}")
                            st.divider()
                if day.get('birthday_reminders'):
                    st.write(t("birthday_employees"))
                    for b in day['birthday_reminders']:
                        st.write(f"- {b['name']} ({b['id_nomor']}) {t('birthday_label')} {b['birth_date']}")
                if day.get('labor_reminders'):
                    st.write(t("labor_expired_label"))
                    for l in day['labor_reminders']:
                        st.write(f"- {l['name']} ({l['id_nomor']}) - {l['item']} {t('next_issue_date_label')} {l['next_issue_date']}")
        else:
            st.info(t("no_history_records"))

if st.sidebar.button(t("logout"), key="logout_btn"):
    st.session_state.access_token = None
    st.rerun()

# 权限变量
is_admin = st.session_state.user_info.get("role") == "admin"
is_admin_account = st.session_state.user_info.get("username") == "admin"
can_write = is_admin

# 在线用户已移至底部状态栏显示

# 辅助函数
def get_gender_options():
    genders = api_get("/meta/性别")
    if not genders:
        genders = ["男", "女"]
    return genders

def get_religion_options():
    religions = api_get("/meta/宗教")
    return religions

# ==================== 数据看板 ====================
if menu == t("dashboard"):
    st.header(t("dashboard"))
    st.markdown(f'<div class="section-note">{t("dashboard_note")}</div>', unsafe_allow_html=True)
    dash = api_get("/dashboard")
    if dash:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric(t("total_active"), dash["total_active"])
        c2.metric(t("total_quota"), dash.get("total_quota", 0))
        c3.metric(t("total_resigned"), dash["total_resigned"])
        c4.metric(t("total_employees"), dash["total_active"] + dash["total_resigned"])
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            f"{t('workshop_dist')}/{t('nation_dist')}",
            f"{t('gender_dist')}/{t('age_dist')}",
            t("resign_trend"),
            t("workshop_nation_matrix"),
            t("workshop_team_nation")
        ])
        with tab1:
            col1, col2 = st.columns(2)
            ws = pd.DataFrame(dash.get("workshop_distribution", []))
            if not ws.empty:
                ws["name"] = ws["name"].apply(t_val)
                fig = px.pie(ws, names="name", values="count", title=t("workshop_dist"))
                fig.update_traces(textposition='inside', textinfo='percent+label')
                col1.plotly_chart(fig, use_container_width=True)
            nat = pd.DataFrame(dash.get("nation_distribution", []))
            if not nat.empty:
                nat["name"] = nat["name"].apply(t_val)
                fig = px.bar(nat, x="name", y="count", title=t("nation_dist"), text="count")
                fig.update_traces(textposition='outside')
                col2.plotly_chart(fig, use_container_width=True)
            
            # Grouped bar chart comparing active vs quota for each workshop
            comp_rows = []
            translated_quota_by_ws = {t_val(k): v for k, v in dash.get("quota_by_ws", {}).items()}
            for r in dash.get("workshop_distribution", []):
                ws_name = t_val(r["name"])
                active_cnt = r["count"]
                quota_cnt = translated_quota_by_ws.get(ws_name, 0)
                comp_rows.append({"workshop": ws_name, "type": t("total_active"), "count": active_cnt})
                comp_rows.append({"workshop": ws_name, "type": t("quota_label"), "count": quota_cnt})
                
            comp_df = pd.DataFrame(comp_rows)
            if not comp_df.empty:
                st.markdown("---")
                fig_comp = px.bar(
                    comp_df, 
                    x="workshop", 
                    y="count", 
                    color="type", 
                    barmode="group",
                    title=t("workshop_quota_comparison"), 
                    text="count",
                    color_discrete_map={t("total_active"): "#1f77b4", t("quota_label"): "#2ca02c"}
                )
                fig_comp.update_traces(textposition='outside')
                st.plotly_chart(fig_comp, use_container_width=True)
        with tab2:
            col1, col2 = st.columns(2)
            gen = pd.DataFrame(dash.get("gender_distribution", []))
            if not gen.empty:
                gen["name"] = gen["name"].apply(t_val)
                fig = px.pie(gen, names="name", values="count", title=t("gender_dist"))
                fig.update_traces(textposition='inside', textinfo='percent+label')
                col1.plotly_chart(fig, use_container_width=True)
            age = pd.DataFrame(dash.get("age_distribution", []))
            if not age.empty:
                fig = px.bar(age, x="name", y="count", title=t("age_dist"), text="count")
                fig.update_traces(textposition='outside')
                col2.plotly_chart(fig, use_container_width=True)
        with tab3:
            resign = pd.DataFrame(dash.get("monthly_resign", []))
            if not resign.empty:
                # Add text labels displaying numbers on the line chart points
                fig = px.line(resign, x="month", y="count", title=t("resign_trend"), markers=True, text="count")
                fig.update_traces(textposition='top center', texttemplate='%{y}', mode='lines+markers+text')
                st.plotly_chart(fig, use_container_width=True)
            
            # Additional charts for workshop, nationality, and team resignations
            st.markdown("---")
            st.subheader(t("resign_distribution_analysis"))
            
            col1, col2 = st.columns(2)
            
            # Workshop resignation distribution (Pie Chart)
            r_ws = pd.DataFrame(dash.get("resign_workshop_distribution", []))
            if not r_ws.empty:
                r_ws["name"] = r_ws["name"].apply(t_val)
                fig_ws = px.pie(r_ws, names="name", values="count", title=t("resign_workshop_dist"))
                fig_ws.update_traces(textposition='inside', textinfo='percent+label')
                col1.plotly_chart(fig_ws, use_container_width=True)
            else:
                col1.info(t("no_data"))
                
            # Nationality resignation distribution (Bar Chart)
            r_nat = pd.DataFrame(dash.get("resign_nation_distribution", []))
            if not r_nat.empty:
                r_nat["name"] = r_nat["name"].apply(t_val)
                fig_nat = px.bar(r_nat, x="name", y="count", title=t("resign_nation_dist"), text="count")
                fig_nat.update_traces(textposition='outside')
                col2.plotly_chart(fig_nat, use_container_width=True)
            else:
                col2.info(t("no_data"))
                
            # Team resignation distribution (Horizontal Bar Chart)
            r_team = pd.DataFrame(dash.get("resign_team_distribution", []))
            if not r_team.empty:
                r_team["name"] = r_team["name"].apply(t_val)
                # Sort values by count ascending for Plotly's bottom-to-top rendering of horizontal bar charts
                r_team = r_team.sort_values(by="count", ascending=True)
                fig_team = px.bar(r_team, x="count", y="name", orientation="h", title=t("resign_team_dist"), text="count")
                fig_team.update_traces(textposition='outside')
                st.plotly_chart(fig_team, use_container_width=True)
        with tab4:
            st.subheader(t("workshop_nation_matrix"))
            all_active = api_get("/employees", {"status": t("status_active"), "page": 1, "page_size": 10000})
            if all_active and all_active.get("data"):
                df_emp = pd.DataFrame(all_active["data"])
                ws_list = api_get("/meta/车间") or []
                nat_list = api_get("/meta/国籍") or []
                col1, col2 = st.columns(2)
                selected_ws = col1.multiselect(t("workshop"), ws_list, default=ws_list, format_func=t_val)
                selected_nat = col2.multiselect(t("nationality"), nat_list, default=nat_list, format_func=t_val)
                if selected_ws:
                    df_emp = df_emp[df_emp["ws_bengkel"].isin(selected_ws)]
                if selected_nat:
                    df_emp = df_emp[df_emp["nat_negara"].isin(selected_nat)]
                if not df_emp.empty:
                    df_emp["ws_bengkel"] = df_emp["ws_bengkel"].apply(t_val)
                    df_emp["nat_negara"] = df_emp["nat_negara"].apply(t_val)
                    pivot = pd.pivot_table(df_emp, values="id_nomor", index="ws_bengkel", columns="nat_negara", aggfunc="count", fill_value=0)
                    pivot[t("total_label")] = pivot.sum(axis=1)
                    translated_quota_by_ws = {t_val(k): v for k, v in dash.get("quota_by_ws", {}).items()}
                    pivot[t("col_quota")] = pivot.index.map(lambda x: translated_quota_by_ws.get(x, 0))
                    total_row = pivot.sum(axis=0).to_frame().T
                    total_row.index = [t("total_label")]
                    pivot = pd.concat([pivot, total_row])
                    pivot = pivot.reset_index()
                    pivot = pivot.rename(columns={"ws_bengkel": label("ws_bengkel")})
                    pivot.insert(0, t("seq_no"), range(1, len(pivot) + 1))
                    st.dataframe(pivot, use_container_width=True, hide_index=True, height=min(600, 38*len(pivot)))
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        pivot.to_excel(writer, sheet_name=t("workshop_dist"))
                    output.seek(0)
                    if is_admin:
                        st.download_button(label="📥 " + t("export"), data=output,
                                           file_name=f"workshop_nation_matrix_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                           key="matrix_download")
                else:
                    st.info(t("no_data"))
            else:
                st.info(t("no_data"))
        with tab5:
            st.subheader(t("workshop_team_nation"))
            matrix_data = dash.get("workshop_team_nation_matrix", [])
            if matrix_data:
                df = pd.DataFrame(matrix_data)
                # Translate columns and values
                df = df.rename(columns={
                    "workshop": label("ws_bengkel"),
                    "team": label("team_grup"),
                    "nation": label("nat_negara"),
                    "count": t("col_total")
                })
                # Handle missing or None values
                df = df.fillna(t("unknown"))
                df.iloc[:, 0] = df.iloc[:, 0].apply(lambda x: t_val(x) if x else t("unknown"))
                df.iloc[:, 1] = df.iloc[:, 1].apply(lambda x: t_val(x) if x else t("unknown"))
                df.iloc[:, 2] = df.iloc[:, 2].apply(lambda x: t_val(x) if x else t("unknown"))
                
                # Filters at the top
                c_filter1, c_filter2 = st.columns(2)
                ws_list = sorted(df[label("ws_bengkel")].unique())
                selected_ws = c_filter1.multiselect(label("ws_bengkel"), ws_list, default=ws_list)
                
                df_filtered = df[df[label("ws_bengkel")].isin(selected_ws)] if selected_ws else df
                
                team_list = sorted(df_filtered[label("team_grup")].unique())
                selected_teams = c_filter2.multiselect(label("team_grup"), team_list, default=team_list)
                
                df_filtered = df_filtered[df_filtered[label("team_grup")].isin(selected_teams)] if selected_teams else df_filtered
                
                if not df_filtered.empty:
                    # VERTICAL MIND MAP (LINEAR TREE) VIEW
                    # Build hierarchy: Root -> WS -> Team -> Nation
                    tree_struct = {}
                    for _, row in df_filtered.iterrows():
                        ws_val = row[label("ws_bengkel")]
                        tm_val = row[label("team_grup")]
                        nt_val = row[label("nat_negara")]
                        cnt_val = row[t("col_total")]
                        
                        if ws_val not in tree_struct:
                            tree_struct[ws_val] = {}
                        if tm_val not in tree_struct[ws_val]:
                            tree_struct[ws_val][tm_val] = {}
                        tree_struct[ws_val][tm_val][nt_val] = cnt_val
                        
                    nodes = []
                    edges = []
                    x_curr = 0.0
                    ws_x_list = []
                    
                    for ws_val, teams_dict in tree_struct.items():
                        team_x_list = []
                        for tm_val, nats_dict in teams_dict.items():
                            nat_x_list = []
                            for nt_val, cnt_val in nats_dict.items():
                                # Leaf: Nationality (at y = 0.0)
                                nt_key = f"nt_{ws_val}_{tm_val}_{nt_val}"
                                nodes.append({
                                    "id": nt_key,
                                    "label": f"{nt_val}<br>({cnt_val})",
                                    "x": x_curr,
                                    "y": 0.0,
                                    "color": "#1f77b4", # Blue
                                    "size": 10,
                                    "textposition": "bottom center"
                                })
                                nat_x_list.append(x_curr)
                                x_curr += 1.0
                            
                            # Team (at y = 1.0)
                            tm_key = f"tm_{ws_val}_{tm_val}"
                            team_x = sum(nat_x_list) / len(nat_x_list) if nat_x_list else 0
                            team_total = sum(nats_dict.values())
                            nodes.append({
                                "id": tm_key,
                                "label": f"{tm_val}<br>({team_total})",
                                "x": team_x,
                                "y": 1.0,
                                "color": "#ff7f0e", # Orange
                                "size": 14,
                                "textposition": "top center"
                            })
                            team_x_list.append(team_x)
                            # Edges from Team to Nats
                            for nt_val in nats_dict.keys():
                                edges.append((tm_key, f"nt_{ws_val}_{tm_val}_{nt_val}"))
                                
                        # Workshop (at y = 2.0)
                        ws_key = f"ws_{ws_val}"
                        ws_x = sum(team_x_list) / len(team_x_list) if team_x_list else 0
                        ws_total = sum(sum(nats_dict.values()) for nats_dict in teams_dict.values())
                        nodes.append({
                            "id": ws_key,
                            "label": f"{ws_val}<br>({ws_total})",
                            "x": ws_x,
                            "y": 2.0,
                            "color": "#2ca02c", # Green
                            "size": 18,
                            "textposition": "top center"
                        })
                        ws_x_list.append(ws_x)
                        # Edges from Workshop to Teams
                        for tm_val in teams_dict.keys():
                            edges.append((ws_key, f"tm_{ws_val}_{tm_val}"))
                        
                        # Extra gap between workshops
                        x_curr += 0.8
                        
                    # Root Node (at y = 3.0)
                    root_key = "root_node"
                    root_x = sum(ws_x_list) / len(ws_x_list) if ws_x_list else 0
                    total_count = df_filtered[t("col_total")].sum()
                    nodes.append({
                        "id": root_key,
                        "label": f"{t('total_employees')}: {total_count}",
                        "x": root_x,
                        "y": 3.0,
                        "color": "#d62728", # Red
                        "size": 22,
                        "textposition": "top center"
                    })
                    for ws_val in tree_struct.keys():
                        edges.append((root_key, f"ws_{ws_val}"))
                        
                    # Build bezier arc shapes for edges
                    shapes = []
                    for edge in edges:
                        start_node = next(n for n in nodes if n["id"] == edge[0])
                        end_node = next(n for n in nodes if n["id"] == edge[1])
                        x0, y0 = start_node["x"], start_node["y"]
                        x1, y1 = end_node["x"], end_node["y"]
                        cy = (y0 + y1) / 2
                        path = f"M {x0},{y0} C {x0},{cy} {x1},{cy} {x1},{y1}"
                        shapes.append(dict(
                            type="path",
                            path=path,
                            line=dict(color="#ccc", width=1.5),
                            fillcolor="rgba(0,0,0,0)",
                            layer="below"
                        ))
                        
                    # Build node scatter trace
                    node_x = [n["x"] for n in nodes]
                    node_y = [n["y"] for n in nodes]
                    node_text = [n["label"] for n in nodes]
                    node_color = [n["color"] for n in nodes]
                    node_size = [n["size"] for n in nodes]
                    node_textposition = [n["textposition"] for n in nodes]
                    
                    node_trace = go.Scatter(
                        x=node_x, y=node_y,
                        mode='markers+text',
                        hoverinfo='text',
                        text=node_text,
                        textposition=node_textposition,
                        marker=dict(
                            showscale=False,
                            color=node_color,
                            size=node_size,
                            line_width=1.5,
                            line_color='#fff'
                        )
                    )
                    
                    x_min = min(node_x) - 1.0 if node_x else -1.0
                    x_max = max(node_x) + 1.0 if node_x else 1.0
                    n_leaves = len([n for n in nodes if n["id"].startswith("nt_")])
                    chart_width = max(700, min(2400, n_leaves * 100 + 200))
                    chart_height = 550

                    fig = go.Figure(
                        data=[node_trace],
                        layout=go.Layout(
                            showlegend=False,
                            hovermode='closest',
                            dragmode="pan",
                            margin=dict(b=60, l=40, r=40, t=40),
                            shapes=shapes,
                            xaxis=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=False, range=[x_min, x_max]),
                            yaxis=dict(showgrid=False, zeroline=False, showticklabels=False, fixedrange=False, range=[-0.5, 3.5]),
                            plot_bgcolor='rgba(0,0,0,0)',
                            paper_bgcolor='rgba(0,0,0,0)',
                            width=chart_width,
                            height=chart_height
                        )
                    )
                    
                    import plotly.io as _pio
                    import streamlit.components.v1 as _components
                    fig_html = _pio.to_html(
                        fig, full_html=False,
                        include_plotlyjs="cdn",
                        config={"displayModeBar": False, "scrollZoom": True}
                    )
                    scroll_html = f"""
                    <div style="
                        overflow-x: auto;
                        overflow-y: hidden;
                        width: 100%;
                        border: 1px solid rgba(128,128,128,0.2);
                        border-radius: 8px;
                        background: transparent;
                        padding-bottom: 6px;
                    ">
                        {fig_html}
                    </div>
                    """
                    _components.html(scroll_html, height=chart_height + 55, scrolling=False)
                    
                    # Detail data table expandable at bottom
                    st.markdown("---")
                    with st.expander(t("view_detail_data"), expanded=False):
                        df_show = df_filtered.copy()
                        df_show.insert(0, t("seq_no"), range(1, len(df_show) + 1))
                        st.dataframe(df_show, use_container_width=True, hide_index=True)
                        
                        total_sum = df_filtered[t("col_total")].sum()
                        st.metric(t("total_employees"), total_sum)
                else:
                    st.info(t("no_data"))
            else:
                st.info(t("no_data"))
    else:
        st.info(t("no_data"))
# ==================== 组织架构图（支持动态国籍） ====================
elif menu == t("org_chart"):
    st.header(t("org_chart"))

    org_data = api_get("/org_chart_data")
    if not org_data or "nodes" not in org_data:
        st.info(t("no_data"))
        st.stop()

    nodes = org_data.get("nodes", [])
    nations = org_data.get("nations", [])
    node_by_key = {node["key"]: node for node in nodes}
    total_people = int(node_by_key.get("root", {}).get("total", 0))
    workshop_count = sum(1 for node in nodes if node.get("level") == 1)
    team_count = sum(1 for node in nodes if node.get("level") == 2)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(t("metric_active_total"), total_people)
    m2.metric(t("metric_workshop_count"), workshop_count)
    m3.metric(t("metric_team_count"), team_count)
    m4.metric(t("metric_nation_count"), len(nations))

    def parent_option(node):
        return t("top_level") if not node.get("key") else f"{node.get('display_name') or node.get('name')} [{node.get('key')}]"

    parent_options = [t("top_level")] + [parent_option(n) for n in nodes]
    option_to_key = {t("top_level"): ""}
    for n in nodes:
        option_to_key[parent_option(n)] = n["key"]
    key_to_option = {v: k for k, v in option_to_key.items()}

    def build_editor_df(source_nodes):
        rows = []
        for idx, node in enumerate(source_nodes):
            rows.append({
                "sort": int(node.get("sort", idx)),
                "key": node["key"],
                "display_name": node.get("display_name") or node.get("name") or node["key"],
                "type": node.get("type") or "",
                "parent_display": key_to_option.get(node.get("parent") or "", t("top_level")),
                "total": int(node.get("total") or 0),
                "source_name": node.get("name") or "",
            })
        return pd.DataFrame(rows)

    current_signature = "|".join(sorted(node["key"] for node in nodes))
    if st.session_state.get("org_nodes_signature") != current_signature:
        st.session_state.org_nodes_signature = current_signature
        st.session_state.org_editor_df = build_editor_df(nodes)

    editor_df = st.session_state.get("org_editor_df", build_editor_df(nodes))
    tab_chart, tab_manage, tab_detail, tab_quota = st.tabs([t("tab_overview"), t("tab_hierarchy"), t("tab_nationality_detail"), t("tab_quota_settings")])

    with tab_manage:
        st.caption(t("org_manage_caption"))
        edited_df = st.data_editor(
            editor_df,
            column_config={
                "sort": st.column_config.NumberColumn(t("col_sort"), min_value=0, step=1),
                "key": st.column_config.TextColumn(t("col_node_id"), disabled=True),
                "source_name": st.column_config.TextColumn(t("col_source"), disabled=True),
                "display_name": st.column_config.TextColumn(t("col_display_name"), required=True),
                "type": st.column_config.SelectboxColumn(
                    t("col_type"),
                    options=["部门", "经理", "高级主任", "主任", "副主任", "车间", "班组", "其他"]
                ),
                "parent_display": st.column_config.SelectboxColumn(t("col_parent"), options=parent_options),
                "total": st.column_config.NumberColumn(t("col_total"), disabled=True),
            },
            use_container_width=True,
            hide_index=True,
            key="org_editor",
            disabled=["key", "source_name", "total"],
            column_order=["sort", "display_name", "type", "parent_display", "total", "source_name", "key"]
        )

    preview_nodes = []
    for idx, row in edited_df.iterrows():
        base = node_by_key.get(row["key"], {})
        parent_key = option_to_key.get(row.get("parent_display"), "")
        if row["key"] == "root":
            parent_key = ""
        preview_nodes.append({
            "key": row["key"],
            "name": base.get("name") or row["display_name"],
            "display_name": str(row["display_name"]).strip() or base.get("name") or row["key"],
            "type": row.get("type") or base.get("type") or "",
            "parent": parent_key,
            "total": int(base.get("total") or 0),
            "nations": base.get("nations") or {},
            "sort": int(row.get("sort") or 0),
        })

    preview_keys = {node["key"] for node in preview_nodes}
    has_error = False
    for node in preview_nodes:
        if node["parent"] and node["parent"] not in preview_keys:
            st.warning(node["display_name"] + " " + t("parent_invalid"))
            has_error = True
        if node["parent"] == node["key"]:
            st.warning(node["display_name"] + " " + t("parent_self_invalid"))
            has_error = True

    # Build hierarchy adjacency list
    adj = {n["key"]: [] for n in preview_nodes}
    for n in preview_nodes:
        p = n["parent"]
        if p and p in adj:
            adj[p].append(n["key"])

    # Quota calculation and caching (moved to top level)
    quota_data = api_get("/org_chart/quota") or {}
    has_any_quota = len(quota_data) > 0
    node_quota = {}
    
    def get_node_quota(key):
        if key in node_quota:
            return node_quota[key]
        direct_quota = quota_data.get(key, {})
        parsed_direct = {nat: int(v) for nat, v in direct_quota.items() if int(v) > 0}
        
        children = adj.get(key, [])
        if not children:
            node_quota[key] = parsed_direct
            return parsed_direct
        
        aggregated = {}
        for child in children:
            child_q = get_node_quota(child)
            for nat, val in child_q.items():
                aggregated[nat] = aggregated.get(nat, 0) + val
        node_quota[key] = aggregated
        return aggregated

    if has_any_quota:
        for n in preview_nodes:
            get_node_quota(n["key"])

    def make_hover(row):
        key = row["key"]
        q_dict = node_quota.get(key, {}) if has_any_quota else {}
        q_total = sum(q_dict.values())
        
        if has_any_quota and q_total > 0:
            total_str = f"{int(row['total'])}/{q_total}"
        else:
            total_str = f"{int(row['total'])}"
            
        nations_data = row.get("nations") or {}
        nat_lines = []
        for nat, cnt in nations_data.items():
            q_val = q_dict.get(nat, 0)
            if has_any_quota and q_val > 0:
                nat_lines.append(f"{t_val(nat)}: {cnt}/{q_val}")
            else:
                nat_lines.append(f"{t_val(nat)}: {cnt}")
        
        if has_any_quota:
            for nat, q_val in q_dict.items():
                if nat not in nations_data and q_val > 0:
                    nat_lines.append(f"{t_val(nat)}: 0/{q_val}")
                    
        nat_str = "<br>".join(nat_lines) or t("no_nationality_detail")
        
        return "{0}: {1}<br>{2}: {3}<br>{4}".format(
            t("col_type"), row["type"],
            t("col_total") if not has_any_quota or q_total == 0 else f"{t('col_total')}/{t('quota_label')}",
            total_str,
            nat_str
        )

    chart_df = pd.DataFrame(sorted(preview_nodes, key=lambda n: (n["sort"], n["display_name"])))
    chart_df["hover"] = chart_df.apply(make_hover, axis=1)

    with tab_chart:
        if chart_df.empty:
            st.info(t("no_data"))
        else:
            # View Mode Selection for Org Chart (with persistence)
            if "org_view_mode" not in st.session_state:
                st.session_state.org_view_mode = "sunburst"
            
            mode_options = [t("sunburst_view"), t("mindmap_view")]
            current_index = 0 if st.session_state.org_view_mode == "sunburst" else 1
            
            selected_mode = st.radio(
                t("view_mode"),
                options=mode_options,
                index=current_index,
                horizontal=True,
                key="org_view_mode_radio_selector"
            )
            
            if selected_mode == t("sunburst_view"):
                st.session_state.org_view_mode = "sunburst"
            else:
                st.session_state.org_view_mode = "mindmap"
            
            if st.session_state.org_view_mode == "sunburst":
                chart_df_display = chart_df.copy()
                chart_df_display["display_name"] = chart_df_display["display_name"].apply(t_val)
                fig = px.sunburst(
                    chart_df_display,
                    ids="key",
                    names="display_name",
                    parents="parent",
                    values="total",
                    color="total",
                    color_continuous_scale="Blues",
                    custom_data=["hover"],
                )
                fig.update_traces(branchvalues="total", textinfo="label+value", hovertemplate="%{customdata[0]}<extra></extra>")
                fig.update_layout(height=620, margin=dict(t=20, l=10, r=10, b=10))
                st.plotly_chart(fig, use_container_width=True)
            else:
                # ── COMPACT MIND MAP WITH BEZIER ARCS ──────────────────────────────
                # (adj is defined globally)

                # Find root
                root_candidates = [n["key"] for n in preview_nodes if not n["parent"] or n["key"] == "root"]
                root_key = "root" if "root" in root_candidates else (root_candidates[0] if root_candidates else None)

                if root_key:
                    depths = {}
                    def calc_depths(u, d):
                        depths[u] = d
                        for v in adj.get(u, []):
                            calc_depths(v, d + 1)
                    calc_depths(root_key, 0)
                    max_depth = max(depths.values()) if depths else 1

                    # Standard compact leaf spacing (no extra space for nat sub-nodes)
                    x_curr = [0.0]
                    x_coords = {}

                    def assign_coords(u):
                        children = adj.get(u, [])
                        if not children:
                            x_coords[u] = x_curr[0]
                            x_curr[0] += 1.0
                        else:
                            for v in children:
                                assign_coords(v)
                            x_coords[u] = sum(x_coords[v] for v in children) / len(children)

                    assign_coords(root_key)

                    # Nationality config (for label embedding)
                    NAT_ORDER = ["China 中国籍", "translator 翻译", "IND 印尼籍"]
                    NAT_LABELS_ZH = {"China 中国籍": "中", "translator 翻译": "翻", "IND 印尼籍": "印"}
                    NAT_LABELS_ID = {"China 中国籍": "CN", "translator 翻译": "TR", "IND 印尼籍": "ID"}
                    NAT_COLORS_HEX = {"China 中国籍": "#e63946", "translator 翻译": "#f4a261", "IND 印尼籍": "#2a9d8f"}

                    lang = st.session_state.get("lang", "zh")
                    nat_short = NAT_LABELS_ZH if lang == "zh" else NAT_LABELS_ID
                    # (quota_data, has_any_quota, and node_quota are defined globally)

                    def build_label(n_data, force_details=False):
                        """Build a node label with multiline nationality counts, with quotas if set."""
                        name = t_val(n_data["display_name"])
                        total = n_data.get("total", 0)
                        nations_data = n_data.get("nations") or {}
                        k = n_data["key"]

                        q_dict = node_quota.get(k, {}) if has_any_quota else {}
                        q_total = sum(q_dict.values())
                        
                        if has_any_quota and q_total > 0:
                            total_str = f"{total}/{q_total}"
                        else:
                            total_str = f"{total}"

                        if adj.get(k) and not force_details:  # non-leaf: just name + total
                            return f"<b>{name}</b><br>{total_str}"

                        # Leaf node or hover tooltip: 5 lines total (name + 4 stats lines)
                        total_label = "合计" if lang == "zh" else "Total"
                        lines = [f"<b>{name}</b>", f"{total_label}: {total_str}"]
                        
                        NAT_FULL_ZH = {"China 中国籍": "中国", "translator 翻译": "翻译", "IND 印尼籍": "印尼"}
                        NAT_FULL_ID = {"China 中国籍": "China", "translator 翻译": "Penerjemah", "IND 印尼籍": "Indonesia"}
                        nat_labels = NAT_FULL_ZH if lang == "zh" else NAT_FULL_ID
                        
                        for nat_key in NAT_ORDER:
                            cnt = nations_data.get(nat_key, 0)
                            q_val = q_dict.get(nat_key, 0)
                            label_str = nat_labels.get(nat_key, nat_key)
                            if has_any_quota:
                                if cnt > 0 or q_val > 0:
                                    lines.append(f"{label_str}: {cnt}/{q_val}")
                            else:
                                if cnt > 0:
                                    lines.append(f"{label_str}: {cnt}")
                            
                        return "<br>".join(lines)

                    # Build node list
                    node_map = {n["key"]: n for n in preview_nodes}
                    plotly_nodes = []
                    for n in preview_nodes:
                        k = n["key"]
                        if k in x_coords and k in depths:
                            plotly_nodes.append({
                                "id": k,
                                "label": build_label(n),
                                "hover": build_label(n, force_details=True),
                                "x": x_coords[k],
                                "y": float(max_depth - depths[k]),
                                "type": n.get("type", ""),
                            })

                    node_by_id = {n["id"]: n for n in plotly_nodes}

                    # Build bezier arc shapes for edges
                    shapes = []
                    for n in preview_nodes:
                        k = n["key"]
                        p = n["parent"]
                        if p and p in node_by_id and k in node_by_id:
                            parent_node = node_by_id[p]
                            child_node = node_by_id[k]
                            x0, y0 = parent_node["x"], parent_node["y"]
                            x1, y1 = child_node["x"], child_node["y"]
                            # Cubic bezier: control points at 1/3 and 2/3 of the vertical drop
                            cy = (y0 + y1) / 2
                            # SVG path: M (start) C (cubic bezier with 2 control points) (end)
                            path = f"M {x0},{y0} C {x0},{cy} {x1},{cy} {x1},{y1}"
                            shapes.append(dict(
                                type="path",
                                path=path,
                                line=dict(color="#aaa", width=1.5),
                                fillcolor="rgba(0,0,0,0)",
                                layer="below"
                            ))

                    # Node colours by level
                    node_x = [n["x"] for n in plotly_nodes]
                    node_y = [n["y"] for n in plotly_nodes]
                    node_text = [n["label"] for n in plotly_nodes]
                    node_color = []
                    node_size = []
                    for n in plotly_nodes:
                        yv = n["y"]
                        if yv == max_depth:
                            node_color.append("#d62728"); node_size.append(20)
                        elif yv == max_depth - 1:
                            node_color.append("#2ca02c"); node_size.append(16)
                        elif yv == max_depth - 2:
                            node_color.append("#ff7f0e"); node_size.append(13)
                        else:
                            node_color.append("#1f77b4"); node_size.append(10)

                    node_trace = go.Scatter(
                        x=node_x, y=node_y,
                        mode="markers+text",
                        hoverinfo="text",
                        text=node_text,
                        hovertext=[n["hover"] for n in plotly_nodes],
                        textposition=["bottom center" if not adj.get(n["id"]) else "top center" for n in plotly_nodes],
                        marker=dict(
                            showscale=False,
                            color=node_color,
                            size=node_size,
                            line_width=1.5,
                            line_color="#fff"
                        )
                    )

                    # Layout ranges
                    all_x = node_x
                    all_y = node_y
                    x_min = min(all_x) - 1.0
                    x_max = max(all_x) + 1.0
                    y_min = min(all_y) - 2.2
                    y_max = max(all_y) + 0.8

                    # Chart pixel width: 100px per leaf step, capped between 700 and 2400px
                    n_leaves = sum(1 for n in preview_nodes if not adj.get(n["key"]))
                    chart_width = max(700, min(2400, n_leaves * 100 + 200))
                    chart_height = 640

                    fig = go.Figure(
                        data=[node_trace],
                        layout=go.Layout(
                            showlegend=False,
                            hovermode="closest",
                            dragmode="pan",
                            margin=dict(b=50, l=20, r=20, t=20),
                            shapes=shapes,
                            xaxis=dict(
                                showgrid=False, zeroline=False, showticklabels=False,
                                range=[x_min, x_max], fixedrange=False
                            ),
                            yaxis=dict(
                                showgrid=False, zeroline=False, showticklabels=False,
                                range=[y_min, y_max], fixedrange=False
                            ),
                            plot_bgcolor="rgba(0,0,0,0)",
                            paper_bgcolor="rgba(0,0,0,0)",
                            width=chart_width,
                            height=chart_height,
                        )
                    )

                    # Render in a scrollable div for real horizontal scrollbar
                    import plotly.io as _pio
                    import streamlit.components.v1 as _components
                    fig_html = _pio.to_html(
                        fig, full_html=False,
                        include_plotlyjs="cdn",
                        config={"displayModeBar": False, "scrollZoom": True}
                    )
                    scroll_html = f"""
                    <div style="
                        overflow-x: auto;
                        overflow-y: hidden;
                        width: 100%;
                        border: 1px solid rgba(128,128,128,0.2);
                        border-radius: 8px;
                        background: transparent;
                        padding-bottom: 6px;
                    ">
                        {fig_html}
                    </div>
                    """
                    _components.html(scroll_html, height=chart_height + 55, scrolling=False)

            
            # Detail table placed at the bottom, hidden under expander by default
            st.markdown("---")
            with st.expander(t("view_detail_data"), expanded=False):
                compact = chart_df[["key", "display_name", "type", "total"]].copy()
                compact["display_name"] = compact["display_name"].apply(t_val)
                if has_any_quota:
                    compact["quota"] = compact.apply(lambda r: sum(node_quota.get(r["key"], {}).values()), axis=1)
                
                rename_cols = {
                    "display_name": t("col_display_name"), 
                    "type": t("col_type"), 
                    "total": t("col_total")
                }
                if has_any_quota:
                    rename_cols["quota"] = t("quota_num")
                    compact = compact.rename(columns=rename_cols)
                    st.dataframe(compact[[t("col_display_name"), t("col_type"), t("col_total"), t("quota_num")]], use_container_width=True, hide_index=True)
                else:
                    compact = compact.rename(columns=rename_cols)
                    st.dataframe(compact[[t("col_display_name"), t("col_type"), t("col_total")]], use_container_width=True, hide_index=True)

    with tab_manage:
        save_col, reset_col = st.columns(2)
        with save_col:
            if st.button(t("save_org"), key="save_org_btn", use_container_width=True, disabled=has_error or not is_admin):
                payload = {"nodes": preview_nodes}
                resp = api_post("/org_chart/save_layout", json_data=payload)
                if resp and resp.get("status") == "success":
                    st.session_state.org_editor_df = edited_df.copy()
                    st.session_state.toast_message = (t("org_saved"), "✅")
                    st.rerun()
                else:
                    st.toast(t("operation_failed"), icon="❌")
        with reset_col:
            if st.button(t("reset_org"), key="reset_org_btn", use_container_width=True, disabled=not is_admin):
                resp = api_post("/org_chart/reset_layout")
                if resp and resp.get("status") == "success":
                    if "org_editor_df" in st.session_state:
                        del st.session_state.org_editor_df
                    st.session_state.toast_message = (t("org_reset"), "✅")
                    st.rerun()
                else:
                    st.toast(t("operation_failed"), icon="❌")
        if not is_admin:
            st.info(t("readonly_org_msg"))

    with tab_detail:
        detail_rows = []
        for node in preview_nodes:
            node_key = node["key"]
            nations_data = node.get("nations") or {}
            q_dict = node_quota.get(node_key, {}) if has_any_quota else {}
            
            all_nats = set(nations_data.keys()) | set(q_dict.keys())
            for nat in all_nats:
                count = nations_data.get(nat, 0)
                q_val = q_dict.get(nat, 0)
                detail_rows.append({
                    "display_name": node["display_name"],
                    "type": node["type"],
                    "nationality": nat,
                    "count": int(count),
                    "quota": int(q_val)
                })
        if detail_rows:
            detail_df = pd.DataFrame(detail_rows)
            detail_df["display_name"] = detail_df["display_name"].apply(t_val)
            detail_df["nationality"] = detail_df["nationality"].apply(t_val)
            
            rename_cols = {
                "display_name": t("col_display_name"),
                "type": t("col_type"),
                "nationality": t("nationality"),
                "count": t("col_total")
            }
            if has_any_quota:
                rename_cols["quota"] = t("quota_num")
                detail_df = detail_df.rename(columns=rename_cols)
                cols_to_show = [t("col_display_name"), t("col_type"), t("nationality"), t("col_total"), t("quota_num")]
            else:
                detail_df = detail_df.rename(columns=rename_cols)
                cols_to_show = [t("col_display_name"), t("col_type"), t("nationality"), t("col_total")]
                
            detail_df = detail_df.reset_index(drop=True)
            detail_df.insert(0, t("seq_no"), range(1, len(detail_df) + 1))
            st.dataframe(detail_df[[t("seq_no")] + cols_to_show], use_container_width=True, hide_index=True)
        else:
            st.info(t("no_nationality_detail"))

    with tab_quota:
        st.subheader(t("tab_quota_settings"))
        quota_data = api_get("/org_chart/quota") or {}
        teams_list = [node for node in preview_nodes if node.get("type") == "班组"]
        if not teams_list:
            st.info(t("no_teams_found"))
        else:
            quota_rows = []
            for team in teams_list:
                team_key = team["key"]
                team_quota = quota_data.get(team_key, {})
                row = {
                    "key": team_key,
                    "workshop": t_val(team.get("parent_name") or team.get("parent") or ""),
                    "team_name": t_val(team["display_name"]),
                }
                for nat in nations:
                    row[nat] = int(team_quota.get(nat, 0))
                quota_rows.append(row)
                
            quota_df = pd.DataFrame(quota_rows)
            column_config = {
                "key": st.column_config.TextColumn("Key", disabled=True),
                "workshop": st.column_config.TextColumn(t("workshop"), disabled=True),
                "team_name": st.column_config.TextColumn(t("team"), disabled=True),
            }
            for nat in nations:
                column_config[nat] = st.column_config.NumberColumn(t_val(nat), min_value=0, step=1)
                
            edited_quota_df = st.data_editor(
                quota_df,
                column_config=column_config,
                use_container_width=True,
                hide_index=True,
                disabled=["key", "workshop", "team_name"],
                key="quota_editor"
            )
            
            if st.button(t("save_quota"), key="save_quota_btn", disabled=not is_admin, use_container_width=True):
                new_quota = {}
                for idx, row in edited_quota_df.iterrows():
                    team_key = row["key"]
                    new_quota[team_key] = {}
                    for nat in nations:
                        val = int(row.get(nat, 0))
                        if val > 0:
                            new_quota[team_key][nat] = val
                
                resp = api_post("/org_chart/quota", json_data=new_quota)
                if resp and resp.get("status") == "success":
                    st.session_state.toast_message = (t("quota_saved"), "✅")
                    st.rerun()
                else:
                    st.toast(t("operation_failed"), icon="❌")
        # ==================== 员工花名册 ====================
elif menu == t("employees"):
    st.header(t("employees"))
    st.markdown(f'<div class="section-note">{t("employees_note")}</div>', unsafe_allow_html=True)
    ws_list = api_get("/meta/车间") or []
    team_list = api_get("/meta/班组") or []
    nationality_list = api_get("/meta/国籍") or []
    with st.expander(t("filter")):
        c1, c2, c3, c4 = st.columns(4)
        status_filter = c1.selectbox(t("status_status"), [t("status_active"), t("status_inactive")], key="status_filter")
        ws_filter = c2.selectbox(label("ws_bengkel"), [""] + ws_list, format_func=lambda x: t_val(x) if x else t("all_workshops"), key="ws_filter")
        team_filter = c3.selectbox(label("team_grup"), [""] + team_list, format_func=lambda x: t_val(x) if x else t("all_teams"), key="team_filter")
        nation_filter = c4.selectbox(label("nat_negara"), [""] + nationality_list, format_func=lambda x: t_val(x) if x else t("all_nations"), key="nation_filter")
        search = st.text_input(t("search"), key="employee_search")
    page = st.number_input(t("page"), min_value=1, value=1, key="employee_page")
    page_size = 20
    res = api_get("/employees", {"status": status_filter, "search": search, "ws": ws_filter,
                                  "team": team_filter, "nation": nation_filter, "page": page, "page_size": page_size})
    if res and "data" in res and res["data"]:
        df = pd.DataFrame(res["data"])
        show_cols = ["id_nomor", "name_nama", "company", "ws_bengkel", "team_grup", "pos_cn_jabatan",
                     "nat_negara", "rel_agama", "id_card", "hire_date", "contract_end", "status_status"]
        df_show = df[show_cols].copy()
        for c in ["ws_bengkel", "team_grup", "gender_jk", "nat_negara", "rel_agama", "status_status"]:
            if c in df_show.columns:
                df_show[c] = df_show[c].apply(t_val)
        df_show = df_show.rename(columns={c: label(c) for c in show_cols})

        df_show = df_show.reset_index(drop=True)
        df_show.insert(0, t("seq_no"), range(1, len(df_show) + 1))
        st.dataframe(df_show, use_container_width=True, height=500, hide_index=True)
        st.caption(t("page_info_format").format(total=res['total'], page=page, max_page=max(1, (res['total']-1)//page_size + 1)))
        if is_admin and st.button(t("export"), key="export_btn"):
            export_params = {"status": status_filter, "ws": ws_filter, "team": team_filter, "nation": nation_filter}
            with st.spinner(t("export_generating")):
                r = requests.get("/api/employees/export", params=export_params, headers=auth_h(), timeout=30)
                if r.status_code == 200:
                    st.download_button(label="📥 " + t("export"), data=r.content,
                                       file_name=f"employees_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key="export_download")
                else:
                    st.toast(t("operation_failed"), icon="❌")
    else:
        st.info(t("no_data"))

    # 编辑对话框
    if st.session_state.edit_employee_id:
        emp_data = api_get(f"/employees/query?id_nomor={st.session_state.edit_employee_id}")
        if emp_data:
            with st.form("edit_employee_form"):
                st.subheader(f"{t('edit_employee')} - {emp_data['id_nomor']} {emp_data['name_nama']}")
                f_id = st.text_input(label("id_nomor"), value=emp_data["id_nomor"])
                f_name = st.text_input(label("name_nama"), value=emp_data["name_nama"])
                col1, col2 = st.columns(2)
                ws_options = [""] + ws_list
                ws_idx = ws_options.index(emp_data.get("ws_bengkel", "")) if emp_data.get("ws_bengkel") else 0
                f_ws = col1.selectbox(label("ws_bengkel"), ws_options, index=ws_idx, format_func=lambda x: t_val(x) if x else "", key="edit_ws")
                team_options = [""] + team_list
                team_idx = team_options.index(emp_data.get("team_grup", "")) if emp_data.get("team_grup") else 0
                f_tm = col2.selectbox(label("team_grup"), team_options, index=team_idx, format_func=lambda x: t_val(x) if x else "", key="edit_team")
                c1, c2, c3 = st.columns(3)
                gender_options = get_gender_options()
                gen_idx = gender_options.index(emp_data.get("gender_jk", "")) if emp_data.get("gender_jk") in gender_options else 0
                f_gen = c1.selectbox(label("gender_jk"), gender_options, index=gen_idx, format_func=lambda x: t_val(x) if x else "", key="edit_gen")
                f_nat = c2.selectbox(label("nat_negara"), nationality_list, index=nationality_list.index(emp_data.get("nat_negara", "")) if emp_data.get("nat_negara") in nationality_list else 0, format_func=lambda x: t_val(x) if x else "", key="edit_nat")
                religion_options = get_religion_options()
                if religion_options:
                    rel_idx = religion_options.index(emp_data.get("rel_agama", "")) if emp_data.get("rel_agama") in religion_options else 0
                    f_rel = c3.selectbox(label("rel_agama"), religion_options, index=rel_idx, format_func=lambda x: t_val(x) if x else "", key="edit_rel")
                else:
                    f_rel = c3.text_input(label("rel_agama"), value=emp_data.get("rel_agama", ""), key="edit_rel")
                f_pcn = st.text_input(label("pos_cn_jabatan"), value=emp_data.get("pos_cn_jabatan", ""))
                f_pid = st.text_input(label("pos_id_jabatan"), value=emp_data.get("pos_id_jabatan", ""))
                f_id_card = st.text_input(t("id_card"), value=emp_data.get("id_card", ""))
                f_company = st.text_input(label("company"), value=emp_data.get("company", ""), key="edit_company")
                # 使用 date_input 宽度自适应
                f_hire = st.date_input(label("hire_date"), value=to_date(emp_data.get("hire_date")), format="YYYY-MM-DD", key="edit_hire")
                f_contract = st.date_input(label("contract_end"), value=to_date(emp_data.get("contract_end")), format="YYYY-MM-DD", key="edit_contract")
                col1, col2 = st.columns(2)
                if col1.form_submit_button(t("save")):
                    payload = {
                        "id_nomor": f_id, "name_nama": f_name, "ws_bengkel": f_ws,
                        "team_grup": f_tm, "gender_jk": f_gen, "nat_negara": f_nat,
                        "pos_cn_jabatan": f_pcn, "pos_id_jabatan": f_pid, "rel_agama": f_rel,
                        "id_card": f_id_card, "company": f_company,
                        "hire_date": f_hire.strftime("%Y-%m-%d") if f_hire else "",
                        "contract_end": f_contract.strftime("%Y-%m-%d") if f_contract else ""
                    }
                    save_res = api_post("/employees/save", params={"is_update": True, "original_id": st.session_state.edit_employee_id}, json_data=payload)
                    if save_res and save_res.get("status") == "success":
                        st.session_state.toast_message = (t("operation_success"), "✅")
                        st.session_state.edit_employee_id = None
                        st.rerun()
                    else:
                        st.toast(t("operation_failed"), icon="❌")
                if col2.form_submit_button(t("cancel")):
                    st.session_state.edit_employee_id = None
                    st.rerun()
        else:
            st.error(t("employee_not_exist"))
            st.session_state.edit_employee_id = None
            st.rerun()

    # 离职对话框
    if st.session_state.resign_employee_id:
        emp_data = api_get(f"/employees/query?id_nomor={st.session_state.resign_employee_id}")
        if emp_data:
            with st.form("resign_employee_form"):
                st.subheader(f"{t('resign_employee')} - {emp_data['id_nomor']} {emp_data['name_nama']}")
                resign_date = st.date_input(t("resign_date"), value=date.today())
                reason = st.text_area(t("resign_reason"))
                col1, col2 = st.columns(2)
                if col1.form_submit_button(t("confirm")):
                    resp = api_post("/employees/resign", params={"id_nomor": st.session_state.resign_employee_id,
                                                                 "reason": reason, "resign_date": resign_date.strftime("%Y-%m-%d")})
                    if resp and resp.get("status") == "success":
                        st.session_state.toast_message = (t("operation_success"), "✅")
                        st.session_state.resign_employee_id = None
                        st.rerun()
                    else:
                        st.toast(t("operation_failed"), icon="❌")
                if col2.form_submit_button(t("cancel")):
                    st.session_state.resign_employee_id = None
                    st.rerun()
        else:
            st.error(t("employee_not_exist"))
            st.session_state.resign_employee_id = None
            st.rerun()

    # 员工信息表单（添加/修改）
    if can_write:
        with st.expander(t("employee_form"), expanded=False):
            mode = st.radio(t("mode"), [t("mode_add"), t("mode_edit")], horizontal=True, key="mode_radio")
            if mode == t("mode_edit"):
                all_emp = api_get("/employees", {"page": 1, "page_size": 1000})
                emp_list = all_emp.get("data", []) if all_emp else []
                emp_dict = {e["id_nomor"]: e for e in emp_list}
                selected = st.selectbox(t("select_employee"), [f"{e['id_nomor']} | {e['name_nama']}" for e in emp_list], key="select_emp")
                if selected:
                    eid = selected.split(" | ")[0]
                    edit_init = emp_dict.get(eid, {})
                else:
                    edit_init = {}
            else:
                edit_init = {}
            with st.form("emp_form"):
                # 第一行：工号、姓名并排
                col1, col2 = st.columns(2)
                with col1:
                    f_id = st.text_input(label("id_nomor"), value=edit_init.get("id_nomor", ""))
                with col2:
                    f_name = st.text_input(label("name_nama"), value=edit_init.get("name_nama", ""))
                
                # 第二行：车间、班组并排
                col3, col4 = st.columns(2)
                with col3:
                    ws_options = [""] + ws_list
                    ws_idx = ws_options.index(edit_init.get("ws_bengkel", "")) if edit_init.get("ws_bengkel") else 0
                    f_ws = st.selectbox(label("ws_bengkel"), ws_options, index=ws_idx, format_func=lambda x: t_val(x) if x else "", key="f_ws")
                with col4:
                    team_options = [""] + team_list
                    team_idx = team_options.index(edit_init.get("team_grup", "")) if edit_init.get("team_grup") else 0
                    f_tm = st.selectbox(label("team_grup"), team_options, index=team_idx, format_func=lambda x: t_val(x) if x else "", key="f_tm")
                
                # 第三行：性别、国籍、宗教三列
                col5, col6, col7 = st.columns(3)
                with col5:
                    gender_options = get_gender_options()
                    gen_idx = gender_options.index(edit_init.get("gender_jk", "")) if edit_init.get("gender_jk") in gender_options else 0
                    f_gen = st.selectbox(label("gender_jk"), gender_options, index=gen_idx, format_func=lambda x: t_val(x) if x else "", key="f_gen")
                with col6:
                    f_nat = st.selectbox(label("nat_negara"), nationality_list, index=nationality_list.index(edit_init.get("nat_negara", "")) if edit_init.get("nat_negara") in nationality_list else 0, format_func=lambda x: t_val(x) if x else "", key="f_nat")
                with col7:
                    religion_options = get_religion_options()
                    if religion_options:
                        rel_idx = religion_options.index(edit_init.get("rel_agama", "")) if edit_init.get("rel_agama") in religion_options else 0
                        f_rel = st.selectbox(label("rel_agama"), religion_options, index=rel_idx, format_func=lambda x: t_val(x) if x else "", key="f_rel")
                    else:
                        f_rel = st.text_input(label("rel_agama"), value=edit_init.get("rel_agama", ""), key="f_rel")
                
                # 第四行：岗位(中)、身份证号并排
                col8, col9 = st.columns(2)
                with col8:
                    f_pcn = st.text_input(label("pos_cn_jabatan"), value=edit_init.get("pos_cn_jabatan", ""))
                with col9:
                    f_id_card = st.text_input(t("id_card"), value=edit_init.get("id_card", ""))
                
                # 第五行：岗位(印)、归属公司并排
                col_pid, col_company = st.columns(2)
                with col_pid:
                    f_pid = st.text_input(label("pos_id_jabatan"), value=edit_init.get("pos_id_jabatan", ""))
                with col_company:
                    f_company = st.text_input(label("company"), value=edit_init.get("company", ""), key="f_company")
                
                # 第六行：入职日期、合同到期日并排
                col10, col11 = st.columns(2)
                with col10:
                    f_hire = st.date_input(label("hire_date"), value=to_date(edit_init.get("hire_date")), format="YYYY-MM-DD", key="f_hire")
                with col11:
                    f_contract = st.date_input(label("contract_end"), value=to_date(edit_init.get("contract_end")), format="YYYY-MM-DD", key="f_contract")
                
                # 提交按钮
                if st.form_submit_button(t("save")):
                    if not f_id or not f_name:
                        st.error(t("id_name_required"))
                    else:
                        payload = {
                            "id_nomor": f_id, "name_nama": f_name, "ws_bengkel": f_ws,
                            "team_grup": f_tm, "gender_jk": f_gen, "nat_negara": f_nat,
                            "pos_cn_jabatan": f_pcn, "pos_id_jabatan": f_pid, "rel_agama": f_rel,
                            "id_card": f_id_card, "company": f_company,
                            "hire_date": f_hire.strftime("%Y-%m-%d") if f_hire else "",
                            "contract_end": f_contract.strftime("%Y-%m-%d") if f_contract else ""
                        }
                        orig_id = None
                        if mode == t("mode_edit") and selected:
                            orig_id = selected.split(" | ")[0]
                        save_res = api_post("/employees/save", params={"is_update": mode == t("mode_edit"), "original_id": orig_id}, json_data=payload)
                        if save_res and save_res.get("status") == "success":
                            st.session_state.toast_message = (t("operation_success"), "✅")
                            st.rerun()
                        else:
                            st.toast(t("operation_failed"), icon="❌")
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            template_data = generate_employee_template()
            st.download_button(label=t("template"), data=template_data, file_name="employee_template.xlsx",
                               mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="template_dl")
        with col2:
            up_file = st.file_uploader(t("upload_excel"), type=["xlsx", "xls"], key="import_file")
            if up_file and st.button(t("import"), key="import_btn"):
                with st.spinner(t("importing")):
                    res_import = api_post("/employees/import", files={"file": up_file})
                    if res_import:
                        imported = res_import.get('imported', 0)
                        updated = res_import.get('updated', 0)
                        total = res_import.get('total_rows', 0)
                        st.toast(t("import_toast_format").format(imported=imported, total=total, added=imported - updated, updated=updated), icon="✅")
                        if res_import.get('skipped'):
                            with st.expander(t("skipped_rows").format(count=len(res_import['skipped']))):
                                for s in res_import['skipped']:
                                    st.caption(s)
                        if res_import.get('errors'):
                            with st.expander(t("error_rows").format(count=len(res_import['errors']))):
                                for e in res_import['errors']:
                                    st.error(e)
    else:
        st.info(t("readonly_msg"))

# ==================== 离职名册 ====================
elif menu == t("resigned"):
    st.header(t("resigned"))
    st.markdown(f'<div class="section-note">{t("resigned_note")}</div>', unsafe_allow_html=True)
    tab1, tab2 = st.tabs([t("resign_list"), t("process_resign")])
    with tab1:
        data = api_get("/employees", {"status": t("status_inactive"), "page": 1, "page_size": 10000})
        if data and data.get("data"):
            df = pd.DataFrame(data["data"])
            display_cols = ["resign_date", "id_nomor", "name_nama", "ws_bengkel", "team_grup", "nat_negara", "remark_ket", "resign_operator"]
            df_display = df[display_cols].copy()
            for c in ["ws_bengkel", "team_grup", "nat_negara"]:
                if c in df_display.columns:
                    df_display[c] = df_display[c].apply(t_val)
            if "resign_operator" in df_display.columns:
                df_display["resign_operator"] = df_display["resign_operator"].fillna("")
            df_display.columns = [label(col) for col in display_cols]
            df_display = df_display.reset_index(drop=True)
            df_display.insert(0, t("seq_no"), range(1, len(df_display) + 1))
            st.dataframe(df_display, use_container_width=True, height=400, hide_index=True)
            st.write(f"**{t('actions')}**")
            target_resign = st.selectbox(
                t("select_employee"),
                df["id_nomor"] + " | " + df["name_nama"],
                key="resign_restore_select"
            )
            if is_admin:
                col_act1, col_act2 = st.columns(2)
                with col_act1:
                    if st.button(t("restore_btn"), key="restore_selected", use_container_width=True):
                        if target_resign:
                            emp_id = target_resign.split(" | ")[0]
                            resp = api_post("/employees/restore", params={"id_nomor": emp_id})
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
                with col_act2:
                    if st.button(t("delete_permanently"), key="delete_permanently_selected", use_container_width=True, type="secondary"):
                        st.session_state.show_permanent_delete_confirm = True
                
                if st.session_state.get("show_permanent_delete_confirm", False):
                    st.warning(t("delete_permanently_warning"))
                    confirm_password = st.text_input(t("input_admin_password_confirm"), type="password", key="confirm_admin_password_input")
                    col_del_c1, col_del_c2 = st.columns(2)
                    if col_del_c1.button(t("confirm_delete_permanently"), key="confirm_permanent_delete_action", type="primary"):
                        if not confirm_password:
                            pw_err = "请输入密码" if st.session_state.get("lang", "zh") == "zh" else "Silakan masukkan kata sandi"
                            st.error(pw_err)
                        else:
                            emp_id = target_resign.split(" | ")[0]
                            resp = api_post("/employees/permanent_delete", params={"id_nomor": emp_id, "admin_password": confirm_password})
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.session_state.show_permanent_delete_confirm = False
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
                    if col_del_c2.button(t("cancel"), key="cancel_permanent_delete_action"):
                        st.session_state.show_permanent_delete_confirm = False
                        st.rerun()
        else:
            st.info(t("no_data"))
    with tab2:
        if not can_write:
            st.info(t("readonly_msg"))
        else:
            active = api_get("/employees", {"status": t("status_active"), "page": 1, "page_size": 10000})
            if active and active.get("data"):
                df = pd.DataFrame(active["data"])
                if "id_nomor" in df.columns:
                    target = st.selectbox(t("select_employee"), df['id_nomor'] + " | " + df['name_nama'], key="resign_select")
                    resign_date = st.date_input(t("resign_date"), value=date.today())
                    reason = st.text_area(t("resign_reason"), key="resign_reason")
                    if st.button(t("resign_btn"), key="resign_btn"):
                        eid = target.split(" | ")[0]
                        resp = api_post("/employees/resign", params={"id_nomor": eid, "reason": reason, "resign_date": resign_date.strftime("%Y-%m-%d")})
                        if resp and resp.get("status") == "success":
                            st.session_state.toast_message = (t("operation_success"), "✅")
                            st.rerun()
                        else:
                            st.toast(t("operation_failed"), icon="❌")
            else:
                st.info(t("no_data"))

# ==================== 劳保用品 ====================
elif menu == t("labor"):
    st.header(t("labor"))
    st.markdown(f'<div class="section-note">{t("labor_note")}</div>', unsafe_allow_html=True)
    tab1, tab2, tab3, tab4, tab5 = st.tabs([t("item_management"), t("inventory_management"), t("issue_management"), t("assign_report"), t("expiry_reminder")])
    
    with tab1:
        items = api_get("/labor/items")
        if items:
            df_items = pd.DataFrame(items)
            df_items_display = df_items.rename(columns={
                "item_name": t("item_name"),
                "item_spec": t("spec"),
                "unit": t("unit"),
                "default_cycle_days": t("default_cycle"), "safety_stock": t("safety_stock")
            })
            df_items_display = df_items_display.reset_index(drop=True)
            df_items_display.insert(0, t("seq_no"), range(1, len(df_items_display) + 1))
            st.dataframe(df_items_display, use_container_width=True, hide_index=True)
        else:
            st.info(t("no_data"))
        if can_write:
            add_panel, edit_panel = st.columns([1, 1], gap="large")
            with add_panel:
                st.markdown(f"#### {t('add_labor_item')}")
                with st.form("add_item_form"):
                    name = st.text_input(t("item_name"))
                    spec = st.text_input(t("spec"))
                    unit = st.text_input(t("unit"), value=t("unit_pieces"))
                    cycle = st.number_input(t("default_cycle"), value=90)
                    safety = st.number_input(t("safety_stock"), value=0)
                    if st.form_submit_button(t("add")):
                        resp = api_post("/labor/items", params={"item_name": name, "spec": spec, "unit": unit,
                                                         "default_cycle_days": cycle, "safety_stock": safety})
                        if resp and resp.get("status") == "success":
                            st.session_state.toast_message = (t("operation_success"), "✅")
                            st.rerun()
                        else:
                            st.toast(t("operation_failed"), icon="❌")
            with edit_panel:
                st.markdown(f"#### {t('edit_delete_labor_item')}")
                if items:
                    edit_id = st.selectbox(t("select_labor_item"), [i["id"] for i in items],
                                           format_func=lambda x: next((i["item_name"] for i in items if i["id"]==x), ""),
                                           key="edit_item_select")
                    current_item = next((i for i in items if i["id"] == edit_id), {})
                    new_name = st.text_input(t("item_name"), value=current_item.get("item_name", ""), key="new_name")
                    new_spec = st.text_input(t("spec"), value=current_item.get("item_spec", "") or "", key="new_spec")
                    new_unit = st.text_input(t("unit"), value=current_item.get("unit", t("unit_pieces")) or t("unit_pieces"), key="new_unit")
                    new_cycle = st.number_input(t("default_cycle"), value=int(current_item.get("default_cycle_days", 90) or 90), key="new_cycle")
                    new_safety = st.number_input(t("safety_stock"), value=int(current_item.get("safety_stock", 0) or 0), key="new_safety")
                    col_up, col_del = st.columns(2)
                    with col_up:
                        if st.button(t("update"), key="update_item_btn"):
                            resp = api_put(f"/labor/items/{edit_id}", params={
                                "item_name": new_name, "spec": new_spec, "unit": new_unit,
                                "default_cycle_days": new_cycle, "safety_stock": new_safety
                            })
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
                    with col_del:
                        confirm_item_delete = st.checkbox(t("confirm_delete_labor_item_checkbox"), key="confirm_delete_item")
                        if st.button(t("delete"), key="delete_item_btn", disabled=not confirm_item_delete):
                            resp = api_delete(f"/labor/items/{edit_id}")
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
        else:
            st.info(t("readonly_msg"))

    with tab2:
        inv = api_get("/labor/inventory")
        if inv:
            stock_data = []
            for i in inv:
                item = i["item"]
                stock = i["stock"]
                safety = item["safety_stock"]
                warning = stock < safety
                stock_data.append({
                    t("item_name"): item["item_name"],
                    t("current_stock"): stock,
                    t("safety_stock"): safety,
                    t("spec"): item["item_spec"],
                    t("status"): t("warning_low_stock") if warning else ""
                })
            df_stock = pd.DataFrame(stock_data)
            df_stock = df_stock.reset_index(drop=True)
            df_stock.insert(0, t("seq_no"), range(1, len(df_stock) + 1))
            st.dataframe(df_stock, use_container_width=True, hide_index=True)
            if can_write:
                col1, col2 = st.columns(2)
                with col1:
                    with st.form("stock_in_form"):
                        item_id = st.selectbox(t("item_name") + " (" + t("stock_in") + ")", [i["item"]["id"] for i in inv],
                                               format_func=lambda x: next((i["item"]["item_name"] for i in inv if i["item"]["id"]==x), ""),
                                               key="stock_in_item")
                        qty_in = st.number_input(t("quantity"), min_value=1, value=1, key="qty_in")
                        rem_in = st.text_input(t("remark"), key="rem_in")
                        if st.form_submit_button(t("stock_in")):
                            resp = api_post("/labor/inventory/in", params={"item_id": item_id, "quantity": qty_in, "remark": rem_in})
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
                with col2:
                    with st.form("stock_out_form"):
                        item_id_out = st.selectbox(t("item_name") + " (" + t("stock_out") + ")", [i["item"]["id"] for i in inv],
                                                   format_func=lambda x: next((i["item"]["item_name"] for i in inv if i["item"]["id"]==x), ""),
                                                   key="stock_out_item")
                        qty_out = st.number_input(t("quantity"), min_value=1, value=1, key="qty_out")
                        rem_out = st.text_input(t("remark"), key="rem_out")
                        if st.form_submit_button(t("stock_out")):
                            resp = api_post("/labor/inventory/out", params={"item_id": item_id_out, "quantity": qty_out, "remark": rem_out})
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
            else:
                st.info(t("readonly_msg"))
        else:
            st.info(t("no_data"))

    with tab3:
        st.subheader(t("issue_management"))
        all_active_emp = api_get("/employees", {"status": t("status_active"), "page": 1, "page_size": 5000})
        if all_active_emp and all_active_emp.get("data"):
            df_emp = pd.DataFrame(all_active_emp["data"])
            all_assignments = api_get("/labor/assignments") or []
            last_issue_map = {}
            for assign in all_assignments:
                if assign.get("status") != "有效":
                    continue
                id_nomor = assign.get("id_nomor")
                last_date = assign.get("last_issue_date", "")
                if id_nomor and last_date and last_date > last_issue_map.get(id_nomor, ""):
                    last_issue_map[id_nomor] = last_date
            search_term = st.text_input(t("search_employee"), key="emp_search_issue")
            filtered_df = df_emp
            if search_term:
                filtered_df = df_emp[df_emp["id_nomor"].str.contains(search_term, na=False) | df_emp["name_nama"].str.contains(search_term, na=False)]
            options = []
            for _, row in filtered_df.iterrows():
                id_nomor = row["id_nomor"]
                name = row["name_nama"]
                ws = row.get("ws_bengkel", "")
                team = row.get("team_grup", "")
                last_date = last_issue_map.get(id_nomor, "")
                last_display = t("last_issue_format").format(date=last_date) if last_date else ""
                options.append(f"{id_nomor} | {name} | {ws} | {team}{last_display}")
            selected_emp = st.selectbox(t("select_employee_issue"), options, key="issue_emp_select")
            if selected_emp:
                emp_id = selected_emp.split(" | ")[0]
                st.write(f"**{t('id_nomor')}:** {emp_id}")
            else:
                emp_id = ""
            items_list = api_get("/labor/items") or []
            inv_list = api_get("/labor/inventory") or []
            stock_map = {i["item"]["id"]: i["stock"] for i in inv_list if i.get("item")}
            with st.form("issue_form"):
                if items_list:
                    selected_item = st.selectbox(t("item_name"), [i["id"] for i in items_list],
                                                 format_func=lambda x: f"{next((i['item_name'] for i in items_list if i['id']==x), '')} | {t('stock_label')} {stock_map.get(x, 0)}",
                                                 key="issue_item_select")
                    selected_item_data = next((i for i in items_list if i["id"] == selected_item), {})
                    current_stock = int(stock_map.get(selected_item, 0))
                    issue_date = st.date_input(t("issue_date"), value=date.today(), key="issue_date")
                    quantity = st.number_input(t("issue_quantity"), min_value=1, max_value=max(1, current_stock), value=1, key="issue_qty")
                    cycle = st.number_input(t("cycle_days") + " (0=" + t("default_cycle") + ")", min_value=0, value=0, key="issue_cycle")
                    confirm_issue = st.checkbox(
                        t("confirm_issue_format").format(emp_id=emp_id or t("unselected_employee"), item_name=selected_item_data.get('item_name', ''), quantity=quantity),
                        key="confirm_issue"
                    )
                    st.caption(t("current_stock_and_cycle_format").format(stock=current_stock, cycle=selected_item_data.get('default_cycle_days', 0)))
                    if st.form_submit_button(t("save")):
                        if not emp_id:
                            st.error(t("please_select_employee"))
                        elif current_stock < quantity:
                            st.error(t("insufficient_stock_format").format(stock=current_stock))
                        elif not confirm_issue:
                            st.error(t("please_check_confirm_issue"))
                        else:
                            params = {"id_nomor": emp_id, "item_id": selected_item,
                                      "issue_date": issue_date.strftime("%Y-%m-%d"),
                                      "quantity": quantity}
                            if cycle > 0:
                                params["cycle_days"] = cycle
                            resp = api_post("/labor/assignments/issue", params=params)
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
                else:
                    st.warning(t("no_data"))

        st.divider()
        search_id = st.text_input(t("view_records"), key="search_assign")
        if search_id:
            assigns = api_get("/labor/assignments", {"id_nomor": search_id})
            if assigns:
                emp_info = api_get(f"/employees/query?id_nomor={search_id}")
                if emp_info:
                    st.write(f"**{t('id_nomor')}:** {emp_info['id_nomor']} | **{t('name_nama')}:** {emp_info['name_nama']} | **{t('ws_bengkel')}:** {emp_info.get('ws_bengkel', '')} | **{t('team_grup')}:** {emp_info.get('team_grup', '')}")
                st.write("---")
                assigns = sorted(assigns, key=lambda a: (a.get("last_issue_date") or "", a.get("id") or 0), reverse=True)
                record_rows = []
                for assign in assigns:
                    item = assign.get("item", {})
                    record_rows.append({
                        t("record_id"): assign.get("id"),
                        t("item_name"): item.get("item_name", "") if isinstance(item, dict) else "",
                        t("issue_date"): assign.get("last_issue_date", ""),
                        t("next_issue"): assign.get("next_issue_date", ""),
                        t("quantity"): assign.get("quantity", 1),
                        t("cycle_days"): assign.get("cycle_days", ""),
                        t("status"): assign.get("status", ""),
                    })
                df_records = pd.DataFrame(record_rows)
                df_records = df_records.reset_index(drop=True)
                df_records.insert(0, t("seq_no"), range(1, len(df_records) + 1))
                st.dataframe(df_records, use_container_width=True, hide_index=True)
                active_assigns = [a for a in assigns if a.get("status") in (t("active_status"), "Aktif")]
                if can_write and active_assigns:
                    with st.expander(t("cancel_edit_issue"), expanded=False):
                        target_assign = st.selectbox(
                            t("choose_record"),
                            active_assigns,
                            format_func=lambda a: f"#{a['id']} | {a.get('item', {}).get('item_name', '')} | {a.get('last_issue_date', '')} | {t('quantity')} {a.get('quantity', 1)}",
                            key="target_assign_action"
                        )
                        col_edit, col_cancel = st.columns(2)
                        with col_edit:
                            if st.button("✏️ " + t("edit_issue_date_cycle"), key=f"edit_assign_{target_assign['id']}", use_container_width=True):
                                st.session_state.edit_assign_id = target_assign['id']
                                st.session_state.edit_assign_data = target_assign
                                st.rerun()
                        with col_cancel:
                            cancel_reason = st.text_input(t("cancel_reason"), value=t("cancel_reason_default"), key=f"cancel_reason_{target_assign['id']}")
                            confirm_cancel = st.checkbox(t("confirm_cancel_stock"), key=f"confirm_cancel_{target_assign['id']}")
                            if st.button(t("cancel_issue"), key=f"cancel_assign_{target_assign['id']}", use_container_width=True):
                                if not confirm_cancel:
                                    st.warning(t("please_check_confirm_cancel"))
                                else:
                                    resp = api_post(f"/labor/assignments/{target_assign['id']}/cancel", params={"reason": cancel_reason})
                                    if resp and resp.get("status") == "success":
                                        st.session_state.toast_message = (t("cancel_success"), "✅")
                                        st.rerun()
                                    else:
                                        st.toast(t("operation_failed"), icon="❌")
                if st.session_state.edit_assign_id:
                    with st.form("edit_assign_form"):
                        st.subheader(t("edit_assign"))
                        assign = st.session_state.edit_assign_data
                        new_issue_date = st.date_input(t("issue_date"), value=to_date(assign.get("last_issue_date")))
                        new_cycle = st.number_input(t("cycle_days"), value=assign.get("cycle_days", 0))
                        new_status = st.selectbox(t("status"), [t("active_status"), t("inactive_status")], index=0 if assign.get("status") in ("有效", "Aktif") else 1)
                        if st.form_submit_button(t("save")):
                            payload = {}
                            if new_issue_date:
                                payload["last_issue_date"] = new_issue_date.strftime("%Y-%m-%d")
                            if new_cycle:
                                payload["cycle_days"] = new_cycle
                            if new_status:
                                payload["status"] = new_status
                            resp = api_put(f"/labor/assignments/{assign['id']}", json_data=payload)
                            if resp and resp.get("status") == "success":
                                st.session_state.toast_message = (t("operation_success"), "✅")
                                st.session_state.edit_assign_id = None
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
                    if st.button(t("cancel")):
                        st.session_state.edit_assign_id = None
                        st.rerun()
                if is_admin and st.button(t("export_records"), key="export_assign_btn"):
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='openpyxl') as writer:
                        pd.DataFrame(assigns).to_excel(writer, index=False)
                    output.seek(0)
                    st.download_button(label="📥 " + t("export"), data=output,
                                       file_name=f"issue_records_{search_id}_{datetime.now().strftime('%Y%m%d')}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key="export_assign_download")
            else:
                st.info(t("no_records"))

    with tab4:
        st.subheader(t("assign_report"))
        with st.form("report_form"):
            col1, col2, col3, col4, col5 = st.columns(5)
            start_date = col1.date_input(t("start_date"), value=date.today() - timedelta(days=30))
            end_date = col2.date_input(t("end_date"), value=date.today())
            items_list = api_get("/labor/items") or []
            item_options = [{"id": 0, "item_name": t("all_items")}] + items_list
            selected_item = col3.selectbox(t("item_name"), item_options, format_func=lambda x: x["item_name"])
            ws_options = [{"name": t("all_workshops")}] + [{"name": w} for w in (api_get("/meta/车间") or [])]
            selected_ws = col4.selectbox(t("ws_bengkel"), ws_options, format_func=lambda x: x["name"])
            team_options = [{"name": t("all_teams")}] + [{"name": t} for t in (api_get("/meta/班组") or [])]
            selected_team = col5.selectbox(t("team_grup"), team_options, format_func=lambda x: x["name"])
            submitted = st.form_submit_button(t("generate_report"))
        if submitted:
            params = {}
            if start_date:
                params["start_date"] = start_date.strftime("%Y-%m-%d")
            if end_date:
                params["end_date"] = end_date.strftime("%Y-%m-%d")
            if selected_item and selected_item["id"] != 0:
                params["item_id"] = selected_item["id"]
            if selected_ws and selected_ws["name"] != t("all_workshops"):
                params["workshop"] = selected_ws["name"]
            if selected_team and selected_team["name"] != t("all_teams"):
                params["team"] = selected_team["name"]
            report_data = api_get("/labor/assignments/report", params=params)
            if report_data:
                df_report = pd.DataFrame(report_data)
                df_report = df_report.rename(columns={
                    "id_nomor": t("id_nomor"),
                    "name": t("name_nama"),
                    "workshop": t("ws_bengkel"),
                    "team": t("team_grup"),
                    "item_name": t("item_name"),
                    "item_spec": t("spec"),
                    "last_issue_date": t("issue_date"),
                    "next_issue_date": t("next_issue"),
                    "cycle_days": t("cycle_days"),
                    "status": t("status"),
                    "quantity": t("quantity")
                })
                df_report = df_report.reset_index(drop=True)
                df_report.insert(0, t("seq_no"), range(1, len(df_report) + 1))
                st.dataframe(df_report, use_container_width=True, hide_index=True)
                output = io.BytesIO()
                with pd.ExcelWriter(output, engine='openpyxl') as writer:
                    df_report.to_excel(writer, index=False)
                output.seek(0)
                if is_admin:
                    st.download_button(label="📥 " + t("export"), data=output,
                                       file_name=f"labor_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key="report_download")
            else:
                st.info(t("no_data"))

    with tab5:
        reminders = api_get("/labor/reminders")
        if reminders:
            df_remind = pd.DataFrame(reminders)
            df_remind = df_remind.rename(columns={
                "id_nomor": t("id_nomor"), "name": t("name_nama"), "item": t("item_name"),
                "next_issue_date": t("issue_date"), "days_left": t("days_left"), "overdue": t("overdue")
            })
            df_remind = df_remind.sort_values(by=t("days_left"))
            df_remind = df_remind.reset_index(drop=True)
            df_remind.insert(0, t("seq_no"), range(1, len(df_remind) + 1))
            st.dataframe(df_remind, use_container_width=True, hide_index=True)
        else:
            st.success(t("no_data"))

# ==================== 异动记录 ====================
elif menu == t("transfer_records"):
    st.header(t("transfer_records"))
    st.markdown(f'<div class="section-note">{t("transfer_records_note")}</div>', unsafe_allow_html=True)
    
    # 员工车间/班组异动功能
    if is_admin:
        with st.expander(t("transfer_workshop_team"), expanded=False):
            # 获取所有在职员工
            active_emp_res = api_get("/employees", {"status": t("status_active"), "page": 1, "page_size": 10000})
            if active_emp_res and "data" in active_emp_res:
                active_emps = active_emp_res["data"]
                emp_options = [f"{e['id_nomor']} | {e['name_nama']}" for e in active_emps]
                selected_emp_str = st.selectbox(t("select_employee_transfer"), [""] + emp_options, format_func=lambda x: x if x else t("please_select_employee_option"), key="transfer_emp_select")
                if selected_emp_str:
                    emp_id = selected_emp_str.split(" | ")[0]
                    emp_details = next((e for e in active_emps if e["id_nomor"] == emp_id), None)
                    if emp_details:
                        current_ws = emp_details.get("ws_bengkel") or ""
                        current_team = emp_details.get("team_grup") or ""
                        
                        st.markdown(f"**{t('current_assignment')}:** {t('workshop')}: `{t_val(current_ws) or t('unassigned')}` | {t('team')}: `{t_val(current_team) or t('unassigned')}`")
                        
                        col1, col2 = st.columns(2)
                        ws_list = api_get("/meta/车间") or []
                        team_list = api_get("/meta/班组") or []
                        
                        ws_opts = [""] + ws_list
                        team_opts = [""] + team_list
                        
                        try:
                            ws_idx = ws_opts.index(current_ws)
                        except ValueError:
                            ws_idx = 0
                        try:
                            team_idx = team_opts.index(current_team)
                        except ValueError:
                            team_idx = 0
                            
                        new_ws = col1.selectbox(t("select_new_workshop"), ws_opts, index=ws_idx, format_func=lambda x: t_val(x) if x else t("none_unassigned"), key="transfer_new_ws")
                        new_team = col2.selectbox(t("select_new_team"), team_opts, index=team_idx, format_func=lambda x: t_val(x) if x else t("none_unassigned"), key="transfer_new_team")
                        
                        if st.button(t("confirm_transfer"), key="confirm_transfer_btn", use_container_width=True):
                            if new_ws == current_ws and new_team == current_team:
                                st.warning(t("no_change_workshop_team"))
                            else:
                                payload = {
                                    "id_nomor": emp_id,
                                    "name_nama": emp_details["name_nama"],
                                    "ws_bengkel": new_ws,
                                    "team_grup": new_team
                                }
                                resp = api_post("/employees/save", params={"is_update": True, "original_id": emp_id}, json_data=payload)
                                if resp and resp.get("status") == "success":
                                    st.session_state.toast_message = (t("operation_success"), "✅")
                                    st.rerun()
                                else:
                                    st.toast(t("operation_failed"), icon="❌")
            else:
                st.info(t("no_active_employees_to_transfer"))

    transfers = api_get("/employee/transfers")
    if transfers and len(transfers) > 0:
        df = pd.DataFrame(transfers)
        df = df.rename(columns={
            "transfer_date": t("transfer_date"),
            "id_nomor": t("id_nomor"),
            "name": t("name_nama"),
            "change_type": t("change_type"),
            "old_value": t("old_value"),
            "new_value": t("new_value"),
            "operator": t("operator")
        })
        df = df[[t("transfer_date"), t("id_nomor"), t("name_nama"), t("change_type"), t("old_value"), t("new_value"), t("operator")]]
        df = df.reset_index(drop=True)
        df.insert(0, t("seq_no"), range(1, len(df) + 1))
        st.dataframe(df, use_container_width=True, hide_index=True)

        # Bulk delete UI
        # Build a mapping of id to display label
        id_options = []
        id_to_label = {}
        for rec in transfers:
            rec_id = rec.get("id")
            if rec_id is None:
                continue
            label = f"{rec_id}: {rec.get('id_nomor', '')} | {rec.get('name_nama', '')}"
            id_options.append(rec_id)
            id_to_label[rec_id] = label
        if id_options:
            selected_ids = st.multiselect(
                t("select_transfers_to_delete"),
                options=id_options,
                format_func=lambda x: id_to_label.get(x, str(x)),
                key="transfer_bulk_delete_select"
            )
            if selected_ids:
                if st.button(t("delete_selected"), key="bulk_delete_btn"):
                    st.session_state.show_transfer_bulk_delete_confirm = True
        # Confirmation dialog
        if st.session_state.get("show_transfer_bulk_delete_confirm", False):
            st.warning(t("confirm_delete_transfers"))
            col_yes, col_no = st.columns(2)
            if col_yes.button(t("confirm_delete_btn"), key="confirm_bulk_delete_yes"):
                resp = api_delete("/employee/transfers", params={"ids": selected_ids})
                if resp and resp.get("deleted", 0) > 0:
                    st.session_state.toast_message = (t("operation_success"), "✅")
                else:
                    st.toast(t("operation_failed"), icon="❌")
                st.session_state.show_transfer_bulk_delete_confirm = False
                st.rerun()
            if col_no.button(t("cancel"), key="cancel_bulk_delete"):
                st.session_state.show_transfer_bulk_delete_confirm = False
                st.rerun()
    else:
        st.info(t("no_data"))

# ==================== 操作日志 ====================
elif menu == t("logs"):
    st.header(t("log_list"))
    st.markdown(f'<div class="section-note">{t("logs_note")}</div>', unsafe_allow_html=True)
    col_export, col_hint = st.columns([1, 3])
    with col_export:
        if is_admin and st.button(t("export_logs"), key="export_logs_btn"):
            with st.spinner(t("generating_report")):
                r = requests.get("/api/logs/report", headers=auth_h(), timeout=30)
                if r.status_code == 200:
                    st.download_button(label="📥 " + t("export"), data=r.content,
                                       file_name=f"log_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       key="log_download")
                else:
                    st.toast(t("operation_failed"), icon="❌")
    with col_hint:
        st.caption(t("log_filter_caption"))
        
    first_res = api_get("/logs", {"page": 1, "page_size": 1}) or {}
    type_options = [t("log_all_types")] + first_res.get("types", [])

    if is_admin_account:
        st.markdown("---")
        with st.expander(t("delete_operation_logs"), expanded=False):
            st.markdown(t("delete_operation_logs_desc"))
            delete_type = st.selectbox(t("select_log_category_to_delete"), type_options, format_func=t, key="delete_log_category_select")
            if st.button(t("confirm_delete_category_logs_btn"), key="delete_logs_confirm_btn", type="primary"):
                st.session_state.show_log_delete_confirm = True
            
            if st.session_state.get("show_log_delete_confirm", False):
                st.warning(t("confirm_delete_category_logs_warning").format(category=t(delete_type)))
                c_del1, c_del2 = st.columns(2)
                if c_del1.button(t("confirm_delete_permanently_btn"), key="confirm_log_delete_action_final", type="primary"):
                    resp = api_delete("/logs", params={"op_type": delete_type})
                    if resp and resp.get("status") == "success":
                        st.session_state.toast_message = (t("operation_success"), "✅")
                        st.session_state.show_log_delete_confirm = False
                        st.rerun()
                    else:
                        st.toast(t("operation_failed"), icon="❌")
                if c_del2.button(t("cancel"), key="cancel_log_delete_action_final"):
                    st.session_state.show_log_delete_confirm = False
                    st.rerun()

    with st.expander(t("filter"), expanded=True):
        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1.4, 2])
        log_start = f1.date_input(t("start_date"), value=date.today() - timedelta(days=30), key="log_start")
        log_end = f2.date_input(t("end_date"), value=date.today(), key="log_end")
        log_type = f3.selectbox(t("log_type_label"), type_options, format_func=t, key="log_type")
        log_search = f4.text_input(t("search"), placeholder=t("log_search_placeholder"), key="log_search")
    p = st.number_input(t("page"), 1, key="log_page")
    params = {
        "page": p,
        "page_size": 30,
        "date_from": log_start.strftime("%Y-%m-%d") if log_start else "",
        "date_to": log_end.strftime("%Y-%m-%d") if log_end else "",
        "search": log_search,
    }
    if log_type != t("log_all_types"):
        params["op_type"] = log_type
    res = api_get("/logs", params)
    if res and "data" in res:
        total = res.get("total", 0)
        st.caption(t("page_info_format").format(total=total, page=p, max_page=max(1, (total - 1) // 30 + 1)))
        rows = res.get("data", [])
        if rows:
            df_logs = pd.DataFrame(rows)

            # -------- 批量删除区域（仅管理员）--------
            if is_admin_account:
                # 初始化勾选状态
                if "log_checked_ids" not in st.session_state:
                    st.session_state.log_checked_ids = set()

                # 当前页所有可选 ID
                page_ids = [r.get("id") for r in rows if r.get("id") is not None]

                all_checked = all(rid in st.session_state.log_checked_ids for rid in page_ids)

                sel_col, btn_col1, btn_col2 = st.columns([2, 1.5, 1.5])
                with sel_col:
                    toggle_all = st.checkbox(
                        t("select_all_page") if not all_checked else t("deselect_all_page"),
                        value=all_checked,
                        key="log_select_all_toggle"
                    )
                    if toggle_all and not all_checked:
                        st.session_state.log_checked_ids.update(page_ids)
                        st.rerun()
                    elif not toggle_all and all_checked:
                        for rid in page_ids:
                            st.session_state.log_checked_ids.discard(rid)
                        st.rerun()

                checked_count = len(st.session_state.log_checked_ids)
                with btn_col1:
                    st.markdown(f"<div style='padding-top:6px;color:#64748b;font-size:13px'>{t('selected_records_count').format(count=checked_count)}</div>", unsafe_allow_html=True)
                with btn_col2:
                    batch_del_btn = st.button(
                        t("batch_delete_with_count").format(count=checked_count),
                        key="log_batch_delete_btn",
                        disabled=(checked_count == 0),
                        type="primary" if checked_count > 0 else "secondary"
                    )
                    if batch_del_btn and checked_count > 0:
                        st.session_state.show_log_batch_delete_confirm = True

                # 二次确认弹窗
                if st.session_state.get("show_log_batch_delete_confirm", False):
                    st.warning(t("confirm_batch_delete_warning").format(count=checked_count))
                    c_ok, c_cancel = st.columns(2)
                    if c_ok.button(t("confirm_batch_delete_btn"), key="log_batch_delete_confirm_ok", type="primary"):
                        del_ids = list(st.session_state.log_checked_ids)
                        try:
                            resp = requests.post(
                                "/api/logs/batch-delete",
                                json={"ids": del_ids},
                                headers=auth_h(),
                                timeout=API_TIMEOUT
                            )
                            if resp.status_code == 200:
                                st.session_state.log_checked_ids = set()
                                st.session_state.show_log_batch_delete_confirm = False
                                st.session_state.toast_message = (t("batch_delete_success_format").format(count=len(del_ids)), "✅")
                                st.rerun()
                            else:
                                st.toast(t("operation_failed"), icon="❌")
                        except Exception as e:
                            st.toast(t("request_failed_format").format(error=e), icon="❌")
                    if c_cancel.button(t("cancel"), key="log_batch_delete_confirm_cancel"):
                        st.session_state.show_log_batch_delete_confirm = False
                        st.rerun()

                st.divider()

                # -------- 带复选框的日志行列表 --------
                hdr = st.columns([0.4, 1.8, 1.2, 1.0, 1.0, 1.0, 0.8, 1.5])
                hdr[0].markdown("**☑️**")
                hdr[1].markdown(f"**{t('log_time')}**")
                hdr[2].markdown(f"**{t('col_type')}**")
                hdr[3].markdown(f"**{t('id_nomor')}**")
                hdr[4].markdown(f"**{t('name_nama')}**")
                hdr[5].markdown(f"**{t('operator')}**")
                hdr[6].markdown("**IP**")
                hdr[7].markdown(f"**{t('reason_alasan')}**")
                st.markdown("<hr style='margin:4px 0 8px 0;border-color:#e2e8f0'>", unsafe_allow_html=True)

                for idx, row in enumerate(rows):
                    rid = row.get("id")
                    is_checked_row = rid in st.session_state.log_checked_ids
                    row_cols = st.columns([0.4, 1.8, 1.2, 1.0, 1.0, 1.0, 0.8, 1.5])
                    chk = row_cols[0].checkbox(
                        t("select"), value=is_checked_row,
                        key=f"log_chk_{rid}_{idx}",
                        label_visibility="collapsed"
                    )
                    if chk and rid not in st.session_state.log_checked_ids:
                        st.session_state.log_checked_ids.add(rid)
                        st.rerun()
                    elif not chk and rid in st.session_state.log_checked_ids:
                        st.session_state.log_checked_ids.discard(rid)
                        st.rerun()

                    row_cols[1].markdown(f"<div style='font-size:12px;padding-top:6px'>{row.get('op_date','')}</div>", unsafe_allow_html=True)
                    row_cols[2].markdown(f"<div style='font-size:12px;padding-top:6px'>{t(row.get('type_tipe',''))}</div>", unsafe_allow_html=True)
                    row_cols[3].markdown(f"<div style='font-size:12px;padding-top:6px'>{row.get('id_nomor','')}</div>", unsafe_allow_html=True)
                    row_cols[4].markdown(f"<div style='font-size:12px;padding-top:6px'>{row.get('name_nama','')}</div>", unsafe_allow_html=True)
                    row_cols[5].markdown(f"<div style='font-size:12px;padding-top:6px'>{row.get('operator','')}</div>", unsafe_allow_html=True)
                    row_cols[6].markdown(f"<div style='font-size:12px;padding-top:6px'>{row.get('ip_address','')}</div>", unsafe_allow_html=True)
                    row_cols[7].markdown(f"<div style='font-size:12px;padding-top:6px'>{t(row.get('reason_alasan',''))}</div>", unsafe_allow_html=True)

            else:
                # 只读用户：直接展示 dataframe，无复选框
                df_show = df_logs.copy()
                df_show["type_tipe"] = df_show["type_tipe"].apply(t)
                df_show["reason_alasan"] = df_show["reason_alasan"].apply(lambda x: t(x) if x else "")
                df_show = df_show.rename(columns={
                    "op_date": t("log_time"),
                    "type_tipe": t("col_type"),
                    "id_nomor": t("id_nomor"),
                    "name_nama": t("name_nama"),
                    "operator": t("operator"),
                    "ip_address": "IP",
                    "reason_alasan": t("reason_alasan"),
                })
                display_cols = [t("log_time"), t("col_type"), t("id_nomor"), t("name_nama"), t("operator"), "IP", t("reason_alasan")]
                display_cols = [c for c in display_cols if c in df_show.columns]
                df_log_display = df_show[display_cols].copy()
                df_log_display = df_log_display.reset_index(drop=True)
                df_log_display.insert(0, t("seq_no"), range(1, len(df_log_display) + 1))
                st.dataframe(df_log_display, use_container_width=True, hide_index=True)

            with st.expander(t("log_detail_title")):
                for row in rows:
                    title = f"{row.get('op_date', '')} | {t(row.get('type_tipe', ''))} | {row.get('operator', '')}"
                    st.markdown(f"**{title}**")
                    if row.get("id_nomor") or row.get("name_nama"):
                        st.caption(t("log_detail_object").format(id=row.get('id_nomor', ''), name=row.get('name_nama', '')))
                    detail_col1, detail_col2 = st.columns(2)
                    detail_col1.text_area(t("log_detail_old"), value=str(row.get("old_payload") or ""), height=90, key=f"log_old_{row.get('id')}")
                    detail_col2.text_area(t("log_detail_new"), value=str(row.get("new_payload") or ""), height=90, key=f"log_new_{row.get('id')}")
                    st.divider()
        else:
            st.info(t("no_data"))
    else:
        st.info(t("no_data"))

# ==================== 导出成本报表 ====================
elif menu == "📊 导出成本报表":
    st.header("📊 导出成本报表")
    st.markdown('<div class="section-note">按日期范围筛选员工（含离职员工），自定义导出字段、字段顺序和列名，导出Excel成本报表。</div>', unsafe_allow_html=True)

    # 所有可导出字段及默认列名
    ALL_COST_FIELDS = [
        ("id_nomor",       "工号",      "ID"),
        ("name_nama",      "姓名",      "Nama"),
        ("company",        "归属公司",  "Perusahaan"),
        ("ws_bengkel",     "车间",      "Bengkel"),
        ("team_grup",      "班组",      "Grup"),
        ("gender_jk",      "性别",      "JK"),
        ("pos_cn_jabatan", "岗位(中)",  "Jabatan (CN)"),
        ("pos_id_jabatan", "岗位(印)",  "Jabatan (ID)"),
        ("nat_negara",     "国籍",      "Kewarganegaraan"),
        ("rel_agama",      "宗教",      "Agama"),
        ("id_card",        "身份证号",  "Nomor KTP"),
        ("hire_date",      "入职日期",  "Tgl Masuk"),
        ("contract_end",   "合同到期日","Kontrak Berakhir"),
        ("status_status",  "状态",      "Status"),
        ("resign_date",    "离职日期",  "Tgl Resign"),
        ("remark_ket",     "备注",      "Keterangan"),
    ]
    lang_now = st.session_state.get("lang", "zh")
    default_label_idx = 1 if lang_now == "zh" else 2

    # 初始化 session state：已选字段（顺序列表）和自定义列名
    if "cost_report_fields" not in st.session_state:
        st.session_state.cost_report_fields = [f[0] for f in ALL_COST_FIELDS]
    if "cost_report_labels" not in st.session_state:
        st.session_state.cost_report_labels = {f[0]: f[default_label_idx] for f in ALL_COST_FIELDS}

    # ---------- 方案模板 ----------
    st.subheader("📋 方案模板")
    template_file = "uploads/cost_report_templates.json"
    templates = {}
    if os.path.exists(template_file):
        try:
            with open(template_file, "r", encoding="utf-8") as f:
                templates = json.load(f)
        except Exception as e:
            st.error(f"加载方案文件失败: {e}")

    col_tpl_sel, col_tpl_btn, col_tpl_save = st.columns([2.5, 2, 3.5])
    current_username = st.session_state.user_info.get("username", "unknown")
    current_role = st.session_state.user_info.get("role", "viewer")

    with col_tpl_sel:
        tpl_options = list(templates.keys())
        selected_tpl_name = st.selectbox(
            "选择已保存的方案",
            options=["-- 请选择 --"] + tpl_options,
            key="cost_tpl_select"
        )

    with col_tpl_btn:
        st.write("<div style='height: 28px;'></div>", unsafe_allow_html=True)
        col_load, col_del = st.columns(2)
        has_selected = (selected_tpl_name != "-- 请选择 --")
        
        # 1. 加载方案
        if col_load.button("加载方案", key="cost_tpl_load_btn", disabled=not has_selected, use_container_width=True):
            tpl_data = templates[selected_tpl_name]
            st.session_state.cost_report_fields = list(tpl_data["fields"])
            st.session_state.cost_report_labels = dict(tpl_data["labels"])
            
            # 同步更新对应 widget 的 session_state 键值，强刷 UI 组件
            for fkey in ALL_COST_FIELDS:
                k = fkey[0]
                st.session_state[f"cf_check_{k}"] = (k in tpl_data["fields"])
                st.session_state[f"cf_label_{k}"] = tpl_data["labels"].get(k, fkey[1])
                
            st.toast(f"方案「{selected_tpl_name}」已加载！", icon="✅")
            st.rerun()

        # 2. 删除方案（防越权：仅创建者或管理员可删）
        is_delete_disabled = True
        if has_selected:
            tpl_owner = templates[selected_tpl_name].get("created_by")
            if current_role == "admin" or tpl_owner == current_username:
                is_delete_disabled = False
                
        if col_del.button("删除方案", key="cost_tpl_del_btn", disabled=is_delete_disabled, use_container_width=True):
            del templates[selected_tpl_name]
            try:
                os.makedirs(os.path.dirname(template_file), exist_ok=True)
                with open(template_file, "w", encoding="utf-8") as f:
                    json.dump(templates, f, ensure_ascii=False, indent=4)
                st.toast(f"方案「{selected_tpl_name}」已删除！", icon="✅")
                st.rerun()
            except Exception as e:
                st.error(f"删除方案失败: {e}")

    with col_tpl_save:
        save_name = st.text_input("保存当前配置为新方案", placeholder="输入方案名称...", key="cost_tpl_name_input")
        st.write("<div style='height: 4px;'></div>", unsafe_allow_html=True)
        
        # 3. 保存方案
        if st.button("💾 保存方案", key="cost_tpl_save_btn", disabled=not save_name.strip(), use_container_width=True):
            clean_name = save_name.strip()
            current_fields = st.session_state.cost_report_fields
            current_labels = st.session_state.cost_report_labels
            
            if not current_fields:
                st.error("无法保存空方案：请至少勾选一个导出字段！")
            else:
                templates[clean_name] = {
                    "created_by": current_username,
                    "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "fields": current_fields,
                    "labels": current_labels
                }
                try:
                    os.makedirs(os.path.dirname(template_file), exist_ok=True)
                    with open(template_file, "w", encoding="utf-8") as f:
                        json.dump(templates, f, ensure_ascii=False, indent=4)
                    st.toast(f"方案「{clean_name}」已成功保存！", icon="✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"保存方案失败: {e}")

    st.divider()

    # ---------- 日期范围 ----------
    st.subheader("📅 日期范围")
    col_s, col_e = st.columns(2)
    with col_s:
        start_date_val = st.date_input("开始日期（入职/在职起点）", value=None, key="cost_start_date", format="YYYY-MM-DD")
    with col_e:
        end_date_val = st.date_input("结束日期（入职/离职终点）", value=date.today(), key="cost_end_date", format="YYYY-MM-DD")

    st.info("筛选逻辑：入职日期 ≤ 结束日期，且（仍在职 或 离职日期 ≥ 开始日期）。留空开始日期则不限制起始时间。")

    st.divider()

    # ---------- 字段选择与排序 ----------
    st.subheader("📋 字段选择与排序")
    st.caption("勾选要导出的字段，使用 ↑↓ 调整顺序，并可自定义列名（留空则使用默认名称）。")

    field_key_set = set(st.session_state.cost_report_fields)
    # 用于暂存本次的勾选和标签
    new_selected = []
    new_labels = dict(st.session_state.cost_report_labels)

    # 构建字段配置表
    header_cols = st.columns([0.4, 0.4, 3, 3, 1, 1])
    header_cols[0].markdown("<div style='white-space: nowrap; font-weight: bold;'>选择</div>", unsafe_allow_html=True)
    header_cols[1].markdown("<div style='white-space: nowrap; font-weight: bold;'>顺序</div>", unsafe_allow_html=True)
    header_cols[2].markdown("<div style='white-space: nowrap; font-weight: bold;'>字段</div>", unsafe_allow_html=True)
    header_cols[3].markdown("<div style='white-space: nowrap; font-weight: bold;'>自定义列名</div>", unsafe_allow_html=True)
    header_cols[4].markdown("<div style='white-space: nowrap; font-weight: bold;'>上移</div>", unsafe_allow_html=True)
    header_cols[5].markdown("<div style='white-space: nowrap; font-weight: bold;'>下移</div>", unsafe_allow_html=True)

    # 操作按钮处理（先于渲染执行，避免冲突）
    if "cost_move_up" in st.session_state:
        idx_up = st.session_state.pop("cost_move_up")
        fields = st.session_state.cost_report_fields
        if idx_up > 0:
            fields[idx_up], fields[idx_up-1] = fields[idx_up-1], fields[idx_up]
        st.rerun()

    if "cost_move_down" in st.session_state:
        idx_dn = st.session_state.pop("cost_move_down")
        fields = st.session_state.cost_report_fields
        if idx_dn < len(fields) - 1:
            fields[idx_dn], fields[idx_dn+1] = fields[idx_dn+1], fields[idx_dn]
        st.rerun()

    # 使用 ALL_COST_FIELDS 的顺序渲染，但按 session_state 顺序标序号
    ordered_fields = st.session_state.cost_report_fields
    # 构建显示顺序（已选字段按session_state顺序，未选字段放末尾）
    all_field_keys = [f[0] for f in ALL_COST_FIELDS]
    unselected = [k for k in all_field_keys if k not in field_key_set]
    display_order = list(ordered_fields) + unselected

    checked_this_run = []
    label_this_run = {}

    for seq_i, fkey in enumerate(display_order):
        finfo = next((f for f in ALL_COST_FIELDS if f[0] == fkey), None)
        if not finfo:
            continue
        default_cn = finfo[1]
        is_checked = fkey in field_key_set
        seq_display = str(ordered_fields.index(fkey) + 1) if is_checked else "-"

        row_cols = st.columns([0.4, 0.4, 3, 3, 1, 1])
        chk_key = f"cf_check_{fkey}"
        if chk_key not in st.session_state:
            st.session_state[chk_key] = is_checked
        lbl_key = f"cf_label_{fkey}"
        if lbl_key not in st.session_state:
            st.session_state[lbl_key] = new_labels.get(fkey, default_cn)

        checked = row_cols[0].checkbox(t("select"), key=chk_key, label_visibility="collapsed")
        row_cols[1].markdown(f"<div style='padding-top:6px;text-align:center;font-weight:600'>{seq_display}</div>", unsafe_allow_html=True)
        row_cols[2].markdown(f"<div style='padding-top:6px; white-space: nowrap;'>{default_cn} <span style='color:#94a3b8;font-size:12px'>({fkey})</span></div>", unsafe_allow_html=True)
        custom_lbl = row_cols[3].text_area(
            "列名",
            key=lbl_key, label_visibility="collapsed",
            height=60
        )
        label_this_run[fkey] = custom_lbl or default_cn

        if checked:
            checked_this_run.append(fkey)

        # 上移/下移按钮仅对已选且排好顺序的字段有效
        if is_checked:
            cur_pos = ordered_fields.index(fkey)
            if row_cols[4].button("↑", key=f"cf_up_{fkey}", disabled=(cur_pos == 0)):
                st.session_state.cost_move_up = cur_pos
                st.rerun()
            if row_cols[5].button("↓", key=f"cf_dn_{fkey}", disabled=(cur_pos == len(ordered_fields) - 1)):
                st.session_state.cost_move_down = cur_pos
                st.rerun()
        else:
            row_cols[4].write("")
            row_cols[5].write("")

    # 同步勾选结果到 session state（保持已有顺序，对新增字段追加）
    prev_order = [k for k in ordered_fields if k in checked_this_run]
    newly_added = [k for k in checked_this_run if k not in ordered_fields]
    st.session_state.cost_report_fields = prev_order + newly_added
    st.session_state.cost_report_labels = {**new_labels, **label_this_run}

    st.divider()

    # ---------- 预览与导出 ----------
    selected_fields_final = st.session_state.cost_report_fields
    labels_final = st.session_state.cost_report_labels

    if not selected_fields_final:
        st.warning("请至少选择一个导出字段。")
    else:
        col_info, col_btn = st.columns([3, 1])
        with col_info:
            preview_cols = [labels_final.get(f, f) for f in selected_fields_final]
            st.markdown(f"**将导出 {len(selected_fields_final)} 个字段：** " + " → ".join(f"`{c}`" for c in preview_cols))
        with col_btn:
            do_export = st.button("📥 生成并下载报表", key="cost_export_btn", type="primary", use_container_width=True)

        if do_export:
            start_str = start_date_val.strftime("%Y-%m-%d") if start_date_val else ""
            end_str = end_date_val.strftime("%Y-%m-%d") if end_date_val else ""
            fields_str = ",".join(selected_fields_final)
            labels_json = json.dumps(labels_final, ensure_ascii=False)
            with st.spinner("生成报表中，请稍候..."):
                try:
                    r = requests.get(
                        "/api/employees/cost_report_export",
                        params={
                            "start_date": start_str,
                            "end_date": end_str,
                            "fields": fields_str,
                            "field_labels": labels_json
                        },
                        headers=auth_h(),
                        timeout=60
                    )
                    if r.status_code == 200:
                        st.success(f"✅ 报表生成成功！共筛选到符合条件的员工数据。")
                        st.download_button(
                            label="📥 点击下载成本报表 Excel",
                            data=r.content,
                            file_name=f"cost_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="cost_report_download"
                        )
                    else:
                        try:
                            err = r.json().get("detail", r.text)
                        except:
                            err = r.text
                        st.error(f"导出失败：{err}")
                except Exception as ex:
                    st.error(f"请求失败：{ex}")

# ==================== 数据备份与还原 ====================
elif menu == t("backup_management"):
    st.header(t("backup_management"))
    st.markdown(f'<div class="section-note">{t("settings_note")}</div>', unsafe_allow_html=True)
    
    # CSS 注入 - 深色宝石绿毛玻璃特效 (Deep Gemstone Green Glassmorphism)
    st.markdown("""
    <style>
        /* 宝石绿毛玻璃容器样式 - 使用 border wrapper 使得卡片包裹紧凑且正确 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) {
            background: linear-gradient(135deg, rgba(2, 48, 40, 0.5), rgba(0, 80, 65, 0.35)) !important;
            backdrop-filter: blur(16px) saturate(180%) !important;
            -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
            border: 1.5px solid rgba(0, 200, 150, 0.45) !important;
            border-radius: 16px !important;
            padding: 24px !important;
            box-shadow: inset 0 1px 1px rgba(255, 255, 255, 0.15), 
                        0 8px 32px 0 rgba(0, 40, 30, 0.35) !important;
            margin-bottom: 24px !important;
        }

        /* 移除卡片内部 form 表单的自带背景与边框，使其透明贴合 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) div[data-testid="stForm"] {
            background: transparent !important;
            border: none !important;
            padding: 0 !important;
            box-shadow: none !important;
        }
        
        /* 深度毛玻璃 Dialog 弹窗样式 */
        div[role="dialog"], div[data-testid="stDialog"] {
            background: linear-gradient(135deg, rgba(2, 60, 50, 0.85), rgba(0, 80, 60, 0.8)) !important;
            backdrop-filter: blur(25px) !important;
            -webkit-backdrop-filter: blur(25px) !important;
            border: 1.5px solid rgba(0, 200, 150, 0.5) !important;
            box-shadow: inset 0 1px 2px rgba(255, 255, 255, 0.3), 
                        0 24px 64px rgba(0, 30, 20, 0.6) !important;
            border-radius: 16px !important;
        }
        
        div[role="dialog"] h2, 
        div[role="dialog"] p,
        div[role="dialog"] span,
        div[data-testid="stDialog"] h2,
        div[data-testid="stDialog"] p,
        div[data-testid="stDialog"] span {
            color: #f8fafc !important;
        }
        
        /* 强制卡片内部的文本颜色，防止在深色背景下看不清 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) p,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) h4,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) label,
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) span {
            color: #f1f5f9 !important;
        }

        /* 高对比度边框输入框 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) input, 
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) select, 
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) div[data-baseweb="select"] > div {
            border: 1.5px solid rgba(0, 200, 150, 0.6) !important;
            background-color: rgba(2, 40, 35, 0.75) !important;
            color: #ffffff !important;
            border-radius: 10px !important;
            transition: all 0.2s ease !important;
        }
        
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) input:focus, 
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) div[data-baseweb="select"] > div:focus-within {
            border-color: #00ffcc !important;
            box-shadow: 0 0 0 3px rgba(0, 255, 204, 0.3) !important;
        }

        /* 高级毛玻璃微立体按钮 */
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) button {
            background: linear-gradient(135deg, rgba(0, 150, 120, 0.45), rgba(0, 100, 80, 0.3)) !important;
            border: 1px solid rgba(0, 255, 200, 0.4) !important;
            color: #ffffff !important;
            border-radius: 8px !important;
            font-weight: 600 !important;
            transition: all 0.2s ease !important;
            box-shadow: 0 2px 8px rgba(0, 40, 30, 0.2) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) button:hover {
            background: linear-gradient(135deg, rgba(0, 180, 140, 0.55), rgba(0, 120, 90, 0.4)) !important;
            border-color: #00ffcc !important;
            box-shadow: 0 4px 12px rgba(0, 255, 204, 0.35) !important;
            transform: translateY(-1px) !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"]:has(.gemstone-card-anchor) button:active {
            transform: translateY(1px) !important;
        }
    </style>
    """, unsafe_allow_html=True)

    if not is_admin:
        st.warning(t("readonly_msg"))
        st.stop()
        
    @st.experimental_dialog(t("restore_confirm_title"))
    def show_restore_dialog(filename):
        st.warning(t("restore_confirm_msg").format(filename=filename))
        col1, col2 = st.columns(2)
        with col1:
            if st.button(t("confirm"), key="restore_confirm_btn", use_container_width=True):
                resp = api_post("/system/backup/restore", json_data={"filename": filename})
                if resp and resp.get("status") == "success":
                    st.success(resp.get("message") or t("operation_success"))
                    st.session_state.toast_message = (t("db_restore_success"), "✅")
                    time.sleep(2)
                    st.rerun()
                else:
                    st.error(t("operation_failed"))
        with col2:
            if st.button(t("cancel"), key="restore_cancel_btn", use_container_width=True):
                st.rerun()
 
    # 获取当前配置
    config = api_get("/system/backup/config") or {"hour": 2, "minute": 0, "retention_days": 7}
    
    # 使用 container + 锚点方式代替原始 HTML 拼接，防止 Streamlit 多解析出空 div 卡片
    with st.container(border=True):
        st.markdown('<div class="gemstone-card-anchor"></div>', unsafe_allow_html=True)
        st.subheader(t("backup_config"))
        
        # 策略配置表单
        with st.form("backup_config_form"):
            col_h, col_m, col_d = st.columns(3)
            with col_h:
                hour_val = st.number_input(t("backup_hour"), min_value=0, max_value=23, value=config.get("hour", 2), step=1)
            with col_m:
                minute_val = st.number_input(t("backup_minute"), min_value=0, max_value=59, value=config.get("minute", 0), step=1)
            with col_d:
                days_val = st.number_input(t("retention_days"), min_value=1, max_value=365, value=config.get("retention_days", 7), step=1)
                
            save_btn = st.form_submit_button(t("save"), use_container_width=True)
            if save_btn:
                resp = api_post("/system/backup/config", json_data={
                    "hour": int(hour_val),
                    "minute": int(minute_val),
                    "retention_days": int(days_val)
                })
                if resp and resp.get("status") == "success":
                    st.session_state.toast_message = (t("save_success"), "✅")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error(t("operation_failed"))
                    
    with st.container(border=True):
        st.markdown('<div class="gemstone-card-anchor"></div>', unsafe_allow_html=True)
        col_title, col_action = st.columns([4, 1])
        with col_title:
            st.subheader(t("backup_files"))
        with col_action:
            # 手动立即备份
            if st.button(t("backup_now"), key="manual_backup_btn", use_container_width=True):
                with st.spinner(t("db_backing_up")):
                    resp = api_post("/system/backup/create")
                    if resp and resp.get("status") == "success":
                        st.session_state.toast_message = (t("operation_success"), "✅")
                        time.sleep(1)
                        st.rerun()
                    else:
                        st.error(t("operation_failed"))
                        
        # 获取并渲染备份文件表格
        backups = api_get("/system/backups") or []
        if backups:
            # 格式化数据用于显示
            formatted_backups = []
            for i, b in enumerate(backups):
                size_mb = f"{b['size_bytes'] / (1024 * 1024):.2f} MB"
                formatted_backups.append({
                    t("seq_no"): i + 1,
                    "File Name": b["filename"],
                    "Size": size_mb,
                    "Time Created": b["created_at"]
                })
            
            df_backups = pd.DataFrame(formatted_backups)
            # 用 streamlit 渲染只读数据表格
            st.dataframe(df_backups, use_container_width=True, hide_index=True)
            
            st.divider()
            st.write("#### " + t("choose_record") + " / " + t("restore"))
            # 提供一个下拉框选择并进行还原
            selected_file = st.selectbox(t("choose_record"), [b["filename"] for b in backups], key="restore_select")
            if selected_file:
                if st.button(t("restore"), key="restore_trigger_btn"):
                    show_restore_dialog(selected_file)
        else:
            st.info(t("no_data"))

# ==================== 考勤排休转换 ====================
elif menu == t("attendance_converter"):
    st.header(t("attendance_converter"))
    st.markdown(f'<div class="section-note">{t("attendance_converter_note")}</div>', unsafe_allow_html=True)
    if not is_admin:
        st.warning(t("readonly_msg"))
        st.stop()
        
    uploaded_logs = st.file_uploader(t("upload_attendance_logs"), type=["xlsx", "xls"], accept_multiple_files=True, key="uploaded_attendance_logs")
    uploaded_template = st.file_uploader(t("upload_attendance_template"), type=["xlsx"], key="uploaded_attendance_template")
    
    if uploaded_logs and uploaded_template:
        if st.button("🚀 " + t("start_conversion"), key="start_attendance_conversion"):
            with st.spinner(t("converting_msg")):
                try:
                    # 构建 multipart 上传数据
                    files = []
                    for f in uploaded_logs:
                        files.append(('files', (f.name, f.getvalue(), f.type)))
                    files.append(('template', (uploaded_template.name, uploaded_template.getvalue(), uploaded_template.type)))
                    
                    # 向后端发起转换请求
                    r = requests.post(
                        f"{_INTERNAL_BACKEND_URL}/api/attendance/convert",
                        files=files,
                        headers=auth_h(),
                        timeout=120
                    )
                    
                    if r.status_code == 200:
                        st.success(t("conversion_success"))
                        st.download_button(
                            label="💾 " + t("download_attendance_result"),
                            data=r.content,
                            file_name=f"attendance_converted_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="download_attendance_result_btn"
                        )
                    else:
                        try:
                            detail = r.json().get("detail", r.text)
                        except Exception:
                            detail = r.text
                        st.error(f"❌ {t('operation_failed')}: {detail}")
                except Exception as e:
                    st.error(f"❌ {t('operation_failed')}: {str(e)}")

# ==================== 系统设置 ====================
elif menu == t("settings"):
    st.header(t("settings"))
    st.markdown(f'<div class="section-note">{t("settings_note")}</div>', unsafe_allow_html=True)
    if not is_admin:
        st.warning(t("readonly_msg"))
        st.stop()
    tab_settings, tab_users, tab_logo = st.tabs([t("meta_maintenance"), t("user_management"), t("company_logo")])
    with tab_settings:
        m_type = st.radio(t("meta_maintenance"), [t("workshop"), t("team"), t("nationality")], horizontal=True, key="meta_type")
        items = api_get(f"/meta/{m_type}") or []
        col1, col2, col3 = st.columns(3)
        with col1:
            add_val = st.text_input(t("new_value"), key="add_val")
            if st.button(t("add"), key="add_meta"):
                if add_val:
                    resp = api_post("/meta/add", params={"m_type": m_type, "value": add_val})
                    if resp and resp.get("status") == "success":
                        st.session_state.toast_message = (t("operation_success"), "✅")
                        st.rerun()
                    else:
                        st.toast(t("operation_failed"), icon="❌")
        with col2:
            if items:
                old = st.selectbox(t("old_value"), items, key="old_val")
                new = st.text_input(t("new_name"), key="new_val")
                if st.button(t("update"), key="update_meta"):
                    if new:
                        resp = api_post("/meta/update", params={"m_type": m_type, "old_val": old, "new_val": new})
                        if resp and resp.get("status") == "success":
                            st.session_state.toast_message = (t("operation_success"), "✅")
                            st.rerun()
                        else:
                            st.toast(t("operation_failed"), icon="❌")
        with col3:
            if items:
                del_val = st.selectbox(t("delete_value"), items, key="del_val")
                if st.button(t("delete"), key="delete_meta"):
                    resp = api_post("/meta/delete", params={"m_type": m_type, "value": del_val})
                    if resp and resp.get("status") == "success":
                        st.session_state.toast_message = (t("operation_success"), "✅")
                        st.rerun()
                    else:
                        st.toast(t("operation_failed"), icon="❌")
        st.divider()
        st.subheader(t("db_maintenance"))
        if st.button(t("backup"), key="backup_db"):
            with st.spinner(t("db_backing_up")):
                r = requests.get("/api/db/backup", headers=auth_h(), timeout=60)
                if r.status_code == 200:
                    st.download_button(t("backup"), data=r.content,
                                       file_name=f"hr_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.sql",
                                       key="backup_download")
                else:
                    st.toast(t("operation_failed"), icon="❌")
        restore_file = st.file_uploader(t("upload_backup"), type=["sql"], key="restore_file")
        if restore_file and st.button(t("restore"), key="restore_db"):
            with st.spinner(t("db_restoring")):
                resp = api_post("/db/restore", files={"file": restore_file})
                if resp and resp.get("status") == "success":
                    st.session_state.toast_message = (t("db_restore_success"), "✅")
                    st.rerun()
                else:
                    st.toast(t("operation_failed"), icon="❌")
    with tab_users:
        st.subheader(t("user_management"))
        all_workshops = api_get("/meta/车间") or []
        users_res = api_get("/users")
        if users_res and "users" in users_res:
            for u in users_res["users"]:
                ws_s = u.get("ws_scope")
                if ws_s:
                    try:
                        lst = json.loads(ws_s)
                        if isinstance(lst, list) and len(lst) > 0:
                            u["ws_scope_display"] = ", ".join([t_val(x) for x in lst])
                        else:
                            u["ws_scope_display"] = t("all")
                    except:
                        u["ws_scope_display"] = ws_s
                else:
                    u["ws_scope_display"] = t("all")

            users_df = pd.DataFrame(users_res["users"])
            users_display = users_df[["username", "role", "ws_scope_display"]].rename(columns={
                "username": t("username"),
                "role": t("role"),
                "ws_scope_display": t("workshop_scope")
            })
            users_display = users_display.reset_index(drop=True)
            users_display.insert(0, t("seq_no"), range(1, len(users_display) + 1))
            st.dataframe(users_display, use_container_width=True, hide_index=True)
            with st.expander(t("add_user")):
                new_user = st.text_input(t("new_username"), key="new_user")
                new_pwd = st.text_input(t("new_password"), type="password", key="new_pwd")
                new_pwd2 = st.text_input(t("confirm_password"), type="password", key="new_pwd2")
                new_role = st.selectbox(t("role"), ["viewer", "admin"], key="new_role")
                new_ws_scope = st.multiselect(t("workshop_scope"), options=all_workshops, format_func=t_val, key="new_ws_scope")
                if st.button(t("add"), key="add_user_btn"):
                    if not new_user or not new_pwd:
                        st.error(t("username_password_required"))
                    elif new_pwd != new_pwd2:
                        st.error(t("password_mismatch"))
                    else:
                        ws_scope_json = json.dumps(new_ws_scope) if new_ws_scope else None
                        resp = api_post("/users", json_data={"username": new_user, "password": new_pwd, "role": new_role, "ws_scope": ws_scope_json})
                        if resp and resp.get("status") == "success":
                            st.session_state.toast_message = (t("operation_success"), "✅")
                            st.rerun()
                        else:
                            st.toast(t("operation_failed"), icon="❌")
            st.write("#### " + t("edit") + " / " + t("delete"))
            if users_res["users"]:
                target_user = st.selectbox(t("select_employee"), [u["username"] for u in users_res["users"] if u["username"] != st.session_state.user_info["username"]], key="target_user")
                if target_user:
                    target_data = next((u for u in users_res["users"] if u["username"] == target_user), None)
                    if target_data:
                        new_role_sel = st.selectbox(t("role"), ["viewer", "admin"], index=0 if target_data["role"]=="viewer" else 1, key="new_role_sel")
                        curr_ws_scope = []
                        if target_data.get("ws_scope"):
                            try:
                                curr_ws_scope = json.loads(target_data["ws_scope"])
                                if not isinstance(curr_ws_scope, list):
                                    curr_ws_scope = []
                            except:
                                pass
                        new_ws_scope_sel = st.multiselect(
                            t("workshop_scope"),
                            options=all_workshops,
                            default=[w for w in curr_ws_scope if w in all_workshops],
                            format_func=t_val,
                            key="new_ws_scope_sel"
                        )
                        col1, col2 = st.columns(2)
                        with col1:
                            if st.button(t("update"), key="update_role_btn"):
                                ws_scope_json = json.dumps(new_ws_scope_sel) if new_ws_scope_sel else None
                                resp = api_put(f"/users/{target_data['id']}/role", params={"role": new_role_sel, "ws_scope": ws_scope_json})
                                if resp and resp.get("status") == "success":
                                    st.session_state.toast_message = (t("operation_success"), "✅")
                                    st.rerun()
                                else:
                                    st.toast(t("operation_failed"), icon="❌")
                        with col2:
                            delete_key = f"del_confirm_{target_user}"
                            if delete_key not in st.session_state:
                                st.session_state[delete_key] = False
                            if st.button(t("delete"), key="delete_user_btn"):
                                st.session_state[delete_key] = True
                            if st.session_state[delete_key]:
                                st.warning(t("confirm_delete_user").format(username=target_user))
                                col_yes, col_no = st.columns(2)
                                if col_yes.button("✅ " + t("confirm"), key="del_confirm_yes"):
                                    resp = api_delete(f"/users/{target_data['id']}")
                                    if resp and resp.get("status") == "success":
                                        st.session_state.toast_message = (t("operation_success"), "✅")
                                        st.session_state[delete_key] = False
                                        st.rerun()
                                    else:
                                        st.toast(t("operation_failed"), icon="❌")
                                if col_no.button("❌ " + t("cancel"), key="del_confirm_no"):
                                    st.session_state[delete_key] = False
                                    st.rerun()
    with tab_logo:
        st.subheader(t("logo_upload_title"))
        uploaded_file = st.file_uploader(t("logo_select_file"), type=["png", "jpg", "jpeg"], key="logo_upload")
        if uploaded_file and st.button(t("logo_upload_btn"), key="upload_logo_btn"):
            files = {"file": uploaded_file}
            resp = api_post("/settings/logo", files=files)
            if resp and resp.get("status") == "success":
                st.session_state.toast_message = (t("logo_upload_success"), "✅")
                st.rerun()
            else:
                st.toast(t("logo_upload_failed"), icon="❌")
        try:
            logo_resp = requests.get("/api/settings/logo", timeout=3)
            if logo_resp.status_code == 200:
                logo_base64 = base64.b64encode(logo_resp.content).decode()
                st.image(f"data:image/png;base64,{logo_base64}", width=150)
            else:
                st.info(t("logo_empty"))
        except:
            st.info(t("logo_get_failed"))

# 渲染屏幕中间的专用提示弹窗
show_modal_message()

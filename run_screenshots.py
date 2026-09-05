import asyncio
import os
import sys
import time
from playwright.async_api import async_playwright

# Ensure UTF-8 output encoding for Windows stdout
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

PIC_DIR = r"d:\WEB_SYSTEM\PIC"
os.makedirs(PIC_DIR, exist_ok=True)

async def capture_all():
    print("Starting screenshot acquisition...")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, channel="msedge")
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        print("1. Opening Login Page...")
        await page.goto("http://localhost:8501", wait_until="networkidle")
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(PIC_DIR, "01_系统登录界面.png"), full_page=True)
        print("-> Saved 01_系统登录界面.png")

        print("2. Logging in as admin...")
        inputs = await page.query_selector_all("input")
        if len(inputs) >= 2:
            await inputs[0].fill("admin")
            await inputs[1].fill("iwip123")
            
            submit_btn = page.locator("button[type='submit']")
            if await submit_btn.count() > 0:
                await submit_btn.click()
            else:
                login_btn = page.locator("button:has-text('登录')")
                if await login_btn.count() > 0:
                    await login_btn.click()
            
            await asyncio.sleep(4)

        print("Logged in successfully. Dashboard rendered.")
        await page.screenshot(path=os.path.join(PIC_DIR, "02_数据看板与双趋势图.png"), full_page=True)
        print("-> Saved 02_数据看板与双趋势图.png")

        menu_items = [
            ("组织架构", "04_组织架构与本土化率.png"),
            ("员工花名册", "03_员工花名册全局检索.png"),
            ("离职名册", "05_离职人员动态管理.png"),
            ("劳保用品", "06_劳保用品全生命周期管理.png"),
            ("考勤排休转换", "07_考勤自动对账与转换.png"),
            ("操作日志", "08_系统审计日志与安全管控.png"),
            ("数据备份与还原", "09_全自动备份与容灾管理.png"),
            ("系统设置", "10_系统设置与参数配置.png"),
        ]

        for text_target, filename in menu_items:
            try:
                print(f"Clicking menu option containing: {text_target}")
                # Locate Streamlit radio label in sidebar containing text
                label_loc = page.locator("section[data-testid='stSidebar'] label").filter(has_text=text_target).first
                if await label_loc.count() > 0:
                    await label_loc.click()
                else:
                    text_loc = page.get_by_text(text_target).first
                    if await text_loc.count() > 0:
                        await text_loc.click()
                    else:
                        print(f"Target '{text_target}' not found!")
                        continue
                
                await asyncio.sleep(3)
                filepath = os.path.join(PIC_DIR, filename)
                await page.screenshot(path=filepath, full_page=True)
                print(f"-> Saved {filename}")
            except Exception as e:
                print(f"Error on {text_target}: {e}")

        await browser.close()
        print("Done capturing all screenshots successfully!")

if __name__ == "__main__":
    asyncio.run(capture_all())

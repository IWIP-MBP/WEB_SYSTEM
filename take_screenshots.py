import asyncio
import os
import time
from playwright.async_api import async_playwright

PIC_DIR = r"d:\WEB_SYSTEM\PIC"
os.makedirs(PIC_DIR, exist_ok=True)

async def capture():
    async with async_playwright() as p:
        # Launch browser with msedge or chrome or chromium
        try:
            browser = await p.chromium.launch(headless=True)
        except Exception as e:
            print("Chromium launch failed, trying channel msedge:", e)
            try:
                browser = await p.chromium.launch(headless=True, channel="msedge")
            except Exception as e2:
                print("msedge launch failed, trying chrome:", e2)
                browser = await p.chromium.launch(headless=True, channel="chrome")
        
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()

        print("1. Navigating to Login Page...")
        await page.goto("http://localhost:8501", wait_until="networkidle")
        await asyncio.sleep(3)
        await page.screenshot(path=os.path.join(PIC_DIR, "01_系统登录界面.png"), full_page=True)
        print("Captured: 01_系统登录界面.png")

        print("2. Logging in as admin...")
        # Locate inputs
        inputs = await page.query_selector_all("input")
        if len(inputs) >= 2:
            await inputs[0].fill("admin")
            await inputs[1].fill("iwip123")
            
            # Click submit / login button
            buttons = await page.query_selector_all("button")
            for btn in buttons:
                txt = await btn.inner_text()
                if "登录" in txt or "Login" in txt or "Masuk" in txt:
                    await btn.click()
                    break
            else:
                # try form submit button
                submit_btn = page.locator("button[type='submit']")
                if await submit_btn.count() > 0:
                    await submit_btn.click()

            await asyncio.sleep(4)

        # Function to click sidebar nav or tab and take screenshot
        async def navigate_and_screenshot(label, filename):
            print(f"Navigating to {label}...")
            # Streamlit radio / sidebar select or buttons
            # Try to locate by text in sidebar or main area
            element = page.get_by_text(label, exact=False).first
            if await element.count() > 0:
                await element.click()
                await asyncio.sleep(3)
            else:
                print(f"Warning: Could not find label '{label}'")
            
            filepath = os.path.join(PIC_DIR, filename)
            await page.screenshot(path=filepath, full_page=True)
            print(f"Captured: {filename}")

        # Let's inspect the page content to find navigation elements
        content = await page.content()
        # Take screenshot of Dashboard first
        await asyncio.sleep(2)
        await page.screenshot(path=os.path.join(PIC_DIR, "02_数据看板与双趋势图.png"), full_page=True)
        print("Captured: 02_数据看板与双趋势图.png")

        # Find all radio options or sidebar buttons
        sidebar = page.locator("section[data-testid='stSidebar']")
        if await sidebar.count() > 0:
            sidebar_text = await sidebar.inner_text()
            print("Sidebar Text:\n", sidebar_text)

        # Let's try clicking through options if available
        options = [
            ("员工花名册", "03_员工花名册全局检索.png"),
            ("组织架构", "04_组织架构与本土化率.png"),
            ("劳保管理", "05_劳保用品全生命周期管理.png"),
            ("考勤管理", "06_考勤考勤管理.png"),
            ("系统日志", "07_系统审计日志与安全管控.png"),
            ("数据备份", "08_自动备份与容灾管理.png"),
            ("系统设置", "09_系统设置与参数配置.png"),
        ]

        for opt_label, opt_file in options:
            try:
                # Click item in sidebar or main
                target = page.locator(f"section[data-testid='stSidebar'] p:has-text('{opt_label}')").first
                if await target.count() == 0:
                    target = page.get_by_text(opt_label).first
                if await target.count() > 0:
                    await target.click()
                    await asyncio.sleep(3)
                    await page.screenshot(path=os.path.join(PIC_DIR, opt_file), full_page=True)
                    print(f"Captured: {opt_file}")
            except Exception as ex:
                print(f"Error capturing {opt_label}:", ex)

        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture())

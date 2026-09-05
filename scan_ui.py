import sys

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

with open(r'd:\WEB_SYSTEM\ui.py', encoding='utf-8') as f:
    lines = f.readlines()

print("--- Scan Results ---")
for idx, line in enumerate(lines):
    line_no = idx + 1
    if any(k in line for k in ["download_button", "file_uploader", "can_write", "is_admin", "is_admin_account", "menu_options"]):
        print(f"Line {line_no}: {line.strip()}")

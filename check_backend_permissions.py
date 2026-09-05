import glob
import re

router_files = glob.glob(r"d:\WEB_SYSTEM\routers\*.py")

print("--- Router Endpoints Check ---")
for rfile in router_files:
    print(f"\nFile: {rfile}")
    with open(rfile, encoding='utf-8') as f:
        content = f.read()

    lines = content.splitlines()
    for idx, line in enumerate(lines):
        if re.search(r'@router\.(post|put|delete|get)\(', line):
            print(f"Line {idx+1}: {line.strip()}")
            # Print next 5 lines to see if get_current_user or role check is present
            for k in range(1, 6):
                if idx + k < len(lines):
                    sub = lines[idx+k].strip()
                    if "current_user" in sub or "role" in sub or "def " in sub:
                        print(f"    + Line {idx+1+k}: {sub}")

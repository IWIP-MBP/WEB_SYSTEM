import os
import sys
import subprocess
import argparse
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("init_department")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

def run_cmd(cmd, check=True):
    logger.info(f"执行命令: {cmd}")
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace"
    )
    if check and result.returncode != 0:
        logger.error(f"命令执行失败:\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}")
        raise RuntimeError(f"命令执行失败: {cmd}")
    return result

def init_department(dept_code: str, dept_name: str, admin_password: str = "iwip123"):
    """
    初始化新部门的基础设施环境：
    1. 在 PostgreSQL 容器 hr_db 中创建独立数据库 hr_system_{dept_code}
    2. 创建独立的本地备份目录 backups_{dept_code}
    3. 创建独立的本地上传目录 uploads_{dept_code}
    """
    dept_code = dept_code.strip().lower()
    db_name = f"hr_system_{dept_code}"
    
    logger.info("=" * 60)
    logger.info(f"开始为新部门 [{dept_name}] (代号: {dept_code}) 初始化独立隔离环境...")
    logger.info("=" * 60)

    # 1. 检查并创建数据库
    logger.info(f"1. 检查数据库 {db_name} 是否已存在...")
    check_sql = f"SELECT 1 FROM pg_database WHERE datname = '{db_name}';"
    check_res = run_cmd(f'docker exec hr_db psql -U admin -d hr_system -tc "{check_sql}"')
    
    if "1" in check_res.stdout:
        logger.warning(f"数据库 {db_name} 已存在，跳过创建。")
    else:
        logger.info(f"正在创建独立数据库: {db_name}...")
        run_cmd(f'docker exec hr_db psql -U admin -d hr_system -c "CREATE DATABASE {db_name} ENCODING \'UTF8\';"')
        logger.info(f"数据库 {db_name} 创建成功！")

    # 2. 创建本地备份和上传目录
    backup_dir = os.path.join(BASE_DIR, f"backups_{dept_code}")
    upload_dir = os.path.join(BASE_DIR, f"uploads_{dept_code}")

    os.makedirs(backup_dir, exist_ok=True)
    os.makedirs(os.path.join(upload_dir, "exports"), exist_ok=True)
    os.makedirs(os.path.join(upload_dir, "logos"), exist_ok=True)

    logger.info(f"2. 独立备份目录已就绪: {backup_dir}")
    logger.info(f"   独立上传目录已就绪: {upload_dir}")

    # 3. 打印配置指引
    logger.info("=" * 60)
    logger.info(f"恭喜！新部门 [{dept_name}] 独立数据底层已初始化完毕。")
    logger.info(f"数据库名称: {db_name}")
    logger.info(f"备份物理路径: {backup_dir}")
    logger.info("当该部门后端容器首次启动时，系统将全自动自动建立所有表结构，并创建默认 admin 账号。")
    logger.info("=" * 60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="初始化新部门独立数据库与目录")
    parser.add_argument("--code", type=str, default="dept2", help="部门代号，例如: dept2")
    parser.add_argument("--name", type=str, default="综合管理部", help="部门中文名，例如: 综合管理部")
    parser.add_argument("--password", type=str, default="iwip123", help="初始admin密码，默认: iwip123")
    
    args = parser.parse_args()
    init_department(args.code, args.name, args.password)

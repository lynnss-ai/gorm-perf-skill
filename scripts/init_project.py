#!/usr/bin/env python3
"""
init_project.py — 将 dbcore 基础包脚手架到目标项目中

用法:
  python3 scripts/init_project.py --output ./internal/dbcore
  python3 scripts/init_project.py --output ./pkg/dbcore --package mydbcore
  python3 scripts/init_project.py --output ./common/dbcore --dry-run

功能:
  1. 将 assets/dbcore/ 下的三个核心文件复制到目标目录
     - base_model.go   泛型 BaseModel（含游标分页、ListAll 上限保护等修复）
     - query_builder.go 查询条件构建器（含 InStrings/InInts Bug 修复、OrGroup）
     - transaction.go  事务管理器（支持嵌套事务）
  2. 将文件头的 package 声明替换为 --package 指定的名称
  3. --dry-run 模式仅打印将要写入的内容，不实际创建文件
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

# assets/dbcore/ 目录相对于本脚本的位置
SCRIPT_DIR = Path(__file__).parent
ASSETS_DIR = SCRIPT_DIR.parent / "assets" / "dbcore"

CORE_FILES = [
    "base_model.go",
    "query_builder.go",
    "transaction.go",
]

# 颜色输出
GREEN  = "\033[92m"
YELLOW = "\033[93m"
RED    = "\033[91m"
RESET  = "\033[0m"
BOLD   = "\033[1m"

def log_ok(msg):    print(f"{GREEN}✅ {msg}{RESET}")
def log_warn(msg):  print(f"{YELLOW}⚠️  {msg}{RESET}")
def log_err(msg):   print(f"{RED}❌ {msg}{RESET}", file=sys.stderr)
def log_info(msg):  print(f"   {msg}")


def replace_package(content: str, new_package: str) -> str:
    """将文件中的 package 声明替换为指定包名"""
    return re.sub(
        r'^package\s+\w+',
        f'package {new_package}',
        content,
        count=1,
        flags=re.MULTILINE
    )


def check_assets():
    """检查 assets 目录是否完整"""
    missing = []
    for fname in CORE_FILES:
        if not (ASSETS_DIR / fname).exists():
            missing.append(fname)
    if missing:
        log_err(f"assets/dbcore/ 中缺少以下文件: {missing}")
        log_err(f"请确认 skill 目录完整，assets 路径: {ASSETS_DIR}")
        sys.exit(1)


def scaffold(output_dir: Path, package_name: str, dry_run: bool, force: bool):
    check_assets()

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n{BOLD}📦 dbcore 脚手架初始化{RESET}")
    print(f"   输出目录: {output_dir}")
    print(f"   包名:     {package_name}")
    print(f"   模式:     {'DRY-RUN（不写入文件）' if dry_run else '写入文件'}")
    print()

    written = []
    skipped = []

    for fname in CORE_FILES:
        src = ASSETS_DIR / fname
        dst = output_dir / fname

        content = src.read_text(encoding="utf-8")

        # 替换 package 声明
        if package_name != "dbcore":
            content = replace_package(content, package_name)

        if dry_run:
            print(f"{BOLD}── {fname} ──────────────────────────────{RESET}")
            # 只打印前 30 行预览
            lines = content.splitlines()
            for line in lines[:30]:
                log_info(line)
            if len(lines) > 30:
                log_info(f"... （共 {len(lines)} 行）")
            print()
            written.append(fname)
            continue

        # 检查是否已存在
        if dst.exists() and not force:
            log_warn(f"{fname} 已存在，跳过（用 --force 覆盖）")
            skipped.append(fname)
            continue

        dst.write_text(content, encoding="utf-8")
        log_ok(f"写入 {dst}")
        written.append(fname)

    # 打印后续步骤
    print()
    if dry_run:
        print(f"{BOLD}DRY-RUN 完成，以上为将要写入的内容。{RESET}")
        print(f"去掉 --dry-run 参数后重新执行以实际写入。")
    else:
        print(f"{BOLD}✨ 初始化完成！{RESET}")
        print(f"   写入: {len(written)} 个文件  跳过: {len(skipped)} 个文件")
        print()
        print(f"{BOLD}后续步骤:{RESET}")
        print(f"  1. 在目标项目中实现 autoFillID / autoFillIDBatch 函数")
        print(f"     （根据项目 ID 生成策略，如雪花算法、UUID 等）")
        print()
        print(f"  2. 初始化 DB 连接，推荐配置：")
        print(f"     db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{{")
        print(f"         SkipDefaultTransaction:                   true,")
        print(f"         PrepareStmt:                              true,")
        print(f"         DisableForeignKeyConstraintWhenMigrating: true,")
        print(f"     }})")
        print(f"     sqlDB, _ := db.DB()")
        print(f"     sqlDB.SetMaxOpenConns(100)")
        print(f"     sqlDB.SetMaxIdleConns(20)")
        print(f"     sqlDB.SetConnMaxLifetime(time.Hour)")
        print()
        print(f"  3. 创建具体 Model（以 Order 为例）：")
        print(f"     type OrderModel struct {{")
        print(f"         {package_name}.BaseModel[Order]")
        print(f"     }}")
        print()
        print(f"  4. 多租户场景：在具体 Model 覆写 List/Page，")
        print(f"     强制注入 tenant_id，防止数据越权。")
        print(f"     详见 references/base-model-pattern.md 第 8 节。")
        print()
        print(f"  5. 软删除 + 唯一索引：复合索引包含 deleted_at，")
        print(f"     避免软删除后重建相同记录报 Duplicate entry。")
        print(f"     详见 references/base-model-pattern.md 第 2 节。")


def main():
    parser = argparse.ArgumentParser(
        description="将 dbcore 基础包脚手架到目标项目",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python3 scripts/init_project.py --output ./internal/dbcore
  python3 scripts/init_project.py --output ./pkg/dbcore --package mydbcore
  python3 scripts/init_project.py --output ./common/dbcore --dry-run
  python3 scripts/init_project.py --output ./internal/dbcore --force
        """
    )
    parser.add_argument(
        "--output", "-o",
        required=True,
        help="输出目录路径（不存在时自动创建）"
    )
    parser.add_argument(
        "--package", "-p",
        default="dbcore",
        help="Go package 名称（默认: dbcore）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="预览模式：打印文件内容，不实际写入"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="强制覆盖已存在的文件"
    )

    args = parser.parse_args()

    # 验证 package 名称合法性
    if not re.match(r'^[a-z][a-z0-9_]*$', args.package):
        log_err(f"package 名称不合法: '{args.package}'（只能含小写字母、数字、下划线）")
        sys.exit(1)

    scaffold(
        output_dir=Path(args.output),
        package_name=args.package,
        dry_run=args.dry_run,
        force=args.force,
    )


if __name__ == "__main__":
    main()

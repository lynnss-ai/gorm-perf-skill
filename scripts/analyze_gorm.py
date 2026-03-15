#!/usr/bin/env python3
"""
analyze_gorm.py — 静态分析 Go 代码中的 GORM 反模式
用法: python3 analyze_gorm.py <go_file_or_stdin>

输出: 只打印命中的问题，没有问题则输出 "✅ 未发现明显反模式"
"""

import sys
import re
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class Issue:
    level: str          # ERROR / WARN / INFO
    rule: str
    line: int
    snippet: str
    suggestion: str

def analyze(code: str) -> List[Issue]:
    issues: List[Issue] = []
    lines = code.splitlines()

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # ── R1: SELECT * (Find without Select) ──────────────────────────────
        if re.search(r'\.(Find|First|Last|Take)\s*\(', stripped) and \
           not re.search(r'\.Select\s*\(', stripped) and \
           not re.search(r'\.Raw\s*\(', stripped):
            # 排除已经有 Select 在前几行的链式调用
            context = "\n".join(lines[max(0,i-4):i])
            if ".Select(" not in context:
                issues.append(Issue(
                    level="WARN", rule="SELECT_STAR",
                    line=i, snippet=stripped,
                    suggestion="添加 .Select(\"id\",\"name\",...) 只查需要字段，减少数据传输和内存分配"
                ))

        # ── R2: OFFSET 大分页 ────────────────────────────────────────────────
        m = re.search(r'\.Offset\s*\(\s*(\w+)', stripped)
        if m:
            val = m.group(1)
            # 如果是字面量且 > 1000，或者是变量（可能很大）
            if val.isdigit() and int(val) > 1000:
                issues.append(Issue(
                    level="ERROR", rule="LARGE_OFFSET",
                    line=i, snippet=stripped,
                    suggestion=f"Offset({val}) 会导致全表扫描前 N 行，改用游标分页: WHERE id > lastID ORDER BY id LIMIT n"
                ))
            elif not val.isdigit():
                issues.append(Issue(
                    level="WARN", rule="DYNAMIC_OFFSET",
                    line=i, snippet=stripped,
                    suggestion="动态 Offset 在大表上性能急剧下降，建议改为游标分页（WHERE id > lastID）"
                ))

        # ── R3: 循环内 DB 操作（N+1） ────────────────────────────────────────
        if re.search(r'for\s+.+range\s+', stripped):
            # 往后几行找 db. 操作
            window = lines[i:min(i+8, len(lines))]
            for j, wline in enumerate(window):
                if re.search(r'\b(db|tx)\.(Find|First|Create|Save|Update|Delete)\b', wline):
                    issues.append(Issue(
                        level="ERROR", rule="N_PLUS_1",
                        line=i+j+1, snippet=wline.strip(),
                        suggestion="循环内 DB 操作 = N+1 查询。改用 Preload / Joins 批量加载，或先收集 ID 再 WHERE id IN (?)"
                    ))
                    break  # 每个 for 只报一次

        # ── R4: struct Updates（零值丢失） ───────────────────────────────────
        if re.search(r'\.Updates\s*\(\s*\w+\s*\{', stripped):
            issues.append(Issue(
                level="WARN", rule="STRUCT_UPDATES_ZERO_VALUE",
                line=i, snippet=stripped,
                suggestion="Updates(struct{}) 会忽略零值字段（int=0, bool=false, string=\"\"）。"
                           "改用 Updates(map[string]any{\"field\": value}) 确保零值也能更新"
            ))

        # ── R5: 未带 WithContext ─────────────────────────────────────────────
        if re.search(r'\b(db)\.(Find|First|Create|Update|Delete|Exec|Raw)\b', stripped) and \
           "WithContext" not in stripped and ".Session(" not in stripped:
            # 只报一次
            if not any(iss.rule == "NO_CONTEXT" for iss in issues):
                issues.append(Issue(
                    level="INFO", rule="NO_CONTEXT",
                    line=i, snippet=stripped,
                    suggestion="建议所有 DB 操作传入 ctx: db.WithContext(ctx).Find(...)，支持超时取消和链路追踪"
                ))

        # ── R6: 未检查 Error ─────────────────────────────────────────────────
        if re.search(r'\b(db|tx)\.(Find|First|Create|Save|Update|Delete|Exec)\b.*\)', stripped):
            # 检查本行或下一行是否有 .Error / err :=
            next_line = lines[i].strip() if i < len(lines) else ""
            if ".Error" not in stripped and "err" not in stripped.lower() \
               and ".Error" not in next_line and "err" not in next_line.lower():
                issues.append(Issue(
                    level="WARN", rule="UNCHECKED_ERROR",
                    line=i, snippet=stripped,
                    suggestion="未检查 DB 错误。应: if err := db.WithContext(ctx).Find(&u).Error; err != nil { ... }"
                ))

        # ── R7: Find 全表（无 Where 条件） ──────────────────────────────────
        if re.search(r'\.(Find)\s*\(&\w+\)\s*$', stripped) and \
           "Where" not in stripped:
            context = "\n".join(lines[max(0,i-5):i])
            if ".Where(" not in context and ".Limit(" not in context:
                issues.append(Issue(
                    level="WARN", rule="FIND_ALL_NO_LIMIT",
                    line=i, snippet=stripped,
                    suggestion="Find 无 Where/Limit 会全表扫描。确认是否需要加条件或 Limit，大表请用 FindInBatches"
                ))

        # ── R8: 事务内有 HTTP/Sleep 等耗时操作 ──────────────────────────────
        if re.search(r'db\.Transaction\(|db\.Begin\(\)', stripped):
            # 检查 transaction block 内是否有 http. / time.Sleep / rpc
            block_end = min(i + 30, len(lines))
            block = "\n".join(lines[i:block_end])
            for pattern, name in [
                (r'http\.(Get|Post|Do)\(', "HTTP 请求"),
                (r'time\.Sleep\(', "time.Sleep"),
                (r'grpc\.|\.Invoke\(', "gRPC 调用"),
                (r'redis\.|\.Set\(|\.Get\(', "Redis 操作（非必要时移出事务）"),
            ]:
                if re.search(pattern, block):
                    issues.append(Issue(
                        level="ERROR", rule="SLOW_OP_IN_TX",
                        line=i, snippet=stripped,
                        suggestion=f"事务内发现 {name}，会长时间持有 DB 连接/锁，"
                                   "应将 IO 操作移到事务外，事务内只做 DB 操作"
                    ))
                    break

        # ── R9: Like '%xxx%' 前后通配 ───────────────────────────────────────
        if re.search(r'LIKE\s+["\']%[^%]+%["\']', stripped, re.IGNORECASE) or \
           re.search(r'like.*"%.*%"', stripped):
            issues.append(Issue(
                level="WARN", rule="LEADING_WILDCARD_LIKE",
                line=i, snippet=stripped,
                suggestion="'%keyword%' 前导通配符无法走索引，触发全表扫描。"
                           "优先使用 'keyword%' 前缀匹配，或改用全文索引 MATCH AGAINST"
            ))

        # ── R10: CreateInBatches / 批量 Create 缺失 ─────────────────────────
        if re.search(r'for\s+.+range\s+', stripped):
            window = lines[i:min(i+5, len(lines))]
            for wline in window:
                if re.search(r'\.(Create)\s*\(', wline) and "Batches" not in wline:
                    issues.append(Issue(
                        level="ERROR", rule="LOOP_CREATE",
                        line=i, snippet=wline.strip(),
                        suggestion="循环内逐条 Create = N 次 INSERT Round-trip。"
                                   "改用 db.CreateInBatches(&slice, 200) 批量插入"
                    ))
                    break

    # 去重（同 rule 只保留第一个）
    seen = set()
    deduped = []
    for iss in issues:
        if iss.rule not in seen:
            seen.add(iss.rule)
            deduped.append(iss)
    return deduped


def format_output(issues: List[Issue]) -> str:
    if not issues:
        return "✅ 未发现明显 GORM 反模式\n"

    level_icon = {"ERROR": "🔴", "WARN": "🟡", "INFO": "🔵"}
    lines = [f"发现 {len(issues)} 个问题：\n"]
    for iss in issues:
        icon = level_icon.get(iss.level, "⚪")
        lines.append(f"{icon} [{iss.level}] {iss.rule}  (第 {iss.line} 行)")
        lines.append(f"   代码: {iss.snippet[:120]}")
        lines.append(f"   建议: {iss.suggestion}")
        lines.append("")
    return "\n".join(lines)


def main():
    if len(sys.argv) > 1 and sys.argv[1] != "-":
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            code = f.read()
    else:
        code = sys.stdin.read()

    issues = analyze(code)
    print(format_output(issues))
    # 退出码：有 ERROR 级别返回 1，方便 CI 集成
    if any(i.level == "ERROR" for i in issues):
        sys.exit(1)


if __name__ == "__main__":
    main()

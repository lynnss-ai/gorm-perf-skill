# gorm-perf-skill

> 适用于 Claude 的 GORM 使用与性能优化专项 Skill

## 功能覆盖

| 场景 | 说明 |
|------|------|
| 代码审查 / 编写 / 调试 | 任何涉及 GORM 的 Go 代码 |
| 慢查询 / N+1 / 全表扫描 | 数据库性能问题定位与优化 |
| 连接池配置 | SetMaxOpenConns / MaxIdleConns 等参数建议 |
| 批量插入 / 更新 | CreateInBatches、Updates map 等最佳实践 |
| 事务管理 | 乐观锁、悲观锁、CAS、FOR UPDATE |
| 读写分离 | dbresolver 插件配置 |
| SQL → GORM struct | CREATE TABLE 转 Go Model |
| 数据库迁移 | golang-migrate、AutoMigrate、ALTER TABLE |
| 单元测试 | sqlmock、SQLite 内存库 |
| Benchmark / pprof | 性能分析代码生成 |
| **分库分表（Sharding）** | gorm.io/sharding 配置、分片算法、双写迁移策略 |
| **监控与可观测性** | Prometheus 指标、慢查询告警、OpenTelemetry 链路追踪 |

## 目录结构

```
gorm-perf/
├── SKILL.md                      # 主技能文件（含快速参考代码）
├── scripts/
│   ├── analyze_gorm.py           # GORM 代码静态分析（R1-R17 反模式检测）
│   ├── gen_model.py              # SQL → GORM struct 生成
│   ├── pool_advisor.py           # 连接池参数建议
│   ├── query_explain.py          # SQL 性能分析
│   ├── migration_gen.py          # 迁移 SQL 生成
│   └── bench_template.py        # Benchmark 代码模板
└── references/
    ├── hooks.md                  # GORM Hooks
    ├── raw-sql.md                # 原生 SQL 使用
    ├── indexing.md               # 索引定义规范
    ├── concurrency.md            # 并发控制（乐观锁等）
    ├── testing.md                # 单元测试
    ├── migration.md              # 数据库迁移
    ├── sharding.md               # 分库分表（NEW v1.0.2）
    └── observability.md          # 监控与可观测性（NEW v1.0.2）
```

## analyze_gorm.py 检测规则（R1–R17）

| 规则 | 级别 | 说明 |
|------|------|------|
| R1: SELECT_STAR | WARN | Find 未指定字段 |
| R2: LARGE_OFFSET | ERROR | Offset > 1000 大分页 |
| R3: N_PLUS_1 | ERROR | 循环内 DB 操作 |
| R4: STRUCT_UPDATES_ZERO_VALUE | WARN | struct Updates 丢零值 |
| R5: NO_CONTEXT | INFO | 未传 WithContext |
| R6: UNCHECKED_ERROR | WARN | 未检查 DB 错误 |
| R7: FIND_ALL_NO_LIMIT | WARN | Find 无 Where/Limit |
| R8: SLOW_OP_IN_TX | ERROR | 事务内 HTTP/Sleep 操作 |
| R9: LEADING_WILDCARD_LIKE | WARN | LIKE '%xxx%' 前导通配 |
| R10: LOOP_CREATE | ERROR | 循环内逐条 Create |
| R11: MISSING_PREPARE_STMT | INFO | 缺少 PrepareStmt 配置 |
| R12: MISSING_SKIP_DEFAULT_TX | INFO | 未使用 SkipDefaultTransaction |
| R13: SQL_INJECTION_RISK | ERROR | Raw SQL 字符串拼接注入风险 |
| R14: PLUCK_MULTI_COLUMN | WARN | Pluck 多列误用 |
| R15: MISSING_POOL_CONFIG | WARN | 未设置连接池 |
| R16: SOFT_DELETE_REMINDER | INFO | DeletedAt 软删除提醒 |
| R17: DB_IN_TX_BLOCK | ERROR | 事务内使用 db 而非 tx |

## 版本历史

| 版本 | 说明 |
|------|------|
| v1.0.2 | 新增分库分表章节、监控可观测性章节；analyze_gorm.py 新增 R11–R17；新增 sharding.md、observability.md |
| v1.0.1 | 优化 description 措辞，通过 ClawHub 安全扫描 |
| v1.0.0 | 初始发布 |

## License

MIT

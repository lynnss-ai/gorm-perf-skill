# gorm-perf-skill

> 适用于 Claude 的 GORM 使用与性能优化专项 Skill

## 功能覆盖

| 场景 | 说明 |
|------|------|
| 代码审查 / 编写 / 调试 | 任何涉及 GORM 的 Go 代码，含反模式静态分析（R1–R18） |
| 慢查询 / N+1 / 全表扫描 | 数据库性能问题定位与优化 |
| 连接池配置 | SetMaxOpenConns / MaxIdleConns 参数建议 + 健康检查代码生成 |
| 批量插入 / 更新 | CreateInBatches、Updates map 等最佳实践 |
| 事务管理 | 乐观锁、悲观锁、CAS、FOR UPDATE、嵌套 Savepoint |
| 读写分离 | dbresolver 插件配置 |
| SQL → GORM struct | CREATE TABLE 转 Go Model，支持 MySQL / PostgreSQL 方言 |
| 数据库迁移 | golang-migrate、AutoMigrate、ALTER TABLE |
| 单元测试 | sqlmock、SQLite 内存库、软删除唯一约束测试 |
| Benchmark / pprof | 性能分析代码生成 |
| **Scopes 与多租户** | 可复用查询条件、行级租户隔离、分页 Scope，支持自动生成 |
| **缓存集成** | Redis Cache-Aside、防击穿（singleflight）、防雪崩（TTL 抖动）、缓存一致性 |
| **分库分表（Sharding）** | gorm.io/sharding 配置、分片算法、双写迁移策略 |
| **监控与可观测性** | Prometheus 指标、慢查询告警、OpenTelemetry 链路追踪、Grafana 仪表盘 |
| **物理外键禁用** | 强制逻辑外键规范，AutoMigrate 禁止 FK 约束，静态检测 R18 |

## 目录结构

```
gorm-perf/
├── SKILL.md                      # 主技能文件（13 节，含快速参考代码）
├── scripts/
│   ├── analyze_gorm.py           # GORM 代码静态分析（R1-R18，双循环架构）
│   ├── gen_model.py              # SQL → GORM struct（支持 MySQL / PostgreSQL）
│   ├── pool_advisor.py           # 连接池参数建议 + 健康检查代码生成
│   ├── query_explain.py          # SQL 性能分析
│   ├── migration_gen.py          # 迁移 SQL 生成
│   ├── bench_template.py         # Benchmark 代码模板
│   ├── scope_gen.py              # Scope 函数自动生成（NEW v1.1.0）
│   └── init_project.py           # dbcore 脚手架生成（NEW v1.2.0）
└── references/
    ├── hooks.md                  # GORM Hooks + 性能陷阱
    ├── raw-sql.md                # 原生 SQL 使用
    ├── indexing.md               # 索引规范（覆盖索引、前缀索引、函数索引、EXPLAIN）
    ├── concurrency.md            # 并发控制（乐观锁等）
    ├── testing.md                # 单元测试 + 软删除唯一约束坑
    ├── migration.md              # 数据库迁移
    ├── sharding.md               # 分库分表
    ├── observability.md          # 监控与可观测性
    ├── scopes.md                 # Scopes 完整参考（NEW v1.1.0）
    └── caching.md                # 缓存集成完整参考（NEW v1.1.0）
    └── base-model-pattern.md    # 泛型 BaseModel 规范与 Bug 修复记录（NEW v1.1.1）
assets/
└── dbcore/
    ├── base_model.go             # 修复版 BaseModel 源文件
    ├── query_builder.go          # 修复版 QueryBuilder 源文件
    └── transaction.go            # 事务管理器源文件
```

## analyze_gorm.py 检测规则（R1–R18）

架构：逐行规则（per-line loop）+ 全文件规则（full-file check）分离，去重按行号排序。

| 规则 | 级别 | 类型 | 说明 |
|------|------|------|------|
| R1: SELECT_STAR | WARN | 逐行 | Find 未指定字段 |
| R2: LARGE_OFFSET / DYNAMIC_OFFSET | ERROR/WARN | 逐行 | 大/动态 Offset 分页 |
| R3: N_PLUS_1 | ERROR | 逐行 | 循环内 DB 操作 |
| R4: STRUCT_UPDATES_ZERO_VALUE | WARN | 逐行 | struct Updates 丢零值 |
| R5: NO_CONTEXT | INFO | 逐行 | 未传 WithContext |
| R6: UNCHECKED_ERROR | WARN | 逐行 | 未检查 DB 错误 |
| R7: FIND_ALL_NO_LIMIT | WARN | 逐行 | Find 无 Where/Limit |
| R8: SLOW_OP_IN_TX | ERROR | 逐行 | 事务内 HTTP/Sleep 操作 |
| R9: LEADING_WILDCARD_LIKE | WARN | 逐行 | LIKE '%xxx%' 前导通配 |
| R10: LOOP_CREATE | ERROR | 逐行 | 循环内逐条 Create |
| R11: MISSING_PREPARE_STMT | INFO | 全文件 | 缺少 PrepareStmt 配置 |
| R12: MISSING_SKIP_DEFAULT_TX | INFO | 全文件 | 未使用 SkipDefaultTransaction |
| R13: SQL_INJECTION_RISK | ERROR | 逐行 | Raw SQL 字符串拼接 |
| R14: PLUCK_MULTI_COLUMN | WARN | 逐行 | Pluck 多列误用 |
| R15: MISSING_POOL_CONFIG | WARN | 全文件 | 未设置连接池 |
| R16: SOFT_DELETE_REMINDER | INFO | 逐行 | DeletedAt 软删除提醒 |
| R17: DB_IN_TX_BLOCK | ERROR | 逐行 | 事务内使用 db 而非 tx |
| R18: PHYSICAL_FOREIGN_KEY / FK_MIGRATION_NOT_DISABLED | ERROR/WARN | 逐行+全文件 | 物理外键约束 |

## 版本历史

| 版本 | 说明 |
|------|------|
| v1.2.0 | 新增 init_project.py 脚手架脚本；新增 assets/dbcore/（base_model.go / query_builder.go / transaction.go 修复版源文件）；SKILL.md 新增第0节「项目初始化」 |
| v1.1.1 | 新增 base-model-pattern.md（QueryBuilder args Bug 修复、软删除唯一索引、Find→Take、ListAll 限制、Page 去重、游标分页、多租户强制隔离、datatypes.JSON）；同步修复 query_builder.go / base_model.go / order.go |
| v1.1.0 | 新增 Scopes/多租户章节、缓存集成章节；新增 scope_gen.py；gen_model.py 支持 PostgreSQL；pool_advisor.py 增加健康检查代码输出；增强 hooks.md / indexing.md；testing.md 补充软删除唯一约束坑；analyze_gorm.py 重构为双循环架构 |
| v1.0.2 | 新增分库分表章节、监控可观测性章节；analyze_gorm.py 新增 R11–R18；新增 sharding.md、observability.md |
| v1.0.1 | 优化 description 措辞，通过 ClawHub 安全扫描 |
| v1.0.0 | 初始发布 |

## License

MIT

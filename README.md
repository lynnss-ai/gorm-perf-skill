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

## 目录结构

```
gorm-perf/
├── SKILL.md              # 主技能文件
├── scripts/
│   ├── analyze_gorm.py   # GORM 代码静态分析
│   ├── gen_model.py      # SQL → GORM struct 生成
│   ├── pool_advisor.py   # 连接池参数建议
│   ├── query_explain.py  # SQL 性能分析
│   ├── migration_gen.py  # 迁移 SQL 生成
│   └── bench_template.py # Benchmark 代码模板
└── references/
    ├── hooks.md          # GORM Hooks
    ├── raw-sql.md        # 原生 SQL 使用
    ├── indexing.md       # 索引定义规范
    ├── concurrency.md    # 并发控制（乐观锁等）
    ├── testing.md        # 单元测试
    └── migration.md      # 数据库迁移
```

## 安装使用

将整个 `gorm-perf/` 目录放入你的 Claude Skills 路径即可。

## License

MIT

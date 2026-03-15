---
name: gorm-expert
version: 1.4.0
description: >
  GORM v2 使用与性能优化专项技能。涵盖：代码审查/调试、慢查询/N+1优化、
  连接池配置、批量操作、事务管理（乐观锁/悲观锁/FOR UPDATE）、读写分离、
  SQL→GORM struct生成（MySQL/PostgreSQL）、数据库迁移、单元测试、
  Benchmark/pprof、分库分表(Sharding)、监控可观测性(Prometheus/OTel)、
  Scopes/多租户隔离、Redis缓存集成(Cache-Aside)、Session/goroutine安全、
  Clause系统(Upsert/RETURNING)、Association关联操作、Serializer/自定义类型、
  泛型BaseModel脚手架生成、QueryBuilder条件构建。
  适用："写个查询"、"数据库好慢"、"加索引"、"写struct"、"分库分表"、
  "Prometheus监控"、"链路追踪"、"Scope"、"多租户"、"缓存"、
  "Session累积"、"goroutine db"、"FOR UPDATE"、"Preload"、"加密字段"。
compatibility:
  runtime:
    - python >= 3.8
  binaries:
    - python3
  no_credentials: true
  disk_access:
    read_only:
      - analyze_gorm.py
      - gen_model.py
      - migration_gen.py
      - pool_advisor.py
      - query_explain.py
      - scope_gen.py
    write_on_explicit_flag:
      - bench_template.py   # 需用户传 --output <file>，默认输出到 stdout
      - init_project.py     # 需用户传 --output <dir>，支持 --dry-run 预览不写盘
---

# GORM 使用与性能优化 Skill

## 脚本工具（优先用脚本，减少 token 消耗）

> **使用规则**：用户提供代码/SQL/参数时，**先跑脚本**，只输出脚本结果 + 针对性说明。
>
> **权限说明**：所有脚本仅依赖 Python 3.8+，不调用任何外部 API 或凭证。
> 🔍 只读脚本（读 stdin 或用户指定文件，输出到 stdout，不写磁盘）
> 📝 写磁盘脚本（仅在用户明确传 `--output` 参数时写文件，建议先用 `--dry-run` 预览）

| 场景 | 脚本 | 权限 | 用法示例 |
|------|------|:----:|---------|
| 用户粘贴 Go 代码，问"有没有问题/如何优化" | `scripts/analyze_gorm.py` | 🔍 | `python3 scripts/analyze_gorm.py - <<< "代码"`（R1–R21，含 v2 专属检测） |
| 用户提供 CREATE TABLE SQL，需要生成 struct | `scripts/gen_model.py` | 🔍 | `echo "CREATE TABLE..." \| python3 scripts/gen_model.py -` |
| 用户问连接池配置，提供了 QPS/实例数等参数 | `scripts/pool_advisor.py` | 🔍 | `python3 scripts/pool_advisor.py --qps 500 --avg-latency-ms 20 --app-instances 4` |
| 用户提供 SQL，问性能/索引问题 | `scripts/query_explain.py` | 🔍 | `python3 scripts/query_explain.py "SELECT * FROM ..."` |
| 用户修改了 struct，问如何生成迁移 SQL | `scripts/migration_gen.py` | 🔍 | `python3 scripts/migration_gen.py old.go new.go --table users` |
| 用户粘贴 struct，问如何生成 Scope 函数 | `scripts/scope_gen.py` | 🔍 | `python3 scripts/scope_gen.py model.go --tenant --paginate` |
| 用户使用 PostgreSQL，需要生成 struct | `scripts/gen_model.py` | 🔍 | `python3 scripts/gen_model.py schema.sql --dialect pg` |
| 用户需要 benchmark / pprof 代码 | `scripts/bench_template.py` | 📝 | 默认输出到 stdout；写文件需加 `--output bench_test.go` |
| **新项目初始化**：用户想引入 dbcore 基础包到项目 | `scripts/init_project.py` | 📝 | 先 `--dry-run` 预览，再 `--output ./internal/dbcore` 写入 |

---

## 核心原则

1. **先测量，再优化** — 用 `db.Debug()` 或自定义 Logger 定位慢 SQL，再做针对性优化
2. **最小数据传输** — 只 Select 需要的字段，只查需要的行
3. **减少 Round-trip** — 批量操作、预加载 vs 懒加载权衡
4. **连接复用** — 正确配置连接池，避免频繁开关连接

---

## 0. 项目初始化（脚手架）

```bash
# 生成 dbcore 基础包（BaseModel + QueryBuilder + Transaction）
python3 scripts/init_project.py --output ./internal/dbcore          # 写入
python3 scripts/init_project.py --output ./internal/dbcore --dry-run # 仅预览
python3 scripts/init_project.py --output ./internal/dbcore --example # 含 OrderModel 示例

# 自定义包名
python3 scripts/init_project.py --output ./pkg/db --package mydb
```

生成后需补充 `autoFillID` / `autoFillIDBatch` 实现，推荐直接复制 `assets/dbcore/auto_id.go`（雪花算法版）。

DB 推荐初始化配置：

```go
db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{
    SkipDefaultTransaction:                   true,
    PrepareStmt:                              true,
    DisableForeignKeyConstraintWhenMigrating: true,
})
sqlDB, _ := db.DB()
sqlDB.SetMaxOpenConns(100)
sqlDB.SetMaxIdleConns(20)
sqlDB.SetConnMaxLifetime(time.Hour)
```

---

## 1. 初始化与连接池配置

```go
db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{
    SkipDefaultTransaction:                   true,  // 写性能 +30%
    PrepareStmt:                              true,  // SQL 编译缓存
    DisableForeignKeyConstraintWhenMigrating: true,  // 禁物理 FK
    Logger: logger.New(writer, logger.Config{
        SlowThreshold: 200 * time.Millisecond,
        LogLevel:      logger.Warn,
    }),
})
sqlDB, _ := db.DB()
sqlDB.SetMaxOpenConns(100)           // 最大连接数
sqlDB.SetMaxIdleConns(20)            // 空闲连接池（MaxOpen 的 20%）
sqlDB.SetConnMaxLifetime(time.Hour)  // 连接最大存活时间
sqlDB.SetConnMaxIdleTime(10 * time.Minute)
```

> 连接池参数建议：`python3 scripts/pool_advisor.py --qps 500 --avg-latency-ms 20`

---

## 2. 查询优化

### 2.1 只查需要的字段

```go
// ❌  SELECT * — 慢
db.Find(&users)
// ✅  SELECT id, name, email
db.Select("id", "name", "email").Find(&users)
// ✅  投影到小 struct，减少内存分配
db.Model(&User{}).Select("id", "name", "email").Find(&dtos)
```

### 2.2 避免 N+1 查询

```go
// ❌ N+1：循环内查 DB
for _, u := range users { db.Where("user_id=?", u.ID).Find(&u.Orders) }
// ✅ Preload：两次查询
db.Preload("Orders").Find(&users)
// ✅ Joins：一次 JOIN，适合需要按关联字段过滤
db.Joins("JOIN orders ON orders.user_id=users.id AND orders.status=?","paid").Find(&users)
// ✅ 带条件 Preload
db.Preload("Orders", "status=?", "paid").Preload("Orders.Items").Find(&users)
```

> Preload vs Joins 选型、`clause.Associations` 一次性预加载详见 `references/association.md`

### 2.3 分批处理大数据集

```go
// ❌ 一次性全部加载
db.Find(&allUsers)
// ✅ FindInBatches：每批 500 条
db.Model(&User{}).FindInBatches(&batch, 500, func(tx *gorm.DB, n int) error {
    process(batch); return nil
})
// ✅ 游标分页（大表推荐，避免 OFFSET 退化）
var lastID uint
for {
    var users []User
    db.Where("id > ?", lastID).Order("id").Limit(500).Find(&users)
    if len(users) == 0 { break }
    lastID = users[len(users)-1].ID
}
```

### 2.4 使用索引提示

```go
db.Clauses(hints.UseIndex("idx_user_name")).Find(&users)
db.Clauses(hints.ForceIndex("idx_created_at").ForOrderBy()).Find(&orders)
```

---

## 3. 写操作优化

### 3.1 批量插入

```go
// ❌ 逐条 INSERT（N 次 Round-trip）
for _, u := range users { db.Create(&u) }
// ✅ 批量插入，指定批次大小
db.CreateInBatches(&users, 200)
```

### 3.2 按需更新，不更新零值

```go
// ❌ struct Updates 忽略零值（int=0, bool=false）
db.Model(&user).Updates(User{Name: "new", Age: 0}) // Age=0 被忽略！
// ✅ map 明确指定字段
db.Model(&user).Updates(map[string]any{"name": "new", "age": 0})
// ✅ Select 限制字段 / Select("*") 强制更新所有字段含零值 / Omit 排除字段
db.Model(&user).Select("name", "email").Updates(&user)
db.Model(&user).Select("*").Updates(&user)
db.Model(&user).Omit("password").Updates(&user)
```

### 3.3 高效 Upsert

```go
db.Clauses(clause.OnConflict{
    Columns:   []clause.Column{{Name: "email"}},
    DoUpdates: clause.AssignmentColumns([]string{"name", "updated_at"}),
}).Create(&user)
db.Clauses(clause.OnConflict{DoNothing: true}).Create(&users) // 忽略冲突
```

---

## 4. 事务管理

```go
// 标准事务
err := db.Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&order).Error; err != nil { return err }
    return tx.Model(&stock).Update("qty", gorm.Expr("qty - ?", 1)).Error
})
// 嵌套事务（GORM 自动 SavePoint）
tx.Transaction(func(tx2 *gorm.DB) error { return tx2.Create(&log).Error })
// 悲观锁（FOR UPDATE）
db.Clauses(clause.Locking{Strength: "UPDATE"}).Where("id=?", id).First(&stock)
```

> 乐观锁、CAS、Savepoint、事务陷阱详见 `references/concurrency.md`

---

## 5. 读写分离

```go
db.Use(dbresolver.Register(dbresolver.Config{
    Sources:  []gorm.Dialector{mysql.Open(writeDSN)},
    Replicas: []gorm.Dialector{mysql.Open(read1DSN), mysql.Open(read2DSN)},
    Policy:   dbresolver.RandomPolicy{},
}).SetMaxOpenConns(50).SetMaxIdleConns(10))
// GORM 自动路由：Find/First → Replica；Create/Update/Delete → Source
db.Clauses(dbresolver.Write).Find(&user) // 强制走主库
```

---

## 6. Scopes 与多租户

```go
// 定义可复用 Scope
func ActiveUser(db *gorm.DB) *gorm.DB { return db.Where("status = ?", "active") }
func AgeOver(age int) func(*gorm.DB) *gorm.DB {
    return func(db *gorm.DB) *gorm.DB { return db.Where("age > ?", age) }
}
db.Scopes(ActiveUser, AgeOver(18)).Find(&users)

// 多租户行级隔离（强制注入，防越权）
func TenantScope(ctx context.Context) func(*gorm.DB) *gorm.DB {
    return func(db *gorm.DB) *gorm.DB {
        if tid, ok := ctx.Value("tenant_id").(uint); ok && tid > 0 {
            return db.Where("tenant_id = ?", tid)
        }
        return db.Where("1 = 0") // 无租户信息时拒绝
    }
}
db.WithContext(ctx).Scopes(TenantScope(ctx)).Find(&orders)
```

> 自动生成 Scope：`python3 scripts/scope_gen.py model.go --tenant --paginate`
> 完整示例详见 `references/scopes.md`

---

## 7. Model 设计规范

### 7.1 基础 Model

```go
type Order struct {
    gorm.Model
    UserID uint   `gorm:"not null;index"`        // 逻辑外键：只加索引，不加 CONSTRAINT
    Status string `gorm:"type:varchar(20);index"`
    Amount int64  `gorm:"not null;default:0"`
}
```

### 7.2 ❌ 禁止使用物理外键

```go
// ❌ 会在 AutoMigrate 时创建 FOREIGN KEY CONSTRAINT
type Order struct {
    User User `gorm:"foreignKey:UserID"` // 触发建 FK
}

// ✅ 显式禁止约束
type Order struct {
    UserID uint `gorm:"not null;index"`
    User   User `gorm:"foreignKey:UserID;constraint:false"`
}

// ✅ 全局禁止（推荐写在 gorm.Config 中）
db, _ := gorm.Open(dsn, &gorm.Config{
    DisableForeignKeyConstraintWhenMigrating: true,
})
```

物理外键的问题：分库分表不兼容、级联操作不可控、高并发性能瓶颈、导入迁移困难。
应用层校验替代方案详见 `references/base-model-pattern.md`。

---

## 8. 调试与性能分析

```go
db.Debug().Find(&users)  // 单次打印 SQL

// DryRun / ToSQL（不执行，只生成 SQL）
sql := db.ToSQL(func(tx *gorm.DB) *gorm.DB {
    return tx.Where("id > ?", 100).Limit(10).Find(&users)
})

// 慢查询 Logger 见第 1 节；pprof 见 references/observability.md
```

---

## 9. 常见坑与反模式

| 问题 | 错误写法 | 正确做法 |
|------|----------|----------|
| 忘记传 Context | `db.Find(&u)` | `db.WithContext(ctx).Find(&u)` |
| struct Updates 丢零值 | `db.Updates(User{Age:0})` | `db.Updates(map[string]any{"age":0})` |
| 大 OFFSET 分页 | `db.Offset(100000).Limit(20)` | 游标分页（Where id > lastID） |
| 未用索引的 Like | `WHERE name LIKE '%foo%'` | 前缀匹配 `LIKE 'foo%'` 或全文索引 |
| 事务内做耗时操作 | 事务 + HTTP 调用 | 事务只包 DB 操作，HTTP 调用放事务外 |
| 未检查 Error | `db.Find(&u); use u` | `if err := db.Find(&u).Error; err != nil` |
| 使用物理外键 | `gorm:"foreignKey:UserID"` 未加 `constraint:false` | 禁止 DB 级 FK，改用应用层校验 + `constraint:false` |

---

## 10. 缓存集成（Cache-Aside）

```go
func (r *UserRepo) GetUser(ctx context.Context, id uint) (*User, error) {
    key := fmt.Sprintf("user:%d", id)
    // 1. 读 Redis
    if val, err := r.rdb.Get(ctx, key).Bytes(); err == nil {
        var u User; json.Unmarshal(val, &u); return &u, nil
    }
    // 2. singleflight 防击穿 + 查 DB
    res, err, _ := r.group.Do(key, func() (any, error) {
        var u User
        if err := r.db.WithContext(ctx).First(&u, id).Error; err != nil {
            if errors.Is(err, gorm.ErrRecordNotFound) {
                r.rdb.Set(ctx, key, "null", time.Minute) // 防穿透
                return nil, ErrNotFound
            }
            return nil, err
        }
        // TTL 加随机抖动防雪崩
        ttl := 30*time.Minute + time.Duration(rand.Int63n(int64(6*time.Minute)))
        data, _ := json.Marshal(u)
        r.rdb.Set(ctx, key, data, ttl)
        return &u, nil
    })
    if err != nil { return nil, err }
    return res.(*User), nil
}
// 写操作：更新 DB → 删缓存（不更新缓存）
func (r *UserRepo) UpdateUser(ctx context.Context, u *User) error {
    if err := r.db.WithContext(ctx).Save(u).Error; err != nil { return err }
    r.rdb.Del(ctx, fmt.Sprintf("user:%d", u.ID))
    return nil
}
```

> 布隆过滤器防穿透、延迟双删、列表缓存版本号方案详见 `references/caching.md`

---

## 11. 分库分表（Sharding）

```go
db.Use(sharding.Register(sharding.Config{
    ShardingKey:         "user_id",
    NumberOfShards:      64,
    PrimaryKeyGenerator: sharding.PKSnowflake,
}, "orders"))

// 携带分片键 → 自动路由（高效）
db.Where("user_id = ?", userID).Find(&orders)
// 不含分片键 → 广播所有分片（慎用，生产接口禁止）
db.Where("status = ?", "pending").Find(&orders)
```

> 分片算法、双写迁移、跨分片查询详见 `references/sharding.md`

---

## 12. 监控与可观测性

```go
// Prometheus 指标
db.Use(prometheus.New(prometheus.Config{DBName: "myapp", RefreshInterval: 15}))
http.Handle("/metrics", promhttp.Handler())

// 慢查询 Logger（生产推荐）
db, _ = gorm.Open(dsn, &gorm.Config{
    Logger: logger.New(writer, logger.Config{
        SlowThreshold: 200 * time.Millisecond,
        LogLevel:      logger.Warn,
        IgnoreRecordNotFoundError: true,
    }),
})

// OpenTelemetry 链路追踪
db.Use(otelgorm.NewPlugin(otelgorm.WithDBName("myapp")))
db.WithContext(ctx).Find(&users) // ctx 需携带 trace context
```

> Prometheus 告警规则、Grafana 仪表盘、连接池健康检查、pprof 详见 `references/observability.md`

---

## 13. GORM v2 核心机制

### 13.1 Session 与 goroutine 安全

```go
// ❌ 条件累积 + goroutine 数据竞争
base := db.Where("tenant_id = ?", tid)
go func() { base.Find(&list1) }() // 危险！

// ✅ Session 隔离
go func() { base.Session(&gorm.Session{NewDB: true}).Find(&list1) }()

// ToSQL 调试（不执行）
sql := db.ToSQL(func(tx *gorm.DB) *gorm.DB {
    return tx.Where("id > ?", 100).Limit(10).Find(&users)
})
```

> Session 配置项、PrepareStmt 缓存、8 种陷阱详见 `references/session.md`

### 13.2 Clause 系统

```go
// FOR UPDATE（悲观锁）
db.Clauses(clause.Locking{Strength: "UPDATE"}).First(&stock)
// SKIP LOCKED（任务队列抢占）
db.Clauses(clause.Locking{Strength: "UPDATE", Options: "SKIP LOCKED"}).Limit(10).Find(&tasks)
// Upsert
db.Clauses(clause.OnConflict{Columns: []clause.Column{{Name: "email"}},
    DoUpdates: clause.AssignmentColumns([]string{"name", "updated_at"})}).Create(&user)
// RETURNING（PostgreSQL）
db.Clauses(clause.Returning{}).Create(&user)
```

> 完整 Clause 用法、自定义 Clause 表达式详见 `references/clause.md`

### 13.3 Association 关联操作

```go
db.Preload("Orders", "status = ?", "paid").Find(&users)
db.Preload(clause.Associations).Find(&users)           // 预加载所有关联
db.Omit(clause.Associations).Create(&user)             // 跳过所有关联写入
db.Model(&user).Association("Orders").Append(&order)   // 添加关联
db.Model(&user).Association("Orders").Replace(&order)  // 替换关联
```

> Preload vs Joins、级联控制、多对多详见 `references/association.md`

### 13.4 Serializer 与自定义类型

```go
type User struct {
    Tags    []string `gorm:"type:json;serializer:json"`   // JSON 自动序列化
    Phone   string   `gorm:"serializer:encrypted"`        // 自定义加密 Serializer
}
// 枚举/Money 类型实现 Scanner/Valuer 接口直接映射 DB 字段
```

> 完整实现、GormDataType 接口、选型建议详见 `references/serializer.md`

### 13.5 Error 处理规范（v2）

```go
// ✅ v2 正确写法
errors.Is(err, gorm.ErrRecordNotFound)
// ❌ v1 旧写法，v2 已移除（R21 检测）
gorm.IsRecordNotFoundError(err)
// Find 不触发 ErrRecordNotFound；First/Take/Last 触发
```

---

## 14. 进阶参考

详细专题见 `references/` 目录（按需加载，不要全量读入）：

| 文件 | 内容 | 触发时机 |
|------|------|---------|
| `references/hooks.md` | BeforeCreate/AfterUpdate 等 Hooks | 用户问 Hook 使用或性能 |
| `references/raw-sql.md` | Raw SQL / Scan / Rows | 用户需要绕开 ORM 写原生 SQL |
| `references/indexing.md` | GORM Tag 定义索引、复合索引 | 用户问索引如何在 struct 上定义 |
| `references/concurrency.md` | 乐观锁、悲观锁、CAS 原子更新 | 用户问并发冲突、超卖、转账等场景 |
| `references/testing.md` | sqlmock 单测、SQLite 集成测试、事务回滚隔离 | 用户问 GORM 代码怎么写单测 |
| `references/migration.md` | golang-migrate 规范、大表在线 DDL | 用户问数据库迁移、AutoMigrate 的生产使用 |
| `references/sharding.md` | 分库分表配置、分片算法、双写迁移 | 用户问分库分表、水平拆分 |
| `references/observability.md` | Prometheus、OpenTelemetry、慢查询告警 | 用户问监控、可观测性、链路追踪 |
| `references/scopes.md` | 可复用 Scope、分页、多租户行级隔离 | 用户问 Scope 用法、多租户设计 |
| `references/caching.md` | Cache-Aside、防击穿/雪崩/穿透、缓存一致性 | 用户问 GORM + Redis 缓存集成 |
| `references/base-model-pattern.md` | 泛型 BaseModel 常见 Bug、游标分页、多租户强制隔离 | 用户问 BaseModel 设计、QueryBuilder、分页优化 |
| `references/session.md` | Session 机制、goroutine 安全、条件累积防范 | 用户问 Session、db 复用、DryRun |
| `references/clause.md` | Clause 系统（Upsert/FOR UPDATE/RETURNING/自定义） | 用户问 FOR UPDATE、Upsert、RETURNING |
| `references/association.md` | Association 关联操作、Preload/Joins、级联控制 | 用户问关联加载、Preload、多对多 |
| `references/serializer.md` | Serializer、自定义数据类型（枚举/Money/加密） | 用户问字段序列化、自定义类型映射 |

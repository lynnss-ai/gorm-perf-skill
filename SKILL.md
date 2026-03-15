---
name: gorm-perf
description: >
  GORM 使用与性能优化专项技能。以下场景必须触发，不得跳过：
  (1) 任何涉及 GORM 的代码审查、编写、调试；
  (2) 数据库慢查询、N+1、全表扫描、索引失效等性能问题；
  (3) 连接池配置（SetMaxOpenConns 等）；
  (4) 批量插入/更新/查询优化；
  (5) 事务管理（乐观锁、悲观锁、CAS、FOR UPDATE）；
  (6) 读写分离（dbresolver）；
  (7) CREATE TABLE SQL 转 GORM struct；
  (8) 数据库迁移（golang-migrate、AutoMigrate、ALTER TABLE）；
  (9) GORM 单元测试（sqlmock、SQLite 内存库）；
  (10) Benchmark / pprof 性能分析代码生成。
  即使用户只说"写个查询"、"数据库好慢"、"怎么加索引"、"帮我写个 struct"也应触发。
---

# GORM 使用与性能优化 Skill

## 脚本工具（优先用脚本，减少 token 消耗）

> **使用规则**：用户提供代码/SQL/参数时，**先跑脚本**，只输出脚本结果 + 针对性说明，
> 不要重复输出 SKILL.md 中的通用内容。

| 场景 | 脚本 | 用法示例 |
|------|------|---------|
| 用户粘贴 Go 代码，问"有没有问题/如何优化" | `scripts/analyze_gorm.py` | `python3 scripts/analyze_gorm.py - <<< "代码"` |
| 用户提供 CREATE TABLE SQL，需要生成 struct | `scripts/gen_model.py` | `echo "CREATE TABLE..." \| python3 scripts/gen_model.py -` |
| 用户问连接池怎么配置，提供了 QPS/实例数等参数 | `scripts/pool_advisor.py` | `python3 scripts/pool_advisor.py --qps 500 --avg-latency-ms 20 --app-instances 4` |
| 用户提供 SQL，问性能/索引问题 | `scripts/query_explain.py` | `python3 scripts/query_explain.py "SELECT * FROM ..."` |
| 用户修改了 struct，问如何生成迁移 SQL | `scripts/migration_gen.py` | `python3 scripts/migration_gen.py old.go new.go --table users` |
| 用户需要 benchmark / pprof 代码 | `scripts/bench_template.py` | `python3 scripts/bench_template.py --func "Fn(db *gorm.DB, id uint)" 或 --scenario bulk_insert` |

---

## 核心原则

1. **先测量，再优化** — 用 `db.Debug()` 或自定义 Logger 定位慢 SQL，再做针对性优化
2. **最小数据传输** — 只 Select 需要的字段，只查需要的行
3. **减少 Round-trip** — 批量操作、预加载 vs 懒加载权衡
4. **连接复用** — 正确配置连接池，避免频繁开关连接

---

## 1. 初始化与连接池配置

```go
import (
    "gorm.io/driver/mysql"
    "gorm.io/gorm"
    "gorm.io/gorm/logger"
    "time"
)

db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{
    // 🚀 关闭默认事务（写操作不自动包 transaction），提升写性能约 30%
    SkipDefaultTransaction: true,
    // 🚀 开启 PreparedStatement 缓存，SQL 编译复用
    PrepareStmt: true,
    // 生产环境用 Warn 或 Error，避免日志 IO 拖慢请求
    Logger: logger.Default.LogMode(logger.Warn),
    // 禁止自动复数表名（按团队规范决定）
    NamingConvention: schema.NamingStrategy{SingularTable: true},
})

// 连接池配置（必做）
sqlDB, _ := db.DB()
sqlDB.SetMaxOpenConns(100)          // 最大连接数，根据 DB 规格设置
sqlDB.SetMaxIdleConns(20)           // 空闲连接池大小，一般为 MaxOpen 的 20%
sqlDB.SetConnMaxLifetime(time.Hour) // 连接最大存活时间，防止 DB 侧主动断开
sqlDB.SetConnMaxIdleTime(10 * time.Minute)
```

> **注意**：`SkipDefaultTransaction` 仅跳过单条 Create/Update/Delete 的隐式事务，
> 显式 `db.Transaction(func...)` 不受影响。

---

## 2. 查询优化

### 2.1 只查需要的字段

```go
// ❌ 慢：SELECT * — 传输、序列化所有字段
db.Find(&users)

// ✅ 快：SELECT id, name, email
db.Select("id", "name", "email").Find(&users)

// ✅ 更好：投影到小 struct，减少内存分配
type UserDTO struct {
    ID    uint
    Name  string
    Email string
}
db.Model(&User{}).Select("id", "name", "email").Find(&dtos)
```

### 2.2 避免 N+1 查询

```go
// ❌ N+1：先查 users，再对每个 user 查 orders（N 次额外查询）
db.Find(&users)
for _, u := range users {
    db.Where("user_id = ?", u.ID).Find(&u.Orders)
}

// ✅ Preload：两次查询解决，适合关联数据量不大的场景
db.Preload("Orders").Find(&users)

// ✅ Joins：一次 JOIN 查询，适合需要过滤关联字段的场景
db.Joins("JOIN orders ON orders.user_id = users.id AND orders.status = ?", "paid").
    Find(&users)

// ✅ 批量 Preload 并加条件
db.Preload("Orders", "status = ?", "paid").
   Preload("Orders.Items").
   Find(&users)
```

> **Preload vs Joins 选择**：
> - 需要过滤主表 by 关联字段 → `Joins`
> - 只是附带加载关联数据 → `Preload`
> - 关联数据量大（万级以上）→ 考虑手动分页查询

### 2.3 分批处理大数据集

```go
// ❌ 危险：一次性加载百万行进内存
db.Find(&allUsers)

// ✅ FindInBatches：每批 500 条
db.Model(&User{}).Where("status = ?", "active").
    FindInBatches(&batch, 500, func(tx *gorm.DB, batchNum int) error {
        for i := range batch {
            process(&batch[i])
        }
        return nil // 返回 error 则中止
    })

// ✅ 游标分页（大表推荐，避免 OFFSET 性能退化）
var lastID uint
for {
    var users []User
    db.Where("id > ?", lastID).Order("id").Limit(500).Find(&users)
    if len(users) == 0 { break }
    for _, u := range users { process(u) }
    lastID = users[len(users)-1].ID
}
```

### 2.4 使用索引提示

```go
import "gorm.io/hints"

// 强制使用指定索引
db.Clauses(hints.UseIndex("idx_user_name")).Find(&users)
db.Clauses(hints.ForceIndex("idx_created_at").ForOrderBy()).Find(&orders)
```

---

## 3. 写操作优化

### 3.1 批量插入

```go
// ❌ 慢：逐条 INSERT，N 次 Round-trip
for _, u := range users {
    db.Create(&u)
}

// ✅ 批量 INSERT，单次 Round-trip
db.Create(&users) // GORM 自动批量（默认无分批）

// ✅ 指定批次大小，防止单条 SQL 过大
db.CreateInBatches(&users, 200)
```

### 3.2 按需更新，不更新零值

```go
// ❌ Updates with struct 会跳过零值字段，可能漏更新
db.Model(&user).Updates(User{Name: "new", Age: 0}) // Age=0 被忽略！

// ✅ 用 map 明确指定需要更新的字段
db.Model(&user).Updates(map[string]any{
    "name": "new",
    "age":  0,
})

// ✅ 精确更新单字段
db.Model(&user).Update("name", "new")

// ✅ Select 限制只更新指定字段（防止意外覆盖）
db.Model(&user).Select("name", "email").Updates(&user)
```

### 3.3 高效 Upsert

```go
// MySQL
db.Clauses(clause.OnConflict{
    Columns:   []clause.Column{{Name: "email"}},
    DoUpdates: clause.AssignmentColumns([]string{"name", "updated_at"}),
}).Create(&user)

// 忽略冲突
db.Clauses(clause.OnConflict{DoNothing: true}).Create(&users)
```

---

## 4. 事务管理

```go
// ✅ 标准事务：自动 rollback on error
err := db.Transaction(func(tx *gorm.DB) error {
    if err := tx.Create(&order).Error; err != nil {
        return err // 触发 rollback
    }
    if err := tx.Model(&stock).Update("qty", gorm.Expr("qty - ?", 1)).Error; err != nil {
        return err
    }
    return nil // 触发 commit
})

// ✅ 手动事务（跨函数传递 tx）
tx := db.Begin()
defer func() {
    if r := recover(); r != nil { tx.Rollback() }
}()
// ... 使用 tx 操作 ...
tx.Commit()

// ⚠️ 大批量写不需要事务一致性时，使用 Session 临时禁用
db.Session(&gorm.Session{SkipDefaultTransaction: true}).CreateInBatches(&records, 500)
```

---

## 5. 读写分离

```go
import "gorm.io/plugin/dbresolver"

db.Use(dbresolver.Register(dbresolver.Config{
    Sources:  []gorm.Dialector{mysql.Open(writeDSN)},
    Replicas: []gorm.Dialector{mysql.Open(read1DSN), mysql.Open(read2DSN)},
    Policy:   dbresolver.RandomPolicy{},
    // 连接池可以对 source/replica 分开配置
}).SetMaxOpenConns(50).SetMaxIdleConns(10))

// GORM 自动路由：Find/First → Replica，Create/Update/Delete → Source
// 强制走主库（刚写完立即读的场景）：
db.Clauses(dbresolver.Write).Find(&user)
```

---

## 6. Model 设计规范

```go
// 嵌入 gorm.Model 获取 ID/CreatedAt/UpdatedAt/DeletedAt（软删除）
type Order struct {
    gorm.Model
    UserID uint   `gorm:"not null;index"`       // 外键加索引
    Status string `gorm:"type:varchar(20);index"` // 状态字段加索引
    Amount int64  `gorm:"not null;default:0"`
}

// 复合索引
type Log struct {
    gorm.Model
    UserID    uint      `gorm:"index:idx_user_time"` // 复合索引
    CreatedAt time.Time `gorm:"index:idx_user_time"` // 复合索引
}

// 软删除：DeletedAt 字段存在时，Delete 只设置时间戳
// 查询自动带上 WHERE deleted_at IS NULL
// 彻底删除：db.Unscoped().Delete(&user)
```

---

## 7. 调试与性能分析

```go
// 单次查询打印 SQL
db.Debug().Find(&users)

// 全局 Logger（开发环境）
db, _ = gorm.Open(dsn, &gorm.Config{
    Logger: logger.Default.LogMode(logger.Info),
})

// 自定义慢查询 Logger（生产推荐）
newLogger := logger.New(
    log.New(os.Stdout, "\r\n", log.LstdFlags),
    logger.Config{
        SlowThreshold:             200 * time.Millisecond, // 超过 200ms 打印
        LogLevel:                  logger.Warn,
        IgnoreRecordNotFoundError: true,
        Colorful:                  false,
    },
)

// DryRun 模式：只生成 SQL，不执行（用于调试复杂查询）
stmt := db.Session(&gorm.Session{DryRun: true}).Find(&users).Statement
fmt.Println(stmt.SQL.String()) // 打印最终 SQL
fmt.Println(stmt.Vars)         // 打印参数
```

---

## 8. 常见坑与反模式

| 问题 | 错误写法 | 正确做法 |
|------|----------|----------|
| 忘记传 Context | `db.Find(&u)` | `db.WithContext(ctx).Find(&u)` |
| struct Updates 丢零值 | `db.Updates(User{Age:0})` | `db.Updates(map[string]any{"age":0})` |
| 大 OFFSET 分页 | `db.Offset(100000).Limit(20)` | 游标分页（Where id > lastID） |
| 未用索引的 Like | `WHERE name LIKE '%foo%'` | 前缀匹配 `LIKE 'foo%'` 或全文索引 |
| 事务内做耗时操作 | 事务 + HTTP 调用 | 事务只包 DB 操作，HTTP 调用放事务外 |
| 未检查 Error | `db.Find(&u); use u` | `if err := db.Find(&u).Error; err != nil` |
| 连接池未配置 | 默认无上限 | 明确设置 MaxOpenConns / MaxIdleConns |

---

## 9. 进阶参考

详细专题见 `references/` 目录（按需加载，不要全量读入）：

| 文件 | 内容 | 触发时机 |
|------|------|---------|
| `references/hooks.md` | BeforeCreate/AfterUpdate 等 Hooks | 用户问 Hook 使用或性能 |
| `references/raw-sql.md` | Raw SQL / Scan / Rows | 用户需要绕开 ORM 写原生 SQL |
| `references/indexing.md` | GORM Tag 定义索引、复合索引 | 用户问索引如何在 struct 上定义 |
| `references/concurrency.md` | 乐观锁、悲观锁、CAS 原子更新 | 用户问并发冲突、超卖、转账等场景 |
| `references/testing.md` | sqlmock 单测、SQLite 集成测试、事务回滚隔离 | 用户问 GORM 代码怎么写单测 |
| `references/migration.md` | golang-migrate 规范、大表在线 DDL | 用户问数据库迁移、AutoMigrate 的生产使用 |

---
name: gorm-perf
version: 1.3.1
description: >
  GORM 使用与性能优化专项技能，覆盖以下场景：
  (1) GORM 代码审查、编写、调试；
  (2) 数据库慢查询、N+1、全表扫描、索引失效等性能问题；
  (3) 连接池配置（SetMaxOpenConns 等）；
  (4) 批量插入/更新/查询优化；
  (5) 事务管理（乐观锁、悲观锁、CAS、FOR UPDATE）；
  (6) 读写分离（dbresolver）；
  (7) CREATE TABLE SQL 转 GORM struct；
  (8) 数据库迁移（golang-migrate、AutoMigrate、ALTER TABLE）；
  (9) GORM 单元测试（sqlmock、SQLite 内存库）；
  (10) Benchmark / pprof 性能分析代码生成；
  (11) 分库分表（Sharding）配置与分片键设计；
  (12) 监控与可观测性（Prometheus 指标、慢查询告警、OpenTelemetry 链路追踪）；
  (13) Scopes 可复用查询条件与多租户行级隔离；
  (14) Redis Cache-Aside 缓存集成（防击穿、防雪崩、缓存一致性）；
  (15) GORM v2 Session 机制与 goroutine 安全；
  (16) Clause 系统（Upsert、FOR UPDATE、RETURNING）；
  (17) Association 关联操作（Preload/Joins/Append/Replace）；
  (18) Serializer 与自定义数据类型（枚举、Money、加密字段）。
  适用于用户提到"写个查询"、"数据库好慢"、"怎么加索引"、"帮我写个 struct"、
  "分库分表怎么配"、"GORM 怎么接 Prometheus"、"链路追踪"、
  "怎么写 Scope"、"多租户怎么隔离"、"GORM 怎么加缓存"、"Session 条件累积"、"goroutine 里用 db"、
  "FOR UPDATE"、"RETURNING"、"Preload 和 Joins"、
  "自定义类型映射"、"字段加密"等场景。
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

新项目引入 `dbcore` 基础包（`BaseModel` + `QueryBuilder` + `Transaction`）时，
直接用脚本生成，无需手动复制：

```bash
# 生成到指定目录，默认 package 名 dbcore
python3 scripts/init_project.py --output ./internal/dbcore

# 自定义 package 名
python3 scripts/init_project.py --output ./pkg/db --package mydb

# 预览模式（不写入文件）
python3 scripts/init_project.py --output ./internal/dbcore --dry-run

# 强制覆盖已存在文件
python3 scripts/init_project.py --output ./internal/dbcore --force
```

生成的三个文件：

| 文件 | 说明 |
|------|------|
| `base_model.go` | 泛型 BaseModel，含 CRUD / 分页 / 游标分页，已修复 Find→Take、ListAll 上限、Page 去重 |
| `query_builder.go` | 链式查询条件构建器，已修复 InStrings/InInts args 顺序 Bug，新增 OrGroup |
| `transaction.go` | 事务管理器，支持嵌套事务（GORM SavePoint） |

生成后需要在同包内实现两个辅助函数（根据项目 ID 策略自行实现）：

```go
// auto_id.go（需自行创建）
package dbcore

import "github.com/bwmarrin/snowflake"

var node, _ = snowflake.NewNode(1)

func autoFillID(v any) {
    // 用反射检查并填充 ID 字段（string 类型，为空时生成雪花 ID）
    // 具体实现见 references/base-model-pattern.md 附录
}

func autoFillIDBatch[T any](v []*T) {
    for _, item := range v {
        autoFillID(item)
    }
}
```

初始化 DB 时推荐配置（详见第 1 节）：

```go
db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{
    SkipDefaultTransaction:                   true,  // 写性能 +30%
    PrepareStmt:                              true,  // SQL 编译缓存
    DisableForeignKeyConstraintWhenMigrating: true,  // 禁止物理外键
})
```

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

// ✅ Select("*") 强制更新所有字段（包括零值），v2 新增
db.Model(&user).Select("*").Updates(&user)

// ✅ Omit 排除特定字段不更新
db.Model(&user).Omit("password", "created_at").Updates(&user)
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

## 6. Scopes 与多租户

### 6.1 可复用查询条件（Scopes）

```go
// 定义 Scope：签名固定为 func(*gorm.DB) *gorm.DB
func ActiveUser(db *gorm.DB) *gorm.DB {
    return db.Where("status = ?", "active")
}

func AgeOver(age int) func(*gorm.DB) *gorm.DB {
    return func(db *gorm.DB) *gorm.DB {
        return db.Where("age > ?", age)
    }
}

// 组合使用
db.Scopes(ActiveUser, AgeOver(18)).Order("created_at DESC").Find(&users)
```

> **自动生成 Scope**：`python3 scripts/scope_gen.py model.go --tenant --paginate`

### 6.2 多租户行级隔离

```go
// 从 context 提取 tenant_id，注入所有查询
func TenantScope(ctx context.Context) func(*gorm.DB) *gorm.DB {
    return func(db *gorm.DB) *gorm.DB {
        tenantID, ok := ctx.Value("tenant_id").(uint)
        if !ok || tenantID == 0 {
            return db.Where("1 = 0") // 无租户信息时拒绝访问
        }
        return db.Where("tenant_id = ?", tenantID)
    }
}

// Service 层统一使用
db.WithContext(ctx).Scopes(TenantScope(ctx)).Find(&orders)
```

> 完整示例（分页 Scope、软删除 Scope、版本号 Scope）见 `references/scopes.md`

---

## 7. Model 设计规范

### 7.1 基础 Model

```go
// 嵌入 gorm.Model 获取 ID/CreatedAt/UpdatedAt/DeletedAt（软删除）
type Order struct {
    gorm.Model
    UserID uint   `gorm:"not null;index"`        // 逻辑外键：只加索引，不加 CONSTRAINT
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

### 7.2 ❌ 禁止使用物理外键（Foreign Key Constraint）

> **团队规范**：禁止在数据库层面创建 `FOREIGN KEY CONSTRAINT`，一律采用**逻辑外键（应用层约束）**。

**物理外键的问题：**

| 问题 | 说明 |
|------|------|
| 分库分表不兼容 | 跨分片的 FK 约束无法建立，迁移到 Sharding 时必须删除 |
| 级联操作不可控 | `ON DELETE CASCADE` 可能引发意外批量删除，难以追踪 |
| 性能开销 | 每次写操作都触发 FK 校验，高并发场景下成为瓶颈 |
| 导入/迁移困难 | 大批量数据导入必须严格按依赖顺序执行，运维复杂 |
| 微服务不友好 | 跨服务数据无法建立 DB 级别约束 |

**GORM 中禁止物理外键的写法：**

```go
// ❌ 错误：会在 AutoMigrate 时创建 FOREIGN KEY CONSTRAINT
type Order struct {
    gorm.Model
    UserID uint
    User   User `gorm:"foreignKey:UserID"`  // 会触发建 FK
}

// ✅ 正确：只建索引，不建 FK 约束
type Order struct {
    gorm.Model
    UserID uint `gorm:"not null;index"` // 逻辑外键，仅索引
    // 不声明 User 关联字段，或使用 constraint:false 禁止建约束
}

// ✅ 如果必须保留关联查询，显式禁止创建约束
type Order struct {
    gorm.Model
    UserID uint `gorm:"not null;index"`
    User   User `gorm:"foreignKey:UserID;constraint:false"` // 禁止建 FK
}
```

**AutoMigrate 全局禁止 FK：**

```go
// 如果使用 AutoMigrate，禁用所有 FK 创建
db.DisableForeignKeyConstraintWhenMigrating = true

// 或在 gorm.Config 中配置
db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{
    DisableForeignKeyConstraintWhenMigrating: true, // 全局禁止 FK 约束
})
```

**应用层约束替代方案：**

```go
// 写入时在 Service 层校验引用完整性
func (s *OrderService) CreateOrder(ctx context.Context, order *Order) error {
    // 应用层校验 user 存在
    var count int64
    if err := s.db.WithContext(ctx).Model(&User{}).
        Where("id = ?", order.UserID).Count(&count).Error; err != nil {
        return err
    }
    if count == 0 {
        return ErrUserNotFound
    }
    return s.db.WithContext(ctx).Create(order).Error
}
```

---

## 8. 调试与性能分析

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

> 详细示例见 `references/caching.md`，以下为核心模式。

```go
func (r *UserRepo) GetUser(ctx context.Context, id uint) (*User, error) {
    key := fmt.Sprintf("user:%d", id)

    // 1. 读 Redis
    if val, err := r.rdb.Get(ctx, key).Bytes(); err == nil {
        var u User
        json.Unmarshal(val, &u)
        return &u, nil
    }

    // 2. 查 DB（singleflight 防击穿）
    res, err, _ := r.group.Do(key, func() (any, error) {
        var u User
        if err := r.db.WithContext(ctx).First(&u, id).Error; err != nil {
            if errors.Is(err, gorm.ErrRecordNotFound) {
                r.rdb.Set(ctx, key, "null", time.Minute) // 防穿透：缓存空值
                return nil, ErrNotFound
            }
            return nil, err
        }
        data, _ := json.Marshal(u)
        // TTL 加随机抖动，防雪崩
        ttl := 30*time.Minute + time.Duration(rand.Int63n(int64(6*time.Minute)))
        r.rdb.Set(ctx, key, data, ttl)
        return &u, nil
    })
    if err != nil { return nil, err }
    return res.(*User), nil
}

// 写操作：更新 DB → 删缓存（不更新缓存，避免并发不一致）
func (r *UserRepo) UpdateUser(ctx context.Context, u *User) error {
    if err := r.db.WithContext(ctx).Save(u).Error; err != nil { return err }
    r.rdb.Del(ctx, fmt.Sprintf("user:%d", u.ID))
    return nil
}
```

> 布隆过滤器防穿透、延迟双删、列表缓存版本号方案详见 `references/caching.md`

---

## 11. 分库分表（Sharding）

> 详细配置见 `references/sharding.md`，以下为快速索引。

```go
import "gorm.io/sharding"

db.Use(sharding.Register(sharding.Config{
    ShardingKey:         "user_id",
    NumberOfShards:      64,
    PrimaryKeyGenerator: sharding.PKSnowflake,
}, "orders")) // 对 orders 表分片

// 查询自动路由到对应分片
db.Where("user_id = ?", 100).Find(&orders)

// 广播查询（跨分片，慎用）
db.Where("status = ?", "pending").Find(&orders)
```

**分片键选择原则**：
- 高基数字段（user_id / tenant_id），避免数据倾斜
- 查询条件中出现频率最高的字段
- 避免跨分片 JOIN 和聚合

> 双写迁移、自定义分片算法、跨分片查询详见 `references/sharding.md`

---

## 12. 监控与可观测性

> 详细配置见 `references/observability.md`，以下为快速索引。

### 12.1 Prometheus 指标

```go
import "github.com/go-gorm/prometheus"

db.Use(prometheus.New(prometheus.Config{
    DBName:          "myapp",
    RefreshInterval: 15,              // 每 15s 刷新指标
    MetricsCollector: []prometheus.MetricsCollector{
        &prometheus.MySQL{VariableNames: []string{"Threads_running"}},
    },
}))
// 自动暴露: gorm_dbstats_max_open_connections, idle_connections, in_use 等
```

### 12.2 慢查询回调

```go
db.Callback().Query().After("gorm:query").Register("slowlog", func(db *gorm.DB) {
    if db.Statement.SQL.String() != "" {
        elapsed := db.Statement.DB.(*gorm.DB).Statement.BuildCondition
        // 超过阈值则告警
    }
})

// 更简洁：直接用自定义 Logger
newLogger := logger.New(writer, logger.Config{
    SlowThreshold: 200 * time.Millisecond,
    LogLevel:      logger.Warn,
})
```

### 12.3 OpenTelemetry 链路追踪

```go
import "github.com/uptrace/opentelemetry-go-extra/otelgorm"

if err := db.Use(otelgorm.NewPlugin(
    otelgorm.WithDBName("myapp"),
)); err != nil {
    panic(err)
}
// 每次 DB 操作自动产生 span，关联到父 trace
db.WithContext(ctx).Find(&users) // ctx 需携带 trace context
```

> Grafana 仪表盘配置、连接池健康检查、告警规则详见 `references/observability.md`

---

## 13. GORM v2 核心机制

### 14.1 Session 与 goroutine 安全

```go
// ❌ 危险：链式条件累积，跨 goroutine 数据竞争
base := db.Where("tenant_id = ?", tenantID)
go func() { base.Find(&list1) }()  // 数据竞争！
go func() { base.Find(&list2) }()  // 数据竞争！

// ✅ 每次查询 Session 隔离
base := db.Where("tenant_id = ?", tenantID)
go func() { base.Session(&gorm.Session{NewDB: true}).Find(&list1) }()
go func() { base.Session(&gorm.Session{NewDB: true}).Find(&list2) }()

// ✅ ToSQL 调试（不执行）
sql := db.ToSQL(func(tx *gorm.DB) *gorm.DB {
    return tx.Where("id > ?", 100).Limit(10).Find(&users)
})
```

> 完整 Session 配置项、PrepareStmt 缓存清理、陷阱汇总见 `references/session.md`

### 14.2 Clause 系统

```go
// FOR UPDATE（库存/余额扣减）
db.Clauses(clause.Locking{Strength: "UPDATE"}).First(&stock)

// SKIP LOCKED（任务队列抢占）
db.Clauses(clause.Locking{Strength: "UPDATE", Options: "SKIP LOCKED"}).
    Limit(10).Find(&tasks)

// Upsert（OnConflict）
db.Clauses(clause.OnConflict{
    Columns:   []clause.Column{{Name: "email"}},
    DoUpdates: clause.AssignmentColumns([]string{"name", "updated_at"}),
}).Create(&user)

// RETURNING（PostgreSQL）
db.Clauses(clause.Returning{}).Create(&user) // 自动填充 DB 生成的字段
```

> Clause 完整用法、自定义 Clause 表达式见 `references/clause.md`

### 14.3 Association 关联操作

```go
// 禁止物理外键，关联字段加 constraint:false
type User struct {
    Orders []Order `gorm:"foreignKey:UserID;constraint:false"`
}

// Preload（推荐：两次查询，内存友好）
db.Preload("Orders", "status = ?", "paid").Find(&users)
db.Preload(clause.Associations).Find(&users) // 预加载所有关联

// 精确控制级联写入
db.Omit(clause.Associations).Create(&user)  // 只写 user，跳过所有关联
db.Select("Orders").Create(&user)            // 只写 user + Orders

// Association 操作
db.Model(&user).Association("Orders").Append(&order)  // 添加关联
db.Model(&user).Association("Orders").Replace(&order) // 替换所有关联
db.Model(&user).Association("Orders").Delete(&order)  // 移除关联
```

> 完整示例、多对多、软删除处理见 `references/association.md`

### 14.4 Serializer 与自定义类型

```go
// JSON 序列化（推荐替代 string 存 JSON）
type User struct {
    Tags    []string `gorm:"type:json;serializer:json"`
    Address Address  `gorm:"type:json;serializer:json"`
}

// 自定义类型（枚举 / Money / 加密字段）
type OrderStatus int8
func (s OrderStatus) Value() (driver.Value, error) { return int64(s), nil }
func (s *OrderStatus) Scan(v interface{}) error { *s = OrderStatus(v.(int64)); return nil }

// 自定义加密 Serializer
type User struct {
    Phone string `gorm:"serializer:encrypted"` // 存储时自动加密，读取时自动解密
}
```

> 完整实现（Money 类型、GormDataType 接口、选型建议）见 `references/serializer.md`

### 14.5 Error 处理规范（v2）

```go
// ✅ v2 正确写法
if errors.Is(err, gorm.ErrRecordNotFound) { }

// ❌ v1 旧写法，v2 已移除（analyze_gorm.py R21 会检测）
if gorm.IsRecordNotFoundError(err) { }

// Find 不触发 ErrRecordNotFound（返回空切片）
// First / Take / Last 触发 ErrRecordNotFound
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

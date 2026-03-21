# GORM Gen v2 代码生成参考

> GORM Gen 是 GORM 官方代码生成工具，通过编译期生成类型安全的查询 API，比传统 GORM 链式调用更安全、自动完成更强。本文覆盖 Gen v2 的完整用法。

---

## 1. 概述与为什么使用 Gen

### 传统 GORM vs Gen

```go
// 传统 GORM：运行时错误，无自动完成
var users []User
db.Where("name = ?", "Alice").Find(&users)  // 运行时才发现拼写错误

// GORM Gen：编译期安全，IDE 智能提示
query := gen.NewQuery(db)
users, err := query.User.Where(query.User.Name.Eq("Alice")).Find()
// 拼写错误 → 编译失败，IDE 有自动完成
```

**Gen 的优势：**
- 类型安全（编译期检查）
- 完整的 IDE 自动完成
- 性能优化（生成后无反射开销）
- 避免 N+1（显式 Preload）
- 运行时无外部依赖

### 何时使用 Gen

| 场景 | 推荐 | 备注 |
|------|------|------|
| 大型项目（表 20+ 个） | ✅ Gen | 类型安全收益大 |
| 快速原型 / Demo | ❌ 传统 | 代码生成维护成本 |
| 动态 SQL（表名/列名变量） | ❌ 传统 | Gen 编译期固定 |
| 复杂自定义查询 | ✅ Gen | 接口注解语法更强大 |
| 生成 API 文档 | ✅ Gen | 查询方法签名明确 |

---

## 2. 安装与配置

### 安装

```bash
go get -u gorm.io/gen
go get -u gorm.io/datatypes  # 额外数据类型支持
```

### 初始化生成器

```go
// main.go（或单独的 gen/gen.go）
package main

import "gorm.io/gen"

func main() {
    // 连接到数据库
    db := setupDB()  // 返回 *gorm.DB

    // 创建生成器
    g := gen.NewGenerator(gen.Config{
        OutPath:      "./internal/model",      // 生成代码输出目录
        OutFile:      "query.gen.go",          // 查询 API 文件名
        ModelPkgPath: "model",                 // Model 包名
        Mode:         gen.WithDefaultQuery |
                      gen.WithQueryInterface,  // 生成接口版本
        FieldNullable:       true,             // 可空字段生成 *Type
        FieldCoverable:      false,            // 是否生成 Cover() 方法
        FieldSignable:       false,            // 是否生成 Signable 接口
        FieldWithIndexTag:   true,             // 保留 index tag
        FieldWithTypeTag:    true,             // 保留 type tag
    })

    // 设置目标数据库
    g.UseDB(db)

    // 运行生成
    g.Execute()
}

// go:generate go run gen/gen.go
```

### 目录结构

```
project/
├── gen/
│   └── gen.go                  # 生成器入口（配置代码）
├── internal/
│   └── model/
│       ├── user.go             # 生成的 Model
│       ├── order.go
│       ├── query.gen.go        # 生成的查询 API（主文件）
│       └── gen.go              # 生成的初始化代码
└── main.go
```

### go:generate 集成

```bash
# 在项目根目录执行生成
go generate ./...

# 或手动
cd gen && go run gen.go
```

---

## 3. 从数据库表生成 Model

### GenerateAllTable（全表生成）

```go
func main() {
    db := setupDB()
    g := gen.NewGenerator(gen.Config{OutPath: "./internal/model"})
    g.UseDB(db)

    // 生成所有表的 Model 和查询 API
    g.GenerateAllTable()

    g.Execute()
}
```

**生成结果：**
- `user.go`, `order.go` 等 Model 文件（每个表一个）
- `query.gen.go` 包含所有查询方法
- `gen.go` 包含初始化代码

### GenerateModel（选择性生成）

```go
func main() {
    db := setupDB()
    g := gen.NewGenerator(gen.Config{OutPath: "./internal/model"})
    g.UseDB(db)

    // 只生成指定表
    g.GenerateModel("users", "orders", "products")

    g.Execute()
}
```

### 数据库字段类型映射

```go
// 自动映射规则（支持 SQL NULL 类型）
/*
MySQL              → Go Type
------------------------------------
INT                → int / int64
VARCHAR/TEXT       → string
TIMESTAMP/DATETIME → time.Time
BOOLEAN            → bool
DECIMAL            → decimal.Decimal（需导入 gorm.io/datatypes）
JSON               → datatypes.JSONMap / datatypes.JSONQuery
BIGINT             → int64
FLOAT/DOUBLE       → float64
DATE               → time.Time
*/

// 字段可空时生成指针
type User struct {
    ID       int64     // NOT NULL → 非指针
    Name     string    // NOT NULL
    Phone    *string   // NULL → 指针
    DeletedAt *time.Time
}
```

### 自定义字段类型

```go
g := gen.NewGenerator(config)
g.UseDB(db)

// 为特定列指定 Go 类型
fieldOpts := []gen.FieldOption{
    gen.FieldType("users", "metadata", "datatypes.JSONMap"),
    gen.FieldType("users", "status", "UserStatus"),  // 自定义枚举类型
}

g.GenerateModel("users", fieldOpts...)
g.Execute()
```

---

## 4. 从现有 Model 生成查询 API

### ApplyBasic（导入已有结构体）

```go
// 如果已有手写 Model，可只生成查询 API
func main() {
    db := setupDB()
    g := gen.NewGenerator(config)
    g.UseDB(db)

    // 定义已有的 Model 结构体
    type User struct {
        ID        int64
        Name      string
        Email     string
        CreatedAt time.Time
    }

    type Order struct {
        ID     int64
        UserID int64
        Amount decimal.Decimal
    }

    // 只生成查询 API（不覆盖 Model）
    g.ApplyBasic(User{}, Order{})

    g.Execute()
}
```

**适用场景：**
- 已有手写 Model，无需重新生成
- Model 有特殊逻辑无法通过生成器配置
- 逐步迁移传统 GORM 代码

---

## 5. 自定义查询方法

### 接口注解语法

```go
type User struct {
    ID    int64
    Name  string
    Email string
    Age   int
}

// @@table("users")
// SELECT * FROM users WHERE name = @name
// @param name string
// int64: user_id
func (q *queryUser) SelectByName(name string) (int64, error) {
    return q.WithContext(context.Background()).
        Where(q.Name.Eq(name)).
        Pluck(q.ID)
}

// @@table("users")
// @param age int
// []*gen.T: *User
func (q *queryUser) SelectByAgeRange(age int) ([]*gen.T, error) {
    return q.Where(q.Age.Gte(age)).Find()
}
```

### 支持的返回类型

```go
// 1. gen.T（Model 类型）
func (q *queryUser) FindOne(id int64) (*gen.T, error)  // *User

// 2. []*gen.T（Model 列表）
func (q *queryUser) FindAll() ([]*gen.T, error)  // []*User

// 3. gen.RowsAffected（影响行数）
func (q *queryUser) DeleteByID(id int64) (gen.RowsAffected, error)

// 4. error（只返回错误）
func (q *queryUser) Verify(id int64) error

// 5. 基本类型（需 Pluck）
func (q *queryUser) CountByStatus(status string) (int64, error)

// 6. 自定义结构体
type UserStat struct {
    ID    int64
    Count int64
}
// []*UserStat: 列表
func (q *queryUser) StatsGroupByID() ([]*UserStat, error)
```

### 条件生成方法

```go
// 生成的查询方法带完整的链式 API
func (q *queryUser) GetActiveUsers() ([]*gen.T, error) {
    return q.Where(
        q.Status.Eq("active"),
        q.DeletedAt.IsNull(),
    ).Order(q.CreatedAt.Desc()).Find()
}

// 动态条件拼接
func (q *queryUser) SearchUsers(name, email string, minAge int) ([]*gen.T, error) {
    query := q

    if name != "" {
        query = query.Where(q.Name.Like("%" + name + "%"))
    }
    if email != "" {
        query = query.Where(q.Email.Eq(email))
    }
    if minAge > 0 {
        query = query.Where(q.Age.Gte(minAge))
    }

    return query.Find()
}
```

---

## 6. 动态条件查询

### gen.Condition 构建动态 WHERE

```go
// 使用 gen.Condition 灵活构建条件
func (q *queryUser) FindByFilter(filter UserFilter) ([]*gen.T, error) {
    var conds []gen.Condition

    if filter.Name != "" {
        conds = append(conds, q.Name.Eq(filter.Name))
    }
    if filter.MinAge > 0 {
        conds = append(conds, q.Age.Gte(filter.MinAge))
    }
    if filter.Status != "" {
        conds = append(conds, q.Status.Eq(filter.Status))
    }

    return q.Where(conds...).Find()
}

// OR 条件
func (q *queryUser) FindByNameOrEmail(name, email string) ([]*gen.T, error) {
    return q.Where(
        q.Or(
            q.Name.Eq(name),
            q.Email.Eq(email),
        ),
    ).Find()
}

// 复杂条件组合
func (q *queryUser) FindComplex(age int, status string) ([]*gen.T, error) {
    return q.Where(
        q.Age.Gte(age),
        q.Or(
            q.Status.Eq(status),
            q.Status.IsNull(),
        ),
    ).Find()
}
```

### 字段操作符

```go
// 比较操作符
query.Where(q.Age.Eq(25))           // =
query.Where(q.Age.Neq(25))          // !=
query.Where(q.Age.Gt(25))           // >
query.Where(q.Age.Gte(25))          // >=
query.Where(q.Age.Lt(30))           // <
query.Where(q.Age.Lte(30))          // <=

// 字符串操作
query.Where(q.Name.Like("%alice%")) // LIKE
query.Where(q.Name.Regexp("^A"))    // REGEXP

// NULL 检查
query.Where(q.DeletedAt.IsNull())   // IS NULL
query.Where(q.Phone.IsNotNull())    // IS NOT NULL

// IN / BETWEEN
query.Where(q.Status.In("active", "pending"))
query.Where(q.Age.Between(20, 30))
```

---

## 7. 关联查询

### Preload 与 Gen

```go
// Model 定义（需 foreignKey tag）
type User struct {
    gorm.Model
    Name   string
    Orders []Order `gorm:"foreignKey:UserID;constraint:false"`
}

type Order struct {
    gorm.Model
    UserID uint
    Amount decimal.Decimal
}

// Gen 查询中使用 Preload
func (q *queryUser) GetWithOrders(id int64) (*gen.T, error) {
    return q.Preload(q.Orders).Where(q.ID.Eq(id)).First()
}

// 带条件的 Preload
func (q *queryUser) GetActiveWithOrders(id int64) (*gen.T, error) {
    return q.Preload(q.Orders, func(db *gen.SubQuery) *gen.SubQuery {
        return db.Where("status = ?", "paid")
    }).Where(q.ID.Eq(id)).First()
}

// 多级 Preload
func (q *queryUser) GetWithOrderItems(id int64) (*gen.T, error) {
    return q.Preload(q.Orders).
        Preload(q.Orders.Items).
        Where(q.ID.Eq(id)).
        First()
}
```

### Join 查询

```go
// 关联过滤
func (q *queryUser) FindWithPaidOrders() ([]*gen.T, error) {
    qo := gen.NewQuery(db).Order  // Order 查询对象

    return q.Joins(qo.
        Where(qo.Status.Eq("paid")),
    ).Distinct().Find()
}

// 手动 Join
func (q *queryUser) JoinOrders(minAmount decimal.Decimal) ([]*gen.T, error) {
    return q.
        LeftJoin(gen.NewQuery(db).Order, "orders.user_id = users.id").
        Where(gen.NewQuery(db).Order.Amount.Gt(minAmount)).
        Distinct().
        Find()
}
```

---

## 8. 事务支持

### WithTx 在 Gen 中使用事务

```go
// 事务操作
func (q *queryUser) CreateUserWithOrders(tx *gorm.DB, user *User, orders []Order) error {
    // WithTx 切换底层数据库连接
    qtx := q.WithContext(context.Background()).WithTx(tx)

    // 创建用户
    if err := qtx.Create(user); err != nil {
        return err
    }

    // 创建订单
    for _, order := range orders {
        order.UserID = user.ID
        if err := gen.NewQuery(tx).Order.Create(&order); err != nil {
            return err  // 自动回滚
        }
    }

    return nil
}

// 调用
err := db.Transaction(func(tx *gorm.DB) error {
    return query.User.CreateUserWithOrders(tx, newUser, newOrders)
})
```

### 并发事务

```go
// 多个事务并行执行
var mu sync.Mutex
users := []User{}

db.Transaction(func(tx *gorm.DB) error {
    qtx := query.User.WithTx(tx)

    // 高并发更新
    return qtx.Where(qtx.Status.Eq("active")).
        Update(qtx.LastLoginAt, time.Now())
})
```

---

## 9. 与传统 GORM API 对比

### 迁移策略

```go
// ❌ 传统 GORM（无类型检查）
db.Where("name = ?", "Alice").
   Where("age > ?", 25).
   Find(&users)

// ✅ GORM Gen（类型安全）
query.User.
    Where(query.User.Name.Eq("Alice")).
    Where(query.User.Age.Gt(25)).
    Find()

// 混合使用（逐步迁移）
query.User.
    Where(query.User.Active.IsTrue()).
    Where(db.Where("custom_field > ?", 100)).
    Find()
```

### 动态 SQL 仍需传统 API

```go
// Gen 不适合表名/列名动态的场景
func QueryByTableName(db *gorm.DB, table string) ([]map[string]interface{}, error) {
    var result []map[string]interface{}

    // 必须用传统 GORM
    db.Table(table).Scan(&result)

    return result, nil
}

// Gen 适合查询条件动态
func QueryByCondition(cond string, args ...interface{}) ([]*User, error) {
    return query.User.Where(db.Where(cond, args...)).Find()
}
```

---

## 10. 最佳实践

### 项目结构

```
project/
├── gen/
│   └── gen.go                      # 生成器配置入口
├── internal/
│   ├── model/
│   │   ├── user.go                 # Model 定义
│   │   ├── order.go
│   │   └── query.gen.go            # 生成的查询 API
│   └── query/
│       ├── user.go                 # 自定义查询方法（可选）
│       └── builder.go              # 动态查询构建器
├── main.go
└── go.mod
```

### 生成代码版本管理

```bash
# 生成的文件应纳入版本控制
git add internal/model/query.gen.go

# 配置 .gitignore（可选，仅保留源）
# internal/model/query.gen.go

# 或在 CI 中每次重新生成
go generate ./...
```

### CI/CD 集成

```yaml
# .github/workflows/test.yml
name: Test
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-go@v4
        with:
          go-version: 1.21

      - name: Generate Code
        run: go generate ./...

      - name: Check No Changes
        run: git diff --exit-code

      - name: Test
        run: go test ./...
```

### 性能优化建议

```go
// 1. 预定义查询对象，避免重复创建
var (
    userQuery = gen.NewQuery(db).User
    orderQuery = gen.NewQuery(db).Order
)

func GetUserFast(id int64) (*User, error) {
    return userQuery.Where(userQuery.ID.Eq(id)).First()
}

// 2. 使用 Select 减少查询列
func GetUserNames() ([]string, error) {
    return userQuery.Select(userQuery.Name).Pluck(userQuery.Name)
}

// 3. 批量操作使用 CreateInBatches
func BulkInsertUsers(users []User) error {
    return userQuery.CreateInBatches(users, 1000)
}
```

---

## 11. 常见坑与解决

| 坑 | 说明 | 解决 |
|----|------|------|
| 生成代码与手写 Model 冲突 | 重新生成覆盖自定义字段 | 使用 `ApplyBasic` + 分离目录 |
| 自定义类型（枚举）生成为 string | 没有配置 `gen.FieldType` | 在生成器中指定自定义类型 |
| Preload 加载大量数据 OOM | 未分页加载关联 | 用 Limit 或手动分批 Preload |
| 编译错误"gen.T undefined" | 生成代码未被导入 | 检查 import 和 OutPath 配置 |
| 修改 Model 后查询编译失败 | 生成代码与源 Model 不同步 | 重新执行 `go generate ./...` |
| 复杂查询无法用 Gen 表达 | 预定义方法不支持特殊 SQL | 用 Raw 或手写 WHERE 条件 |
| 多数据库选择性生成 | 配置切换数据库源 | 为不同库创建独立 gen.go |
| 生成文件过大（>5MB） | 单表字段太多或关联复杂 | 拆分为多个 Model 文件 |

### 调试生成代码

```go
// 查看生成的 SQL
db.Debug().WithContext(ctx).Where(...).Find(&users)

// 输出 SQL 日志
import "gorm.io/logger"

db := gorm.Open(sqlite.Open("test.db"), &gorm.Config{
    Logger: logger.Default.LogMode(logger.Info),
})
```

---

## 参考链接

- [GORM Gen 官方文档](https://gorm.io/gen/)
- [Gen 接口注解完整列表](https://pkg.go.dev/gorm.io/gen)
- [GORM Hooks 与生成代码集成](https://gorm.io/hooks.html)

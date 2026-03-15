# GORM 泛型 BaseModel 设计规范

> 本文档总结在实际项目（`dbcore.BaseModel[T]` 模式）中发现的常见 Bug、性能问题与最佳实践。

---

## 1. QueryBuilder —— args 顺序 Bug（高危）

### 问题

`InStrings` / `InInts` 在循环内边追加 `args` 边构建 `placeholders`，当有多个链式条件时，`args` 的追加顺序与 `conditions` 中占位符的顺序错位：

```go
// ❌ 错误写法：args 在循环内追加，condition 在循环外追加
func (q *QueryBuilder) InStrings(field string, values []string) *QueryBuilder {
    if len(values) > 0 {
        placeholders := make([]string, len(values))
        for i, v := range values {
            placeholders[i] = "?"
            q.args = append(q.args, v)   // ← 先追加 args
        }
        q.conditions = append(q.conditions, ...) // ← 后追加 condition
    }
}
// 对比 In() 是 q.args = append(q.args, values...) 在循环外统一追加
// 不一致导致：链式调用时 args 顺序与占位符不匹配，SQL 参数绑定出错
```

### 修复

```go
// ✅ 正确写法：先构建 placeholders 和 ifaces，再统一追加
func (q *QueryBuilder) InStrings(field string, values []string) *QueryBuilder {
    if len(values) > 0 {
        placeholders := make([]string, len(values))
        ifaces := make([]interface{}, len(values))
        for i, v := range values {
            placeholders[i] = "?"
            ifaces[i] = v
        }
        // condition 和 args 同步追加，顺序一致
        q.conditions = append(q.conditions,
            fmt.Sprintf("%s IN (%s)", field, strings.Join(placeholders, ",")))
        q.args = append(q.args, ifaces...)
    }
    return q
}
```

> `InInts` 同样有此问题，修复方式相同。

---

## 2. 软删除 + 唯一索引冲突

### 问题

`uniqueIndex` 不包含 `deleted_at` 时，软删除后该字段值仍占用唯一约束，重新创建相同值报 `Duplicate entry`：

```go
// ❌ 软删除后 order_no 仍占用唯一约束，同订单号无法重建
OrderNo    string         `gorm:"uniqueIndex"`
DeletedAt  gorm.DeletedAt `gorm:"index"`
```

### 修复

```go
// ✅ 复合唯一索引：order_no + deleted_at
// 软删除后 deleted_at = timestamp（非 NULL），不与新记录的 NULL 冲突
OrderNo    string         `gorm:"column:order_no;uniqueIndex:idx_order_no_del"`
DeletedAt  gorm.DeletedAt `gorm:"index;uniqueIndex:idx_order_no_del"`
```

> 原理：MySQL 唯一索引中多个 NULL 不冲突。软删除前 `deleted_at IS NULL`，软删除后 `deleted_at = 时间戳`，两者不相等，新记录可以正常插入。

---

## 3. AutoMigrate 生产环境风险

### 问题

```go
// ❌ 服务启动时执行 AutoMigrate，大表会锁表，影响线上服务
func NewOrderModel(db *gorm.DB, isMigrate bool) OrderModel {
    if isMigrate {
        db.AutoMigrate(&Order{})  // 100万行以上会触发 ALTER TABLE 锁表
    }
}
```

### 修复

```go
// ✅ 生产环境禁用 AutoMigrate，使用 golang-migrate 脚本管理迁移
func NewOrderModel(db *gorm.DB, isMigrate bool) OrderModel {
    if isMigrate {
        migrateDB := db.Session(&gorm.Session{})
        migrateDB.DisableForeignKeyConstraintWhenMigrating = true // 禁止物理 FK
        if err := migrateDB.AutoMigrate(&Order{}); err != nil {
            panic(err)
        }
    }
    // ...
}
```

**环境策略**：

| 环境 | isMigrate | 迁移方式 |
|------|-----------|----------|
| 本地开发 | `true` | AutoMigrate（快速迭代） |
| 测试环境 | `true` | AutoMigrate |
| 生产环境 | `false` | golang-migrate 脚本（详见 references/migration.md） |

---

## 4. Find() 应使用 Take() 而非 First()

### 问题

```go
// ❌ First() 会隐式追加 ORDER BY id，按主键查单条无需排序
func (m *BaseModel[T]) Find(ctx context.Context, id string) (*T, error) {
    m.GetTxDB(ctx).Where("id = ?", id).First(&v)
    // 实际执行: SELECT * FROM t WHERE id=? ORDER BY id LIMIT 1
}
```

### 修复

```go
// ✅ Take() 不追加 ORDER BY，语义更准确，略微减少排序开销
m.GetTxDB(ctx).Where("id = ?", id).Take(&v)
// 实际执行: SELECT * FROM t WHERE id=? LIMIT 1
```

| 方法 | 语义 | 隐式 ORDER BY |
|------|------|--------------|
| `First()` | 按主键升序取第一条 | `ORDER BY id ASC` |
| `Last()` | 按主键降序取第一条 | `ORDER BY id DESC` |
| `Take()` | 不排序取一条 | 无 |

---

## 5. ListAll() 建议加软上限

### 问题

```go
// ❌ 无行数限制，百万级表直接 OOM
func (m *BaseModel[T]) ListAll(...) ([]*T, error) {
    db.Find(&list) // 全表加载
}
```

### 修复

```go
const maxListAllSize = 10_000

func (m *BaseModel[T]) ListAll(ctx context.Context, orders ...Order) ([]*T, error) {
    var list []*T
    db := applyOrders(m.GetTxDB(ctx), orders)
    return list, db.Limit(maxListAllSize).Find(&list).Error
}
```

> 如需处理超大数据集，使用 `FindInBatches` 替代 `ListAll`：
> ```go
> db.FindInBatches(&batch, 500, func(tx *gorm.DB, batchNum int) error {
>     process(batch)
>     return nil
> })
> ```

---

## 6. Page() 消除重复的 WHERE 条件构建

### 问题

```go
// ❌ COUNT 和数据查询各自重复构建相同的 WHERE 条件
countDB := m.GetTxDB(ctx).Model(new(T))
if query != "" { countDB = countDB.Where(query, args...) }
countDB.Count(&total)

queryDB := m.GetTxDB(ctx).Model(new(T))          // 完全重复
if query != "" { queryDB = queryDB.Where(query, args...) }
queryDB.Offset(offset).Limit(pageSize).Find(&list)
```

### 修复

```go
// ✅ 提取公共 baseDB，两次查询复用，Session() 隔离避免条件累积
baseDB := m.GetTxDB(ctx).Model(new(T))
if query != "" {
    baseDB = baseDB.Where(query, args...)
}

baseDB.Session(&gorm.Session{}).Count(&total)

applyOrders(baseDB.Session(&gorm.Session{}), orders).
    Offset(offset).Limit(pageSize).Find(&list)
```

> **为什么要 `Session(&gorm.Session{})`**：GORM 的 `*gorm.DB` 是值语义，但内部 `Statement` 是指针，直接复用 `baseDB` 做两次查询会导致条件累积（第二次查询携带第一次的 COUNT 相关状态）。`Session` 开启新的独立会话，安全复用条件。

---

## 7. 游标分页（大数据量推荐）

```go
// Page() 的 OFFSET 分页在大页码时性能退化（扫描并丢弃前 N 行）
// page=1000, pageSize=20 → OFFSET=19980 → 扫描近 2 万行

// ✅ 游标分页：无论第几页，只扫描 pageSize 行
func (m *BaseModel[T]) PageAfter(ctx context.Context,
    afterID string, pageSize int,
    query string, orders []Order, args ...interface{}) ([]*T, error) {

    if afterID != "" {
        if query != "" {
            query = "id > ? AND (" + query + ")"
            args = append([]interface{}{afterID}, args...)
        } else {
            query = "id > ?"
            args = []interface{}{afterID}
        }
    }
    // ...
    db.Order("id ASC").Limit(pageSize).Find(&list)
}

// 使用方式
page1, _ := model.PageAfter(ctx, "", 20, "status=?", nil, 1)
lastID := page1[len(page1)-1].ID
page2, _ := model.PageAfter(ctx, lastID, 20, "status=?", nil, 1)
```

---

## 8. 多租户隔离在 Model 层强制

```go
// ❌ 通用方法不知道租户概念，调用方需手动带 tenant_id=? 条件
// 容易漏写导致数据越权
orders, _ := model.List(ctx, "order_status=?", nil, 1) // 漏了 tenant_id！

// ✅ 在具体 Model 覆写，注入 tenant_id
func (m *defaultOrderModel) ListByTenant(ctx context.Context,
    tenantID string, query string,
    orders []dbcore.Order, args ...interface{}) ([]*Order, error) {

    if tenantID == "" {
        return []*Order{}, nil // 无租户信息时拒绝查询
    }
    if query != "" {
        query = "tenant_id = ? AND (" + query + ")"
        args = append([]interface{}{tenantID}, args...)
    } else {
        query = "tenant_id = ?"
        args = []interface{}{tenantID}
    }
    return m.List(ctx, query, orders, args...)
}
```

---

## 9. 扩展 JSON 字段用 datatypes.JSON

```go
// ❌ string 存 JSON：需手动 Marshal/Unmarshal，无法利用 MySQL JSON 函数查询
ExtData string `gorm:"column:ext_data;type:text"`

// ✅ datatypes.JSON：自动序列化，支持 JSONQuery
import "gorm.io/datatypes"

ExtData datatypes.JSON `gorm:"column:ext_data;type:json"`

// 支持 JSON 字段查询
db.Where(datatypes.JSONQuery("ext_data").HasKey("source")).Find(&orders)
db.Where(datatypes.JSONQuery("ext_data").Equals("神州", "source")).Find(&orders)
```

---

## 10. QueryBuilder.OrGroup —— OR 分组支持

```go
// ❌ 原版只能通过 Raw() 手写 OR 条件，容易出错
qb.Raw("(order_status = ? OR order_status = ?)", 4, 5)

// ✅ 使用 OrGroup 组合多个子条件
qb.OrGroup(
    NewQueryBuilder().Eq("order_status", 4),
    NewQueryBuilder().Eq("order_status", 5),
)
// 生成: (order_status = ? OR order_status = ?)  args: [4, 5]

// 复合 OrGroup
qb.Eq("tenant_id", tenantID).
   OrGroup(
       NewQueryBuilder().Eq("pay_status", 2),
       NewQueryBuilder().Eq("pay_status", 3),
   ).
   Gte("create_at", startTime)
// 生成: tenant_id=? AND (pay_status=? OR pay_status=?) AND create_at>=?
```

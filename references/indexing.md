# GORM 索引定义最佳实践

## Tag 定义索引

```go
type User struct {
    gorm.Model
    Name  string `gorm:"index"`                          // 普通索引
    Email string `gorm:"uniqueIndex"`                    // 唯一索引
    Age   int    `gorm:"index:idx_age,sort:desc"`         // 带排序方向
    Phone string `gorm:"index:idx_phone,comment:手机号索引"` // 带注释
}
```

## 复合索引

```go
type Order struct {
    gorm.Model
    UserID    uint      `gorm:"index:idx_user_status_time,priority:1"`
    Status    string    `gorm:"index:idx_user_status_time,priority:2"`
    CreatedAt time.Time `gorm:"index:idx_user_status_time,priority:3"`
}
// 生成：CREATE INDEX idx_user_status_time ON orders (user_id, status, created_at)
```

## 唯一复合索引

```go
type UserRole struct {
    UserID uint `gorm:"uniqueIndex:idx_user_role"`
    RoleID uint `gorm:"uniqueIndex:idx_user_role"`
}
```

## 函数索引（MySQL 8.0+）

```go
// 需要用 AutoMigrate 之外的迁移工具，或手动执行
// CREATE INDEX idx_lower_email ON users ((LOWER(email)));
```

## 索引设计原则

1. **最左前缀原则**：复合索引查询条件顺序要匹配索引列顺序
2. **选择性高的列放前面**：user_id（高选择性）> status（低选择性）
3. **覆盖索引**：SELECT 的字段都在索引中，避免回表
4. **避免过多索引**：每个索引都增加写入开销，一般单表不超过 5-8 个
5. **范围查询字段放最后**：`WHERE user_id = 1 AND created_at > ?`，created_at 放复合索引最后

## 使用 Index Hints（GORM）

```go
import "gorm.io/hints"

// 建议使用某索引（optimizer 可忽略）
db.Clauses(hints.UseIndex("idx_user_status")).Find(&orders)

// 强制使用
db.Clauses(hints.ForceIndex("idx_created_at").ForOrderBy()).Find(&logs)

// 忽略某索引
db.Clauses(hints.IgnoreIndex("idx_name").ForGroupBy()).Find(&users)
```

## AutoMigrate 注意事项

- AutoMigrate 只**新增**索引，不删除已有索引
- 生产环境推荐用 `golang-migrate` + 手写 SQL 迁移，而非依赖 AutoMigrate
- 大表加索引应使用 `ALTER TABLE ... ADD INDEX` 的在线 DDL（MySQL 8.0+ 支持）

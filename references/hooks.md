# GORM Hooks 使用与性能注意事项

## 可用 Hook 列表

| Hook | 触发时机 |
|------|---------|
| `BeforeCreate` / `AfterCreate` | Create / Save 前后 |
| `BeforeUpdate` / `AfterUpdate` | Update / Save 前后 |
| `BeforeDelete` / `AfterDelete` | Delete 前后 |
| `AfterFind` | Find / First / Last 后 |
| `BeforeSave` / `AfterSave` | Create 和 Update 都触发 |

## 标准写法

```go
func (u *User) BeforeCreate(tx *gorm.DB) error {
    u.UUID = uuid.New().String()
    return nil // 返回 error 会中止操作并 rollback
}

func (u *User) AfterFind(tx *gorm.DB) error {
    // 解密敏感字段等
    u.Phone = decrypt(u.Phone)
    return nil
}
```

## 性能注意事项

1. **AfterFind 是高频 Hook**，每条记录都会调用一次，避免放耗时操作（HTTP 调用、加密等大计算）
2. **Hook 内避免再次触发 Hook** — 用 `tx.Session(&gorm.Session{SkipHooks: true}).Update(...)` 跳过
3. **批量操作下 Hook 行为**：
   - `CreateInBatches` — 每条记录都会触发 BeforeCreate/AfterCreate（开销大时可用 `SkipHooks`）
   - `db.Model(&User{}).Where(...).Updates(...)` — **不触发** Hook（直接 UPDATE SQL）
4. **注册全局 Plugin 代替 Hook**，适合审计日志等横切关注点：

```go
type AuditPlugin struct{}

func (p *AuditPlugin) Name() string { return "audit" }
func (p *AuditPlugin) Initialize(db *gorm.DB) error {
    db.Callback().Create().After("gorm:create").Register("audit:create", auditCreate)
    return nil
}
db.Use(&AuditPlugin{})
```

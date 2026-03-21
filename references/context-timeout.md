# GORM Context 超时管理

> 覆盖 Context 超时最佳实践、连接泄漏排查、事务超时策略、生产配置建议。Context 是 GORM 中资源安全的第一道防线。

---

## 1. 为什么 Context 超时至关重要

### 1.1 三大风险场景

| 风险 | 表现 | 后果 |
|------|------|------|
| **连接泄漏** | 查询未响应，连接未释放 | 连接池耗尽，新请求挂起 |
| **Goroutine 泄漏** | 查询阻塞，Goroutine 无法退出 | 内存增长，最终 OOM |
| **资源耗尽** | 长时间慢查询堆积 | 数据库磁盘、内存压力激增 |

### 1.2 没有超时的危害

```go
// ❌ 危险：DB 查询永远阻塞，连接泄漏
result := db.Find(&users) // 若数据库网络故障，永远等待

// ❌ 危险：HTTP 请求超时，DB 查询继续执行
func handler(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context() // HTTP 请求可能 10s 超时
    // 但 db.Find() 仍会执行 30s，连接被浪费
    db.Find(&users)
}

// ✅ 正确：显式设置超时，超时自动取消
ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
defer cancel()
db.WithContext(ctx).Find(&users)
```

---

## 2. WithContext 行为详解

### 2.1 Context 在 GORM 中的传递链路

```go
// Context 传入 GORM Session
db := db.WithContext(ctx)

// GORM 传入 database/sql 驱动
// 驱动使用 ctx 进行：
// - 连接获取超时
// - 语句执行超时
// - 行扫描超时
```

### 2.2 Context 取消 vs 超时

```go
// 场景 1: 显式取消（如用户中止请求）
ctx, cancel := context.WithCancel(context.Background())
go func() {
    time.Sleep(1 * time.Second)
    cancel() // 主动取消
}()
db.WithContext(ctx).Find(&users) // 1s 后中断

// 场景 2: 超时自动取消
ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
defer cancel() // 3s 后自动取消
db.WithContext(ctx).Find(&users)

// 场景 3: 截止时间（指定具体时刻）
deadline := time.Now().Add(5 * time.Second)
ctx, cancel := context.WithDeadline(context.Background(), deadline)
defer cancel()
db.WithContext(ctx).Find(&users)
```

### 2.3 Context 超时时的数据库行为

```go
// 当 context 超时时：
// 1. database/sql 调用驱动的 Stmt.ExecContext() / QueryContext()
// 2. 驱动（如 MySQL driver）立即返回 context.DeadlineExceeded 错误
// 3. GORM 捕获错误返回给应用
// 4. 连接被标记为不可用，返回连接池

var users []User
ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
defer cancel()

err := db.WithContext(ctx).Find(&users).Error
// 若查询耗时 > 100ms，err = context.DeadlineExceeded
// 连接池自动释放该连接
```

---

## 3. 查询超时

### 3.1 简单查询超时

```go
// 单条查询：3 秒超时
func GetUser(ctx context.Context, id uint) (*User, error) {
    ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
    defer cancel() // 重要！必须释放 context

    var user User
    if err := db.WithContext(ctx).First(&user, id).Error; err != nil {
        return nil, err
    }
    return &user, nil
}

// 列表查询：10 秒超时（因可能数据量大）
func ListUsers(ctx context.Context, offset, limit int) ([]User, error) {
    ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
    defer cancel()

    var users []User
    if err := db.WithContext(ctx).
        Offset(offset).Limit(limit).
        Find(&users).Error; err != nil {
        return nil, err
    }
    return users, nil
}

// 聚合查询：5 秒超时
func CountActiveUsers(ctx context.Context) (int64, error) {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    var count int64
    if err := db.WithContext(ctx).
        Model(&User{}).
        Where("status = ?", "active").
        Count(&count).Error; err != nil {
        return 0, err
    }
    return count, nil
}
```

### 3.2 批量查询与超时

```go
// ❌ 错误：超时太短，批量查询易失败
ctx, cancel := context.WithTimeout(context.Background(), 100*time.Millisecond)
defer cancel()
db.WithContext(ctx).Find(&users) // 1 万条记录可能需要 500ms

// ✅ 正确：根据预期数据量调整超时
func BatchGetUsers(ctx context.Context, ids []uint) ([]User, error) {
    // 100 条数据 + 500ms 网络延迟 + 500ms 扫描时间 ≈ 2s
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    var users []User
    if err := db.WithContext(ctx).
        Where("id IN ?", ids).
        Find(&users).Error; err != nil {
        return nil, err
    }
    return users, nil
}
```

### 3.3 流式查询超时

```go
// 大量数据逐行处理，超时不应该过短
func ProcessLargeDataset(ctx context.Context, fn func(*User) error) error {
    // 整个流式处理给 60 秒，不是每行 1 秒
    ctx, cancel := context.WithTimeout(ctx, 60*time.Second)
    defer cancel()

    rows, err := db.WithContext(ctx).Model(&User{}).Rows()
    if err != nil {
        return err
    }
    defer rows.Close()

    for rows.Next() {
        var user User
        db.ScanRows(rows, &user)
        if err := fn(&user); err != nil {
            return err
        }
    }
    return rows.Err()
}
```

---

## 4. 事务超时策略

### 4.1 事务级别超时

```go
// 事务超时：从 BeginTx 到 Commit 的整个时间
func TransferFunds(ctx context.Context, from, to uint, amount decimal.Decimal) error {
    // 事务级别 5 秒超时（包含多条 SQL）
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    tx := db.WithContext(ctx).BeginTx(ctx, &sql.TxOptions{
        Isolation: sql.LevelReadCommitted,
    })
    if tx.Error != nil {
        return tx.Error
    }

    // 在事务内的所有操作共享同一 context 和超时
    var fromAccount, toAccount Account

    if err := tx.First(&fromAccount, from).Error; err != nil {
        tx.Rollback()
        return err
    }

    if err := tx.First(&toAccount, to).Error; err != nil {
        tx.Rollback()
        return err
    }

    // 更新账户
    if err := tx.Model(&fromAccount).
        Update("balance", gorm.Expr("balance - ?", amount)).Error; err != nil {
        tx.Rollback()
        return err
    }

    if err := tx.Model(&toAccount).
        Update("balance", gorm.Expr("balance + ?", amount)).Error; err != nil {
        tx.Rollback()
        return err
    }

    // 若此时已超时，Commit 会立即失败
    if err := tx.Commit().Error; err != nil {
        return err
    }
    return nil
}

// 使用 BeginTx 显式设置隔离级别和超时
func CreateOrderWithContext(ctx context.Context, order *Order) error {
    ctx, cancel := context.WithTimeout(ctx, 10*time.Second)
    defer cancel()

    tx := db.WithContext(ctx).BeginTx(ctx, &sql.TxOptions{
        Isolation: sql.LevelRepeatableRead,
        ReadOnly:  false,
    })
    if tx.Error != nil {
        return tx.Error
    }

    if err := tx.Create(order).Error; err != nil {
        tx.Rollback()
        return err
    }

    // 插入订单项
    for _, item := range order.Items {
        item.OrderID = order.ID
        if err := tx.Create(&item).Error; err != nil {
            tx.Rollback()
            return err
        }
    }

    return tx.Commit().Error
}
```

### 4.2 语句级别超时 vs 事务级别超时

```go
// ❌ 错误：混淆概念，多个短超时
func badBatch(ctx context.Context) error {
    tx := db.BeginTx(ctx, nil)

    // 事务 A：3s 超时
    ctx1, cancel1 := context.WithTimeout(ctx, 3*time.Second)
    defer cancel1()
    if err := tx.WithContext(ctx1).Create(&order1).Error; err != nil {
        tx.Rollback()
        return err
    }

    // 事务 B：再用 3s（但已花费 2s），只剩 1s
    ctx2, cancel2 := context.WithTimeout(ctx, 3*time.Second) // 错误！
    defer cancel2()
    if err := tx.WithContext(ctx2).Create(&order2).Error; err != nil {
        tx.Rollback()
        return err
    }

    return tx.Commit().Error
}

// ✅ 正确：事务级别单一超时
func goodBatch(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 10*time.Second) // 整个事务 10s
    defer cancel()

    tx := db.WithContext(ctx).BeginTx(ctx, nil)
    if tx.Error != nil {
        return tx.Error
    }

    if err := tx.Create(&order1).Error; err != nil {
        tx.Rollback()
        return err
    }
    if err := tx.Create(&order2).Error; err != nil {
        tx.Rollback()
        return err
    }

    return tx.Commit().Error
}
```

### 4.3 嵌套事务与超时

```go
// ⚠️ 嵌套事务：内层 context 超时会影响外层
func outerTx(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 30*time.Second)
    defer cancel()

    tx := db.WithContext(ctx).Begin()
    if tx.Error != nil {
        return tx.Error
    }

    // 内层事务
    if err := innerTx(tx, ctx); err != nil { // 继承同一 context
        tx.Rollback()
        return err
    }

    // 若 innerTx 耗时 25s，外层只剩 5s
    if err := tx.Create(&anotherOrder).Error; err != nil {
        tx.Rollback()
        return err
    }

    return tx.Commit().Error
}

func innerTx(tx *gorm.DB, ctx context.Context) error {
    // 不要在此重新创建超时！继承父 context
    if err := tx.Create(&order).Error; err != nil {
        return err
    }
    return nil
}
```

---

## 5. 连接泄漏排查

### 5.1 连接泄漏症状

| 症状 | 诊断 |
|------|------|
| "too many connections" 错误 | 连接池中活连接达到上限 |
| 新请求卡住 | 等待可用连接，但没有连接释放 |
| 内存持续增长 | Goroutine 阻塞，堆栈占用内存 |
| 数据库 Processlist 中大量 sleep 连接 | 应用持有但不使用的连接 |

### 5.2 使用 sqlDB.Stats() 监控连接池

```go
import "database/sql"

func monitorConnectionPool(db *gorm.DB) {
    sqlDB, err := db.DB()
    if err != nil {
        return
    }

    ticker := time.NewTicker(10 * time.Second)
    defer ticker.Stop()

    for range ticker.C {
        stats := sqlDB.Stats()

        log.Printf("DB Connection Stats:\n"+
            "  OpenConnections: %d\n"+
            "  InUse: %d\n"+
            "  Idle: %d\n"+
            "  WaitCount: %d\n"+
            "  WaitDuration: %v\n"+
            "  MaxIdleClosed: %d\n"+
            "  MaxLifetimeClosed: %d\n",
            stats.OpenConnections,
            stats.InUse,
            stats.Idle,
            stats.WaitCount,
            stats.WaitDuration,
            stats.MaxIdleClosed,
            stats.MaxLifetimeClosed,
        )

        // 告警：使用率 > 90%
        if stats.OpenConnections > 0 &&
           float64(stats.InUse)/float64(stats.OpenConnections) > 0.9 {
            log.Printf("WARNING: Connection pool usage high: %d/%d",
                stats.InUse, stats.OpenConnections)
        }
    }
}
```

### 5.3 常见泄漏原因与修复

```go
// ❌ 错误：查询结果未关闭
func badQuery(ctx context.Context) error {
    rows, err := db.WithContext(ctx).Model(&User{}).Rows()
    if err != nil {
        return err
    }
    // 忘记 defer rows.Close()，连接泄漏！
    for rows.Next() {
        var user User
        rows.Scan(&user)
    }
    return nil
}

// ✅ 正确：显式关闭 rows
func goodQuery(ctx context.Context) error {
    rows, err := db.WithContext(ctx).Model(&User{}).Rows()
    if err != nil {
        return err
    }
    defer rows.Close() // 重要！

    for rows.Next() {
        var user User
        rows.Scan(&user)
    }
    return rows.Err()
}

// ❌ 错误：无超时的查询
func queryWithoutTimeout(ctx context.Context) error {
    // DB 网络故障，永远阻塞，连接永远泄漏
    var users []User
    return db.WithContext(ctx).Find(&users).Error
}

// ✅ 正确：加超时保护
func queryWithTimeout(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    var users []User
    return db.WithContext(ctx).Find(&users).Error
}

// ❌ 错误：goroutine 内无超时
func backgroundTask(ctx context.Context) {
    go func() {
        // 此 goroutine 可能永远运行，持有连接
        db.WithContext(context.Background()).Find(&users)
    }()
}

// ✅ 正确：background task 也要超时
func backgroundTaskFixed(ctx context.Context) {
    go func() {
        taskCtx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
        defer cancel()
        db.WithContext(taskCtx).Find(&users)
    }()
}
```

---

## 6. HTTP Handler 集成

### 6.1 从 Request Context 派生超时

```go
import "net/http"

func GetUserHandler(w http.ResponseWriter, r *http.Request) {
    // HTTP 请求的 context（支持超时和取消）
    ctx := r.Context()

    // 方案 A：使用 HTTP context（若客户端断连立即取消）
    var user User
    if err := db.WithContext(ctx).First(&user, r.PathValue("id")).Error; err != nil {
        http.Error(w, err.Error(), http.StatusInternalServerError)
        return
    }
    json.NewEncoder(w).Encode(user)
}

// HTTP server 可能有全局超时，需要协调
func main() {
    srv := &http.Server{
        Addr:         ":8080",
        ReadTimeout:  10 * time.Second,
        WriteTimeout: 30 * time.Second,
    }
    // 但 DB 查询应该有单独的控制，不依赖 HTTP 超时
}
```

### 6.2 超时分层策略

```go
// 推荐：三层超时控制
// 1. HTTP 层超时（保护网络）
// 2. 业务层超时（保护逻辑）
// 3. DB 层超时（保护数据库）

func GetUserHandler(w http.ResponseWriter, r *http.Request) {
    ctx := r.Context()

    // 从 HTTP context 中提取剩余时间，额外减少缓冲
    deadline, ok := ctx.Deadline()
    if ok {
        remaining := time.Until(deadline)
        if remaining > 2*time.Second {
            // 给 DB 分配 remaining - 1s（缓冲给日志、序列化等）
            remaining = remaining - 1*time.Second
        } else {
            // HTTP 超时倒计时，请求已经接近超时，拒绝
            http.Error(w, "Request timeout", http.StatusRequestTimeout)
            return
        }

        var cancel context.CancelFunc
        ctx, cancel = context.WithTimeout(ctx, remaining)
        defer cancel()
    } else {
        // 没有 HTTP 超时，自己设定 DB 超时
        var cancel context.CancelFunc
        ctx, cancel = context.WithTimeout(context.Background(), 3*time.Second)
        defer cancel()
    }

    // 调用业务层
    user, err := getUserService(ctx)
    if err != nil {
        handleError(w, err)
        return
    }
    json.NewEncoder(w).Encode(user)
}

func getUserService(ctx context.Context) (*User, error) {
    return getUserFromDB(ctx)
}

func getUserFromDB(ctx context.Context) (*User, error) {
    var user User
    if err := db.WithContext(ctx).First(&user).Error; err != nil {
        return nil, err
    }
    return &user, nil
}
```

### 6.3 Middleware 中统一管理超时

```go
func TimeoutMiddleware(defaultTimeout time.Duration) func(http.Handler) http.Handler {
    return func(next http.Handler) http.Handler {
        return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
            ctx := r.Context()

            // 如果请求已有截止时间，使用最紧的那个
            deadline, ok := ctx.Deadline()
            if !ok {
                var cancel context.CancelFunc
                ctx, cancel = context.WithTimeout(ctx, defaultTimeout)
                defer cancel()
            } else {
                // 验证超时是否足够（比如 > 1s）
                remaining := time.Until(deadline)
                if remaining < 1*time.Second {
                    http.Error(w, "Request timeout", http.StatusRequestTimeout)
                    return
                }
            }

            r = r.WithContext(ctx)
            next.ServeHTTP(w, r)
        })
    }
}

func main() {
    mux := http.NewServeMux()
    mux.HandleFunc("/user/{id}", GetUserHandler)

    // 应用中间件
    handler := TimeoutMiddleware(5 * time.Second)(mux)
    http.ListenAndServe(":8080", handler)
}
```

---

## 7. 后台任务与 CronJob

### 7.1 使用 context.Background() 的正确方式

```go
// ❌ 错误：无限期运行，无超时
func backgroundSync() {
    go func() {
        for {
            db.Find(&allUsers) // 无超时，可能泄漏
            time.Sleep(1 * time.Minute)
        }
    }()
}

// ✅ 正确：每个任务周期内设定超时
func backgroundSync() {
    ticker := time.NewTicker(1 * time.Minute)
    defer ticker.Stop()

    for range ticker.C {
        // 每个同步周期 30 秒超时
        ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
        if err := syncDatabase(ctx); err != nil {
            log.Error("Sync failed:", err)
        }
        cancel()
    }
}

func syncDatabase(ctx context.Context) error {
    var users []User
    return db.WithContext(ctx).Find(&users).Error
}
```

### 7.2 优雅关闭（Graceful Shutdown）

```go
import "context"

type App struct {
    db         *gorm.DB
    syncCancel context.CancelFunc
}

func (app *App) StartBackgroundSync() {
    // 创建可取消的 context，用于优雅关闭
    ctx, cancel := context.WithCancel(context.Background())
    app.syncCancel = cancel

    go func() {
        ticker := time.NewTicker(1 * time.Minute)
        defer ticker.Stop()

        for {
            select {
            case <-ctx.Done():
                log.Info("Background sync stopped")
                return
            case <-ticker.C:
                // 每个任务 30s 超时
                taskCtx, taskCancel := context.WithTimeout(ctx, 30*time.Second)
                if err := app.syncDatabase(taskCtx); err != nil {
                    log.Error("Sync failed:", err)
                }
                taskCancel()
            }
        }
    }()
}

func (app *App) syncDatabase(ctx context.Context) error {
    var users []User
    return app.db.WithContext(ctx).Find(&users).Error
}

// 服务器关闭时调用
func (app *App) Shutdown(ctx context.Context) error {
    // 通知后台任务停止
    app.syncCancel()

    // 等待后台任务完成（最多 5 秒）
    done := make(chan struct{})
    go func() {
        time.Sleep(1 * time.Second) // 等待任务自然结束
        done <- struct{}{}
    }()

    select {
    case <-done:
    case <-ctx.Done():
        return ctx.Err()
    }

    return nil
}
```

---

## 8. 连接池健康检查

### 8.1 PingContext 定期检查

```go
func setupHealthCheck(db *gorm.DB) {
    sqlDB, err := db.DB()
    if err != nil {
        panic(err)
    }

    ticker := time.NewTicker(30 * time.Second)
    defer ticker.Stop()

    go func() {
        for range ticker.C {
            ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
            if err := sqlDB.PingContext(ctx); err != nil {
                log.Error("DB Ping failed:", err)
            }
            cancel()
        }
    }()
}

// 在 HTTP /health 端点暴露
func HealthHandler(w http.ResponseWriter, r *http.Request) {
    ctx, cancel := context.WithTimeout(r.Context(), 3*time.Second)
    defer cancel()

    if err := db.WithContext(ctx).Raw("SELECT 1").Scan(nil).Error; err != nil {
        http.Error(w, `{"db":"unhealthy"}`, http.StatusServiceUnavailable)
        return
    }
    w.Header().Set("Content-Type", "application/json")
    w.WriteHeader(http.StatusOK)
    json.NewEncoder(w).Encode(map[string]string{"db": "healthy"})
}
```

### 8.2 连接池监控告警

```go
func monitorPoolHealth(db *gorm.DB) {
    sqlDB, err := db.DB()
    if err != nil {
        return
    }

    // 配置连接池参数（与数据库最大连接数协调）
    sqlDB.SetMaxOpenConns(100)   // 最多 100 个连接
    sqlDB.SetMaxIdleConns(10)    // 最多保留 10 个空闲
    sqlDB.SetConnMaxLifetime(5 * time.Minute)  // 连接最长活跃 5 分钟

    ticker := time.NewTicker(30 * time.Second)
    defer ticker.Stop()

    for range ticker.C {
        stats := sqlDB.Stats()

        // 告警条件
        inUsePercent := float64(stats.InUse) / float64(stats.OpenConnections)
        if inUsePercent > 0.9 {
            log.Warn("Connection pool high usage",
                "in_use", stats.InUse,
                "open", stats.OpenConnections,
            )
        }

        // 监控泄漏迹象：很多 idle 连接但频繁等待
        if stats.Idle > 50 && stats.WaitCount > 100 {
            log.Warn("Possible connection leak detected")
        }

        log.Info("Pool stats",
            "open", stats.OpenConnections,
            "in_use", stats.InUse,
            "idle", stats.Idle,
            "wait_count", stats.WaitCount,
        )
    }
}
```

---

## 9. 常见坑与反模式

### 9.1 context.TODO() 滥用

```go
// ❌ 错误：TODO 无超时，潜在泄漏
func badQuery() {
    var users []User
    db.WithContext(context.TODO()).Find(&users) // TODO 用于临时代码！
}

// ✅ 正确：显式创建带超时的 context
func goodQuery(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 3*time.Second)
    defer cancel()

    var users []User
    return db.WithContext(ctx).Find(&users).Error
}
```

### 9.2 超时过短导致幽灵错误

```go
// ❌ 错误：超时只有 100ms，正常查询也超时
func unreliableQuery(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 100*time.Millisecond)
    defer cancel()

    var users []User
    // 即使查询正常需要 500ms，也会因超时而失败
    return db.WithContext(ctx).Find(&users).Error
}

// ✅ 正确：根据预期延迟和数据量调整
func reliableQuery(ctx context.Context) error {
    // 预期：网络 50ms + 查询 200ms + 扫描 100ms = 350ms
    // 超时应该 > 350ms，推荐 500ms-1s
    ctx, cancel := context.WithTimeout(ctx, 1*time.Second)
    defer cancel()

    var users []User
    return db.WithContext(ctx).Find(&users).Error
}
```

### 9.3 事务提交后仍使用 context

```go
// ❌ 错误：Commit 后 context 可能已过期
func badTransaction(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    tx := db.WithContext(ctx).Begin()
    if err := tx.Create(&order).Error; err != nil {
        tx.Rollback()
        return err
    }

    if err := tx.Commit().Error; err != nil {
        return err
    }

    // 此时 context 可能已超时（5s 已过）
    // 如果此后继续使用 ctx 查询，会失败
    return nil
}

// ✅ 正确：事务后续操作用新 context
func goodTransaction(ctx context.Context) error {
    txCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel()

    tx := db.WithContext(txCtx).Begin()
    if err := tx.Create(&order).Error; err != nil {
        tx.Rollback()
        return err
    }

    if err := tx.Commit().Error; err != nil {
        return err
    }

    // 事务后续查询用新 context
    queryCtx, cancel2 := context.WithTimeout(ctx, 3*time.Second)
    defer cancel2()
    return db.WithContext(queryCtx).Find(&results).Error
}
```

### 9.4 并发查询中的 cancel 陷阱

```go
// ❌ 错误：cancel 过早，未完成的查询被中断
func concurrentQueryBad(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)

    var user User
    var posts []Post

    // 两个并发查询
    errChan := make(chan error, 2)
    go func() {
        errChan <- db.WithContext(ctx).First(&user).Error
    }()
    go func() {
        errChan <- db.WithContext(ctx).Find(&posts).Error
    }()

    cancel() // 立即取消！（错误）

    // 两个查询都可能被中断
    return <-errChan
}

// ✅ 正确：等待所有并发查询完成再 cancel
func concurrentQueryGood(ctx context.Context) error {
    ctx, cancel := context.WithTimeout(ctx, 5*time.Second)
    defer cancel() // defer 保证等待完成

    var user User
    var posts []Post

    errChan := make(chan error, 2)
    go func() {
        errChan <- db.WithContext(ctx).First(&user).Error
    }()
    go func() {
        errChan <- db.WithContext(ctx).Find(&posts).Error
    }()

    // 等待两个结果
    for i := 0; i < 2; i++ {
        if err := <-errChan; err != nil {
            return err
        }
    }
    return nil
}
```

---

## 10. 生产配置建议

### 10.1 超时值参考

| 场景 | 推荐超时 | 说明 |
|------|---------|------|
| 单行查询（PK 或索引） | 500ms - 1s | 响应快，包含网络延迟 |
| 列表查询（10-1000 条） | 2s - 5s | 数据量可变，需要扫描 |
| 批量写入（1000+ 行） | 10s - 30s | 可能涉及日志刷新 |
| 复杂报表（汇总、JOIN） | 10s - 30s | 计算密集，可能临时表 |
| 后台同步任务 | 30s - 60s | 离线操作，容许较长耗时 |
| HTTP handler | 5s - 10s | 需减去网络、序列化时间 |
| 事务（多条语句） | 5s - 15s | 根据语句数调整 |

### 10.2 完整配置示例

```go
type DBConfig struct {
    // 连接池配置
    MaxOpenConns    int           // 最大连接数，推荐 = (CPU 核数 * 4)
    MaxIdleConns    int           // 最大空闲，推荐 = MaxOpenConns / 2
    ConnMaxLifetime time.Duration // 连接最长活跃时间，防止 DB 侧关闭
    ConnMaxIdleTime time.Duration // 空闲连接超时

    // 超时配置
    QueryTimeout      time.Duration // 单条查询超时
    TransactionTimeout time.Duration // 事务超时
    HealthCheckInterval time.Duration // 健康检查间隔
}

var defaultConfig = DBConfig{
    MaxOpenConns:       100,
    MaxIdleConns:       10,
    ConnMaxLifetime:    5 * time.Minute,
    ConnMaxIdleTime:    1 * time.Minute,
    QueryTimeout:       3 * time.Second,
    TransactionTimeout: 10 * time.Second,
    HealthCheckInterval: 30 * time.Second,
}

func InitDB(dsn string, cfg DBConfig) (*gorm.DB, error) {
    db, err := gorm.Open(mysql.Open(dsn), &gorm.Config{})
    if err != nil {
        return nil, err
    }

    sqlDB, err := db.DB()
    if err != nil {
        return nil, err
    }

    // 应用配置
    sqlDB.SetMaxOpenConns(cfg.MaxOpenConns)
    sqlDB.SetMaxIdleConns(cfg.MaxIdleConns)
    sqlDB.SetConnMaxLifetime(cfg.ConnMaxLifetime)
    sqlDB.SetConnMaxIdleTime(cfg.ConnMaxIdleTime)

    // 启动健康检查
    go monitorPoolHealth(db, cfg)

    return db, nil
}

// 工厂函数，自动注入超时
func (cfg DBConfig) QueryWithTimeout(ctx context.Context) context.Context {
    if _, ok := ctx.Deadline(); !ok {
        ctx, _ = context.WithTimeout(ctx, cfg.QueryTimeout)
    }
    return ctx
}
```

### 10.3 生产级日志记录

```go
import "go.uber.org/zap"

type DBLogger struct {
    logger *zap.Logger
}

func (dl *DBLogger) Trace(ctx context.Context, begin time.Time,
    fc func() (string, int64), err error) {

    elapsed := time.Since(begin)
    sql, rows := fc()

    fields := []zap.Field{
        zap.String("sql", sql),
        zap.Int64("rows", rows),
        zap.Duration("elapsed", elapsed),
    }

    // 标记超时错误
    if err != nil && errors.Is(err, context.DeadlineExceeded) {
        fields = append(fields, zap.String("error_type", "timeout"))
        dl.logger.Warn("query timeout", fields...)
        return
    }

    if err != nil {
        fields = append(fields, zap.Error(err))
        dl.logger.Error("query error", fields...)
        return
    }

    if elapsed > 1*time.Second {
        dl.logger.Warn("slow query", fields...)
    }
}
```

---

## 总结清单

- [ ] 所有数据库操作都使用 `context.WithTimeout()`
- [ ] 事务使用单一的 context 超时，而非多个短超时
- [ ] HTTP handler 中从 `request.Context()` 派生 DB context
- [ ] `defer cancel()` 用于确保资源释放
- [ ] 后台任务定期设定超时，而非单一长超时
- [ ] 监控 `sqlDB.Stats()` 检测连接泄漏
- [ ] 定期 `PingContext()` 检查连接健康
- [ ] 根据场景调整超时值（不要盲目使用 1s）
- [ ] 避免 `context.TODO()` 和无 cancel 的 `context.Background()`
- [ ] 生产环境启用慢查询日志和连接池监控

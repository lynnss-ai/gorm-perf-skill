package dbcore

import (
	"context"
	"fmt"
	"strings"

	"gorm.io/gorm"
)

// IBaseModel 通用数据库操作接口
type IBaseModel[T any] interface {
	// ==================== 插入操作 ====================
	Insert(ctx context.Context, v *T) error
	InsertBatch(ctx context.Context, v []*T, batchSize int) error

	// ==================== 更新操作 ====================
	Update(ctx context.Context, id string, v map[string]interface{}) error
	UpdateBy(ctx context.Context, v map[string]interface{}, query string, args ...interface{}) error
	Save(ctx context.Context, v *T) error

	// ==================== 删除操作 ====================
	Delete(ctx context.Context, id string) error
	DeleteByIds(ctx context.Context, ids []string) error
	DeleteBy(ctx context.Context, query string, args ...interface{}) error

	// ==================== 查询单条 ====================
	Find(ctx context.Context, id string) (*T, error)
	First(ctx context.Context, query string, args ...interface{}) (*T, error)

	// ==================== 查询列表 ====================
	ListByIds(ctx context.Context, ids []string, orders ...Order) ([]*T, error)
	List(ctx context.Context, query string, orders []Order, args ...interface{}) ([]*T, error)
	ListAll(ctx context.Context, orders ...Order) ([]*T, error)

	// ==================== 分页查询 ====================
	Page(ctx context.Context, page, pageSize int, query string, orders []Order, args ...interface{}) ([]*T, int64, error)

	// PageAfter 游标分页（大数据量推荐，避免 OFFSET 性能退化）
	// afterID 为上一页最后一条记录的 ID，首页传空字符串
	PageAfter(ctx context.Context, afterID string, pageSize int, query string, orders []Order, args ...interface{}) ([]*T, error)

	// ==================== 统计操作 ====================
	Exist(ctx context.Context, query string, args ...interface{}) (bool, error)
	Count(ctx context.Context, query string, args ...interface{}) (int64, error)
}

// maxListAllSize ListAll 的软上限，防止意外全表加载导致 OOM
// 如确有需要超过此限制，请使用 FindInBatches 代替
const maxListAllSize = 10_000

// BaseModel 通用数据库操作基础模型（泛型）
// 使用方式：嵌入到具体 Model 结构体中
//
//	type UserModel struct {
//	    dbcore.BaseModel[User]
//	}
type BaseModel[T any] struct {
	DB *gorm.DB
}

// Order 排序条件
type Order struct {
	Field string // 排序字段，对应数据库列名
	Desc  bool   // true=降序(DESC)，false=升序(ASC)
}

func (o Order) String() string {
	if o.Desc {
		return fmt.Sprintf("%s DESC", o.Field)
	}
	return fmt.Sprintf("%s ASC", o.Field)
}

// GetTxDB 获取数据库连接（优先从 ctx 中取事务连接）
func (m *BaseModel[T]) GetTxDB(ctx context.Context) *gorm.DB {
	return GetDB(ctx, m.DB).WithContext(ctx)
}

// ==================== 插入操作 ====================

func (m *BaseModel[T]) Insert(ctx context.Context, v *T) error {
	autoFillID(v)
	return m.GetTxDB(ctx).Create(v).Error
}

func (m *BaseModel[T]) InsertBatch(ctx context.Context, v []*T, batchSize int) error {
	if len(v) == 0 {
		return nil
	}
	autoFillIDBatch(v)
	if batchSize <= 0 {
		batchSize = 100
	}
	return m.GetTxDB(ctx).CreateInBatches(v, batchSize).Error
}

// ==================== 更新操作 ====================

func (m *BaseModel[T]) Update(ctx context.Context, id string, v map[string]interface{}) error {
	if id == "" {
		return gorm.ErrMissingWhereClause
	}
	return m.GetTxDB(ctx).Model(new(T)).Where("id = ?", id).Updates(v).Error
}

func (m *BaseModel[T]) UpdateBy(ctx context.Context, v map[string]interface{}, query string, args ...interface{}) error {
	if query == "" {
		return gorm.ErrMissingWhereClause
	}
	return m.GetTxDB(ctx).Model(new(T)).Where(query, args...).Updates(v).Error
}

func (m *BaseModel[T]) Save(ctx context.Context, v *T) error {
	return m.GetTxDB(ctx).Save(v).Error
}

// ==================== 删除操作 ====================

func (m *BaseModel[T]) Delete(ctx context.Context, id string) error {
	if id == "" {
		return gorm.ErrMissingWhereClause
	}
	return m.GetTxDB(ctx).Where("id = ?", id).Delete(new(T)).Error
}

func (m *BaseModel[T]) DeleteByIds(ctx context.Context, ids []string) error {
	if len(ids) == 0 {
		return nil
	}
	return m.GetTxDB(ctx).Where("id IN ?", ids).Delete(new(T)).Error
}

func (m *BaseModel[T]) DeleteBy(ctx context.Context, query string, args ...interface{}) error {
	if query == "" {
		return gorm.ErrMissingWhereClause
	}
	return m.GetTxDB(ctx).Where(query, args...).Delete(new(T)).Error
}

// ==================== 查询单条 ====================

// Find 根据主键 ID 查询单条数据
//
// 修复说明: 原版本使用 First()，会隐式追加 ORDER BY id，按主键查单条无需排序。
// 改用 Take() 语义更准确，且无额外排序开销。
func (m *BaseModel[T]) Find(ctx context.Context, id string) (*T, error) {
	var v T
	if err := m.GetTxDB(ctx).Where("id = ?", id).Take(&v).Error; err != nil {
		return nil, err
	}
	return &v, nil
}

func (m *BaseModel[T]) First(ctx context.Context, query string, args ...interface{}) (*T, error) {
	var v T
	db := m.GetTxDB(ctx)
	if query != "" {
		db = db.Where(query, args...)
	}
	if err := db.First(&v).Error; err != nil {
		return nil, err
	}
	return &v, nil
}

// ==================== 查询列表 ====================

func (m *BaseModel[T]) ListByIds(ctx context.Context, ids []string, orders ...Order) ([]*T, error) {
	if len(ids) == 0 {
		return []*T{}, nil
	}
	var list []*T
	db := applyOrders(m.GetTxDB(ctx).Where("id IN ?", ids), orders)
	return list, db.Find(&list).Error
}

func (m *BaseModel[T]) List(ctx context.Context, query string, orders []Order, args ...interface{}) ([]*T, error) {
	var list []*T
	db := m.GetTxDB(ctx)
	if query != "" {
		db = db.Where(query, args...)
	}
	db = applyOrders(db, orders)
	return list, db.Find(&list).Error
}

// ListAll 查询全部数据
//
// 修复说明: 新增 maxListAllSize 软上限（默认 10000 条），防止意外全表加载导致 OOM。
// 如需处理超大数据集，请使用 GORM 的 FindInBatches 替代。
func (m *BaseModel[T]) ListAll(ctx context.Context, orders ...Order) ([]*T, error) {
	var list []*T
	db := applyOrders(m.GetTxDB(ctx), orders)
	return list, db.Limit(maxListAllSize).Find(&list).Error
}

// ==================== 分页查询 ====================

// Page OFFSET 分页查询
//
// 修复说明: 原版本对 COUNT 和数据查询各自构建了两套完全相同的 WHERE 条件，
// 现提取公共 baseDB，COUNT 和数据查询复用同一条件，消除重复代码。
//
// 注意: OFFSET 分页在大页码（page > 1000 且 pageSize > 20）时性能退化严重，
// 此场景建议切换到 PageAfter 游标分页。
func (m *BaseModel[T]) Page(ctx context.Context, page, pageSize int, query string, orders []Order, args ...interface{}) ([]*T, int64, error) {
	var total int64

	// 构建公共 base 查询（COUNT 和数据查询复用）
	baseDB := m.GetTxDB(ctx).Model(new(T))
	if query != "" {
		baseDB = baseDB.Where(query, args...)
	}

	// 第一步：COUNT（复用 baseDB，开新 Session 避免条件累积）
	if err := baseDB.Session(&gorm.Session{}).Count(&total).Error; err != nil {
		return nil, 0, err
	}
	if total == 0 {
		return []*T{}, 0, nil
	}

	// 第二步：查询当前页数据（复用 baseDB，开新 Session）
	var list []*T
	offset := (page - 1) * pageSize
	err := applyOrders(baseDB.Session(&gorm.Session{}), orders).
		Offset(offset).Limit(pageSize).Find(&list).Error

	return list, total, err
}

// PageAfter 游标分页
//
// 相比 OFFSET 分页，游标分页无论翻到第几页性能恒定（走主键索引）。
// 适用场景：无限滚动列表、数据导出、大数据量分页。
//
// 参数:
//   - afterID: 上一页最后一条记录的 ID，首页传空字符串 ""
//   - pageSize: 每页条数
//
// 限制: 默认按 id ASC 游标，如需自定义游标字段请在子类覆写。
func (m *BaseModel[T]) PageAfter(ctx context.Context, afterID string, pageSize int, query string, orders []Order, args ...interface{}) ([]*T, error) {
	var list []*T
	db := m.GetTxDB(ctx).Model(new(T))

	if afterID != "" {
		if query != "" {
			query = "id > ? AND (" + query + ")"
			args = append([]interface{}{afterID}, args...)
		} else {
			query = "id > ?"
			args = []interface{}{afterID}
		}
	}
	if query != "" {
		db = db.Where(query, args...)
	}

	// 游标分页默认 ORDER BY id ASC
	if len(orders) == 0 {
		db = db.Order("id ASC")
	} else {
		db = applyOrders(db, orders)
	}

	return list, db.Limit(pageSize).Find(&list).Error
}

// ==================== 统计操作 ====================

func (m *BaseModel[T]) Exist(ctx context.Context, query string, args ...interface{}) (bool, error) {
	var count int64
	db := m.GetTxDB(ctx).Model(new(T))
	if query != "" {
		db = db.Where(query, args...)
	}
	err := db.Limit(1).Count(&count).Error
	return count > 0, err
}

func (m *BaseModel[T]) Count(ctx context.Context, query string, args ...interface{}) (int64, error) {
	var count int64
	db := m.GetTxDB(ctx).Model(new(T))
	if query != "" {
		db = db.Where(query, args...)
	}
	return count, db.Count(&count).Error
}

// ==================== 辅助函数 ====================

func applyOrders(db *gorm.DB, orders []Order) *gorm.DB {
	for _, order := range orders {
		if field := strings.TrimSpace(order.Field); field != "" {
			db = db.Order(order.String())
		}
	}
	return db
}

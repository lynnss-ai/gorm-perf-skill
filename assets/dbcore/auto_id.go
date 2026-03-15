package dbcore

// auto_id.go — 自动填充 ID 字段（雪花算法实现）
//
// 依赖：go get github.com/bwmarrin/snowflake
// 如不使用雪花算法，可替换为 UUID：
//   import "github.com/google/uuid"
//   func generateID() string { return uuid.New().String() }
//
// 磁盘写入：无（纯内存操作）
// 外部依赖：github.com/bwmarrin/snowflake（可替换）

import (
	"fmt"
	"reflect"
	"sync"

	"github.com/bwmarrin/snowflake"
)

var (
	sfNode     *snowflake.Node
	sfNodeOnce sync.Once
)

// initSnowflake 初始化雪花算法节点（线程安全，只初始化一次）
// nodeID 范围 0-1023，多实例部署时需保证每个实例 nodeID 不同
// 推荐从环境变量或配置中心读取：os.Getenv("SNOWFLAKE_NODE_ID")
func initSnowflake(nodeID int64) {
	sfNodeOnce.Do(func() {
		var err error
		sfNode, err = snowflake.NewNode(nodeID)
		if err != nil {
			panic(fmt.Sprintf("snowflake node init failed: %v", err))
		}
	})
}

// generateID 生成雪花 ID（字符串格式）
func generateID() string {
	// 默认节点 ID = 1，生产环境建议通过配置注入
	initSnowflake(1)
	return sfNode.Generate().String()
}

// autoFillID 用反射检查 v 的 ID 字段，若为空字符串则自动填充雪花 ID
// 支持的 struct 形式：
//   - ID string `gorm:"primaryKey"`
//   - ID string `json:"id"`
func autoFillID(v any) {
	if v == nil {
		return
	}
	rv := reflect.ValueOf(v)
	// 支持指针
	if rv.Kind() == reflect.Ptr {
		rv = rv.Elem()
	}
	if rv.Kind() != reflect.Struct {
		return
	}
	idField := rv.FieldByName("ID")
	if !idField.IsValid() || !idField.CanSet() {
		return
	}
	// 只处理 string 类型的 ID，且当前为空
	if idField.Kind() == reflect.String && idField.String() == "" {
		idField.SetString(generateID())
	}
}

// autoFillIDBatch 批量填充 ID
func autoFillIDBatch[T any](v []*T) {
	for _, item := range v {
		autoFillID(item)
	}
}

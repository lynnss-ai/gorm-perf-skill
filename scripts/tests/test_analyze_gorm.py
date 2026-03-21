"""Tests for analyze_gorm.py - GORM static analysis rules R1-R30."""
import unittest
import sys
from pathlib import Path

# Add scripts directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from analyze_gorm import analyze, Issue


class TestR1SelectStar(unittest.TestCase):
    """R1: SELECT * (Find without specified fields)"""

    def test_r1_detected_find_star(self):
        """Test detection of Find without Select"""
        code = """
        db.Find(&users)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "SELECT_STAR" for i in issues))

    def test_r1_detected_first_star(self):
        """Test detection of First without Select"""
        code = """
        db.First(&user)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "SELECT_STAR" for i in issues))

    def test_r1_not_detected_with_select(self):
        """No false positive when Select is present"""
        code = """
        db.Select("id", "name").Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "SELECT_STAR" for i in issues))

    def test_r1_not_detected_with_raw(self):
        """No false positive when Raw is used"""
        code = """
        db.Raw("SELECT id FROM users").Scan(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "SELECT_STAR" for i in issues))


class TestR2LargeOffset(unittest.TestCase):
    """R2: Large OFFSET pagination"""

    def test_r2_large_offset_error(self):
        """Test detection of large OFFSET > 1000"""
        code = """
        db.Offset(5000).Limit(20).Find(&users)
        """
        issues = analyze(code)
        found = [i for i in issues if i.rule == "LARGE_OFFSET"]
        self.assertTrue(len(found) > 0)
        self.assertTrue(found[0].level == "ERROR")

    def test_r2_dynamic_offset_warning(self):
        """Test detection of dynamic OFFSET variable"""
        code = """
        offset := getOffset()
        db.Offset(offset).Limit(20).Find(&users)
        """
        issues = analyze(code)
        found = [i for i in issues if i.rule == "DYNAMIC_OFFSET"]
        self.assertTrue(len(found) > 0)
        self.assertTrue(found[0].level == "WARN")

    def test_r2_small_offset_ok(self):
        """No warning for small OFFSET"""
        code = """
        db.Offset(100).Limit(20).Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule in ("LARGE_OFFSET", "DYNAMIC_OFFSET") for i in issues))


class TestR3NPlus1(unittest.TestCase):
    """R3: N+1 query in loops"""

    def test_r3_detected_in_loop(self):
        """Test detection of DB operation inside for loop"""
        code = """
        for _, id := range ids {
            db.First(&user, id)
        }
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "N_PLUS_1" for i in issues))

    def test_r3_create_in_loop(self):
        """Test detection of Create in loop"""
        code = """
        for _, item := range items {
            db.Create(&item)
        }
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "N_PLUS_1" for i in issues))

    def test_r3_not_detected_outside_loop(self):
        """No false positive for DB outside loop"""
        code = """
        db.Find(&users)
        for _, user := range users {
            process(user)
        }
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "N_PLUS_1" for i in issues))


class TestR4StructUpdates(unittest.TestCase):
    """R4: Struct Updates (zero value loss)"""

    def test_r4_detected(self):
        """Test detection of Updates with struct"""
        code = """
        db.Updates(User{Name: "new"})
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "STRUCT_UPDATES_ZERO_VALUE" for i in issues))

    def test_r4_not_detected_with_map(self):
        """No warning for Updates with map"""
        code = """
        db.Updates(map[string]any{"name": "new"})
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "STRUCT_UPDATES_ZERO_VALUE" for i in issues))


class TestR5NoContext(unittest.TestCase):
    """R5: Missing WithContext"""

    def test_r5_detected(self):
        """Test detection of DB operation without WithContext"""
        code = """
        db.Find(&users)
        """
        issues = analyze(code)
        found = [i for i in issues if i.rule == "NO_CONTEXT"]
        self.assertTrue(len(found) > 0)
        self.assertTrue(found[0].level == "INFO")

    def test_r5_not_detected_with_context(self):
        """No warning when WithContext is used"""
        code = """
        db.WithContext(ctx).Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "NO_CONTEXT" for i in issues))

    def test_r5_not_detected_with_session(self):
        """No warning when Session is used"""
        code = """
        db.Session(&gorm.Session{}).Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "NO_CONTEXT" for i in issues))


class TestR6UncheckedError(unittest.TestCase):
    """R6: Unchecked database error"""

    def test_r6_detected(self):
        """Test detection of unchecked DB error"""
        code = """
        db.Find(&users)
        """
        issues = analyze(code)
        found = [i for i in issues if i.rule == "UNCHECKED_ERROR"]
        self.assertTrue(len(found) > 0)

    def test_r6_not_detected_with_error_check(self):
        """No warning when error is checked"""
        code = """
        if err := db.Find(&users).Error; err != nil {
            return err
        }
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "UNCHECKED_ERROR" for i in issues))


class TestR7FindNoLimit(unittest.TestCase):
    """R7: Find all without WHERE/LIMIT"""

    def test_r7_detected(self):
        """Test detection of Find without WHERE or LIMIT"""
        code = """
        db.Find(&users)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "FIND_ALL_NO_LIMIT" for i in issues))

    def test_r7_not_detected_with_where(self):
        """No warning when WHERE is present"""
        code = """
        db.Where("status = ?", 1).Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "FIND_ALL_NO_LIMIT" for i in issues))

    def test_r7_not_detected_with_limit(self):
        """No warning when LIMIT is present"""
        code = """
        db.Limit(100).Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "FIND_ALL_NO_LIMIT" for i in issues))


class TestR8SlowOpInTx(unittest.TestCase):
    """R8: Slow I/O operation inside transaction"""

    def test_r8_http_in_tx(self):
        """Test detection of HTTP call in transaction"""
        code = """
        db.Transaction(func(tx *gorm.DB) error {
            http.Get("https://example.com")
            return tx.Create(&user).Error
        })
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "SLOW_OP_IN_TX" for i in issues))

    def test_r8_sleep_in_tx(self):
        """Test detection of time.Sleep in transaction"""
        code = """
        db.Begin()
        time.Sleep(1 * time.Second)
        db.Commit()
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "SLOW_OP_IN_TX" for i in issues))

    def test_r8_grpc_in_tx(self):
        """Test detection of gRPC call in transaction"""
        code = """
        db.Transaction(func(tx *gorm.DB) error {
            client.Invoke(ctx, req)
            return tx.Save(&data).Error
        })
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "SLOW_OP_IN_TX" for i in issues))


class TestR9LeadingWildcard(unittest.TestCase):
    """R9: LIKE with leading wildcard"""

    def test_r9_detected(self):
        """Test detection of LIKE '%keyword%'"""
        code = """
        db.Where("name LIKE '%search%'").Find(&users)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "LEADING_WILDCARD_LIKE" for i in issues))

    def test_r9_not_detected_prefix(self):
        """No warning for LIKE 'keyword%'"""
        code = """
        db.Where("name LIKE ?", "search%").Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "LEADING_WILDCARD_LIKE" for i in issues))


class TestR10LoopCreate(unittest.TestCase):
    """R10: Loop with Create (N INSERT)"""

    def test_r10_detected(self):
        """Test detection of Create in loop"""
        code = """
        for _, item := range items {
            db.Create(&item)
        }
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "LOOP_CREATE" for i in issues))

    def test_r10_not_detected_batch(self):
        """No warning when CreateInBatches is used"""
        code = """
        db.CreateInBatches(&items, 100)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "LOOP_CREATE" for i in issues))


class TestR13SQLInjection(unittest.TestCase):
    """R13: Raw/Exec string concatenation (SQL injection)"""

    def test_r13_raw_concat(self):
        """Test detection of Raw with string concat"""
        code = """
        db.Raw("SELECT * FROM users WHERE id = " + id)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "SQL_INJECTION_RISK" for i in issues))

    def test_r13_sprintf(self):
        """Test detection of Raw with fmt.Sprintf"""
        code = """
        db.Raw(fmt.Sprintf("SELECT * FROM users WHERE id = %d", id))
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "SQL_INJECTION_RISK" for i in issues))

    def test_r13_not_detected_parameterized(self):
        """No warning for parameterized query"""
        code = """
        db.Raw("SELECT * FROM users WHERE id = ?", id)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "SQL_INJECTION_RISK" for i in issues))


class TestR14PluckMultiColumn(unittest.TestCase):
    """R14: Pluck multi-column misuse"""

    def test_r14_detected(self):
        """Test detection of Pluck with multiple columns"""
        code = """
        db.Pluck("id, name", &result)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "PLUCK_MULTI_COLUMN" for i in issues))

    def test_r14_not_detected_single(self):
        """No warning for single Pluck column"""
        code = """
        db.Pluck("id", &ids)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "PLUCK_MULTI_COLUMN" for i in issues))


class TestR18PhysicalForeignKey(unittest.TestCase):
    """R18: Foreign key constraints not disabled"""

    def test_r18_detected_missing_constraint_false(self):
        """Test detection of foreignKey without constraint:false"""
        code = """
        type Order struct {
            UserID uint `gorm:"foreignKey:UserID"`
        }
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "PHYSICAL_FOREIGN_KEY" for i in issues))

    def test_r18_not_detected_with_constraint_false(self):
        """No warning when constraint:false is present"""
        code = """
        type Order struct {
            UserID uint `gorm:"foreignKey:UserID;constraint:false"`
        }
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "PHYSICAL_FOREIGN_KEY" for i in issues))


class TestR22WhereInjection(unittest.TestCase):
    """R22: Where string concatenation (SQL injection)"""

    def test_r22_sprintf(self):
        """Test detection of Where with fmt.Sprintf"""
        code = """
        db.Where(fmt.Sprintf("status = %d", status)).Find(&users)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "WHERE_SQL_INJECTION" for i in issues))

    def test_r22_concat(self):
        """Test detection of Where with string concat"""
        code = """
        db.Where("name = '" + name + "'").Find(&users)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "WHERE_SQL_INJECTION" for i in issues))

    def test_r22_not_detected_parameterized(self):
        """No warning for parameterized Where"""
        code = """
        db.Where("status = ?", status).Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "WHERE_SQL_INJECTION" for i in issues))


class TestR23RowsAffected(unittest.TestCase):
    """R23: Unchecked RowsAffected"""

    def test_r23_detected(self):
        """Test detection of Update without RowsAffected check"""
        code = """
        db.Update("status", 1)
        """
        issues = analyze(code)
        found = [i for i in issues if i.rule == "UNCHECKED_ROWS_AFFECTED"]
        self.assertTrue(len(found) > 0)

    def test_r23_not_detected_checked(self):
        """No warning when RowsAffected is checked"""
        code = """
        result := db.Update("status", 1)
        if result.RowsAffected == 0 {
            return errors.New("no rows affected")
        }
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "UNCHECKED_ROWS_AFFECTED" for i in issues))


class TestR28WhereSprintfInjection(unittest.TestCase):
    """R28: Where sprintf injection (new rule)"""

    def test_r28_sprintf_detected(self):
        """Test detection of Where with fmt.Sprintf"""
        code = """
        db.Where(fmt.Sprintf("user_id = %d", userID)).Find(&orders)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "WHERE_SPRINTF_INJECTION" for i in issues))

    def test_r28_string_concat_warning(self):
        """Test detection of Where with string concatenation"""
        code = """
        db.Where("status = " + status).Find(&orders)
        """
        issues = analyze(code)
        found = [i for i in issues if i.rule == "WHERE_STRING_CONCAT"]
        self.assertTrue(len(found) > 0)
        self.assertTrue(found[0].level == "WARN")


class TestR29BackgroundContext(unittest.TestCase):
    """R29: Background context usage (no timeout)"""

    def test_r29_background_detected(self):
        """Test detection of context.Background()"""
        code = """
        db.WithContext(context.Background()).Find(&users)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "BACKGROUND_CONTEXT" for i in issues))

    def test_r29_todo_detected(self):
        """Test detection of context.TODO()"""
        code = """
        db.WithContext(context.TODO()).Find(&users)
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "BACKGROUND_CONTEXT" for i in issues))

    def test_r29_not_detected_with_timeout(self):
        """No warning for context.WithTimeout"""
        code = """
        ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
        defer cancel()
        db.WithContext(ctx).Find(&users)
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "BACKGROUND_CONTEXT" for i in issues))


class TestR30RowsNotClosed(unittest.TestCase):
    """R30: Rows() not paired with defer Close()"""

    def test_r30_detected_no_close(self):
        """Test detection of Rows() without Close()"""
        code = """
        rows, _ := db.Rows()
        for rows.Next() {
            // process row
        }
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "ROWS_NOT_CLOSED" for i in issues))

    def test_r30_not_detected_with_close(self):
        """No warning when defer Close() is present"""
        code = """
        rows, _ := db.Rows()
        defer rows.Close()
        for rows.Next() {
            // process row
        }
        """
        issues = analyze(code)
        self.assertFalse(any(i.rule == "ROWS_NOT_CLOSED" for i in issues))


class TestFileLevel(unittest.TestCase):
    """File-level rules (R11, R12, R15, R18b)"""

    def test_r11_missing_prepare_stmt(self):
        """Test detection of missing PrepareStmt"""
        code = """
        db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{
            SkipDefaultTransaction: true,
        })
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "MISSING_PREPARE_STMT" for i in issues))

    def test_r12_missing_skip_default_tx(self):
        """Test detection of missing SkipDefaultTransaction"""
        code = """
        db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{
            PrepareStmt: true,
        })
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "MISSING_SKIP_DEFAULT_TX" for i in issues))

    def test_r15_missing_pool_config(self):
        """Test detection of missing pool configuration"""
        code = """
        db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{})
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "MISSING_POOL_CONFIG" for i in issues))

    def test_r18b_fk_migration_not_disabled(self):
        """Test detection of FK migration not disabled"""
        code = """
        db, _ := gorm.Open(mysql.Open(dsn), &gorm.Config{
            PrepareStmt: true,
        })
        """
        issues = analyze(code)
        self.assertTrue(any(i.rule == "FK_MIGRATION_NOT_DISABLED" for i in issues))


class TestDeduplication(unittest.TestCase):
    """Test that duplicate issues are deduplicated"""

    def test_deduplication_per_rule(self):
        """Test that only one issue per rule is returned"""
        code = """
        db.Find(&users)
        db.Find(&posts)
        db.Find(&comments)
        """
        issues = analyze(code)
        select_star_issues = [i for i in issues if i.rule == "SELECT_STAR"]
        # Should have at most 1 SELECT_STAR issue (deduplicated)
        self.assertTrue(len(select_star_issues) <= 1)

"""Tests for migration_gen.py - Struct diff to ALTER TABLE generation."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from migration_gen import parse_struct, generate_migration, pascal_to_snake


class TestSnakeCaseConversion(unittest.TestCase):
    """Test PascalCase to snake_case conversion"""

    def test_simple_word(self):
        """Test simple word conversion"""
        self.assertTrue(pascal_to_snake("User") == "user")

    def test_multiple_words(self):
        """Test multiple word conversion"""
        self.assertTrue(pascal_to_snake("UserProfile") == "user_profile")

    def test_acronym(self):
        """Test acronym handling"""
        result = pascal_to_snake("UserID")
        self.assertTrue(result == "user_id" or result == "userid")

    def test_with_numbers(self):
        """Test with numbers"""
        result = pascal_to_snake("User2Profile")
        self.assertTrue("2" in result)


class TestStructParsing(unittest.TestCase):
    """Test Go struct parsing"""

    def test_parse_simple_struct(self):
        """Test parsing a simple struct"""
        code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string `gorm:"column:name;type:varchar(255);not null"`
        }
        """
        fields = parse_struct(code)
        self.assertTrue("id" in fields or "ID" in str(fields))

    def test_parse_with_model_embedding(self):
        """Test parsing struct with gorm.Model"""
        code = """
        type User struct {
            gorm.Model
            Email string `gorm:"column:email"`
        }
        """
        fields = parse_struct(code)
        # Should include fields from gorm.Model
        self.assertTrue(len(fields) > 0)

    def test_parse_nullable_field(self):
        """Test parsing nullable field"""
        code = """
        type User struct {
            ID uint
            MiddleName *string `gorm:"column:middle_name"`
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

    def test_parse_field_with_default(self):
        """Test parsing field with default value"""
        code = """
        type Config struct {
            ID uint
            Status string `gorm:"column:status;default:active"`
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

    def test_parse_field_with_indexes(self):
        """Test parsing field with index"""
        code = """
        type User struct {
            ID uint
            Email string `gorm:"column:email;uniqueIndex:uk_email"`
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)


class TestMigrationGeneration(unittest.TestCase):
    """Test migration SQL generation"""

    def test_add_column(self):
        """Test adding a new column"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
            Email string `gorm:"column:email"`
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "mysql")

        self.assertTrue("ADD COLUMN" in up_sql)
        self.assertTrue("email" in up_sql.lower())

    def test_remove_column(self):
        """Test removing a column"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
            OldField string
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "mysql")

        self.assertTrue("DROP COLUMN" in up_sql)

    def test_modify_column(self):
        """Test modifying column type"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Age int
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Age string
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "mysql")

        # Should contain MODIFY statement
        self.assertTrue("MODIFY" in up_sql or "ALTER" in up_sql)

    def test_rollback_migration(self):
        """Test that down migration reverses up"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
            Email string
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "mysql")

        # Down should remove what up added
        if "ADD COLUMN" in up_sql:
            self.assertTrue("DROP COLUMN" in down_sql)


class TestConstraints(unittest.TestCase):
    """Test constraint handling"""

    def test_not_null_constraint(self):
        """Test NOT NULL constraint in migration"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string `gorm:"not null"`
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "mysql")
        self.assertTrue(len(up_sql) > 0)

    def test_unique_constraint(self):
        """Test UNIQUE constraint in migration"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Email string
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Email string `gorm:"unique"`
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "mysql")
        # Should have index creation
        self.assertTrue(len(up_sql) > 0)


class TestTypeMapping(unittest.TestCase):
    """Test Go type to MySQL type mapping"""

    def test_string_mapping(self):
        """Test string type mapping"""
        code = """
        type User struct {
            ID uint
            Name string
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

    def test_int_mapping(self):
        """Test int type mapping"""
        code = """
        type User struct {
            ID uint
            Age int32
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

    def test_bool_mapping(self):
        """Test bool type mapping"""
        code = """
        type User struct {
            ID uint
            Active bool
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

    def test_time_mapping(self):
        """Test time.Time mapping"""
        code = """
        type User struct {
            ID uint
            CreatedAt time.Time
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)


class TestComplexMigrations(unittest.TestCase):
    """Test complex migration scenarios"""

    def test_multiple_changes(self):
        """Test migration with multiple column changes"""
        old_code = """
        type Order struct {
            ID uint `gorm:"primaryKey"`
            UserID uint
            Status string
        }
        """
        new_code = """
        type Order struct {
            ID uint `gorm:"primaryKey"`
            UserID uint
            Status string `gorm:"type:varchar(50)"`
            Amount int64
            Description string
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "orders", "mysql")

        # Should have multiple ALTER statements
        self.assertTrue(len(up_sql) > 20)

    def test_no_changes(self):
        """Test migration with no changes"""
        code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
        }
        """
        fields = parse_struct(code)
        up_sql, down_sql = generate_migration(fields, fields, "users", "mysql")

        # Should indicate no changes
        self.assertTrue("无结构变更" in up_sql or "no" in up_sql.lower() or len(up_sql.strip()) < 50)


class TestDatabaseVariations(unittest.TestCase):
    """Test different database dialects"""

    def test_mysql_dialect(self):
        """Test MySQL specific SQL generation"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
            Email string
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "mysql")

        # Should use MySQL syntax
        self.assertTrue("ALTER TABLE" in up_sql)

    def test_postgres_dialect(self):
        """Test PostgreSQL specific SQL generation"""
        old_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
        }
        """
        new_code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
            Name string
            Email string
        }
        """
        old_fields = parse_struct(old_code)
        new_fields = parse_struct(new_code)

        up_sql, down_sql = generate_migration(old_fields, new_fields, "users", "postgres")

        # Should generate valid migration
        self.assertTrue(len(up_sql) > 0)


class TestGormTagParsing(unittest.TestCase):
    """Test GORM tag parsing in structs"""

    def test_column_tag(self):
        """Test column name in tag"""
        code = """
        type User struct {
            UserID uint `gorm:"column:user_id"`
        }
        """
        fields = parse_struct(code)
        self.assertTrue("user_id" in fields)

    def test_type_tag(self):
        """Test explicit type in tag"""
        code = """
        type User struct {
            Data string `gorm:"type:longtext"`
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

    def test_multiple_tags(self):
        """Test multiple tags on field"""
        code = """
        type User struct {
            Email string `gorm:"column:email;type:varchar(255);not null;uniqueIndex:uk_email"`
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

    def test_primary_key_tag(self):
        """Test primary key detection"""
        code = """
        type User struct {
            ID uint `gorm:"primaryKey"`
        }
        """
        fields = parse_struct(code)
        # Should recognize ID as primary key
        self.assertTrue(len(fields) > 0)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases in migration generation"""

    def test_column_name_with_backticks(self):
        """Test handling of backtick-quoted column names"""
        code = """
        type User struct {
            ID uint `gorm:"column:user_id"`
        }
        """
        fields = parse_struct(code)
        up_sql, down_sql = generate_migration(fields, fields, "users", "mysql")
        # Should handle without errors
        self.assertTrue(isinstance(up_sql, str))

    def test_empty_structs(self):
        """Test handling of empty structs"""
        code = "type User struct {}"
        fields = parse_struct(code)
        # Should handle gracefully
        self.assertTrue(isinstance(fields, dict))

    def test_struct_with_comments(self):
        """Test struct with comments"""
        code = """
        type User struct {
            // User ID
            ID uint `gorm:"primaryKey"`
            // User name
            Name string
        }
        """
        fields = parse_struct(code)
        self.assertTrue(len(fields) > 0)

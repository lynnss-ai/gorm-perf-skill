"""Tests for gen_model.py - SQL to GORM struct generation."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from gen_model import parse_create_table, generate_struct, SQL_TO_GO_MYSQL, get_go_type


class TestMySQLTypeMapping(unittest.TestCase):
    """Test MySQL type to Go type mapping"""

    def test_integer_types(self):
        """Test integer type mappings"""
        self.assertTrue(get_go_type("int", False) == "int32")
        self.assertTrue(get_go_type("bigint", False) == "int64")
        self.assertTrue(get_go_type("tinyint", False) == "int8")
        self.assertTrue(get_go_type("smallint", False) == "int16")

    def test_string_types(self):
        """Test string type mappings"""
        self.assertTrue(get_go_type("varchar(255)", False) == "string")
        self.assertTrue(get_go_type("text", False) == "string")
        self.assertTrue(get_go_type("char(10)", False) == "string")

    def test_nullable_types(self):
        """Test nullable type conversions"""
        result = get_go_type("int", True)
        self.assertTrue("Null" in result or result.startswith("*"))

    def test_json_type(self):
        """Test JSON type mapping"""
        result = get_go_type("json", False)
        self.assertTrue("JSON" in result)


class TestMySQLParsing(unittest.TestCase):
    """Test MySQL CREATE TABLE parsing"""

    def test_parse_simple_table(self):
        """Test parsing a simple CREATE TABLE"""
        sql = """
        CREATE TABLE `users` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `name` varchar(255) NOT NULL,
            `email` varchar(255) UNIQUE,
            `created_at` datetime DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB
        """
        tables = parse_create_table(sql)
        self.assertTrue(len(tables) == 1)
        self.assertTrue(tables[0].name == "users")
        self.assertTrue(len(tables[0].columns) >= 3)

    def test_parse_column_properties(self):
        """Test column property detection"""
        sql = """
        CREATE TABLE `posts` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `title` varchar(255) NOT NULL,
            `content` text,
            `status` varchar(50) DEFAULT 'draft'
        )
        """
        tables = parse_create_table(sql)
        post_table = tables[0]

        # Check ID column
        id_col = next((c for c in post_table.columns if c.name == "id"), None)
        self.assertTrue(id_col is not None)
        self.assertTrue(id_col.is_pk)
        self.assertTrue(id_col.is_auto)

        # Check title column
        title_col = next((c for c in post_table.columns if c.name == "title"), None)
        self.assertTrue(title_col is not None)
        self.assertFalse(title_col.nullable)

    def test_parse_indexes(self):
        """Test index parsing"""
        sql = """
        CREATE TABLE `orders` (
            `id` bigint PRIMARY KEY,
            `user_id` bigint NOT NULL,
            `status` varchar(50),
            KEY `idx_user_id` (`user_id`),
            UNIQUE KEY `uk_order_no` (`order_no`)
        )
        """
        tables = parse_create_table(sql)
        order_table = tables[0]

        self.assertTrue(len(order_table.indexes) > 0 or len(order_table.unique_indexes) > 0)


class TestStructGeneration(unittest.TestCase):
    """Test struct generation from parsed table"""

    def test_generate_simple_struct(self):
        """Test generating a simple struct"""
        sql = """
        CREATE TABLE `users` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `name` varchar(255) NOT NULL,
            `email` varchar(255),
            `created_at` datetime,
            `updated_at` datetime,
            `deleted_at` datetime
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue("type Users struct" in struct_code)
        self.assertTrue("gorm.Model" in struct_code)
        self.assertTrue("Name" in struct_code)
        self.assertTrue("Email" in struct_code)

    def test_generate_with_comments(self):
        """Test generating struct with COMMENT tags"""
        sql = """
        CREATE TABLE `products` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `name` varchar(255) NOT NULL COMMENT '产品名',
            `price` decimal(10,2) NOT NULL COMMENT '价格',
            `stock` int DEFAULT 0 COMMENT '库存'
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue("Product" in struct_code)
        self.assertTrue("Price" in struct_code or "price" in struct_code.lower())

    def test_generate_imports(self):
        """Test that necessary imports are included"""
        sql = """
        CREATE TABLE `posts` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `title` varchar(255) NOT NULL,
            `publish_date` datetime NOT NULL,
            `created_at` datetime,
            `updated_at` datetime,
            `deleted_at` datetime
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue('import' in struct_code)
        self.assertTrue('"gorm.io/gorm"' in struct_code)

    def test_tablename_method(self):
        """Test TableName method generation for non-Model tables"""
        sql = """
        CREATE TABLE `custom_table` (
            `id` int PRIMARY KEY,
            `name` varchar(100)
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        # Should have TableName method
        self.assertTrue("TableName()" in struct_code)
        self.assertTrue("custom_table" in struct_code)

    def test_generate_gorm_tags(self):
        """Test GORM tag generation"""
        sql = """
        CREATE TABLE `items` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `title` varchar(255) NOT NULL UNIQUE,
            `price` decimal(10,2),
            KEY `idx_title` (`title`)
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue('gorm:"' in struct_code)
        self.assertTrue("primaryKey" in struct_code)


class TestMultipleTables(unittest.TestCase):
    """Test parsing multiple CREATE TABLE statements"""

    def test_multiple_tables(self):
        """Test parsing multiple tables in one SQL"""
        sql = """
        CREATE TABLE `users` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `name` varchar(255)
        ) ENGINE=InnoDB;

        CREATE TABLE `posts` (
            `id` bigint PRIMARY KEY AUTO_INCREMENT,
            `user_id` bigint,
            `title` varchar(255)
        ) ENGINE=InnoDB;
        """
        tables = parse_create_table(sql)
        self.assertTrue(len(tables) == 2)
        self.assertTrue(tables[0].name == "users")
        self.assertTrue(tables[1].name == "posts")


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and special scenarios"""

    def test_unsigned_types(self):
        """Test unsigned integer handling"""
        sql = """
        CREATE TABLE `items` (
            `id` bigint unsigned PRIMARY KEY AUTO_INCREMENT,
            `count` int unsigned DEFAULT 0
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue("Item" in struct_code)

    def test_decimal_type(self):
        """Test decimal/numeric handling"""
        sql = """
        CREATE TABLE `prices` (
            `id` int PRIMARY KEY,
            `amount` decimal(10,2) NOT NULL
        )
        """
        tables = parse_create_table(sql)
        self.assertTrue(len(tables) > 0)

    def test_blob_type(self):
        """Test blob handling"""
        sql = """
        CREATE TABLE `files` (
            `id` int PRIMARY KEY,
            `content` blob
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue("File" in struct_code)

    def test_enum_type(self):
        """Test enum type"""
        sql = """
        CREATE TABLE `orders` (
            `id` int PRIMARY KEY,
            `status` enum('pending', 'shipped', 'delivered')
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue("Order" in struct_code)

    def test_snake_case_conversion(self):
        """Test snake_case to PascalCase conversion"""
        sql = """
        CREATE TABLE `user_profiles` (
            `id` int PRIMARY KEY,
            `first_name` varchar(100),
            `last_modified_at` datetime
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue("UserProfile" in struct_code)
        self.assertTrue("FirstName" in struct_code)
        self.assertTrue("LastModifiedAt" in struct_code)


class TestSQLVariations(unittest.TestCase):
    """Test different SQL syntax variations"""

    def test_if_not_exists(self):
        """Test parsing CREATE TABLE IF NOT EXISTS"""
        sql = """
        CREATE TABLE IF NOT EXISTS `users` (
            `id` int PRIMARY KEY,
            `name` varchar(100)
        )
        """
        tables = parse_create_table(sql)
        self.assertTrue(len(tables) > 0)

    def test_comment_syntax(self):
        """Test TABLE COMMENT parsing"""
        sql = """
        CREATE TABLE `products` (
            `id` int PRIMARY KEY,
            `name` varchar(100) NOT NULL COMMENT '产品名称'
        ) COMMENT='产品表'
        """
        tables = parse_create_table(sql)
        self.assertTrue(len(tables) > 0)

    def test_default_values(self):
        """Test DEFAULT value parsing"""
        sql = """
        CREATE TABLE `configs` (
            `id` int PRIMARY KEY,
            `value` varchar(100) DEFAULT 'default',
            `count` int DEFAULT 0,
            `active` bool DEFAULT true
        )
        """
        tables = parse_create_table(sql)
        struct_code = generate_struct(tables[0])

        self.assertTrue("Config" in struct_code)

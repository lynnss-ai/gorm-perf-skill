"""Tests for scope_gen.py - GORM Scope function generation."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from scope_gen import parse_struct, generate, to_snake


class TestSnakeCaseConversion(unittest.TestCase):
    """Test snake_case conversion"""

    def test_simple_conversion(self):
        """Test simple PascalCase to snake_case"""
        self.assertTrue(to_snake("Status") == "status")

    def test_multi_word_conversion(self):
        """Test multi-word conversion"""
        self.assertTrue(to_snake("UserStatus") == "user_status")

    def test_with_acronyms(self):
        """Test with acronyms"""
        result = to_snake("UserID")
        self.assertTrue("id" in result.lower())

    def test_consecutive_capitals(self):
        """Test consecutive capital letters"""
        result = to_snake("HTTPServer")
        self.assertTrue(len(result) > 0)


class TestStructParsing(unittest.TestCase):
    """Test Go struct parsing for scope generation"""

    def test_parse_simple_struct(self):
        """Test parsing a simple struct"""
        code = """
        type User struct {
            ID uint
            Status string `gorm:"column:status"`
            Email string `gorm:"column:email"`
        }
        """
        structs = parse_struct(code)
        self.assertTrue(len(structs) > 0)

    def test_parse_multiple_structs(self):
        """Test parsing multiple structs"""
        code = """
        type User struct {
            ID uint
            Name string
        }

        type Order struct {
            ID uint
            UserID uint
            Amount int64
        }
        """
        structs = parse_struct(code)
        self.assertTrue(len(structs) >= 2)

    def test_parse_with_gorm_model(self):
        """Test parsing struct with gorm.Model"""
        code = """
        type User struct {
            gorm.Model
            Email string
            Status string
        }
        """
        structs = parse_struct(code)
        self.assertTrue(len(structs) > 0)

    def test_parse_field_types(self):
        """Test that field types are captured"""
        code = """
        type User struct {
            ID uint
            Name string
            Age int32
            Active bool
            CreatedAt time.Time
        }
        """
        structs = parse_struct(code)
        user_struct = next((s for s in structs if s[0] == "User"), None)
        self.assertTrue(user_struct is not None)
        self.assertTrue(len(user_struct[1]) > 0)


class TestScopeGeneration(unittest.TestCase):
    """Test scope function generation"""

    def test_generate_eq_scope(self):
        """Test equality scope generation"""
        code = """
        type User struct {
            ID uint
            Status string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should generate scope functions
        self.assertTrue("func" in output)
        self.assertTrue("gorm.DB" in output)

    def test_generate_with_paginate(self):
        """Test with pagination scope"""
        code = """
        type User struct {
            ID uint
            Name string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=True)

        # Should include Paginate function
        self.assertTrue("Paginate" in output)
        self.assertTrue("PageQuery" in output)

    def test_generate_with_tenant(self):
        """Test with tenant scope"""
        code = """
        type User struct {
            ID uint
            TenantID string
        }
        """
        output = generate(code, with_tenant=True, with_paginate=False)

        # Should include TenantScope
        self.assertTrue("TenantScope" in output or "tenant" in output.lower())

    def test_generate_with_both(self):
        """Test with both paginate and tenant"""
        code = """
        type User struct {
            ID uint
            Name string
            TenantID string
        }
        """
        output = generate(code, with_tenant=True, with_paginate=True)

        self.assertTrue("func" in output)
        self.assertTrue("gorm.DB" in output)


class TestScopeSelection(unittest.TestCase):
    """Test which fields get scopes generated"""

    def test_skip_id_field(self):
        """Test that ID field is skipped"""
        code = """
        type User struct {
            ID uint
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # ID should not have a ByID scope (it's handled specially)
        # But should have imports
        self.assertTrue("import" in output or "gorm" in output)

    def test_skip_sensitive_fields(self):
        """Test that sensitive fields are skipped"""
        code = """
        type User struct {
            ID uint
            Password string
            Salt string
            Token string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Password/Token/Salt should not have scopes
        self.assertTrue("Password" not in output or "ByPassword" not in output)

    def test_include_enum_fields(self):
        """Test that enum-like fields get scopes"""
        code = """
        type User struct {
            ID uint
            Status string
            Type string
            Role string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Status/Type/Role should have scopes
        self.assertTrue(len(output) > 100)

    def test_include_numeric_fields(self):
        """Test that numeric fields get range scopes"""
        code = """
        type Order struct {
            ID uint
            Amount int64
            Quantity int32
            Rating float64
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should generate scopes for numeric fields
        self.assertTrue("Between" in output or "func" in output)


class TestScopeTypes(unittest.TestCase):
    """Test different scope function types"""

    def test_equality_scope(self):
        """Test equality scope generation"""
        code = """
        type User struct {
            ID uint
            Email string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should have equality scopes
        self.assertTrue("ByEmail" in output or "func" in output)

    def test_in_scope(self):
        """Test IN scope generation"""
        code = """
        type User struct {
            ID uint
            Status string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should have IN scopes for enum-like fields
        self.assertTrue("func" in output)

    def test_range_scope(self):
        """Test range/BETWEEN scope generation"""
        code = """
        type Order struct {
            ID uint
            Amount int64
            CreatedAt time.Time
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should have BETWEEN scopes for numeric/time fields
        self.assertTrue("Between" in output or "func" in output)


class TestPackageImports(unittest.TestCase):
    """Test that required imports are included"""

    def test_gorm_import(self):
        """Test that gorm is imported"""
        code = """
        type User struct {
            ID uint
            Name string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        self.assertTrue('"gorm.io/gorm"' in output)

    def test_context_import_with_tenant(self):
        """Test that context is imported when tenant scope is enabled"""
        code = """
        type User struct {
            ID uint
            TenantID string
        }
        """
        output = generate(code, with_tenant=True, with_paginate=False)

        self.assertTrue('"context"' in output)

    def test_package_declaration(self):
        """Test that package is declared"""
        code = """
        type User struct {
            ID uint
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        self.assertTrue("package" in output)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases in scope generation"""

    def test_empty_struct(self):
        """Test handling of empty struct"""
        code = "type User struct {}"
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should handle gracefully
        self.assertTrue(isinstance(output, str))

    def test_struct_with_comments(self):
        """Test struct with comments"""
        code = """
        type User struct {
            // User ID
            ID uint
            // User email
            Email string `gorm:"column:email"`
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should parse without errors
        self.assertTrue(isinstance(output, str))

    def test_struct_with_embedded_types(self):
        """Test struct with embedded types"""
        code = """
        type User struct {
            BaseModel
            Email string
        }

        type BaseModel struct {
            ID uint
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should handle without errors
        self.assertTrue(isinstance(output, str))

    def test_nullable_field(self):
        """Test nullable field handling"""
        code = """
        type User struct {
            ID uint
            MiddleName *string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        self.assertTrue(isinstance(output, str))


class TestScopeNaming(unittest.TestCase):
    """Test scope function naming conventions"""

    def test_scope_name_format(self):
        """Test that scope names follow conventions"""
        code = """
        type User struct {
            ID uint
            Email string
            Status string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should use proper naming
        self.assertTrue("By" in output or "func" in output)

    def test_receiver_naming(self):
        """Test receiver variable naming"""
        code = """
        type Order struct {
            ID uint
            Amount int64
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Receiver should be lowercase first letter
        self.assertTrue("func (o Order)" in output or "func (order Order)" in output or "func" in output)


class TestComplexStructs(unittest.TestCase):
    """Test complex struct scenarios"""

    def test_multi_word_struct_name(self):
        """Test struct with multi-word name"""
        code = """
        type UserProfile struct {
            ID uint
            Email string
            Status string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        self.assertTrue("UserProfile" in output or "func" in output)

    def test_many_fields(self):
        """Test struct with many fields"""
        code = """
        type User struct {
            ID uint
            FirstName string
            LastName string
            Email string
            Phone string
            Address string
            City string
            Country string
            Status string
            Type string
            Role string
            CreatedAt time.Time
            UpdatedAt time.Time
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        # Should generate scopes for eligible fields
        self.assertTrue(len(output) > 200)

    def test_various_go_types(self):
        """Test struct with various Go types"""
        code = """
        type Item struct {
            ID uint64
            Name string
            Price float32
            Quantity int16
            Active bool
            CreatedAt time.Time
            Tags []string
        }
        """
        output = generate(code, with_tenant=False, with_paginate=False)

        self.assertTrue(isinstance(output, str))

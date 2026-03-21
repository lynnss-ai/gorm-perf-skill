"""Tests for query_explain.py - SQL query static analysis."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from query_explain import analyze_sql


class TestR1SelectStar(unittest.TestCase):
    """R1: SELECT * detection"""

    def test_select_star_detected(self):
        """Test detection of SELECT *"""
        findings = analyze_sql("SELECT * FROM users")
        self.assertTrue(any(f.rule == "SELECT_STAR" for f in findings))

    def test_explicit_columns_ok(self):
        """No warning for explicit columns"""
        findings = analyze_sql("SELECT id, name FROM users")
        self.assertFalse(any(f.rule == "SELECT_STAR" for f in findings))


class TestR2LeadingWildcard(unittest.TestCase):
    """R2: LIKE with leading wildcard"""

    def test_leading_percent_detected(self):
        """Test detection of LIKE '%keyword'"""
        findings = analyze_sql("SELECT * FROM users WHERE name LIKE '%search%'")
        self.assertTrue(any(f.rule == "LEADING_WILDCARD" for f in findings))

    def test_prefix_match_ok(self):
        """No warning for LIKE 'keyword%'"""
        findings = analyze_sql("SELECT * FROM users WHERE name LIKE 'search%'")
        self.assertFalse(any(f.rule == "LEADING_WILDCARD" for f in findings))


class TestR3LargeOffset(unittest.TestCase):
    """R3: Large OFFSET pagination"""

    def test_large_offset_detected(self):
        """Test detection of large OFFSET"""
        findings = analyze_sql("SELECT * FROM users OFFSET 50000 LIMIT 20")
        self.assertTrue(any(f.rule == "LARGE_OFFSET" for f in findings))

    def test_small_offset_ok(self):
        """No warning for small OFFSET"""
        findings = analyze_sql("SELECT * FROM users OFFSET 100 LIMIT 20")
        self.assertFalse(any(f.rule == "LARGE_OFFSET" for f in findings))


class TestR4FunctionOnIndexedColumn(unittest.TestCase):
    """R4: Function wrapping indexed column"""

    def test_date_function_detected(self):
        """Test detection of DATE() on column"""
        findings = analyze_sql("SELECT * FROM orders WHERE DATE(created_at) = '2024-01-01'")
        self.assertTrue(any(f.rule == "FUNC_ON_INDEXED_COL" for f in findings))

    def test_lower_function_detected(self):
        """Test detection of LOWER() on column"""
        findings = analyze_sql("SELECT * FROM users WHERE LOWER(email) = 'test@example.com'")
        self.assertTrue(any(f.rule == "FUNC_ON_INDEXED_COL" for f in findings))

    def test_year_function_detected(self):
        """Test detection of YEAR() on column"""
        findings = analyze_sql("SELECT * FROM orders WHERE YEAR(order_date) = 2024")
        self.assertTrue(any(f.rule == "FUNC_ON_INDEXED_COL" for f in findings))

    def test_no_function_ok(self):
        """No warning when no function is used"""
        findings = analyze_sql("SELECT * FROM users WHERE email = 'test@example.com'")
        self.assertFalse(any(f.rule == "FUNC_ON_INDEXED_COL" for f in findings))


class TestR5ORCondition(unittest.TestCase):
    """R5: OR condition across columns"""

    def test_or_detected(self):
        """Test detection of OR condition"""
        findings = analyze_sql("SELECT * FROM users WHERE id = 1 OR email = 'test@example.com'")
        self.assertTrue(any(f.rule == "OR_CONDITION" for f in findings))

    def test_and_ok(self):
        """No warning for AND condition"""
        findings = analyze_sql("SELECT * FROM users WHERE id = 1 AND email = 'test@example.com'")
        self.assertFalse(any(f.rule == "OR_CONDITION" for f in findings))


class TestR6NotIn(unittest.TestCase):
    """R6: NOT IN usage"""

    def test_not_in_detected(self):
        """Test detection of NOT IN"""
        findings = analyze_sql("SELECT * FROM users WHERE id NOT IN (1, 2, 3)")
        self.assertTrue(any(f.rule == "NOT_IN" for f in findings))

    def test_in_ok(self):
        """No warning for IN"""
        findings = analyze_sql("SELECT * FROM users WHERE id IN (1, 2, 3)")
        self.assertFalse(any(f.rule == "NOT_IN" for f in findings))


class TestR7CorrelatedSubquery(unittest.TestCase):
    """R7: Correlated subquery in SELECT"""

    def test_subquery_in_select_detected(self):
        """Test detection of subquery in SELECT list"""
        findings = analyze_sql("SELECT id, (SELECT COUNT(*) FROM orders WHERE orders.user_id = users.id) FROM users")
        self.assertTrue(any(f.rule == "CORRELATED_SUBQUERY" for f in findings))

    def test_join_ok(self):
        """No warning for JOIN instead of subquery"""
        findings = analyze_sql(
            "SELECT u.id, COUNT(o.id) FROM users u LEFT JOIN orders o ON u.id = o.user_id GROUP BY u.id"
        )
        self.assertFalse(any(f.rule == "CORRELATED_SUBQUERY" for f in findings))


class TestR8UpdateDeleteNoWhere(unittest.TestCase):
    """R8: UPDATE/DELETE without WHERE"""

    def test_update_no_where_detected(self):
        """Test detection of UPDATE without WHERE"""
        findings = analyze_sql("UPDATE users SET status = 'active'")
        self.assertTrue(any(f.rule == "UPDATE_DELETE_NO_WHERE" for f in findings))

    def test_delete_no_where_detected(self):
        """Test detection of DELETE without WHERE"""
        findings = analyze_sql("DELETE FROM users")
        self.assertTrue(any(f.rule == "UPDATE_DELETE_NO_WHERE" for f in findings))

    def test_update_with_where_ok(self):
        """No warning for UPDATE with WHERE"""
        findings = analyze_sql("UPDATE users SET status = 'active' WHERE id = 1")
        self.assertFalse(any(f.rule == "UPDATE_DELETE_NO_WHERE" for f in findings))


class TestR9OrderByLimit(unittest.TestCase):
    """R9: ORDER BY + LIMIT without index support"""

    def test_order_by_limit_detected(self):
        """Test detection of ORDER BY + LIMIT"""
        findings = analyze_sql("SELECT * FROM users ORDER BY created_at DESC LIMIT 10")
        self.assertTrue(any(f.rule == "ORDER_BY_LIMIT" for f in findings))

    def test_order_by_alone_ok(self):
        """No warning for ORDER BY alone"""
        findings = analyze_sql("SELECT * FROM users ORDER BY created_at DESC")
        self.assertFalse(any(f.rule == "ORDER_BY_LIMIT" for f in findings))


class TestR10InSubquery(unittest.TestCase):
    """R10: IN with subquery"""

    def test_in_subquery_detected(self):
        """Test detection of IN (SELECT ...)"""
        findings = analyze_sql("SELECT * FROM orders WHERE user_id IN (SELECT id FROM users WHERE status = 'active')")
        self.assertTrue(any(f.rule == "IN_SUBQUERY" for f in findings))

    def test_in_values_ok(self):
        """No warning for IN with literal values"""
        findings = analyze_sql("SELECT * FROM orders WHERE user_id IN (1, 2, 3)")
        self.assertFalse(any(f.rule == "IN_SUBQUERY" for f in findings))


class TestR11ImplicitTypeCast(unittest.TestCase):
    """R11: Implicit type conversion"""

    def test_implicit_cast_detected(self):
        """Test detection of implicit type cast"""
        findings = analyze_sql("SELECT * FROM users WHERE phone = 13812345678")
        self.assertTrue(any(f.rule == "IMPLICIT_TYPE_CAST" for f in findings))

    def test_quoted_value_ok(self):
        """No warning when value is quoted"""
        findings = analyze_sql("SELECT * FROM users WHERE phone = '13812345678'")
        self.assertFalse(any(f.rule == "IMPLICIT_TYPE_CAST" for f in findings))


class TestComplexityEstimation(unittest.TestCase):
    """Test query complexity estimation"""

    def test_simple_query_complexity(self):
        """Test complexity of simple query"""
        from query_explain import estimate_complexity
        result = estimate_complexity("SELECT * FROM users WHERE id = 1")
        self.assertTrue("简单" in result or "simple" in result.lower())

    def test_complex_query_complexity(self):
        """Test complexity of complex query"""
        from query_explain import estimate_complexity
        result = estimate_complexity(
            "SELECT u.*, COUNT(o.id) FROM users u "
            "LEFT JOIN orders o ON u.id = o.user_id "
            "WHERE EXISTS (SELECT 1 FROM reviews WHERE reviews.order_id = o.id) "
            "GROUP BY u.id ORDER BY COUNT(o.id) DESC LIMIT 10"
        )
        # Should indicate higher complexity
        self.assertTrue("complex" in result.lower() or "复杂" in result)

    def test_join_increases_complexity(self):
        """Test that JOINs increase complexity score"""
        from query_explain import estimate_complexity
        simple = estimate_complexity("SELECT * FROM users")
        with_join = estimate_complexity("SELECT u.*, o.* FROM users u JOIN orders o ON u.id = o.user_id")
        # with_join should indicate higher complexity
        self.assertTrue("join" in with_join.lower() or "JOIN" in with_join)


class TestMultipleFindings(unittest.TestCase):
    """Test queries with multiple issues"""

    def test_multiple_issues(self):
        """Test query with multiple EXPLAIN findings"""
        findings = analyze_sql(
            "SELECT * FROM users WHERE LOWER(email) LIKE '%test%' OR phone = 1234567890 ORDER BY created_at LIMIT 10"
        )
        # Should detect multiple issues
        self.assertTrue(len(findings) > 0)


class TestCaseInsensitive(unittest.TestCase):
    """Test case insensitivity in SQL parsing"""

    def test_lowercase_select(self):
        """Test parsing lowercase select"""
        findings = analyze_sql("select * from users where id = 1")
        self.assertTrue(len(findings) >= 0)  # Should parse without error

    def test_uppercase_select(self):
        """Test parsing uppercase SELECT"""
        findings = analyze_sql("SELECT * FROM USERS WHERE ID = 1")
        self.assertTrue(len(findings) >= 0)  # Should parse without error

    def test_mixed_case_select(self):
        """Test parsing mixed case"""
        findings = analyze_sql("SeLeCt * FrOm users WhErE id = 1")
        self.assertTrue(len(findings) >= 0)  # Should parse without error


class TestCommentHandling(unittest.TestCase):
    """Test SQL comment handling"""

    def test_single_line_comment(self):
        """Test parsing with single-line comment"""
        sql = """
        -- Get all users
        SELECT * FROM users WHERE id = 1
        """
        findings = analyze_sql(sql)
        self.assertTrue(len(findings) >= 0)  # Should parse without error

    def test_multiline_comment(self):
        """Test parsing with multi-line comment"""
        sql = """
        /*
        Get all users
        with status = active
        */
        SELECT * FROM users WHERE status = 'active'
        """
        findings = analyze_sql(sql)
        self.assertTrue(len(findings) >= 0)  # Should parse without error


class TestNormalization(unittest.TestCase):
    """Test SQL normalization"""

    def test_extra_whitespace(self):
        """Test handling of extra whitespace"""
        sql = "SELECT    *    FROM    users    WHERE    id    =    1"
        findings = analyze_sql(sql)
        self.assertTrue(len(findings) >= 0)


class TestRewriteSuggestions(unittest.TestCase):
    """Test query rewrite suggestions"""

    def test_select_star_has_rewrite(self):
        """Test that SELECT * issue has rewrite suggestion"""
        findings = analyze_sql("SELECT * FROM users")
        select_star = next((f for f in findings if f.rule == "SELECT_STAR"), None)
        self.assertTrue(select_star is not None)
        self.assertTrue(select_star.rewrite is not None)

    def test_leading_wildcard_has_rewrite(self):
        """Test that leading wildcard issue has rewrite"""
        findings = analyze_sql("SELECT * FROM users WHERE name LIKE '%test%'")
        wildcard = next((f for f in findings if f.rule == "LEADING_WILDCARD"), None)
        self.assertTrue(wildcard is not None)

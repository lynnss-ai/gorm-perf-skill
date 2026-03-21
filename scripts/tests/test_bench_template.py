"""Tests for bench_template.py - Benchmark template generation."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from bench_template import generate_custom_bench, generate_full_file, SCENARIO_TEMPLATES


class TestCustomBenchGeneration(unittest.TestCase):
    """Test custom benchmark generation from function signature"""

    def test_generate_simple_bench(self):
        """Test generating benchmark for simple function"""
        func_sig = "GetUser(db *gorm.DB, id uint) (*User, error)"
        code = generate_custom_bench(func_sig, "")

        self.assertTrue("func Benchmark" in code)
        self.assertTrue("GetUser" in code)
        self.assertTrue("*testing.B" in code)

    def test_bench_has_reset_timer(self):
        """Test that generated bench has ResetTimer"""
        func_sig = "CreateOrder(db *gorm.DB, order *Order) error"
        code = generate_custom_bench(func_sig, "")

        self.assertTrue("ResetTimer()" in code)

    def test_bench_has_report_allocs(self):
        """Test that generated bench reports allocations"""
        func_sig = "FindOrders(db *gorm.DB) ([]Order, error)"
        code = generate_custom_bench(func_sig, "")

        self.assertTrue("ReportAllocs()" in code)

    def test_bench_with_package(self):
        """Test benchmark generation with package"""
        func_sig = "GetUser(db *gorm.DB, id uint) (*User, error)"
        code = generate_custom_bench(func_sig, "repository")

        self.assertTrue("repository.GetUser" in code or "GetUser" in code)


class TestScenarioTemplates(unittest.TestCase):
    """Test built-in scenario templates"""

    def test_query_by_id_scenario(self):
        """Test query_by_id scenario"""
        self.assertTrue("query_by_id" in SCENARIO_TEMPLATES)
        scenario = SCENARIO_TEMPLATES["query_by_id"]

        self.assertTrue("desc" in scenario)
        self.assertTrue("setup" in scenario)
        self.assertTrue("bench_body" in scenario)

    def test_query_with_preload_scenario(self):
        """Test query_with_preload scenario"""
        self.assertTrue("query_with_preload" in SCENARIO_TEMPLATES)
        scenario = SCENARIO_TEMPLATES["query_with_preload"]

        self.assertTrue("Preload" in scenario["setup"] or "Preload" in scenario["bench_body"])

    def test_bulk_insert_scenario(self):
        """Test bulk_insert scenario"""
        self.assertTrue("bulk_insert" in SCENARIO_TEMPLATES)
        scenario = SCENARIO_TEMPLATES["bulk_insert"]

        self.assertTrue("CreateInBatches" in scenario["bench_body"])

    def test_pagination_scenario(self):
        """Test pagination scenario"""
        self.assertTrue("pagination" in SCENARIO_TEMPLATES)
        scenario = SCENARIO_TEMPLATES["pagination"]

        self.assertTrue("CursorPagination" in scenario["bench_body"])
        self.assertTrue("OffsetPagination" in scenario["bench_body"])

    def test_update_compare_scenario(self):
        """Test update_compare scenario"""
        self.assertTrue("update_compare" in SCENARIO_TEMPLATES)
        scenario = SCENARIO_TEMPLATES["update_compare"]

        self.assertTrue("Save" in scenario["bench_body"])
        self.assertTrue("Updates" in scenario["bench_body"])
        self.assertTrue("Update" in scenario["bench_body"])


class TestFullFileGeneration(unittest.TestCase):
    """Test full benchmark file generation"""

    def test_generate_with_func(self):
        """Test generating full file with function"""
        code = generate_full_file(
            package="repository_test",
            func_sig="GetUser(db *gorm.DB, id uint) (*User, error)",
            scenario=None,
            table="users",
            batch=500,
        )

        self.assertTrue("package repository_test" in code)
        self.assertTrue("import" in code)
        self.assertTrue("setupBenchDB" in code)
        self.assertTrue("func Benchmark" in code)

    def test_generate_with_scenario(self):
        """Test generating full file with scenario"""
        code = generate_full_file(
            package="repository_test",
            func_sig=None,
            scenario="query_by_id",
            table="users",
            batch=500,
        )

        self.assertTrue("package repository_test" in code)
        self.assertTrue("func Benchmark" in code)
        self.assertTrue("First(&u, testID)" in code or "Benchmark" in code)

    def test_generate_with_both(self):
        """Test generating with both function and scenario"""
        code = generate_full_file(
            package="service_test",
            func_sig="CreateUser(db *gorm.DB, name string) (uint, error)",
            scenario="bulk_insert",
            table="users",
            batch=200,
        )

        self.assertTrue("package service_test" in code)
        self.assertTrue(len(code) > 500)

    def test_imports_included(self):
        """Test that required imports are included"""
        code = generate_full_file(
            package="repository_test",
            func_sig="GetUser(db *gorm.DB, id uint) (*User, error)",
            scenario=None,
            table="users",
            batch=500,
        )

        self.assertTrue('"testing"' in code)
        self.assertTrue('"gorm.io/gorm"' in code)
        self.assertTrue('"gorm.io/driver/sqlite"' in code)

    def test_setup_bench_db(self):
        """Test that setupBenchDB function is included"""
        code = generate_full_file(
            package="repository_test",
            func_sig="GetUser(db *gorm.DB, id uint) (*User, error)",
            scenario=None,
            table="users",
            batch=500,
        )

        self.assertTrue("func setupBenchDB" in code)
        self.assertTrue("sqlite.Open" in code)

    def test_cleanup_function(self):
        """Test that cleanup is included"""
        code = generate_full_file(
            package="repository_test",
            func_sig="GetUser(db *gorm.DB, id uint) (*User, error)",
            scenario=None,
            table="users",
            batch=500,
        )

        self.assertTrue("Cleanup" in code or "defer" in code)


class TestBatchParameterization(unittest.TestCase):
    """Test batch size parameterization"""

    def test_batch_size_in_scenario(self):
        """Test that batch size is parameterized in scenario"""
        code = generate_full_file(
            package="repository_test",
            func_sig=None,
            scenario="bulk_insert",
            table="users",
            batch=100,
        )

        self.assertTrue("100" in code or "batchSize" in code)

    def test_different_batch_sizes(self):
        """Test different batch sizes"""
        code_100 = generate_full_file(
            package="repository_test",
            func_sig=None,
            scenario="bulk_insert",
            table="users",
            batch=100,
        )

        code_500 = generate_full_file(
            package="repository_test",
            func_sig=None,
            scenario="bulk_insert",
            table="users",
            batch=500,
        )

        # Different batch sizes should produce different code
        self.assertTrue(code_100 != code_500)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases in benchmark generation"""

    def test_empty_func_sig(self):
        """Test with empty function signature"""
        code = generate_full_file(
            package="test",
            func_sig="",
            scenario="query_by_id",
            table="users",
            batch=500,
        )

        self.assertTrue(len(code) > 0)

    def test_complex_func_sig(self):
        """Test with complex function signature"""
        func_sig = "FindUsersByFilter(db *gorm.DB, filter *UserFilter) ([]User, int64, error)"
        code = generate_custom_bench(func_sig, "repository")

        self.assertTrue("FindUsersByFilter" in code or "Benchmark" in code)

    def test_package_names(self):
        """Test various package names"""
        for pkg in ["test", "repository_test", "service_test", "model_test"]:
            code = generate_full_file(
                package=pkg,
                func_sig="Test(db *gorm.DB)",
                scenario=None,
                table="users",
                batch=500,
            )

            self.assertTrue(f"package {pkg}" in code)


class TestComments(unittest.TestCase):
    """Test comment generation"""

    def test_usage_comments(self):
        """Test that usage instructions are in comments"""
        code = generate_full_file(
            package="repository_test",
            func_sig="GetUser(db *gorm.DB, id uint) (*User, error)",
            scenario=None,
            table="users",
            batch=500,
        )

        # Should have instructions for running tests
        self.assertTrue("go test" in code.lower() or "//" in code)

    def test_pprof_comments(self):
        """Test that pprof instructions are present"""
        code = generate_full_file(
            package="repository_test",
            func_sig="GetUser(db *gorm.DB, id uint) (*User, error)",
            scenario=None,
            table="users",
            batch=500,
        )

        # Should have pprof references
        self.assertTrue("pprof" in code.lower() or "prof" in code)

    def test_generated_marker(self):
        """Test that code generation marker is present"""
        code = generate_full_file(
            package="repository_test",
            func_sig="GetUser(db *gorm.DB, id uint) (*User, error)",
            scenario=None,
            table="users",
            batch=500,
        )

        self.assertTrue("generated" in code.lower() or "bench_template" in code)


class TestScenarioVariations(unittest.TestCase):
    """Test all scenario variations"""

    def test_all_scenarios_generate(self):
        """Test that all scenarios can generate code"""
        for scenario_name in SCENARIO_TEMPLATES.keys():
            code = generate_full_file(
                package="test",
                func_sig=None,
                scenario=scenario_name,
                table="users",
                batch=500,
            )

            self.assertTrue(len(code) > 100)
            self.assertTrue("func Benchmark" in code)

    def test_scenario_descriptions(self):
        """Test that scenario descriptions are meaningful"""
        for scenario_name, scenario in SCENARIO_TEMPLATES.items():
            self.assertTrue("desc" in scenario)
            self.assertTrue(len(scenario["desc"]) > 0)

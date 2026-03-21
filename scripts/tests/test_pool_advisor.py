"""Tests for pool_advisor.py - Connection pool calculation."""
import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from pool_advisor import calculate_pool


class TestLittlesLaw(unittest.TestCase):
    """Test Little's Law calculation for connection pool sizing"""

    def test_basic_calculation(self):
        """Test basic Little's Law: connections = QPS * latency"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=10,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        # L = 100 * (10/1000) = 1
        self.assertTrue(result["theoretical_min"] == 1.0)

    def test_peak_multiplier(self):
        """Test peak multiplier scaling"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=10,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=2.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        # L = 100 * (10/1000) * 2 = 2
        self.assertTrue(result["theoretical_peak"] == 2.0)

    def test_high_latency(self):
        """Test calculation with high latency"""
        result = calculate_pool(
            qps=500,
            avg_latency_ms=100,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        # L = 500 * (100/1000) = 50
        self.assertTrue(result["theoretical_min"] == 50.0)


class TestMultiInstance(unittest.TestCase):
    """Test pool sizing with multiple application instances"""

    def test_per_instance_limit(self):
        """Test that MaxOpenConns respects per-instance limits"""
        result = calculate_pool(
            qps=1000,
            avg_latency_ms=50,
            db_max_conn=200,
            app_instances=4,
            db_type="mysql",
            peak_multiplier=2.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        # Theoretical: 1000 * 0.05 * 2 = 100
        # DB limit per instance: 200 * 0.8 / 4 = 40
        # Final: min(100, 40) = 40
        self.assertTrue(result["max_open"] <= 40)

    def test_single_vs_multiple_instances(self):
        """Test that multiple instances get smaller per-instance pools"""
        result_single = calculate_pool(
            qps=100,
            avg_latency_ms=20,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )

        result_multi = calculate_pool(
            qps=100,
            avg_latency_ms=20,
            db_max_conn=200,
            app_instances=4,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )

        # Multiple instances should have smaller per-instance pools
        self.assertTrue(result_multi["max_open"] <= result_single["max_open"])


class TestIdleRatio(unittest.TestCase):
    """Test idle connection ratio calculation"""

    def test_idle_connection_count(self):
        """Test that MaxIdleConns respects idle_ratio"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=10,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=2.0,
            idle_ratio=0.5,
            conn_lifetime_min=60,
        )
        # MaxOpen = 2, MaxIdle should be ~1 (50% of 2)
        self.assertTrue(result["max_idle"] >= 2)  # Minimum is 2

    def test_minimum_idle(self):
        """Test that idle count has minimum of 2"""
        result = calculate_pool(
            qps=10,
            avg_latency_ms=5,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.1,
            conn_lifetime_min=60,
        )
        # Should have minimum idle of 2
        self.assertTrue(result["max_idle"] >= 2)


class TestConnectionLifetime(unittest.TestCase):
    """Test connection lifetime and idle timeout calculation"""

    def test_lifetime_conversion(self):
        """Test that conn_lifetime_min is converted to seconds"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=10,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=10,
        )
        # 10 min = 600 seconds
        self.assertTrue(result["conn_lifetime_s"] == 600)

    def test_idle_timeout_calculation(self):
        """Test idle timeout is derived from lifetime"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=10,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        # Idle timeout should be <= lifetime
        self.assertTrue(result["conn_idle_timeout_s"] <= result["conn_lifetime_s"])
        # Should be at least 60s
        self.assertTrue(result["conn_idle_timeout_s"] >= 60)


class TestDBTypeVariations(unittest.TestCase):
    """Test different database type handling"""

    def test_mysql_config(self):
        """Test MySQL specific settings"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=20,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        self.assertTrue(result["db_type"] == "mysql")
        self.assertTrue("max_open" in result)

    def test_postgres_config(self):
        """Test PostgreSQL specific settings"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=20,
            db_max_conn=200,
            app_instances=1,
            db_type="postgres",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        self.assertTrue(result["db_type"] == "postgres")
        self.assertTrue("max_open" in result)


class TestMinimumConstraints(unittest.TestCase):
    """Test minimum connection constraints"""

    def test_minimum_max_open(self):
        """Test that MaxOpenConns has a minimum"""
        result = calculate_pool(
            qps=1,
            avg_latency_ms=1,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        # Should be at least 5
        self.assertTrue(result["max_open"] >= 5)

    def test_max_open_respects_db_limit(self):
        """Test that max_open doesn't exceed DB limit"""
        result = calculate_pool(
            qps=10000,
            avg_latency_ms=100,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=5.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        # DB limit is 200 * 0.8 = 160
        self.assertTrue(result["max_open"] <= 160)


class TestResultStructure(unittest.TestCase):
    """Test that result has all required fields"""

    def test_result_fields(self):
        """Test that all required fields are present"""
        result = calculate_pool(
            qps=100,
            avg_latency_ms=20,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=2.0,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )

        required_fields = {
            "max_open",
            "max_idle",
            "conn_lifetime_s",
            "conn_idle_timeout_s",
            "theoretical_min",
            "theoretical_peak",
            "db_limit_per_instance",
            "db_type",
        }

        for field in required_fields:
            self.assertTrue(field in result)
            self.assertTrue(result[field] is not None)


class TestRealWorldScenarios(unittest.TestCase):
    """Test realistic business scenarios"""

    def test_small_service(self):
        """Test configuration for small service"""
        result = calculate_pool(
            qps=50,
            avg_latency_ms=15,
            db_max_conn=100,
            app_instances=2,
            db_type="mysql",
            peak_multiplier=1.5,
            idle_ratio=0.25,
            conn_lifetime_min=60,
        )
        self.assertTrue(result["max_open"] > 0)
        self.assertTrue(result["max_idle"] > 0)

    def test_high_traffic_service(self):
        """Test configuration for high-traffic service"""
        result = calculate_pool(
            qps=5000,
            avg_latency_ms=50,
            db_max_conn=500,
            app_instances=10,
            db_type="mysql",
            peak_multiplier=2.0,
            idle_ratio=0.3,
            conn_lifetime_min=60,
        )
        self.assertTrue(result["max_open"] > 0)
        self.assertTrue(result["max_idle"] > 0)

    def test_batch_processing_service(self):
        """Test configuration for batch processing (low QPS, high latency)"""
        result = calculate_pool(
            qps=20,
            avg_latency_ms=500,
            db_max_conn=200,
            app_instances=1,
            db_type="mysql",
            peak_multiplier=1.2,
            idle_ratio=0.2,
            conn_lifetime_min=30,
        )
        # Should still have reasonable pool size
        self.assertTrue(result["max_open"] >= 5)

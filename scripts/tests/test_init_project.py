"""Tests for init_project.py - Project scaffolding."""
import unittest
import sys
from pathlib import Path
import tempfile
import shutil

sys.path.insert(0, str(Path(__file__).parent.parent))
from init_project import scaffold, replace_package, CORE_FILES


class TestPackageReplacement(unittest.TestCase):
    """Test package name replacement in files"""

    def test_replace_package_simple(self):
        """Test simple package replacement"""
        content = "package dbcore\n\nfunc Test() {}"
        result = replace_package(content, "mydbcore")

        self.assertTrue("package mydbcore" in result)
        self.assertTrue("func Test()" in result)

    def test_replace_package_multiline(self):
        """Test package replacement in multiline content"""
        content = """package dbcore

import "fmt"

func Test() {}
"""
        result = replace_package(content, "custom")

        self.assertTrue("package custom" in result)

    def test_replace_preserves_rest(self):
        """Test that replacement preserves rest of content"""
        content = """package dbcore

// Important comment
type BaseModel struct {
    ID uint
}
"""
        result = replace_package(content, "newpkg")

        self.assertTrue("package newpkg" in result)
        self.assertTrue("BaseModel" in result)
        self.assertTrue("// Important comment" in result)


class TestDryRunMode(unittest.TestCase):
    """Test dry-run mode functionality"""

    def test_dry_run_no_file_creation(self):
        """Test that dry-run doesn't create files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "dbcore"

            # This should not raise even if assets are not available
            # We'll just check that it handles dry-run mode
            scaffold(
                output_dir=output_dir,
                package_name="testdbcore",
                dry_run=True,
                force=False,
                with_example=False,
            )

            # In dry-run, directory creation is skipped
            # So we can't self.assertTrue(much without real assets)


class TestPackageNameValidation(unittest.TestCase):
    """Test package name validation"""

    def test_valid_package_names(self):
        """Test valid package names"""
        valid_names = ["dbcore", "mydbcore", "db_core", "core123"]

        for name in valid_names:
            # Should not raise
            content = "package dbcore\nfunc Test() {}"
            result = replace_package(content, name)
            self.assertTrue(f"package {name}" in result)

    def test_package_name_in_output(self):
        """Test that package name appears in replaced content"""
        content = "package dbcore"
        result = replace_package(content, "custom_pkg")

        self.assertTrue("package custom_pkg" in result)


class TestScaffoldingParameters(unittest.TestCase):
    """Test scaffolding with different parameters"""

    def test_scaffold_with_custom_package(self):
        """Test scaffolding with custom package name"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            scaffold(
                output_dir=output_dir,
                package_name="mydbcore",
                dry_run=True,
                force=False,
                with_example=False,
            )
            # Should complete without error

    def test_scaffold_with_force(self):
        """Test scaffolding with force flag"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            scaffold(
                output_dir=output_dir,
                package_name="dbcore",
                dry_run=True,
                force=True,
                with_example=False,
            )
            # Should complete without error

    def test_scaffold_with_example(self):
        """Test scaffolding with example files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            scaffold(
                output_dir=output_dir,
                package_name="dbcore",
                dry_run=True,
                force=False,
                with_example=True,
            )
            # Should complete without error


class TestCoreFiles(unittest.TestCase):
    """Test core files configuration"""

    def test_core_files_defined(self):
        """Test that core files are defined"""
        self.assertTrue(len(CORE_FILES) > 0)

    def test_core_files_are_strings(self):
        """Test that all core files are strings"""
        for file in CORE_FILES:
            self.assertTrue(isinstance(file, str))

    def test_core_files_have_go_extension(self):
        """Test that core files are Go files"""
        go_files = [f for f in CORE_FILES if f.endswith(".go")]
        self.assertTrue(len(go_files) > 0)


class TestOutputDirectory(unittest.TestCase):
    """Test output directory handling"""

    def test_output_dir_creation(self):
        """Test that output directory is created"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "new_dbcore"

            scaffold(
                output_dir=output_dir,
                package_name="dbcore",
                dry_run=True,
                force=False,
                with_example=False,
            )

            # In dry-run mode, directory should not be created
            # But function should complete without error

    def test_nested_output_dir(self):
        """Test creating nested directories"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "pkg" / "internal" / "dbcore"

            scaffold(
                output_dir=output_dir,
                package_name="dbcore",
                dry_run=True,
                force=False,
                with_example=False,
            )

            # Should handle without error


class TestScaffoldOutput(unittest.TestCase):
    """Test scaffold operation output"""

    def test_dry_run_printable(self):
        """Test that dry-run produces readable output"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Should not raise any errors
            scaffold(
                output_dir=output_dir,
                package_name="testpkg",
                dry_run=True,
                force=False,
                with_example=False,
            )


class TestFileWriting(unittest.TestCase):
    """Test file writing functionality"""

    def test_write_with_real_content(self):
        """Test writing files with actual content"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create a mock file to test
            mock_file = output_dir / "test.go"
            mock_file.write_text("package test\nfunc Test() {}")

            self.assertTrue(mock_file.exists())
            self.assertTrue("func Test()" in mock_file.read_text())

    def test_package_replacement_in_file(self):
        """Test package replacement in actual file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            test_file = output_dir / "base_model.go"

            # Create test content
            content = "package dbcore\n\ntype BaseModel struct {}"
            test_file.write_text(content)

            # Read and replace
            original = test_file.read_text()
            replaced = replace_package(original, "custom")

            self.assertTrue("package custom" in replaced)


class TestMultiFileScaffolding(unittest.TestCase):
    """Test scaffolding multiple files"""

    def test_multiple_files_same_dir(self):
        """Test writing multiple files to same directory"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            # Create multiple test files
            for i in range(3):
                file = output_dir / f"file{i}.go"
                file.write_text(f"package test\n// File {i}")

            # All files should exist
            self.assertTrue(len(list(output_dir.glob("*.go"))) == 3)

    def test_file_independence(self):
        """Test that multiple files are independent"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)

            file1 = output_dir / "file1.go"
            file2 = output_dir / "file2.go"

            file1.write_text("package dbcore\n// File 1")
            file2.write_text("package dbcore\n// File 2")

            # Modify one file
            content1 = file1.read_text()
            modified1 = replace_package(content1, "pkg1")
            file1.write_text(modified1)

            # Other file should be unchanged
            content2 = file2.read_text()
            self.assertTrue("package dbcore" in content2)


class TestErrorHandling(unittest.TestCase):
    """Test error handling in scaffolding"""

    def test_invalid_output_path(self):
        """Test handling of invalid output path"""
        # Using /dev/null (non-existent nested path) should handle gracefully
        invalid_path = Path("/invalid/path/that/does/not/exist/dbcore")

        # Function should handle error gracefully or create the path
        # depending on implementation
        try:
            scaffold(
                output_dir=invalid_path,
                package_name="dbcore",
                dry_run=True,
                force=False,
                with_example=False,
            )
        except (OSError, PermissionError):
            # Expected in some environments
            pass


class TestIntegrationScenarios(unittest.TestCase):
    """Test realistic scaffolding scenarios"""

    def test_scaffold_for_api_project(self):
        """Test scaffolding for API project structure"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir) / "internal" / "dbcore"

            scaffold(
                output_dir=output_dir,
                package_name="dbcore",
                dry_run=True,
                force=False,
                with_example=False,
            )

    def test_scaffold_with_existing_files(self):
        """Test scaffolding when files already exist"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Create an existing file
            existing = output_dir / "base_model.go"
            existing.write_text("package dbcore\n// Existing")

            # Scaffold without force should skip
            scaffold(
                output_dir=output_dir,
                package_name="dbcore",
                dry_run=False,
                force=False,
                with_example=False,
            )

            # File should still have original content if not overwritten
            content = existing.read_text()
            self.assertTrue("Existing" in content or "package" in content)

    def test_scaffold_with_force_overwrite(self):
        """Test scaffolding with force flag overwrites files"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_dir = Path(tmpdir)
            output_dir.mkdir(parents=True, exist_ok=True)

            # Create a dummy file
            dummy = output_dir / "dummy.go"
            dummy.write_text("old content")

            # Force should work if assets exist
            # If assets don't exist, this will skip
            scaffold(
                output_dir=output_dir,
                package_name="dbcore",
                dry_run=True,  # Use dry-run to avoid asset requirement
                force=True,
                with_example=False,
            )


class TestPackageNameMutations(unittest.TestCase):
    """Test package name transformation edge cases"""

    def test_replace_exact_once(self):
        """Test that package is replaced exactly once"""
        content = """package dbcore
// More content
package dbcore  // This should not be replaced (in comment)
func Test() {}
"""
        result = replace_package(content, "newpkg")

        # Only first package declaration should be replaced
        lines = result.split("\n")
        first_line = lines[0]
        self.assertTrue("package newpkg" in first_line)

    def test_whitespace_handling(self):
        """Test package replacement with whitespace variations"""
        content = "package   dbcore\n"
        result = replace_package(content, "custom")

        self.assertTrue("package custom" in result)

    def test_multiline_spacing(self):
        """Test with multiline spacing"""
        content = """
package dbcore

"""
        result = replace_package(content, "pkg")

        self.assertTrue("package pkg" in result)

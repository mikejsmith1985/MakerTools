"""
Tests for the runtime_paths module that resolves data directories for source and frozen builds.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.runtime_paths import resolve_runtime_app_dir


class TestResolveRuntimeAppDir(unittest.TestCase):
    """Verify resolve_runtime_app_dir returns correct paths for source and frozen modes."""

    def test_source_mode_returns_parent_of_module_file(self) -> None:
        """In normal source runs the app dir is the directory containing the given file."""
        module_file_path = os.path.abspath(__file__)
        result_dir = resolve_runtime_app_dir(module_file_path)
        expected_dir = os.path.dirname(module_file_path)
        self.assertEqual(result_dir, expected_dir)

    def test_source_mode_returns_absolute_path(self) -> None:
        result_dir = resolve_runtime_app_dir("relative/fake_module.py")
        self.assertTrue(os.path.isabs(result_dir))

    def test_source_mode_parent_level_ascends_directory(self) -> None:
        module_file_path = os.path.join("C:\\", "Projects", "MakerTools", "WiringWizard", "core", "ai_intake.py")
        result_dir = resolve_runtime_app_dir(module_file_path, source_parent_levels=1)
        expected_dir = os.path.join("C:\\", "Projects", "MakerTools", "WiringWizard")
        self.assertEqual(result_dir, expected_dir)

    def test_negative_parent_levels_are_clamped_to_zero(self) -> None:
        module_file_path = os.path.abspath(__file__)
        result_dir = resolve_runtime_app_dir(module_file_path, source_parent_levels=-3)
        expected_dir = os.path.dirname(module_file_path)
        self.assertEqual(result_dir, expected_dir)

    def test_frozen_mode_uses_stable_appdata_dir(self) -> None:
        """When sys.frozen is set, the resolved dir should be the stable user data dir."""
        original_frozen = getattr(sys, "frozen", None)
        try:
            sys.frozen = True

            result_dir = resolve_runtime_app_dir(__file__)
            # On Windows, should resolve to %APPDATA%\WiringWizard.
            if sys.platform == "win32":
                appdata = os.environ.get("APPDATA", "")
                if appdata:
                    expected_dir = os.path.join(appdata, "WiringWizard")
                else:
                    expected_dir = os.path.join(os.path.expanduser("~"), ".wiringwizard")
            else:
                expected_dir = os.path.join(os.path.expanduser("~"), ".wiringwizard")
            self.assertEqual(result_dir, expected_dir)
        finally:
            if original_frozen is None:
                if hasattr(sys, "frozen"):
                    del sys.frozen
            else:
                sys.frozen = original_frozen

    def test_result_contains_no_trailing_separator(self) -> None:
        result_dir = resolve_runtime_app_dir(__file__)
        self.assertFalse(result_dir.endswith(os.sep))


if __name__ == "__main__":
    unittest.main()

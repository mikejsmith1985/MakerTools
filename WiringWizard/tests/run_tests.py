"""
WiringWizard test runner for local development.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

if __name__ == "__main__":
    test_loader = unittest.TestLoader()
    test_suite = test_loader.discover(os.path.join(ROOT_DIR, "tests"), pattern="test_*.py")
    test_runner = unittest.TextTestRunner(verbosity=2)
    test_result = test_runner.run(test_suite)
    sys.exit(0 if test_result.wasSuccessful() else 1)


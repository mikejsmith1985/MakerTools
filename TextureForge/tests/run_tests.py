"""
ReliefForge test runner.
Usage: python tests/run_tests.py  (from C:\\ProjectsWin\\ReliefForge)
"""

import sys
import os
import unittest

root = os.path.dirname(os.path.dirname(__file__))
if root not in sys.path:
    sys.path.insert(0, root)

if __name__ == '__main__':
    loader = unittest.TestLoader()
    suite  = loader.discover(os.path.join(root, 'tests'), pattern='test_*.py')
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)

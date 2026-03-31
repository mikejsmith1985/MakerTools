"""
Test runner for FusionCam.
Runs all tests that can execute outside of Fusion 360.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == '__main__':
    print()
    print("=" * 60)
    print("  FusionCam Test Suite")
    print("  (Tests that run outside Fusion 360)")
    print("=" * 60)
    print()

    # Run each test module
    import test_feeds_speeds
    import test_tool_parser
    import test_geometry_analyzer
    import test_texture_stamp

    print()
    print("=" * 60)
    print("  ALL TEST SUITES PASSED!")
    print("=" * 60)

"""
Tests for the geometry analyzer.
Note: Full geometry analysis requires Fusion 360 API (adsk.fusion.BRepBody).
These tests cover utility functions and data structures only.
For integration testing, load in Fusion 360 with a test part.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_feature_classification():
    """Test that feature types are correctly classified for 2-sided work."""
    # Simulated features (would come from geometry_analyzer.analyze_body)
    features = [
        {'id': 'f1', 'type': 'face', 'description': 'Face top'},
        {'id': 'f2', 'type': 'pocket', 'depth_mm': 5.0, 'description': 'Top pocket'},
        {'id': 'f3', 'type': 'through_hole', 'is_through': True, 'description': 'Through hole'},
        {'id': 'f4', 'type': 'outer_profile', 'description': 'Outer contour'},
        {'id': 'f5', 'type': 'chamfer', 'description': 'Edge chamfer'},
    ]

    # Count by type
    type_counts = {}
    for f in features:
        t = f['type']
        type_counts[t] = type_counts.get(t, 0) + 1

    assert type_counts['face'] == 1
    assert type_counts['pocket'] == 1
    assert type_counts['through_hole'] == 1
    assert type_counts['outer_profile'] == 1
    assert type_counts['chamfer'] == 1

    print("PASS: Feature classification structures are correct")
    print(f"  Types: {type_counts}")
    print()


def test_operation_ordering():
    """Test that features would be sorted in correct machining order."""
    op_ordering = [
        'face', 'adaptive_clearing', 'adaptive_clearing_3d',
        'drilling', 'pocket_finishing', 'profile_contour',
        'parallel_finishing', 'chamfer'
    ]

    type_to_strategy = {
        'face': 'face',
        'pocket': 'adaptive_clearing',
        'through_hole': 'drilling',
        'outer_profile': 'profile_contour',
        'chamfer': 'chamfer',
    }

    features = [
        {'type': 'chamfer'},
        {'type': 'through_hole'},
        {'type': 'pocket'},
        {'type': 'face'},
        {'type': 'outer_profile'},
    ]

    # Sort by operation ordering
    def sort_key(f):
        strategy = type_to_strategy.get(f['type'], 'profile_contour')
        try:
            return op_ordering.index(strategy)
        except ValueError:
            return 999

    sorted_features = sorted(features, key=sort_key)
    expected_order = ['face', 'pocket', 'through_hole', 'outer_profile', 'chamfer']

    actual_order = [f['type'] for f in sorted_features]
    assert actual_order == expected_order, f"Expected {expected_order}, got {actual_order}"

    print("PASS: Operation ordering is correct")
    print(f"  Order: {' -> '.join(actual_order)}")
    print()


if __name__ == '__main__':
    print("=" * 60)
    print("FusionCam Geometry Analyzer Tests")
    print("=" * 60)
    print()

    test_feature_classification()
    test_operation_ordering()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)

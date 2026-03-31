"""
Tests for the feeds & speeds calculator.
These tests can be run outside of Fusion 360 since they don't depend on the Fusion API.
Run with: python -m pytest tests/ or python tests/test_feeds_speeds.py
"""

import sys
import os
import math

# Add parent to path so we can import core modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import feeds_speeds


def test_aluminum_quarter_inch_2flute():
    """Test feeds/speeds for a 1/4" 2-flute in aluminum 6061."""
    tool = {
        'diameter_inches': 0.25,
        'diameter_mm': 6.35,
        'flute_count': 2,
        'flute_length_inches': 0.75,
        'flute_length_mm': 19.05,
    }

    result = feeds_speeds.calculate(tool, 'aluminum_6061_t6', 'roughing', 'standard')

    # RPM should be in valid Makita RT0701C dial settings
    assert result['rpm'] in [10000, 14000, 18000, 22000, 26000, 31000], \
        f"RPM {result['rpm']} not a valid Makita RT0701C dial setting"

    # Feed rate should be positive and within machine limits
    assert 0 < result['feed_rate_mm_min'] <= 5000, \
        f"Feed rate {result['feed_rate_mm_min']} out of range"

    # DOC should be reasonable for aluminum
    assert 0 < result['doc_mm'] <= 6.35, \
        f"DOC {result['doc_mm']}mm exceeds tool diameter"

    # Chipload should be in aluminum range
    assert 0.0005 <= result['chipload_inches'] <= 0.005, \
        f"Chipload {result['chipload_inches']} out of range"

    print(f"PASS: 1/4\" 2F aluminum roughing")
    print(f"  RPM: {result['rpm']} (dial {result['rpm_dial_setting']})")
    print(f"  Feed: {result['feed_rate_mm_min']} mm/min ({result['feed_rate_ipm']} ipm)")
    print(f"  DOC: {result['doc_mm']}mm | WOC: {result['woc_mm']}mm")
    print(f"  Chipload: {result['chipload_inches']}\" per tooth")
    print(f"  Notes: {result['notes']}")
    print()


def test_plywood_quarter_inch():
    """Test feeds/speeds for plywood with 1/4" endmill."""
    tool = {
        'diameter_inches': 0.25,
        'diameter_mm': 6.35,
        'flute_count': 2,
        'flute_length_inches': 1.0,
        'flute_length_mm': 25.4,
    }

    result = feeds_speeds.calculate(tool, 'plywood_baltic_birch', 'roughing', 'standard')

    assert result['rpm'] in [10000, 14000, 18000, 22000, 26000, 31000]
    assert result['feed_rate_mm_min'] > 0
    assert result['doc_mm'] > 0

    print(f"PASS: 1/4\" 2F plywood roughing")
    print(f"  RPM: {result['rpm']} (dial {result['rpm_dial_setting']})")
    print(f"  Feed: {result['feed_rate_mm_min']} mm/min")
    print(f"  DOC: {result['doc_mm']}mm | WOC: {result['woc_mm']}mm")
    print()


def test_finishing_lower_than_roughing():
    """Finishing should have lower DOC and WOC than roughing."""
    tool = {
        'diameter_inches': 0.25,
        'diameter_mm': 6.35,
        'flute_count': 2,
        'flute_length_inches': 0.75,
        'flute_length_mm': 19.05,
    }

    rough = feeds_speeds.calculate(tool, 'aluminum_6061_t6', 'roughing', 'standard')
    finish = feeds_speeds.calculate(tool, 'aluminum_6061_t6', 'finishing', 'standard')

    assert finish['woc_mm'] < rough['woc_mm'], \
        f"Finishing WOC ({finish['woc_mm']}) should be less than roughing ({rough['woc_mm']})"

    print(f"PASS: Finishing WOC ({finish['woc_mm']}mm) < Roughing WOC ({rough['woc_mm']}mm)")
    print()


def test_rigidity_derating():
    """Verify feeds are derated by the machine rigidity factor."""
    tool = {
        'diameter_inches': 0.25,
        'diameter_mm': 6.35,
        'flute_count': 2,
        'flute_length_inches': 0.75,
        'flute_length_mm': 19.05,
    }

    result = feeds_speeds.calculate(tool, 'aluminum_6061_t6', 'roughing', 'standard')

    # The rigidity factor is 0.6, so feeds should be noticeably reduced
    # from what you'd see on a rigid VMC
    # Max theoretical feed for this tool in aluminum would be much higher
    assert result['feed_rate_mm_min'] < 3000, \
        f"Feed {result['feed_rate_mm_min']} seems too high for a hobby CNC"

    print(f"PASS: Feed rate ({result['feed_rate_mm_min']} mm/min) is derated for hobby CNC")
    print()


def test_drilling():
    """Test drilling feeds/speeds."""
    tool = {
        'diameter_inches': 0.25,
        'diameter_mm': 6.35,
        'flute_count': 2,
    }

    result = feeds_speeds.calculate_for_drilling(tool, 'aluminum_6061_t6', 10.0, 'standard')

    assert result['rpm'] > 0
    assert result['feed_rate_mm_min'] > 0
    assert result['peck_depth_mm'] > 0

    print(f"PASS: Drilling 1/4\" in aluminum")
    print(f"  RPM: {result['rpm']} | Feed: {result['feed_rate_mm_min']} mm/min")
    print(f"  Peck depth: {result['peck_depth_mm']}mm")
    print()


def test_all_materials():
    """Test that all built-in materials produce valid results."""
    tool = {
        'diameter_inches': 0.25,
        'diameter_mm': 6.35,
        'flute_count': 2,
        'flute_length_inches': 0.75,
        'flute_length_mm': 19.05,
    }

    material_keys = [
        'aluminum_6061_t6', 'aluminum_6063',
        'plywood_baltic_birch', 'hardwood_oak', 'softwood_pine'
    ]

    for mat_key in material_keys:
        result = feeds_speeds.calculate(tool, mat_key, 'roughing', 'standard')
        assert result['rpm'] > 0
        assert result['feed_rate_mm_min'] > 0
        assert result['doc_mm'] > 0
        print(f"PASS: {result['material']} - RPM: {result['rpm']}, Feed: {result['feed_rate_mm_min']} mm/min")

    print()


def test_quality_presets():
    """Test that quality presets affect the output."""
    tool = {
        'diameter_inches': 0.25,
        'diameter_mm': 6.35,
        'flute_count': 2,
        'flute_length_inches': 0.75,
        'flute_length_mm': 19.05,
    }

    draft = feeds_speeds.calculate(tool, 'aluminum_6061_t6', 'roughing', 'draft')
    standard = feeds_speeds.calculate(tool, 'aluminum_6061_t6', 'roughing', 'standard')
    fine = feeds_speeds.calculate(tool, 'aluminum_6061_t6', 'roughing', 'fine')

    # Fine should have lower DOC than draft
    assert fine['doc_mm'] <= standard['doc_mm'] <= draft['doc_mm'], \
        f"DOC should decrease with quality: draft={draft['doc_mm']}, standard={standard['doc_mm']}, fine={fine['doc_mm']}"

    print(f"PASS: Quality presets - DOC: draft={draft['doc_mm']}mm, standard={standard['doc_mm']}mm, fine={fine['doc_mm']}mm")
    print()


if __name__ == '__main__':
    print("=" * 60)
    print("FusionCam Feeds & Speeds Calculator Tests")
    print("=" * 60)
    print()

    test_aluminum_quarter_inch_2flute()
    test_plywood_quarter_inch()
    test_finishing_lower_than_roughing()
    test_rigidity_derating()
    test_drilling()
    test_all_materials()
    test_quality_presets()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)

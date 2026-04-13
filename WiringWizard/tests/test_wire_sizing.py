"""
Tests for core.wire_sizing — verifies AWG recommendations, voltage-drop calculations,
and boundary conditions across different voltage classes.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.wire_sizing import (
    AWG_ORDER, AWG_TABLE, calculate_voltage_drop, recommend_awg,
)


class TestRecommendAwg(unittest.TestCase):
    """Tests for recommend_awg()."""

    def test_returns_required_keys(self):
        result = recommend_awg(5.0, 10.0, 'lv_12v')
        required_keys = [
            'recommended_awg', 'ampacity', 'voltage_drop_volts',
            'voltage_drop_percent', 'is_ampacity_limited', 'notes',
        ]
        for key in required_keys:
            self.assertIn(key, result, msg=f'Missing key: {key}')

    def test_recommended_awg_is_in_awg_table(self):
        result = recommend_awg(5.0, 10.0, 'lv_12v')
        self.assertIn(result['recommended_awg'], AWG_TABLE)

    def test_low_current_short_run_gets_small_gauge(self):
        result = recommend_awg(1.0, 2.0, 'lv_12v')
        # 1A over 2 ft should comfortably fit in AWG 22
        self.assertIn(result['recommended_awg'], AWG_ORDER[:4])  # small gauges

    def test_high_current_gets_heavy_gauge(self):
        result = recommend_awg(80.0, 5.0, 'lv_12v')
        heavy_gauges = {'8', '6', '4', '2', '1/0', '2/0', '3/0', '4/0'}
        self.assertIn(result['recommended_awg'], heavy_gauges)

    def test_long_run_increases_gauge_for_voltage_drop(self):
        short_result = recommend_awg(5.0, 2.0, 'lv_12v')
        long_result  = recommend_awg(5.0, 50.0, 'lv_12v')
        short_index = AWG_ORDER.index(short_result['recommended_awg'])
        long_index  = AWG_ORDER.index(long_result['recommended_awg'])
        # Long run should require same or heavier gauge (higher index = heavier)
        self.assertGreaterEqual(long_index, short_index)

    def test_voltage_drop_percent_within_limit(self):
        result = recommend_awg(5.0, 10.0, 'lv_12v')
        self.assertLessEqual(result['voltage_drop_percent'], 3.0)

    def test_5v_system_selects_heavier_gauge_than_12v_same_params(self):
        result_5v  = recommend_awg(3.0, 10.0, 'lv_5v')
        result_12v = recommend_awg(3.0, 10.0, 'lv_12v')
        index_5v  = AWG_ORDER.index(result_5v['recommended_awg'])
        index_12v = AWG_ORDER.index(result_12v['recommended_awg'])
        # 5V is more drop-sensitive, so it should need same or heavier gauge
        self.assertGreaterEqual(index_5v, index_12v)

    def test_ampacity_field_matches_table(self):
        result = recommend_awg(5.0, 10.0, 'lv_12v')
        expected_ampacity = AWG_TABLE[result['recommended_awg']]['ampacity']
        self.assertEqual(result['ampacity'], expected_ampacity)

    def test_voltage_drop_volts_is_non_negative(self):
        result = recommend_awg(5.0, 10.0, 'lv_24v')
        self.assertGreaterEqual(result['voltage_drop_volts'], 0)

    def test_notes_is_non_empty_string(self):
        result = recommend_awg(5.0, 10.0, 'lv_12v')
        self.assertIsInstance(result['notes'], str)
        self.assertTrue(len(result['notes']) > 0)

    def test_unknown_voltage_class_falls_back_gracefully(self):
        # Should not raise — should use default 12V nominal
        result = recommend_awg(5.0, 10.0, 'lv_unknown')
        self.assertIn('recommended_awg', result)


class TestCalculateVoltageDrop(unittest.TestCase):
    """Tests for calculate_voltage_drop()."""

    def test_returns_non_negative_value(self):
        drop = calculate_voltage_drop('14', 5.0, 10.0)
        self.assertGreaterEqual(drop, 0)

    def test_heavier_gauge_has_lower_drop(self):
        drop_14 = calculate_voltage_drop('14', 10.0, 10.0)
        drop_10 = calculate_voltage_drop('10', 10.0, 10.0)
        self.assertLess(drop_10, drop_14)

    def test_longer_run_has_higher_drop(self):
        drop_short = calculate_voltage_drop('14', 5.0, 5.0)
        drop_long  = calculate_voltage_drop('14', 5.0, 50.0)
        self.assertGreater(drop_long, drop_short)

    def test_zero_current_gives_zero_drop(self):
        drop = calculate_voltage_drop('14', 0.0, 10.0)
        self.assertEqual(drop, 0.0)

    def test_raises_for_unknown_awg(self):
        with self.assertRaises(ValueError):
            calculate_voltage_drop('99', 5.0, 10.0)

    def test_round_trip_is_used(self):
        """Verify the function uses round-trip length (2× one-way)."""
        # Calculate manually: R = (resistance_per_1000ft/1000) * 2 * run_ft * current
        from core.wire_sizing import AWG_TABLE
        run_ft = 10.0
        current = 5.0
        awg = '14'
        resistance_per_1000ft = AWG_TABLE[awg]['resistance_ohms_per_1000ft']
        expected_drop = current * (resistance_per_1000ft / 1000.0) * run_ft * 2
        actual_drop = calculate_voltage_drop(awg, current, run_ft)
        self.assertAlmostEqual(actual_drop, expected_drop, places=4)


class TestAwgTable(unittest.TestCase):
    """Sanity checks on the AWG_TABLE constants."""

    def test_all_awg_order_entries_in_table(self):
        for awg in AWG_ORDER:
            self.assertIn(awg, AWG_TABLE, msg=f'AWG {awg} missing from AWG_TABLE')

    def test_ampacity_increases_with_heavier_gauge(self):
        for index in range(len(AWG_ORDER) - 1):
            lighter = AWG_ORDER[index]
            heavier = AWG_ORDER[index + 1]
            self.assertLess(
                AWG_TABLE[lighter]['ampacity'],
                AWG_TABLE[heavier]['ampacity'],
                msg=f'Expected AWG {heavier} to have higher ampacity than {lighter}',
            )

    def test_resistance_decreases_with_heavier_gauge(self):
        for index in range(len(AWG_ORDER) - 1):
            lighter = AWG_ORDER[index]
            heavier = AWG_ORDER[index + 1]
            self.assertGreater(
                AWG_TABLE[lighter]['resistance_ohms_per_1000ft'],
                AWG_TABLE[heavier]['resistance_ohms_per_1000ft'],
                msg=f'Expected AWG {heavier} to have lower resistance than {lighter}',
            )


if __name__ == '__main__':
    unittest.main()

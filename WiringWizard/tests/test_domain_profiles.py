"""
Tests for core.domain_profiles — verifies domain lookup, the is_mains helper,
and the completeness of every domain entry.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.domain_profiles import (
    DOMAIN_PROFILES, get_domain_profile, is_mains_domain, list_domains,
)


class TestListDomains(unittest.TestCase):
    """Tests for list_domains()."""

    def test_returns_all_four_domains(self):
        domains = list_domains()
        self.assertIn('automotive', domains)
        self.assertIn('cnc_control', domains)
        self.assertIn('3d_printer', domains)
        self.assertIn('home_electrical', domains)

    def test_returns_list(self):
        self.assertIsInstance(list_domains(), list)


class TestGetDomainProfile(unittest.TestCase):
    """Tests for get_domain_profile()."""

    def test_returns_dict_for_valid_domain(self):
        profile = get_domain_profile('automotive')
        self.assertIsInstance(profile, dict)

    def test_raises_key_error_for_unknown_domain(self):
        with self.assertRaises(KeyError):
            get_domain_profile('underwater_welding')

    def test_all_domains_have_required_keys(self):
        required_keys = [
            'display_name', 'default_voltage_class', 'allowed_voltage_classes',
            'wire_standard', 'typical_wire_colors', 'common_components',
            'fuse_required', 'is_mains', 'notes',
        ]
        for domain_name in list_domains():
            profile = get_domain_profile(domain_name)
            for key in required_keys:
                self.assertIn(
                    key, profile,
                    msg=f'Domain {domain_name!r} is missing required key {key!r}'
                )


class TestIsMainsDomain(unittest.TestCase):
    """Tests for is_mains_domain()."""

    def test_home_electrical_is_mains(self):
        self.assertTrue(is_mains_domain('home_electrical'))

    def test_automotive_is_not_mains(self):
        self.assertFalse(is_mains_domain('automotive'))

    def test_cnc_control_is_not_mains(self):
        self.assertFalse(is_mains_domain('cnc_control'))

    def test_3d_printer_is_not_mains(self):
        self.assertFalse(is_mains_domain('3d_printer'))

    def test_raises_for_unknown_domain(self):
        with self.assertRaises(KeyError):
            is_mains_domain('space_station')


class TestDomainProfileContents(unittest.TestCase):
    """Spot-check selected domain profile values."""

    def test_automotive_default_voltage_is_12v(self):
        profile = get_domain_profile('automotive')
        self.assertEqual(profile['default_voltage_class'], 'lv_12v')

    def test_3d_printer_default_voltage_is_24v(self):
        profile = get_domain_profile('3d_printer')
        self.assertEqual(profile['default_voltage_class'], 'lv_24v')

    def test_home_electrical_is_mains_flag_true(self):
        profile = get_domain_profile('home_electrical')
        self.assertTrue(profile['is_mains'])

    def test_all_low_voltage_domains_have_is_mains_false(self):
        for domain_name in ('automotive', 'cnc_control', '3d_printer'):
            profile = get_domain_profile(domain_name)
            self.assertFalse(
                profile['is_mains'],
                msg=f'Domain {domain_name!r} should have is_mains=False'
            )

    def test_cnc_control_allows_48v(self):
        profile = get_domain_profile('cnc_control')
        self.assertIn('lv_48v', profile['allowed_voltage_classes'])

    def test_automotive_does_not_allow_mains(self):
        profile = get_domain_profile('automotive')
        self.assertNotIn('mains_120v', profile['allowed_voltage_classes'])


if __name__ == '__main__':
    unittest.main()

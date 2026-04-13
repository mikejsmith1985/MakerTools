"""
Tests for core.project_schema — verifies the WiringProject data structures,
default values, and the find_component / find_connection helper methods.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.project_schema import (
    Component, Connection, ProjectProfile, WiringProject,
    SUPPORTED_DOMAINS, SUPPORTED_VOLTAGE_CLASSES,
)


class TestProjectProfile(unittest.TestCase):
    """Tests for the ProjectProfile dataclass."""

    def test_required_fields_stored(self):
        profile = ProjectProfile(
            project_name='Test Rig',
            domain='automotive',
            voltage_class='lv_12v',
        )
        self.assertEqual(profile.project_name, 'Test Rig')
        self.assertEqual(profile.domain, 'automotive')
        self.assertEqual(profile.voltage_class, 'lv_12v')

    def test_description_defaults_to_empty_string(self):
        profile = ProjectProfile(project_name='Rig', domain='cnc_control', voltage_class='lv_24v')
        self.assertEqual(profile.description, '')


class TestSupportedConstants(unittest.TestCase):
    """Tests for the constants exported by project_schema."""

    def test_all_expected_domains_present(self):
        expected = {'automotive', 'cnc_control', '3d_printer', 'home_electrical'}
        self.assertEqual(set(SUPPORTED_DOMAINS), expected)

    def test_all_expected_voltage_classes_present(self):
        expected = {'lv_5v', 'lv_12v', 'lv_24v', 'lv_48v', 'mains_120v', 'mains_240v'}
        self.assertEqual(set(SUPPORTED_VOLTAGE_CLASSES), expected)


class TestComponent(unittest.TestCase):
    """Tests for the Component dataclass."""

    def test_fields_stored_correctly(self):
        comp = Component(
            component_id='psu1',
            component_name='Main PSU',
            component_type='power_supply',
            current_draw_amps=10.0,
            position_label='rear-panel',
        )
        self.assertEqual(comp.component_id, 'psu1')
        self.assertEqual(comp.current_draw_amps, 10.0)
        self.assertEqual(comp.position_label, 'rear-panel')

    def test_position_label_defaults_to_empty_string(self):
        comp = Component('c1', 'Motor', 'motor', 5.0)
        self.assertEqual(comp.position_label, '')


class TestConnection(unittest.TestCase):
    """Tests for the Connection dataclass."""

    def test_fields_stored_correctly(self):
        conn = Connection(
            connection_id='conn_01',
            from_component_id='psu1',
            from_pin='+12V',
            to_component_id='motor1',
            to_pin='VCC',
            current_amps=5.0,
            run_length_ft=3.0,
            wire_color='red',
        )
        self.assertEqual(conn.connection_id, 'conn_01')
        self.assertEqual(conn.current_amps, 5.0)
        self.assertIsNone(conn.awg_override)

    def test_awg_override_stored(self):
        conn = Connection('c2', 'a', 'p1', 'b', 'p2', 1.0, 2.0, 'black', awg_override='16')
        self.assertEqual(conn.awg_override, '16')


class TestWiringProject(unittest.TestCase):
    """Tests for WiringProject helper methods."""

    def setUp(self):
        profile = ProjectProfile('My Project', 'automotive', 'lv_12v')
        comp1 = Component('psu1', 'Battery', 'battery', 50.0)
        comp2 = Component('load1', 'Motor', 'motor', 5.0)
        conn1 = Connection('c1', 'psu1', '+', 'load1', 'VCC', 5.0, 2.0, 'red')
        self.project = WiringProject(
            profile=profile,
            components=[comp1, comp2],
            connections=[conn1],
        )

    def test_find_component_returns_correct_object(self):
        comp = self.project.find_component('psu1')
        self.assertIsNotNone(comp)
        self.assertEqual(comp.component_name, 'Battery')

    def test_find_component_returns_none_for_unknown_id(self):
        self.assertIsNone(self.project.find_component('does_not_exist'))

    def test_find_connection_returns_correct_object(self):
        conn = self.project.find_connection('c1')
        self.assertIsNotNone(conn)
        self.assertEqual(conn.from_component_id, 'psu1')

    def test_find_connection_returns_none_for_unknown_id(self):
        self.assertIsNone(self.project.find_connection('x99'))

    def test_components_default_to_empty_list(self):
        profile = ProjectProfile('P', 'automotive', 'lv_12v')
        project = WiringProject(profile=profile)
        self.assertEqual(project.components, [])

    def test_connections_default_to_empty_list(self):
        profile = ProjectProfile('P', 'automotive', 'lv_12v')
        project = WiringProject(profile=profile)
        self.assertEqual(project.connections, [])


if __name__ == '__main__':
    unittest.main()

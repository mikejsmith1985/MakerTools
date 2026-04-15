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
    Pin, LibraryComponent, PIN_TYPES,
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


class TestPin(unittest.TestCase):
    """Tests for the Pin dataclass added in v2.0."""

    def test_pin_stores_all_fields(self):
        pin = Pin(pin_id='A1', name='B+', pin_type='power_input', description='12V main power')
        self.assertEqual(pin.pin_id, 'A1')
        self.assertEqual(pin.name, 'B+')
        self.assertEqual(pin.pin_type, 'power_input')
        self.assertEqual(pin.description, '12V main power')

    def test_pin_defaults(self):
        pin = Pin(pin_id='X', name='Test')
        self.assertEqual(pin.pin_type, 'general')
        self.assertEqual(pin.description, '')

    def test_pin_types_constant_has_expected_types(self):
        self.assertIn('power_input', PIN_TYPES)
        self.assertIn('ground', PIN_TYPES)
        self.assertIn('can_high', PIN_TYPES)
        self.assertIn('can_low', PIN_TYPES)
        self.assertIn('pwm_output', PIN_TYPES)
        self.assertIn('general', PIN_TYPES)


class TestLibraryComponent(unittest.TestCase):
    """Tests for the LibraryComponent dataclass round-trip serialization."""

    def _make_component(self):
        return LibraryComponent(
            library_id='test-ecu',
            name='Test ECU',
            manufacturer='Acme',
            part_number='ECU-100',
            component_type='ecu',
            voltage_nominal=12.0,
            current_draw_amps=5.0,
            pins=[
                Pin('A1', 'B+', 'power_input', 'Main power'),
                Pin('A2', 'GND', 'ground', 'Power ground'),
                Pin('B1', 'CAN-H', 'can_high', 'CAN bus high'),
            ],
            notes='Test notes',
        )

    def test_to_dict_returns_serializable_dict(self):
        comp = self._make_component()
        result = comp.to_dict()
        self.assertEqual(result['library_id'], 'test-ecu')
        self.assertEqual(result['name'], 'Test ECU')
        self.assertIsInstance(result['pins'], list)
        self.assertEqual(len(result['pins']), 3)
        self.assertEqual(result['pins'][0]['pin_id'], 'A1')

    def test_from_dict_round_trip(self):
        original = self._make_component()
        data = original.to_dict()
        restored = LibraryComponent.from_dict(data)
        self.assertEqual(restored.library_id, original.library_id)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(len(restored.pins), 3)
        self.assertEqual(restored.pins[2].pin_type, 'can_high')

    def test_find_pin_returns_matching_pin(self):
        comp = self._make_component()
        pin = comp.find_pin('A2')
        self.assertIsNotNone(pin)
        self.assertEqual(pin.name, 'GND')

    def test_find_pin_returns_none_for_missing(self):
        comp = self._make_component()
        self.assertIsNone(comp.find_pin('Z99'))

    def test_pins_by_type_filters_correctly(self):
        comp = self._make_component()
        ground_pins = comp.pins_by_type('ground')
        self.assertEqual(len(ground_pins), 1)
        self.assertEqual(ground_pins[0].pin_id, 'A2')

    def test_component_dataclass_has_pins_field(self):
        """Project Component now carries optional pin data from the library."""
        comp = Component(
            component_id='kv8',
            component_name='Emtron KV8',
            component_type='ecu',
            current_draw_amps=5.0,
            pins=[Pin('A1', 'B+', 'power_input')],
            library_id='emtron-kv8',
        )
        self.assertEqual(len(comp.pins), 1)
        self.assertEqual(comp.library_id, 'emtron-kv8')


if __name__ == '__main__':
    unittest.main()

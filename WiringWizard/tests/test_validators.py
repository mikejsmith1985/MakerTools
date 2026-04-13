"""
Tests for core.validators — verifies profile, component, and connection validation,
including required-field checks, numeric range limits, and domain/voltage compatibility.
"""

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.project_schema import Component, Connection, ProjectProfile, WiringProject
from core.validators import (
    ValidationError,
    assert_project_valid,
    validate_component,
    validate_connection,
    validate_project,
    validate_project_profile,
)


def _make_valid_project() -> WiringProject:
    """Build a minimal, fully valid WiringProject for use in tests."""
    profile = ProjectProfile('Test Project', 'automotive', 'lv_12v')
    comp1 = Component('psu1', 'Battery', 'battery', 50.0)
    comp2 = Component('load1', 'Motor', 'motor', 5.0)
    conn1 = Connection('c1', 'psu1', '+12V', 'load1', 'VCC', 5.0, 3.0, 'red')
    return WiringProject(profile=profile, components=[comp1, comp2], connections=[conn1])


class TestValidateProjectProfile(unittest.TestCase):
    """Tests for validate_project_profile()."""

    def test_valid_profile_returns_no_errors(self):
        profile = ProjectProfile('My Project', 'automotive', 'lv_12v')
        self.assertEqual(validate_project_profile(profile), [])

    def test_blank_project_name_produces_error(self):
        profile = ProjectProfile('', 'automotive', 'lv_12v')
        errors = validate_project_profile(profile)
        self.assertTrue(any('project_name' in e for e in errors))

    def test_whitespace_only_name_produces_error(self):
        profile = ProjectProfile('   ', 'automotive', 'lv_12v')
        errors = validate_project_profile(profile)
        self.assertTrue(any('project_name' in e for e in errors))

    def test_unsupported_domain_produces_error(self):
        profile = ProjectProfile('P', 'underwater', 'lv_12v')
        errors = validate_project_profile(profile)
        self.assertTrue(any('domain' in e for e in errors))

    def test_unsupported_voltage_class_produces_error(self):
        profile = ProjectProfile('P', 'automotive', 'lv_999v')
        errors = validate_project_profile(profile)
        self.assertTrue(any('voltage_class' in e for e in errors))

    def test_voltage_class_incompatible_with_domain_produces_error(self):
        # mains_120v is not allowed for automotive domain
        profile = ProjectProfile('P', 'automotive', 'mains_120v')
        errors = validate_project_profile(profile)
        self.assertTrue(len(errors) > 0)

    def test_home_electrical_with_mains_120v_is_valid(self):
        profile = ProjectProfile('Home', 'home_electrical', 'mains_120v')
        self.assertEqual(validate_project_profile(profile), [])


class TestValidateComponent(unittest.TestCase):
    """Tests for validate_component()."""

    def test_valid_component_returns_no_errors(self):
        comp = Component('psu1', 'Battery', 'battery', 50.0)
        self.assertEqual(validate_component(comp, []), [])

    def test_blank_component_id_produces_error(self):
        comp = Component('', 'Battery', 'battery', 50.0)
        errors = validate_component(comp, [])
        self.assertTrue(any('component_id' in e for e in errors))

    def test_duplicate_component_id_produces_error(self):
        comp = Component('psu1', 'Battery', 'battery', 50.0)
        errors = validate_component(comp, ['psu1'])
        self.assertTrue(any('Duplicate' in e for e in errors))

    def test_negative_current_produces_error(self):
        comp = Component('c1', 'Motor', 'motor', -1.0)
        errors = validate_component(comp, [])
        self.assertTrue(any('current_draw_amps' in e for e in errors))

    def test_excessive_current_produces_error(self):
        comp = Component('c1', 'Monster', 'motor', 999.0)
        errors = validate_component(comp, [])
        self.assertTrue(len(errors) > 0)

    def test_blank_component_name_produces_error(self):
        comp = Component('c1', '', 'motor', 5.0)
        errors = validate_component(comp, [])
        self.assertTrue(any('component_name' in e for e in errors))

    def test_blank_component_type_produces_error(self):
        comp = Component('c1', 'Motor', '', 5.0)
        errors = validate_component(comp, [])
        self.assertTrue(any('component_type' in e for e in errors))


class TestValidateConnection(unittest.TestCase):
    """Tests for validate_connection()."""

    def _valid_conn(self):
        return Connection('c1', 'psu1', '+12V', 'load1', 'VCC', 5.0, 3.0, 'red')

    def test_valid_connection_returns_no_errors(self):
        conn = self._valid_conn()
        errors = validate_connection(conn, ['psu1', 'load1'], [])
        self.assertEqual(errors, [])

    def test_missing_from_component_produces_error(self):
        conn = self._valid_conn()
        errors = validate_connection(conn, ['load1'], [])
        self.assertTrue(any('from_component_id' in e for e in errors))

    def test_missing_to_component_produces_error(self):
        conn = self._valid_conn()
        errors = validate_connection(conn, ['psu1'], [])
        self.assertTrue(any('to_component_id' in e for e in errors))

    def test_current_below_minimum_produces_error(self):
        conn = Connection('c1', 'psu1', '+', 'load1', 'V', 0.001, 3.0, 'red')
        errors = validate_connection(conn, ['psu1', 'load1'], [])
        self.assertTrue(any('current_amps' in e for e in errors))

    def test_run_length_below_minimum_produces_error(self):
        conn = Connection('c1', 'psu1', '+', 'load1', 'V', 5.0, 0.01, 'red')
        errors = validate_connection(conn, ['psu1', 'load1'], [])
        self.assertTrue(any('run_length_ft' in e for e in errors))

    def test_duplicate_connection_id_produces_error(self):
        conn = self._valid_conn()
        errors = validate_connection(conn, ['psu1', 'load1'], ['c1'])
        self.assertTrue(any('Duplicate' in e for e in errors))

    def test_blank_wire_color_produces_error(self):
        conn = Connection('c1', 'psu1', '+', 'load1', 'V', 5.0, 3.0, '')
        errors = validate_connection(conn, ['psu1', 'load1'], [])
        self.assertTrue(any('wire_color' in e for e in errors))


class TestValidateProject(unittest.TestCase):
    """Tests for validate_project() and assert_project_valid()."""

    def test_valid_project_returns_no_errors(self):
        project = _make_valid_project()
        self.assertEqual(validate_project(project), [])

    def test_assert_valid_does_not_raise_for_valid_project(self):
        project = _make_valid_project()
        assert_project_valid(project)  # Should not raise

    def test_assert_valid_raises_for_invalid_project(self):
        profile = ProjectProfile('', 'automotive', 'lv_12v')
        project = WiringProject(profile=profile)
        with self.assertRaises(ValidationError):
            assert_project_valid(project)

    def test_invalid_connection_reference_produces_error(self):
        project = _make_valid_project()
        # Add a connection that references a non-existent component
        bad_conn = Connection('c99', 'ghost_id', '+', 'load1', 'VCC', 5.0, 3.0, 'red')
        project.connections.append(bad_conn)
        errors = validate_project(project)
        self.assertTrue(any('ghost_id' in e for e in errors))


if __name__ == '__main__':
    unittest.main()

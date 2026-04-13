"""
Tests for core.revision_engine, validating add/update/remove behavior and validation failures.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.project_schema import Component, Connection, ProjectProfile, WiringProject
from core.revision_engine import apply_changes
from core.validators import ValidationError


def create_revision_project() -> WiringProject:
    """Create a project fixture used by revision tests."""
    profile = ProjectProfile("Revision Test", "automotive", "lv_12v")
    components = [
        Component("battery1", "Main Battery", "battery", 50.0),
        Component("ecu1", "Aftermarket ECU", "ecu", 8.0),
    ]
    connections = [
        Connection("conn_001", "battery1", "+12V", "ecu1", "BATT+", 8.0, 6.0, "red"),
    ]
    return WiringProject(profile=profile, components=components, connections=connections)


class TestApplyChanges(unittest.TestCase):
    """Behavior tests for revision operations."""

    def test_add_component_and_connection(self) -> None:
        project = create_revision_project()
        change_requests = [
            {
                "operation": "add_component",
                "payload": {
                    "component_id": "relay1",
                    "component_name": "Main Relay",
                    "component_type": "relay",
                    "current_draw_amps": 1.0,
                },
            },
            {
                "operation": "add_connection",
                "payload": {
                    "connection_id": "conn_002",
                    "from_component_id": "battery1",
                    "from_pin": "+12V",
                    "to_component_id": "relay1",
                    "to_pin": "IN",
                    "current_amps": 4.0,
                    "run_length_ft": 4.0,
                    "wire_color": "red",
                },
            },
        ]
        updated_project = apply_changes(project, change_requests)
        self.assertIsNotNone(updated_project.find_component("relay1"))
        self.assertIsNotNone(updated_project.find_connection("conn_002"))

    def test_remove_component_cascades_to_connections(self) -> None:
        project = create_revision_project()
        change_requests = [{"operation": "remove_component", "payload": {"component_id": "ecu1"}}]
        updated_project = apply_changes(project, change_requests)
        self.assertIsNone(updated_project.find_component("ecu1"))
        self.assertEqual(len(updated_project.connections), 0)

    def test_unknown_operation_raises_value_error(self) -> None:
        project = create_revision_project()
        with self.assertRaises(ValueError):
            apply_changes(project, [{"operation": "teleport_wire", "payload": {}}])

    def test_invalid_post_change_state_raises_validation_error(self) -> None:
        project = create_revision_project()
        change_requests = [
            {
                "operation": "update_connection",
                "payload": {
                    "connection_id": "conn_001",
                    "run_length_ft": 0.01,
                },
            },
        ]
        with self.assertRaises(ValidationError):
            apply_changes(project, change_requests)


if __name__ == "__main__":
    unittest.main()


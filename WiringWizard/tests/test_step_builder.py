"""
Tests for core.step_builder, validating low-voltage instructions and mains checklist behavior.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.project_schema import Component, Connection, ProjectProfile, WiringProject
from core.step_builder import MAINS_SAFETY_CHECKLIST, build_step_list


def create_low_voltage_project() -> WiringProject:
    """Create a low-voltage automotive project fixture for step tests."""
    profile = ProjectProfile("Step Test", "automotive", "lv_12v")
    components = [
        Component("battery1", "Main Battery", "battery", 50.0),
        Component("ecu1", "Aftermarket ECU", "ecu", 8.0),
    ]
    connections = [
        Connection("conn_001", "battery1", "+12V", "ecu1", "BATT+", 8.0, 6.0, "red"),
    ]
    return WiringProject(profile=profile, components=components, connections=connections)


def create_mains_project() -> WiringProject:
    """Create a home electrical fixture to verify mains checklist-only behavior."""
    profile = ProjectProfile("Home Step Test", "home_electrical", "mains_120v")
    components = [Component("panel1", "Panel", "breaker", 20.0)]
    return WiringProject(profile=profile, components=components, connections=[])


class TestBuildStepList(unittest.TestCase):
    """Behavior tests for generated instruction lists."""

    def test_low_voltage_project_returns_numbered_steps(self) -> None:
        project = create_low_voltage_project()
        steps = build_step_list(project)
        self.assertGreater(len(steps), 5)
        self.assertTrue(any("Step 1" in step for step in steps))
        self.assertTrue(any("Connection 1" in step for step in steps))

    def test_mains_project_returns_checklist_only(self) -> None:
        project = create_mains_project()
        steps = build_step_list(project)
        self.assertEqual(steps, MAINS_SAFETY_CHECKLIST)
        self.assertTrue(any("does NOT generate full mains" in step for step in steps))


if __name__ == "__main__":
    unittest.main()


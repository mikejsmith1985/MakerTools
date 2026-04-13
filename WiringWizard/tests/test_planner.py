"""
Tests for core.planner, covering connection record enrichment and component summaries.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.planner import build_component_summary, build_connection_records
from core.project_schema import Component, Connection, ProjectProfile, WiringProject


def create_sample_project() -> WiringProject:
    """Create a deterministic sample wiring project for planner tests."""
    profile = ProjectProfile("Planner Test", "automotive", "lv_12v")
    components = [
        Component("battery1", "Main Battery", "battery", 60.0),
        Component("ecu1", "Aftermarket ECU", "ecu", 8.0),
        Component("relay1", "Main Relay", "relay", 1.0),
    ]
    connections = [
        Connection("conn_002", "relay1", "OUT", "ecu1", "BATT+", 8.0, 7.0, "red"),
        Connection("conn_001", "battery1", "+12V", "relay1", "IN", 12.0, 3.0, "red"),
    ]
    return WiringProject(profile=profile, components=components, connections=connections)


class TestBuildConnectionRecords(unittest.TestCase):
    """Behavior tests for planner connection enrichment output."""

    def test_records_are_sorted_by_connection_id(self) -> None:
        project = create_sample_project()
        connection_records = build_connection_records(project)
        connection_ids = [record["connection_id"] for record in connection_records]
        self.assertEqual(connection_ids, ["conn_001", "conn_002"])

    def test_record_includes_resolved_component_names(self) -> None:
        project = create_sample_project()
        connection_records = build_connection_records(project)
        first_record = connection_records[0]
        self.assertEqual(first_record["from_component_name"], "Main Battery")
        self.assertEqual(first_record["to_component_name"], "Main Relay")

    def test_awg_override_is_applied_when_present(self) -> None:
        project = create_sample_project()
        project.connections[0].awg_override = "12"
        connection_records = build_connection_records(project)
        self.assertEqual(connection_records[1]["effective_awg"], "12")
        self.assertTrue(connection_records[1]["is_awg_overridden"])


class TestBuildComponentSummary(unittest.TestCase):
    """Behavior tests for planner component summary calculations."""

    def test_component_current_totals_are_computed(self) -> None:
        project = create_sample_project()
        summary_rows = build_component_summary(project)

        by_id = {row["component_id"]: row for row in summary_rows}
        self.assertEqual(by_id["battery1"]["connected_outgoing_amps"], 12.0)
        self.assertEqual(by_id["battery1"]["connected_incoming_amps"], 0.0)
        self.assertEqual(by_id["relay1"]["connected_outgoing_amps"], 8.0)
        self.assertEqual(by_id["relay1"]["connected_incoming_amps"], 12.0)


if __name__ == "__main__":
    unittest.main()


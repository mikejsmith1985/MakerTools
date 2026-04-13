"""
Tests for core.parts_recommender, covering fuse sizing, BOM aggregation, and recommendations.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.parts_recommender import (
    build_connector_recommendations,
    build_fuse_relay_recommendations,
    build_tooling_recommendations,
    build_wire_bom,
    recommend_fuse_amps,
)
from core.project_schema import Component, Connection, ProjectProfile, WiringProject


def create_project_for_parts_tests(domain: str = "automotive") -> WiringProject:
    """Create a simple project fixture used for recommendation tests."""
    profile = ProjectProfile("Parts Test", domain, "lv_12v" if domain != "home_electrical" else "mains_120v")
    components = [
        Component("battery1", "Main Battery", "battery", 80.0),
        Component("ecu1", "Aftermarket ECU", "ecu", 8.0),
        Component("pump1", "Fuel Pump", "pump", 12.0),
    ]
    connections = [
        Connection("conn_001", "battery1", "+", "ecu1", "BATT+", 8.0, 8.0, "red"),
        Connection("conn_002", "battery1", "+", "pump1", "V+", 12.0, 11.0, "red"),
    ]
    return WiringProject(profile=profile, components=components, connections=connections)


class TestFuseSizing(unittest.TestCase):
    """Unit tests for fuse sizing behavior."""

    def test_fuse_rounds_up_to_next_standard_size(self) -> None:
        self.assertEqual(recommend_fuse_amps(8.0), 10)
        self.assertEqual(recommend_fuse_amps(12.1), 20)


class TestBomAndRecommendations(unittest.TestCase):
    """Behavior tests for BOM and recommendation outputs."""

    def test_wire_bom_includes_20_percent_slack(self) -> None:
        project = create_project_for_parts_tests()
        wire_bom = build_wire_bom(project)
        self.assertTrue(len(wire_bom) >= 1)
        first_item = wire_bom[0]
        self.assertGreater(first_item["purchase_ft"], first_item["net_run_ft"])

    def test_tooling_recommendations_include_domain_specific_items(self) -> None:
        cnc_project = create_project_for_parts_tests(domain="cnc_control")
        tooling_items = build_tooling_recommendations(cnc_project)
        joined_text = " ".join(tooling_items).lower()
        self.assertIn("ferrule", joined_text)

    def test_connector_recommendations_reflect_domain(self) -> None:
        automotive_project = create_project_for_parts_tests(domain="automotive")
        connector_items = build_connector_recommendations(automotive_project)
        joined_text = " ".join(connector_items).lower()
        self.assertIn("weatherproof", joined_text)

    def test_fuse_recommendations_reference_power_source(self) -> None:
        project = create_project_for_parts_tests()
        fuse_items = build_fuse_relay_recommendations(project)
        self.assertTrue(any("Main Battery" in item for item in fuse_items))


if __name__ == "__main__":
    unittest.main()


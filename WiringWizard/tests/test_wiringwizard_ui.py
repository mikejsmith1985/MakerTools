"""
Tests for WiringWizard.py helper functions used by the desktop UI.
"""

import json
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from WiringWizard import build_report_for_project, create_project_from_input_strings
from core.ai_intake import draft_project_from_brief


class TestCreateProjectFromInputStrings(unittest.TestCase):
    """Behavior tests for JSON parsing and project construction helpers."""

    def test_valid_payload_creates_project(self) -> None:
        project = create_project_from_input_strings(
            project_name="UI Helper Project",
            domain="automotive",
            voltage_class="lv_12v",
            description="Test project",
            components_json_text='[{"component_id":"battery1","component_name":"Battery","component_type":"battery","current_draw_amps":30}]',
            connections_json_text='[]',
        )
        self.assertEqual(project.profile.project_name, "UI Helper Project")
        self.assertEqual(len(project.components), 1)

    def test_invalid_components_json_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            create_project_from_input_strings(
                project_name="Bad JSON",
                domain="automotive",
                voltage_class="lv_12v",
                description="",
                components_json_text="{bad_json",
                connections_json_text="[]",
            )


class TestBuildReportForProject(unittest.TestCase):
    """Behavior tests for full report generation helper."""

    def test_report_contains_expected_sections(self) -> None:
        project = create_project_from_input_strings(
            project_name="Report Project",
            domain="automotive",
            voltage_class="lv_12v",
            description="Generate report",
            components_json_text=(
                '[{"component_id":"battery1","component_name":"Battery","component_type":"battery","current_draw_amps":30},'
                '{"component_id":"ecu1","component_name":"ECU","component_type":"ecu","current_draw_amps":8}]'
            ),
            connections_json_text=(
                '[{"connection_id":"conn_001","from_component_id":"battery1","from_pin":"+12V","to_component_id":"ecu1",'
                '"to_pin":"BATT+","current_amps":8,"run_length_ft":8,"wire_color":"red"}]'
            ),
        )
        report_text = build_report_for_project(project)
        self.assertIn("WIRING DIAGRAM", report_text)
        self.assertIn("CONNECTION TABLE", report_text)
        self.assertIn("STEP-BY-STEP INSTRUCTIONS", report_text)


class TestAiDraftCompatibilityWithProjectBuilder(unittest.TestCase):
    """
    Verify that the fallback draft payload from draft_project_from_brief produces
    JSON that can be parsed by create_project_from_input_strings without raising.

    This confirms the two modules stay compatible without requiring a live AI token.
    """

    def test_fallback_components_json_is_parseable_by_project_builder(self) -> None:
        import os
        for var in ("WIRINGWIZARD_GITHUB_TOKEN", "GITHUB_MODELS_TOKEN", "GITHUB_AI_TOKEN"):
            os.environ.pop(var, None)

        draft_payload = draft_project_from_brief(
            brief_text="Arduino Nano controls a fan via relay, powered by 12V battery",
            requested_project_name="Fan Controller",
        )

        components_json_text = json.dumps(draft_payload["components"])
        connections_json_text = json.dumps(draft_payload["connections"])

        # create_project_from_input_strings must not raise for well-formed fallback output.
        project = create_project_from_input_strings(
            project_name=draft_payload["project_name"],
            domain="automotive",
            voltage_class="lv_12v",
            description=draft_payload["description"],
            components_json_text=components_json_text,
            connections_json_text=connections_json_text,
        )
        self.assertGreaterEqual(len(project.components), 1)

    def test_fallback_draft_used_ai_is_false_without_token(self) -> None:
        import os
        for var in ("WIRINGWIZARD_GITHUB_TOKEN", "GITHUB_MODELS_TOKEN", "GITHUB_AI_TOKEN"):
            os.environ.pop(var, None)

        draft_payload = draft_project_from_brief("battery and led project", "LED Test")
        self.assertFalse(draft_payload["used_ai"])


if __name__ == "__main__":
    unittest.main()


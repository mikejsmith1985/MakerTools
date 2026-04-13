"""
Tests for core.diagram_renderer, validating diagram, table, and full report output.
"""

import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.diagram_renderer import (
    render_ascii_diagram,
    render_component_centered_layout,
    render_connection_table,
    render_full_report,
    render_pin_cross_reference,
    render_wire_color_legend,
)
from core.project_schema import Component, Connection, ProjectProfile, WiringProject


def create_render_project() -> WiringProject:
    """Create a consistent project fixture for rendering tests."""
    profile = ProjectProfile("Renderer Test", "automotive", "lv_12v")
    components = [
        Component("battery1", "Main Battery", "battery", 60.0),
        Component("ecu1", "Aftermarket ECU", "ecu", 8.0),
    ]
    connections = [
        Connection("conn_001", "battery1", "+12V", "ecu1", "BATT+", 8.0, 8.0, "red"),
    ]
    return WiringProject(profile=profile, components=components, connections=connections)


class TestRenderAsciiDiagram(unittest.TestCase):
    """Behavior tests for ASCII diagram generation."""

    def test_diagram_contains_project_name_and_connection_line(self) -> None:
        project = create_render_project()
        diagram_text = render_ascii_diagram(project)
        self.assertIn("Renderer Test", diagram_text)
        self.assertIn("Main Battery", diagram_text)
        self.assertIn("Aftermarket ECU", diagram_text)


class TestRenderConnectionTable(unittest.TestCase):
    """Behavior tests for connection table output."""

    def test_table_contains_headers_and_connection_id(self) -> None:
        project = create_render_project()
        table_text = render_connection_table(project)
        self.assertIn("CONNECTION TABLE", table_text)
        self.assertIn("conn_001", table_text)
        self.assertIn("V-DROP%", table_text)


class TestRenderComponentCenteredLayout(unittest.TestCase):
    """Behavior tests for module-centered harness layout generation."""

    def test_layout_contains_module_layout_header(self) -> None:
        project = create_render_project()
        layout_text = render_component_centered_layout(project)
        self.assertIn('MODULE LAYOUT', layout_text)

    def test_layout_contains_component_name_type_and_block_border(self) -> None:
        # Each component block starts with '+--' followed by the component name and type
        project = create_render_project()
        layout_text = render_component_centered_layout(project)
        self.assertIn('Main Battery', layout_text)
        self.assertIn('battery', layout_text)
        self.assertIn('+--', layout_text)

    def test_layout_shows_outgoing_section_for_source_component(self) -> None:
        # The battery is the wire source, so its block must have an Outgoing section
        project = create_render_project()
        layout_text = render_component_centered_layout(project)
        self.assertIn('Outgoing', layout_text)

    def test_layout_shows_incoming_section_for_destination_component(self) -> None:
        # The ECU is the wire destination, so its block must have an Incoming section
        project = create_render_project()
        layout_text = render_component_centered_layout(project)
        self.assertIn('Incoming', layout_text)

    def test_layout_shows_pin_labels_and_wire_color(self) -> None:
        project = create_render_project()
        layout_text = render_component_centered_layout(project)
        self.assertIn('+12V', layout_text)
        self.assertIn('BATT+', layout_text)
        self.assertIn('red', layout_text)


class TestRenderWireColorLegend(unittest.TestCase):
    """Behavior tests for wire colour / function legend output."""

    def test_legend_contains_section_header_and_domain_display_name(self) -> None:
        project = create_render_project()
        legend_text = render_wire_color_legend(project)
        self.assertIn('WIRE COLOUR / FUNCTION LEGEND', legend_text)
        # Automotive domain display name from domain_profiles
        self.assertIn('Automotive / 12V\u201324V', legend_text)

    def test_used_marker_present_for_wire_color_used_in_project(self) -> None:
        # The fixture uses "red" wire; that entry must be tagged [used]
        project = create_render_project()
        legend_text = render_wire_color_legend(project)
        red_line = next(
            (line for line in legend_text.splitlines() if line.strip().startswith('red')),
            None,
        )
        self.assertIsNotNone(red_line, 'Expected a legend row for color "red"')
        self.assertIn('[used]', red_line)

    def test_used_marker_absent_for_color_not_wired_in_project(self) -> None:
        # "black" is defined in the automotive profile but not used in the test fixture
        project = create_render_project()
        legend_text = render_wire_color_legend(project)
        black_line = next(
            (line for line in legend_text.splitlines() if line.strip().startswith('black')),
            None,
        )
        self.assertIsNotNone(black_line, 'Expected a legend row for color "black"')
        self.assertNotIn('[used]', black_line)

    def test_project_specific_color_labeled_and_marked_used(self) -> None:
        # "purple" is not in the automotive domain profile, so it becomes project-specific
        profile = ProjectProfile('Legend Test', 'automotive', 'lv_12v')
        components = [
            Component('battery1', 'Main Battery', 'battery', 60.0),
            Component('relay1', 'Main Relay', 'relay', 5.0),
        ]
        connections = [
            Connection('conn_a01', 'battery1', '+12V', 'relay1', 'IN', 5.0, 3.0, 'purple'),
        ]
        project = WiringProject(profile=profile, components=components, connections=connections)
        legend_text = render_wire_color_legend(project)
        purple_line = next(
            (line for line in legend_text.splitlines() if 'purple' in line),
            None,
        )
        self.assertIsNotNone(purple_line, 'Expected a legend row for color "purple"')
        self.assertIn('project-specific', purple_line)
        self.assertIn('[used]', purple_line)


class TestRenderPinCrossReference(unittest.TestCase):
    """Behavior tests for pin cross-reference table generation."""

    def test_xref_contains_section_header(self) -> None:
        project = create_render_project()
        xref_text = render_pin_cross_reference(project)
        self.assertIn('PIN CROSS-REFERENCE', xref_text)

    def test_xref_contains_all_column_headers(self) -> None:
        project = create_render_project()
        xref_text = render_pin_cross_reference(project)
        for expected_header in ('ID', 'FROM', 'TO', 'COLOR', 'AWG'):
            self.assertIn(expected_header, xref_text)

    def test_xref_row_contains_connection_and_component_data(self) -> None:
        project = create_render_project()
        xref_text = render_pin_cross_reference(project)
        self.assertIn('conn_001', xref_text)
        self.assertIn('Main Battery', xref_text)
        self.assertIn('Aftermarket ECU', xref_text)
        self.assertIn('+12V', xref_text)
        self.assertIn('BATT+', xref_text)
        self.assertIn('red', xref_text)



class TestRenderFullReport(unittest.TestCase):
    """Behavior tests for full report assembly."""

    def test_full_report_includes_all_sections(self) -> None:
        project = create_render_project()
        report_text = render_full_report(
            project,
            step_list=["Step 1: Do something safe."],
            bom_items=[{"item": "AWG 14 red wire", "purchase_ft": 10, "net_run_ft": 8, "connection_count": 1}],
            tooling=["Wire stripper"],
            fuse_recommendations=["Main Battery: install 15A fuse."],
            connector_recommendations=["Use ring terminals."],
        )
        self.assertIn("WIRING DIAGRAM", report_text)
        self.assertIn("CONNECTION TABLE", report_text)
        self.assertIn("BILL OF MATERIALS", report_text)
        self.assertIn("STEP-BY-STEP INSTRUCTIONS", report_text)


    def test_full_report_includes_all_new_section_headers_in_expected_order(self) -> None:
        # Sections must appear in this exact order in the assembled report
        project = create_render_project()
        report_text = render_full_report(project)
        expected_ordered_headers = [
            'WIRING DIAGRAM',
            'MODULE LAYOUT',
            'WIRE COLOUR / FUNCTION LEGEND',
            'PIN CROSS-REFERENCE',
            'CONNECTION TABLE',
        ]
        last_found_position = -1
        for section_header in expected_ordered_headers:
            found_position = report_text.find(section_header)
            self.assertGreater(
                found_position,
                last_found_position,
                msg=f"Section '{section_header}' missing or out of order in full report.",
            )
            last_found_position = found_position



if __name__ == "__main__":
    unittest.main()

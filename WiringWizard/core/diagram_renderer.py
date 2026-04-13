"""
WiringWizard diagram renderer — generates an ASCII block diagram, module-centered layout,
wire colour legend, pin cross-reference, and a formatted connection table for
human-readable, printable plain-text output.
"""

from typing import Any, Dict, List, Set

from .domain_profiles import DOMAIN_PROFILES
from .planner import build_component_summary, build_connection_records
from .project_schema import WiringProject

# ── Layout constants ──
DIAGRAM_WIDTH    = 60   # width of the header/diagram section
MODULE_BLOCK_WIDTH = 62 # width of each component block in the module layout
LEGEND_WIDTH     = 52   # width of the colour legend section
XREF_COL_ID      = 14   # column width: connection ID in the pin cross-reference
XREF_COL_FROM    = 28   # column width: from-component cell
XREF_COL_TO      = 28   # column width: to-component cell
XREF_COL_COLOR   = 12   # column width: wire colour
XREF_COL_AWG     = 6    # column width: AWG gauge


def render_ascii_diagram(project: WiringProject) -> str:
    """
    Generate a simple ASCII block diagram showing all components as numbered labels
    and all connections as annotated arrows.
    Returns a single multi-line string suitable for plain-text output.
    """
    connection_records = build_connection_records(project)
    component_summary = build_component_summary(project)

    # Map component_id -> display label so arrows can show short names
    label_map: Dict[str, str] = {}
    for index, summary in enumerate(component_summary):
        label_map[summary['component_id']] = f'[{index + 1}] {summary["component_name"]}'

    lines: List[str] = []
    lines.append('=' * 60)
    lines.append(f'  WIRING DIAGRAM: {project.profile.project_name}')
    lines.append(f'  Domain: {project.profile.domain}  |  Voltage: {project.profile.voltage_class}')
    lines.append('=' * 60)
    lines.append('')

    lines.append('COMPONENTS:')
    for index, summary in enumerate(component_summary):
        position_note = (
            f'  [{summary["position_label"]}]'
            if summary['position_label']
            else ''
        )
        lines.append(
            f'  [{index + 1}] {summary["component_name"]} '
            f'({summary["component_type"]}){position_note}'
        )
    lines.append('')

    lines.append('CONNECTIONS:')
    for record in connection_records:
        from_label = label_map.get(record['from_component_id'], record['from_component_id'])
        to_label   = label_map.get(record['to_component_id'],   record['to_component_id'])

        awg_note = f'AWG {record["effective_awg"]}'
        if record['is_awg_overridden']:
            awg_note += '*'

        lines.append(
            f'  {from_label} ({record["from_pin"]})'
            f'  ---[{record["wire_color"]} {awg_note} {record["current_amps"]}A]--->'
            f'  {to_label} ({record["to_pin"]})'
        )

    lines.append('')
    lines.append('  (* = user-overridden AWG gauge)')
    lines.append('')

    return '\n'.join(lines)


def render_component_centered_layout(project: WiringProject) -> str:
    """
    Generate a module-centered harness layout: each component is shown as a bordered
    block listing all outgoing and incoming wires with their pin labels, colour, and AWG.
    Inspired by draw.io harness block-diagram style for at-a-glance readability.
    Returns a single multi-line string.
    """
    connection_records = build_connection_records(project)
    component_summary  = build_component_summary(project)

    # Index connection records by component so lookups are O(1) per component
    outgoing_by_component: Dict[str, List[Dict[str, Any]]] = {}
    incoming_by_component: Dict[str, List[Dict[str, Any]]] = {}
    for record in connection_records:
        outgoing_by_component.setdefault(record['from_component_id'], []).append(record)
        incoming_by_component.setdefault(record['to_component_id'], []).append(record)

    separator_bar = '+' + '-' * (MODULE_BLOCK_WIDTH - 1)

    lines: List[str] = []
    lines.append('=' * MODULE_BLOCK_WIDTH)
    lines.append('  MODULE LAYOUT')
    lines.append('=' * MODULE_BLOCK_WIDTH)
    lines.append('')

    for summary in component_summary:
        component_id    = summary['component_id']
        component_title = f'{summary["component_name"]}  [{summary["component_type"]}]'

        # Top border with component title embedded
        title_padding = MODULE_BLOCK_WIDTH - 4 - len(component_title)
        lines.append(f'+-- {component_title} ' + '-' * max(0, title_padding))

        # Location and current summary
        if summary['position_label']:
            lines.append(f'|  Location : {summary["position_label"]}')
        lines.append(
            f'|  Rated {summary["rated_current_draw_amps"]}A'
            f'  |  Incoming {summary["connected_incoming_amps"]}A'
            f'  |  Outgoing {summary["connected_outgoing_amps"]}A'
        )

        # Outgoing wires — this component is the source
        outgoing_records = outgoing_by_component.get(component_id, [])
        if outgoing_records:
            lines.append('|  -- Outgoing ----------------------------------------')
            for record in outgoing_records:
                awg_note = f'AWG {record["effective_awg"]}' + ('*' if record['is_awg_overridden'] else '')
                lines.append(
                    f'|    [{record["from_pin"]}]'
                    f'  --{record["wire_color"]} {awg_note}-->'
                    f'  {record["to_component_name"]} [{record["to_pin"]}]'
                )

        # Incoming wires — this component is the destination
        incoming_records = incoming_by_component.get(component_id, [])
        if incoming_records:
            lines.append('|  -- Incoming ----------------------------------------')
            for record in incoming_records:
                awg_note = f'AWG {record["effective_awg"]}' + ('*' if record['is_awg_overridden'] else '')
                lines.append(
                    f'|    [{record["to_pin"]}]'
                    f'  <--{record["wire_color"]} {awg_note}--'
                    f'  {record["from_component_name"]} [{record["from_pin"]}]'
                )

        lines.append(separator_bar)
        lines.append('')

    return '\n'.join(lines)


def render_wire_color_legend(project: WiringProject) -> str:
    """
    Build a wire colour / function legend by combining:
      1. Domain-profile typical_wire_colors — the standard colour-to-function mapping
         defined for this wiring domain (automotive, CNC, etc.)
      2. Any extra colours actually used in this project not covered by the domain profile.
    Colours present in the project are marked [used] for quick identification.
    Returns a single multi-line string.
    """
    domain_profile = DOMAIN_PROFILES.get(project.profile.domain, {})
    typical_colors = domain_profile.get('typical_wire_colors', {})

    # Build colour -> function_label map; when one colour serves multiple functions,
    # keep the first (most prominent) function name from the domain profile dict.
    color_to_function: Dict[str, str] = {}
    for function_label, color_name in typical_colors.items():
        if color_name not in color_to_function:
            color_to_function[color_name] = function_label

    # Colours actually wired in this project
    colors_used_in_project: Set[str] = {conn.wire_color for conn in project.connections}

    # Merge project colours not covered by the domain profile
    for project_color in colors_used_in_project:
        if project_color not in color_to_function:
            color_to_function[project_color] = 'project-specific'

    domain_display_name = domain_profile.get('display_name', project.profile.domain)

    lines: List[str] = []
    lines.append('=' * LEGEND_WIDTH)
    lines.append('  WIRE COLOUR / FUNCTION LEGEND')
    lines.append(f'  Domain: {domain_display_name}')
    lines.append('=' * LEGEND_WIDTH)

    for color_name in sorted(color_to_function):
        function_label  = color_to_function[color_name]
        in_use_marker   = '  [used]' if color_name in colors_used_in_project else ''
        lines.append(f'  {color_name:<14}  {function_label}{in_use_marker}')

    lines.append('')
    return '\n'.join(lines)


def render_pin_cross_reference(project: WiringProject) -> str:
    """
    Generate a compact pin cross-reference table listing every connection as a row:
    connection ID | from component (pin) | to component (pin) | colour | AWG.
    Useful when terminating connectors — find any pin quickly by scanning one table.
    Returns a single multi-line string.
    """
    connection_records = build_connection_records(project)

    table_width = XREF_COL_ID + XREF_COL_FROM + XREF_COL_TO + XREF_COL_COLOR + XREF_COL_AWG + 4
    separator   = '-' * table_width

    lines: List[str] = []
    lines.append('=' * table_width)
    lines.append('  PIN CROSS-REFERENCE')
    lines.append('=' * table_width)

    header = (
        f'{"ID":<{XREF_COL_ID}} '
        f'{"FROM  component (pin)":<{XREF_COL_FROM}} '
        f'{"TO  component (pin)":<{XREF_COL_TO}} '
        f'{"COLOR":<{XREF_COL_COLOR}} '
        f'{"AWG":<{XREF_COL_AWG}}'
    )
    lines.append(header)
    lines.append(separator)

    for record in connection_records:
        from_cell   = f'{record["from_component_name"]} ({record["from_pin"]})'
        to_cell     = f'{record["to_component_name"]} ({record["to_pin"]})'
        awg_display = record['effective_awg'] + ('*' if record['is_awg_overridden'] else '')

        row = (
            f'{record["connection_id"]:<{XREF_COL_ID}} '
            f'{from_cell:<{XREF_COL_FROM}} '
            f'{to_cell:<{XREF_COL_TO}} '
            f'{record["wire_color"]:<{XREF_COL_COLOR}} '
            f'{awg_display:<{XREF_COL_AWG}}'
        )
        lines.append(row)

    lines.append(separator)
    lines.append('')
    return '\n'.join(lines)


def render_connection_table(project: WiringProject) -> str:
    """
    Generate a formatted text table listing every connection with full details:
    ID, from/to component+pin, wire colour, AWG, current, run length, and voltage drop %.
    Returns a single multi-line string.
    """
    connection_records = build_connection_records(project)

    separator = '-' * 102
    lines: List[str] = []
    lines.append('=' * 102)
    lines.append('  CONNECTION TABLE')
    lines.append('=' * 102)

    header = (
        f'{"ID":<14} '
        f'{"FROM (pin)":<25} '
        f'{"TO (pin)":<25} '
        f'{"COLOR":<10} '
        f'{"AWG":<5} '
        f'{"AMPS":>6} '
        f'{"RUN FT":>7} '
        f'{"V-DROP%":>8}'
    )
    lines.append(header)
    lines.append(separator)

    for record in connection_records:
        from_cell  = f'{record["from_component_name"]} ({record["from_pin"]})'
        to_cell    = f'{record["to_component_name"]} ({record["to_pin"]})'
        awg_display = record['effective_awg'] + ('*' if record['is_awg_overridden'] else '')

        row = (
            f'{record["connection_id"]:<14} '
            f'{from_cell:<25} '
            f'{to_cell:<25} '
            f'{record["wire_color"]:<10} '
            f'{awg_display:<5} '
            f'{record["current_amps"]:>6.2f} '
            f'{record["run_length_ft"]:>7.1f} '
            f'{record["voltage_drop_percent"]:>7.2f}%'
        )
        lines.append(row)

    lines.append(separator)
    lines.append('')

    return '\n'.join(lines)


def render_full_report(
    project: WiringProject,
    step_list: List[str] = None,
    bom_items: List[Dict[str, Any]] = None,
    tooling: List[str] = None,
    fuse_recommendations: List[str] = None,
    connector_recommendations: List[str] = None,
) -> str:
    """
    Assemble all report sections into one printable plain-text report:
      1. ASCII diagram (component list + connection arrows)
      2. Module layout (component-centered blocks with labelled ports)
      3. Wire colour / function legend (domain profile + project-specific colours)
      4. Pin cross-reference (compact from/to lookup table)
      5. Connection table (full detail: AWG, amps, run length, voltage drop)
      6. Fuse / protection recommendations (if provided)
      7. Connector / terminal recommendations (if provided)
      8. Bill of materials — wire (if provided)
      9. Tools & supplies (if provided)
     10. Step-by-step instructions (if provided)
    Returns a single multi-line string.
    """
    sections: List[str] = []

    sections.append(render_ascii_diagram(project))
    sections.append(render_component_centered_layout(project))
    sections.append(render_wire_color_legend(project))
    sections.append(render_pin_cross_reference(project))
    sections.append(render_connection_table(project))

    if fuse_recommendations:
        sections.append('FUSE / PROTECTION RECOMMENDATIONS:')
        for rec in fuse_recommendations:
            sections.append(f'  \u2022 {rec}')
        sections.append('')

    if connector_recommendations:
        sections.append('CONNECTOR / TERMINAL RECOMMENDATIONS:')
        for rec in connector_recommendations:
            sections.append(f'  \u2022 {rec}')
        sections.append('')

    if bom_items:
        sections.append('BILL OF MATERIALS \u2014 WIRE:')
        for item in bom_items:
            sections.append(
                f'  \u2022 {item["item"]} \u2014 {item["purchase_ft"]} ft '
                f'({item["net_run_ft"]} ft net + 20% slack, '
                f'{item["connection_count"]} connection(s))'
            )
        sections.append('')

    if tooling:
        sections.append('TOOLS & SUPPLIES NEEDED:')
        for tool_item in tooling:
            sections.append(f'  \u2022 {tool_item}')
        sections.append('')

    if step_list:
        sections.append('STEP-BY-STEP INSTRUCTIONS:')
        for step in step_list:
            sections.append(f'  {step}')
        sections.append('')

    return '\n'.join(sections)

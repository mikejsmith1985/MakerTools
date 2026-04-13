"""
WiringWizard harness planner — converts a validated WiringProject into deterministic,
enriched connection records and component summaries ready for rendering and output.
"""

from typing import Any, Dict, List

from .project_schema import WiringProject
from .wire_sizing import recommend_awg


def build_connection_records(project: WiringProject) -> List[Dict[str, Any]]:
    """
    Process every connection in the project and return a list of enriched records.
    Each record adds resolved component names, auto-sized AWG, and voltage-drop data.
    Results are sorted by connection_id for repeatable, deterministic output.
    """
    sorted_connections = sorted(project.connections, key=lambda conn: conn.connection_id)
    records = []

    for connection in sorted_connections:
        from_component = project.find_component(connection.from_component_id)
        to_component = project.find_component(connection.to_component_id)

        sizing = recommend_awg(
            connection.current_amps,
            connection.run_length_ft,
            project.profile.voltage_class,
        )

        # Honour user override if one was provided
        effective_awg = (
            connection.awg_override
            if connection.awg_override
            else sizing['recommended_awg']
        )
        is_awg_overridden = connection.awg_override is not None

        record = {
            'connection_id':       connection.connection_id,
            'from_component_id':   connection.from_component_id,
            'from_component_name': from_component.component_name if from_component else '???',
            'from_pin':            connection.from_pin,
            'to_component_id':     connection.to_component_id,
            'to_component_name':   to_component.component_name if to_component else '???',
            'to_pin':              connection.to_pin,
            'current_amps':        connection.current_amps,
            'run_length_ft':       connection.run_length_ft,
            'wire_color':          connection.wire_color,
            'recommended_awg':     sizing['recommended_awg'],
            'effective_awg':       effective_awg,
            'is_awg_overridden':   is_awg_overridden,
            'ampacity':            sizing['ampacity'],
            'voltage_drop_volts':  sizing['voltage_drop_volts'],
            'voltage_drop_percent': sizing['voltage_drop_percent'],
            'sizing_notes':        sizing['notes'],
        }
        records.append(record)

    return records


def build_component_summary(project: WiringProject) -> List[Dict[str, Any]]:
    """
    Build a summary list of all components, each annotated with the total current
    flowing out of and into it across all connections.
    Results are sorted by component_id for deterministic output.
    """
    summaries = []

    for component in sorted(project.components, key=lambda comp: comp.component_id):
        outgoing_amps = sum(
            conn.current_amps
            for conn in project.connections
            if conn.from_component_id == component.component_id
        )
        incoming_amps = sum(
            conn.current_amps
            for conn in project.connections
            if conn.to_component_id == component.component_id
        )

        summaries.append({
            'component_id':             component.component_id,
            'component_name':           component.component_name,
            'component_type':           component.component_type,
            'rated_current_draw_amps':  component.current_draw_amps,
            'connected_outgoing_amps':  round(outgoing_amps, 3),
            'connected_incoming_amps':  round(incoming_amps, 3),
            'position_label':           component.position_label,
        })

    return summaries

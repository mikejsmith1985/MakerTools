"""
WiringWizard revision engine — applies user-requested changes (add, update, remove)
to the components and connections of a WiringProject and re-validates the result.
"""

from typing import Any, Dict, List

from .project_schema import Component, Connection, WiringProject
from .validators import ValidationError, validate_project

# Recognised revision operations
VALID_OPERATIONS = (
    'add_component',    'update_component',    'remove_component',
    'add_connection',   'update_connection',   'remove_connection',
)


def apply_changes(
    project: WiringProject,
    change_requests: List[Dict[str, Any]],
) -> WiringProject:
    """
    Apply a list of change requests to a WiringProject and return the modified project.

    Each change_request dict must have:
      'operation': one of VALID_OPERATIONS
      'payload':   dict containing the data for the change

    Raises ValueError for unknown operations.
    Raises ValidationError if the project is invalid after all changes are applied.
    """
    for change_request in change_requests:
        operation = change_request.get('operation')
        payload   = change_request.get('payload', {})

        if operation == 'add_component':
            project = _add_component(project, payload)
        elif operation == 'update_component':
            project = _update_component(project, payload)
        elif operation == 'remove_component':
            project = _remove_component(project, payload)
        elif operation == 'add_connection':
            project = _add_connection(project, payload)
        elif operation == 'update_connection':
            project = _update_connection(project, payload)
        elif operation == 'remove_connection':
            project = _remove_connection(project, payload)
        else:
            raise ValueError(
                f'Unknown revision operation: {operation!r}. '
                f'Valid operations: {VALID_OPERATIONS}'
            )

    errors = validate_project(project)
    if errors:
        raise ValidationError(
            'Project is invalid after applying changes:\n' +
            '\n'.join(f'  \u2022 {error}' for error in errors)
        )

    return project


def _add_component(project: WiringProject, payload: Dict[str, Any]) -> WiringProject:
    """Add a new component to the project. Raises ValueError if the ID already exists."""
    component_id = payload.get('component_id', '')
    if project.find_component(component_id):
        raise ValueError(f'Component with id {component_id!r} already exists.')

    new_component = Component(
        component_id=component_id,
        component_name=payload.get('component_name', ''),
        component_type=payload.get('component_type', ''),
        current_draw_amps=float(payload.get('current_draw_amps', 0.0)),
        position_label=payload.get('position_label', ''),
    )
    project.components.append(new_component)
    return project


def _update_component(project: WiringProject, payload: Dict[str, Any]) -> WiringProject:
    """Update fields on an existing component. Raises ValueError if not found."""
    component_id = payload.get('component_id', '')
    target = project.find_component(component_id)
    if target is None:
        raise ValueError(f'Component {component_id!r} not found for update.')

    if 'component_name' in payload:
        target.component_name = payload['component_name']
    if 'component_type' in payload:
        target.component_type = payload['component_type']
    if 'current_draw_amps' in payload:
        target.current_draw_amps = float(payload['current_draw_amps'])
    if 'position_label' in payload:
        target.position_label = payload['position_label']

    return project


def _remove_component(project: WiringProject, payload: Dict[str, Any]) -> WiringProject:
    """
    Remove a component by ID and cascade-remove any connections that reference it.
    Raises ValueError if the component is not found.
    """
    component_id = payload.get('component_id', '')
    if not project.find_component(component_id):
        raise ValueError(f'Component {component_id!r} not found for removal.')

    project.components = [
        comp for comp in project.components
        if comp.component_id != component_id
    ]
    # Remove connections that now have a dangling reference
    project.connections = [
        conn for conn in project.connections
        if conn.from_component_id != component_id
        and conn.to_component_id != component_id
    ]
    return project


def _add_connection(project: WiringProject, payload: Dict[str, Any]) -> WiringProject:
    """Add a new connection to the project. Raises ValueError if the ID already exists."""
    connection_id = payload.get('connection_id', '')
    if project.find_connection(connection_id):
        raise ValueError(f'Connection with id {connection_id!r} already exists.')

    new_connection = Connection(
        connection_id=connection_id,
        from_component_id=payload.get('from_component_id', ''),
        from_pin=payload.get('from_pin', ''),
        to_component_id=payload.get('to_component_id', ''),
        to_pin=payload.get('to_pin', ''),
        current_amps=float(payload.get('current_amps', 0.1)),
        run_length_ft=float(payload.get('run_length_ft', 1.0)),
        wire_color=payload.get('wire_color', 'red'),
        awg_override=payload.get('awg_override'),
    )
    project.connections.append(new_connection)
    return project


def _update_connection(project: WiringProject, payload: Dict[str, Any]) -> WiringProject:
    """Update fields on an existing connection. Raises ValueError if not found."""
    connection_id = payload.get('connection_id', '')
    target = project.find_connection(connection_id)
    if target is None:
        raise ValueError(f'Connection {connection_id!r} not found for update.')

    if 'from_component_id' in payload:
        target.from_component_id = payload['from_component_id']
    if 'from_pin' in payload:
        target.from_pin = payload['from_pin']
    if 'to_component_id' in payload:
        target.to_component_id = payload['to_component_id']
    if 'to_pin' in payload:
        target.to_pin = payload['to_pin']
    if 'current_amps' in payload:
        target.current_amps = float(payload['current_amps'])
    if 'run_length_ft' in payload:
        target.run_length_ft = float(payload['run_length_ft'])
    if 'wire_color' in payload:
        target.wire_color = payload['wire_color']
    if 'awg_override' in payload:
        target.awg_override = payload['awg_override']

    return project


def _remove_connection(project: WiringProject, payload: Dict[str, Any]) -> WiringProject:
    """Remove a connection by ID. Raises ValueError if not found."""
    connection_id = payload.get('connection_id', '')
    if not project.find_connection(connection_id):
        raise ValueError(f'Connection {connection_id!r} not found for removal.')

    project.connections = [
        conn for conn in project.connections
        if conn.connection_id != connection_id
    ]
    return project

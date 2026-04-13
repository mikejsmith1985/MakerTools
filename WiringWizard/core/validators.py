"""
WiringWizard validators — validates WiringProject data structures for completeness,
sane numeric ranges, and domain/voltage-class compatibility before any planning is done.
"""

from typing import List

from .project_schema import (
    WiringProject, ProjectProfile, Component, Connection,
    SUPPORTED_DOMAINS, SUPPORTED_VOLTAGE_CLASSES,
)
from .domain_profiles import get_domain_profile

# ── Numeric sanity limits ──
MAX_CURRENT_AMPS = 400.0    # hard ceiling for any single wire in a low-voltage system
MIN_CURRENT_AMPS = 0.01     # below this is noise / sensor-signal territory
MAX_RUN_LENGTH_FT = 500.0   # practical maximum run length in a single harness
MIN_RUN_LENGTH_FT = 0.1


class ValidationError(Exception):
    """Raised when a WiringProject fails validation checks."""
    pass


def validate_project_profile(profile: ProjectProfile) -> List[str]:
    """
    Check that a ProjectProfile has all required fields and valid values.
    Returns a list of error message strings; an empty list means no errors.
    """
    errors = []

    if not profile.project_name or not profile.project_name.strip():
        errors.append('project_name is required and cannot be blank.')

    if profile.domain not in SUPPORTED_DOMAINS:
        errors.append(
            f'domain {profile.domain!r} is not supported. '
            f'Choose from: {SUPPORTED_DOMAINS}'
        )

    if profile.voltage_class not in SUPPORTED_VOLTAGE_CLASSES:
        errors.append(
            f'voltage_class {profile.voltage_class!r} is not supported. '
            f'Choose from: {SUPPORTED_VOLTAGE_CLASSES}'
        )

    # Cross-check: voltage class must be legal for the chosen domain
    if profile.domain in SUPPORTED_DOMAINS and profile.voltage_class in SUPPORTED_VOLTAGE_CLASSES:
        try:
            domain_profile = get_domain_profile(profile.domain)
            allowed_classes = domain_profile['allowed_voltage_classes']
            if profile.voltage_class not in allowed_classes:
                errors.append(
                    f'voltage_class {profile.voltage_class!r} is not compatible with '
                    f'domain {profile.domain!r}. Allowed: {allowed_classes}'
                )
        except KeyError:
            pass  # Domain error already captured above

    return errors


def validate_component(component: Component, existing_ids: List[str]) -> List[str]:
    """
    Check that a Component is valid and its ID is unique among existing_ids.
    Returns a list of error message strings.
    """
    errors = []

    if not component.component_id or not component.component_id.strip():
        errors.append('component_id is required.')
    elif component.component_id in existing_ids:
        errors.append(f'Duplicate component_id: {component.component_id!r}')

    if not component.component_name or not component.component_name.strip():
        errors.append(
            f'component_name is required for component {component.component_id!r}.'
        )

    if not component.component_type or not component.component_type.strip():
        errors.append(
            f'component_type is required for component {component.component_id!r}.'
        )

    if component.current_draw_amps < 0:
        errors.append(
            f'current_draw_amps must be >= 0 for component {component.component_id!r}.'
        )

    if component.current_draw_amps > MAX_CURRENT_AMPS:
        errors.append(
            f'current_draw_amps {component.current_draw_amps}A exceeds the sanity '
            f'limit of {MAX_CURRENT_AMPS}A for component {component.component_id!r}.'
        )

    return errors


def validate_connection(
    connection: Connection,
    component_ids: List[str],
    existing_conn_ids: List[str],
) -> List[str]:
    """
    Check that a Connection references existing components and has sane numeric values.
    Returns a list of error message strings.
    """
    errors = []

    if not connection.connection_id or not connection.connection_id.strip():
        errors.append('connection_id is required.')
    elif connection.connection_id in existing_conn_ids:
        errors.append(f'Duplicate connection_id: {connection.connection_id!r}')

    if connection.from_component_id not in component_ids:
        errors.append(
            f'from_component_id {connection.from_component_id!r} '
            f'not found in project components.'
        )

    if connection.to_component_id not in component_ids:
        errors.append(
            f'to_component_id {connection.to_component_id!r} '
            f'not found in project components.'
        )

    if connection.current_amps < MIN_CURRENT_AMPS:
        errors.append(
            f'current_amps {connection.current_amps}A is below the minimum '
            f'{MIN_CURRENT_AMPS}A for connection {connection.connection_id!r}.'
        )

    if connection.current_amps > MAX_CURRENT_AMPS:
        errors.append(
            f'current_amps {connection.current_amps}A exceeds the sanity limit '
            f'{MAX_CURRENT_AMPS}A for connection {connection.connection_id!r}.'
        )

    if connection.run_length_ft < MIN_RUN_LENGTH_FT:
        errors.append(
            f'run_length_ft {connection.run_length_ft} is below the minimum '
            f'{MIN_RUN_LENGTH_FT} ft for connection {connection.connection_id!r}.'
        )

    if connection.run_length_ft > MAX_RUN_LENGTH_FT:
        errors.append(
            f'run_length_ft {connection.run_length_ft} exceeds the maximum '
            f'{MAX_RUN_LENGTH_FT} ft for connection {connection.connection_id!r}.'
        )

    if not connection.wire_color or not connection.wire_color.strip():
        errors.append(
            f'wire_color is required for connection {connection.connection_id!r}.'
        )

    return errors


def validate_project(project: WiringProject) -> List[str]:
    """
    Validate an entire WiringProject — profile, all components, and all connections.
    Returns a consolidated list of all error message strings.
    An empty list means the project is valid.
    """
    all_errors = []

    all_errors.extend(validate_project_profile(project.profile))

    # Track seen IDs so we can detect duplicates
    seen_component_ids: List[str] = []
    for component in project.components:
        component_errors = validate_component(component, seen_component_ids)
        all_errors.extend(component_errors)
        if component.component_id not in seen_component_ids:
            seen_component_ids.append(component.component_id)

    seen_connection_ids: List[str] = []
    for connection in project.connections:
        conn_errors = validate_connection(connection, seen_component_ids, seen_connection_ids)
        all_errors.extend(conn_errors)
        if connection.connection_id not in seen_connection_ids:
            seen_connection_ids.append(connection.connection_id)

    return all_errors


def assert_project_valid(project: WiringProject) -> None:
    """
    Raise a ValidationError if the project has any validation errors.
    Convenience wrapper around validate_project for use in processing pipelines.
    """
    errors = validate_project(project)
    if errors:
        raise ValidationError(
            'Project validation failed:\n' +
            '\n'.join(f'  \u2022 {error}' for error in errors)
        )

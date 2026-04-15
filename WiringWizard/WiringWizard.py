"""
WiringWizard desktop application for building low-voltage wiring plans and harness outputs.

Serves an interactive web UI via Eel (HTML/CSS/JS in the web/ folder) with a Python backend
providing AI-assisted drafting, report generation, and project persistence.
"""

import json
import os
import sys
from dataclasses import asdict
from typing import Any, Dict, List, Optional

# Allow running from this folder directly with "python WiringWizard.py"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from core.ai_intake import (
    clear_saved_gui_api_token,
    draft_project_from_brief,
    get_saved_gui_api_token,
    remap_project_with_ai,
    save_gui_api_token,
)
from core.diagram_renderer import render_full_report
from core.domain_profiles import DOMAIN_PROFILES, get_domain_profile, list_domains
from core.parts_recommender import (
    build_connector_recommendations,
    build_fuse_relay_recommendations,
    build_tooling_recommendations,
    build_wire_bom,
)
from core.planner import build_connection_records
from core.project_schema import Component, Connection, ProjectProfile, WiringProject
from core.revision_engine import apply_changes
from core.runtime_paths import resolve_runtime_app_dir
from core.step_builder import build_step_list
from core.validators import ValidationError, assert_project_valid

APP_DIR = resolve_runtime_app_dir(__file__)
DATA_DIR = os.path.join(APP_DIR, "data")
DRAFT_FILE_PATH = os.path.join(DATA_DIR, "project_draft.json")

# Eel's web directory: in frozen builds PyInstaller extracts --add-data to sys._MEIPASS
_IS_FROZEN = bool(getattr(sys, "frozen", False))
_BASE_DIR = getattr(sys, "_MEIPASS", SCRIPT_DIR) if _IS_FROZEN else SCRIPT_DIR
WEB_DIR = os.path.join(_BASE_DIR, "web")




def create_project_from_input_strings(
    project_name: str,
    domain: str,
    voltage_class: str,
    description: str,
    components_json_text: str,
    connections_json_text: str,
) -> WiringProject:
    """Build a WiringProject from raw UI string inputs and JSON payload text."""
    try:
        component_payload_items = json.loads(components_json_text or "[]")
    except json.JSONDecodeError as parse_error:
        raise ValueError(f"Components JSON is invalid: {parse_error.msg}") from parse_error

    try:
        connection_payload_items = json.loads(connections_json_text or "[]")
    except json.JSONDecodeError as parse_error:
        raise ValueError(f"Connections JSON is invalid: {parse_error.msg}") from parse_error

    if not isinstance(component_payload_items, list):
        raise ValueError("Components JSON must be a JSON array.")
    if not isinstance(connection_payload_items, list):
        raise ValueError("Connections JSON must be a JSON array.")

    profile = ProjectProfile(
        project_name=project_name.strip(),
        domain=domain.strip(),
        voltage_class=voltage_class.strip(),
        description=description.strip(),
    )
    components = [_create_component_from_payload(component_payload) for component_payload in component_payload_items]
    connections = [_create_connection_from_payload(connection_payload) for connection_payload in connection_payload_items]
    return WiringProject(profile=profile, components=components, connections=connections)


def build_report_for_project(project: WiringProject) -> str:
    """Generate a full WiringWizard report string for a validated project."""
    assert_project_valid(project)
    connection_records = build_connection_records(project)
    wire_bom_items = build_wire_bom(project)
    tooling_items = build_tooling_recommendations(project)
    connector_items = build_connector_recommendations(project)
    fuse_items = build_fuse_relay_recommendations(project)
    step_items = build_step_list(project, connection_records)
    return render_full_report(
        project,
        step_list=step_items,
        bom_items=wire_bom_items,
        tooling=tooling_items,
        fuse_recommendations=fuse_items,
        connector_recommendations=connector_items,
    )


def _create_component_from_payload(component_payload: Dict[str, Any]) -> Component:
    """Create a Component dataclass from a parsed JSON payload dictionary."""
    return Component(
        component_id=str(component_payload.get("component_id", "")).strip(),
        component_name=str(component_payload.get("component_name", "")).strip(),
        component_type=str(component_payload.get("component_type", "")).strip(),
        current_draw_amps=float(component_payload.get("current_draw_amps", 0.0)),
        position_label=str(component_payload.get("position_label", "")).strip(),
    )


def _create_connection_from_payload(connection_payload: Dict[str, Any]) -> Connection:
    """Create a Connection dataclass from a parsed JSON payload dictionary."""
    return Connection(
        connection_id=str(connection_payload.get("connection_id", "")).strip(),
        from_component_id=str(connection_payload.get("from_component_id", "")).strip(),
        from_pin=str(connection_payload.get("from_pin", "")).strip(),
        to_component_id=str(connection_payload.get("to_component_id", "")).strip(),
        to_pin=str(connection_payload.get("to_pin", "")).strip(),
        current_amps=float(connection_payload.get("current_amps", 0.0)),
        run_length_ft=float(connection_payload.get("run_length_ft", 0.0)),
        wire_color=str(connection_payload.get("wire_color", "")).strip(),
        awg_override=_normalize_optional_string(connection_payload.get("awg_override")),
    )


def _normalize_optional_string(raw_value: Any) -> Optional[str]:
    """Normalize optional string inputs, returning None for blank or missing values."""
    if raw_value is None:
        return None
    normalized_value = str(raw_value).strip()
    return normalized_value if normalized_value else None


# ── Eel-Exposed Backend API ──────────────────────────────────────────────────
# These functions are called from JavaScript via the Eel bridge.
# They are only registered when the module is run as main (not imported by tests).

def _build_project_from_dicts(
    profile_dict: Dict[str, Any],
    components_list: List[Dict[str, Any]],
    connections_list: List[Dict[str, Any]],
) -> WiringProject:
    """Reconstruct a WiringProject from raw dictionaries sent by the JS frontend."""
    profile = ProjectProfile(
        project_name=profile_dict.get("project_name", "Untitled"),
        domain=profile_dict.get("domain", "automotive"),
        voltage_class=profile_dict.get("voltage_class", "lv_12v"),
        description=profile_dict.get("description", ""),
    )
    components = [_create_component_from_payload(item) for item in components_list]
    connections = [_create_connection_from_payload(item) for item in connections_list]
    return WiringProject(profile=profile, components=components, connections=connections)


def _ensure_data_directory_exists() -> None:
    """Create the persistent data directory if it does not already exist."""
    os.makedirs(DATA_DIR, exist_ok=True)


def _register_eel_endpoints() -> None:
    """Register all @eel.expose endpoints. Called only when running as main entry point."""
    import eel as _eel

    @_eel.expose
    def list_available_domains() -> List[str]:
        """Return the list of supported wiring domain identifiers."""
        return list_domains()

    @_eel.expose
    def draft_from_brief(
        brief_text: str,
        project_name: str,
        token_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run the AI intake pipeline and return a structured draft dictionary."""
        try:
            draft_result = draft_project_from_brief(
                brief_text, project_name, api_token_override=token_override
            )
            return draft_result
        except Exception as draft_error:
            return {"error": str(draft_error)}

    @_eel.expose
    def generate_report(
        profile_dict: Dict[str, Any],
        components_list: List[Dict[str, Any]],
        connections_list: List[Dict[str, Any]],
    ) -> Any:
        """Generate the full wiring plan report text from project data."""
        try:
            project = _build_project_from_dicts(
                profile_dict, components_list, connections_list
            )
            report_text = build_report_for_project(project)
            return report_text
        except (ValidationError, ValueError) as report_error:
            return {"error": str(report_error)}

    @_eel.expose
    def apply_changes_to_project(
        profile_dict: Dict[str, Any],
        components_list: List[Dict[str, Any]],
        connections_list: List[Dict[str, Any]],
        changes_json: str,
    ) -> Dict[str, Any]:
        """Apply a JSON array of change requests and return updated project data."""
        try:
            project = _build_project_from_dicts(
                profile_dict, components_list, connections_list
            )
            change_requests = json.loads(changes_json)
            updated_project = apply_changes(project, change_requests)
            return {
                "components": [asdict(c) for c in updated_project.components],
                "connections": [asdict(c) for c in updated_project.connections],
            }
        except (json.JSONDecodeError, ValidationError, ValueError) as change_error:
            return {"error": str(change_error)}

    @_eel.expose
    def ai_remap_project(
        profile_dict: Dict[str, Any],
        components_list: List[Dict[str, Any]],
        connections_list: List[Dict[str, Any]],
        change_description: str,
    ) -> Dict[str, Any]:
        """Use AI to apply natural-language change requests to the current project."""
        try:
            return remap_project_with_ai(
                components_list, connections_list, change_description
            )
        except Exception as remap_error:
            return {"error": str(remap_error)}

    @_eel.expose
    def save_draft(draft_data: Dict[str, Any]) -> Dict[str, Any]:
        """Persist the current project draft to disk as JSON."""
        try:
            _ensure_data_directory_exists()
            with open(DRAFT_FILE_PATH, "w", encoding="utf-8") as draft_file:
                json.dump(draft_data, draft_file, indent=2)
            return {"ok": True}
        except OSError as save_error:
            return {"error": str(save_error)}

    @_eel.expose
    def load_draft() -> Dict[str, Any]:
        """Load a previously saved project draft from disk."""
        try:
            if not os.path.isfile(DRAFT_FILE_PATH):
                return {"error": "No saved draft found"}
            with open(DRAFT_FILE_PATH, "r", encoding="utf-8") as draft_file:
                return json.load(draft_file)
        except (OSError, json.JSONDecodeError) as load_error:
            return {"error": str(load_error)}

    @_eel.expose
    def save_api_token(token_value: str) -> Dict[str, Any]:
        """Persist the GitHub Models API token for future sessions."""
        try:
            save_gui_api_token(token_value)
            return {"ok": True}
        except Exception as token_error:
            return {"error": str(token_error)}

    @_eel.expose
    def clear_api_token() -> Dict[str, Any]:
        """Remove the saved API token."""
        try:
            clear_saved_gui_api_token()
            return {"ok": True}
        except Exception as token_error:
            return {"error": str(token_error)}

    @_eel.expose
    def has_saved_token() -> bool:
        """Check whether a token is currently saved."""
        saved_token = get_saved_gui_api_token()
        return bool(saved_token)


# ── Application Entry Point ──────────────────────────────────────────────────


def main() -> None:
    """Launch the WiringWizard Eel web application."""
    import eel as _eel

    _eel.init(WEB_DIR)
    _register_eel_endpoints()

    _ensure_data_directory_exists()

    # Try Edge first (always available on Windows 10+), fall back to Chrome
    eel_start_options = {
        "size": (1400, 900),
        "port": 0,
        "host": "localhost",
    }

    try:
        _eel.start("index.html", mode="edge", **eel_start_options)
    except EnvironmentError:
        try:
            _eel.start("index.html", mode="chrome", **eel_start_options)
        except EnvironmentError:
            # Last resort: open in default browser
            _eel.start("index.html", mode="default", **eel_start_options)


if __name__ == "__main__":
    main()

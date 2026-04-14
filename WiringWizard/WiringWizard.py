"""
WiringWizard desktop application for building low-voltage wiring plans and harness outputs.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import font as tkfont
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional

# Allow running from this folder directly with "python WiringWizard.py"
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

from core.ai_intake import (
    clear_saved_gui_api_token,
    draft_project_from_brief,
    get_saved_gui_api_token,
    save_gui_api_token,
)
from core.diagram_renderer import render_full_report
from core.domain_profiles import DOMAIN_PROFILES, get_domain_profile
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

WINDOW_TITLE = "WiringWizard — Wiring Diagram & Harness Planner"
WINDOW_SIZE = "1200x820"

APP_DIR = resolve_runtime_app_dir(__file__)
DATA_DIR = os.path.join(APP_DIR, "data")
DRAFT_FILE_PATH = os.path.join(DATA_DIR, "project_draft.json")

# ── Dark Theme Palette (matches ToolBox app design) ──────────────────────────
# GitHub-dark inspired color system: layered surfaces with blue accent.

COLOR_BG = "#0d1117"
COLOR_SURFACE = "#0d1117"
COLOR_SURFACE2 = "#21262d"
COLOR_SURFACE3 = "#2d333b"
COLOR_BORDER = "#30363d"
COLOR_BORDER_STRONG = "#484f58"
COLOR_TEXT = "#e6edf3"
COLOR_TEXT_MUTED = "#7d8590"
COLOR_TEXT_SUBTLE = "#484f58"
COLOR_ACCENT = "#2f81f7"
COLOR_ACCENT_HOVER = "#388bfd"
COLOR_SUCCESS = "#3fb950"
COLOR_DANGER = "#f85149"

# Semantic aliases referenced throughout the UI
COLOR_HEADER_BG = COLOR_SURFACE2
COLOR_HEADER_FG = COLOR_TEXT
COLOR_CARD_BG = "#161b22"
COLOR_MUTED_FG = COLOR_TEXT_MUTED
COLOR_STATUS_BG = "#161b22"
COLOR_EDITOR_BG = "#0d1117"
COLOR_EDITOR_FG = COLOR_TEXT

DEFAULT_COMPONENTS_TEMPLATE = """[
  {
    "component_id": "battery1",
    "component_name": "Main Battery",
    "component_type": "battery",
    "current_draw_amps": 60.0,
    "position_label": "Engine bay"
  },
  {
    "component_id": "ecu1",
    "component_name": "Aftermarket ECU",
    "component_type": "ecu",
    "current_draw_amps": 8.0,
    "position_label": "Passenger footwell"
  }
]"""

DEFAULT_CONNECTIONS_TEMPLATE = """[
  {
    "connection_id": "conn_001",
    "from_component_id": "battery1",
    "from_pin": "+12V",
    "to_component_id": "ecu1",
    "to_pin": "BATT+",
    "current_amps": 8.0,
    "run_length_ft": 9.0,
    "wire_color": "red"
  }
]"""

DEFAULT_REMAP_TEMPLATE = """[
  {
    "operation": "update_connection",
    "payload": {
      "connection_id": "conn_001",
      "run_length_ft": 11.5
    }
  }
]"""

# ── Sample Data — 2G DSM SMART 150 Wiring Harness ────────────────────────────
# Pre-built component and connection data extracted from the user's draw.io
# reference diagram so the app launches with a realistic populated example.
SAMPLE_PROJECT_NAME = "2G DSM SMART 150 Harness"
SAMPLE_DOMAIN = "automotive"
SAMPLE_VOLTAGE = "lv_12v"
SAMPLE_DESCRIPTION = (
    "Complete wiring harness for a 2nd-generation DSM (Eagle Talon / Mitsubishi Eclipse) "
    "using a SMART 150 TCU for automatic transmission control.  Includes connections "
    "from the TCU to the shift selector, transmission solenoid valve body, vehicle "
    "sensors (TPS, tach, speed, brake), and 12 V ignition power."
)

SAMPLE_COMPONENTS: list[dict[str, Any]] = [
    {"component_id": "smart150",  "component_name": "SMART 150 TCU",
     "component_type": "ecu",       "current_draw_amps": 3.0,
     "position_label": "Center console"},
    {"component_id": "prndl_mod",  "component_name": "PRND2L Module",
     "component_type": "sensor",    "current_draw_amps": 0.5,
     "position_label": "Shifter area"},
    {"component_id": "shift_sw",   "component_name": "PRND2L Shift Selector (Late Style)",
     "component_type": "sensor",    "current_draw_amps": 0.2,
     "position_label": "Steering column"},
    {"component_id": "sol_body",   "component_name": "Transmission Solenoid Valve Body",
     "component_type": "solenoid",  "current_draw_amps": 12.0,
     "position_label": "Transmission"},
    {"component_id": "ign_12v",    "component_name": "+12 V Ignition Source",
     "component_type": "power",     "current_draw_amps": 0.0,
     "position_label": "Fuse box"},
    {"component_id": "chassis_gnd","component_name": "Chassis Ground",
     "component_type": "ground",    "current_draw_amps": 0.0,
     "position_label": "Firewall"},
    {"component_id": "tps_sensor", "component_name": "TPS (Throttle Position Sensor)",
     "component_type": "sensor",    "current_draw_amps": 0.1,
     "position_label": "Throttle body"},
    {"component_id": "tach_src",   "component_name": "Engine Tach Signal",
     "component_type": "sensor",    "current_draw_amps": 0.1,
     "position_label": "ECU / Coil"},
    {"component_id": "speed_src",  "component_name": "Speed Signal (MPH)",
     "component_type": "sensor",    "current_draw_amps": 0.1,
     "position_label": "Instrument cluster"},
    {"component_id": "brake_sw",   "component_name": "Brake Switch",
     "component_type": "sensor",    "current_draw_amps": 0.1,
     "position_label": "Brake pedal"},
]

SAMPLE_CONNECTIONS: list[dict[str, Any]] = [
    # Power and ground
    {"connection_id": "c01", "from_component_id": "ign_12v",   "from_pin": "+12V",
     "to_component_id": "smart150",  "to_pin": "Pin 14", "current_amps": 3.0,
     "run_length_ft": 4.0, "wire_color": "red"},
    {"connection_id": "c02", "from_component_id": "ign_12v",   "from_pin": "+12V",
     "to_component_id": "smart150",  "to_pin": "Pin 16", "current_amps": 3.0,
     "run_length_ft": 4.0, "wire_color": "red"},
    {"connection_id": "c03", "from_component_id": "smart150",  "from_pin": "Pin 12",
     "to_component_id": "chassis_gnd","to_pin": "GND",   "current_amps": 3.0,
     "run_length_ft": 2.0, "wire_color": "black"},
    # Sensor inputs
    {"connection_id": "c04", "from_component_id": "tps_sensor","from_pin": "Signal",
     "to_component_id": "smart150",  "to_pin": "Pin 2 (AI1 TPS)",
     "current_amps": 0.1, "run_length_ft": 5.0, "wire_color": "orange"},
    {"connection_id": "c05", "from_component_id": "brake_sw",  "from_pin": "Signal",
     "to_component_id": "smart150",  "to_pin": "Pin 5 (DI3)",
     "current_amps": 0.1, "run_length_ft": 6.0, "wire_color": "white"},
    {"connection_id": "c06", "from_component_id": "speed_src", "from_pin": "MPH",
     "to_component_id": "smart150",  "to_pin": "Pin 6",
     "current_amps": 0.1, "run_length_ft": 5.0, "wire_color": "green"},
    {"connection_id": "c07", "from_component_id": "tach_src",  "from_pin": "RPM",
     "to_component_id": "smart150",  "to_pin": "Pin 8",
     "current_amps": 0.1, "run_length_ft": 4.0, "wire_color": "white"},
    # Solenoid outputs
    {"connection_id": "c08", "from_component_id": "smart150",  "from_pin": "Pin 15 (SOL-A)",
     "to_component_id": "sol_body",  "to_pin": "SOL-A",
     "current_amps": 3.0, "run_length_ft": 3.0, "wire_color": "yellow"},
    {"connection_id": "c09", "from_component_id": "smart150",  "from_pin": "Pin 13 (SOL-B)",
     "to_component_id": "sol_body",  "to_pin": "SOL-B",
     "current_amps": 3.0, "run_length_ft": 3.0, "wire_color": "brown"},
    {"connection_id": "c10", "from_component_id": "smart150",  "from_pin": "Pin 11 (SOL-C)",
     "to_component_id": "sol_body",  "to_pin": "SOL-C / Lockup",
     "current_amps": 3.0, "run_length_ft": 3.0, "wire_color": "green"},
    {"connection_id": "c11", "from_component_id": "smart150",  "from_pin": "Pin 9 (SOL-D)",
     "to_component_id": "sol_body",  "to_pin": "SOL-D / PCS",
     "current_amps": 3.0, "run_length_ft": 3.0, "wire_color": "blue"},
    # Shift buttons
    {"connection_id": "c12", "from_component_id": "shift_sw",  "from_pin": "Up",
     "to_component_id": "smart150",  "to_pin": "Pin 1 (DI1 Up)",
     "current_amps": 0.2, "run_length_ft": 4.0, "wire_color": "purple"},
    {"connection_id": "c13", "from_component_id": "shift_sw",  "from_pin": "Down",
     "to_component_id": "smart150",  "to_pin": "Pin 3 (DI2 Down)",
     "current_amps": 0.2, "run_length_ft": 4.0, "wire_color": "purple"},
    # PRND2L module bus
    {"connection_id": "c14", "from_component_id": "prndl_mod", "from_pin": "Red (+12V)",
     "to_component_id": "ign_12v",   "to_pin": "+12V",
     "current_amps": 0.5, "run_length_ft": 3.0, "wire_color": "red"},
    {"connection_id": "c15", "from_component_id": "prndl_mod", "from_pin": "Black (GND)",
     "to_component_id": "chassis_gnd","to_pin": "GND",
     "current_amps": 0.5, "run_length_ft": 2.0, "wire_color": "black"},
    {"connection_id": "c16", "from_component_id": "prndl_mod", "from_pin": "Orange (Signal)",
     "to_component_id": "smart150",  "to_pin": "Pin 4 (AI2/DI6)",
     "current_amps": 0.1, "run_length_ft": 3.0, "wire_color": "orange"},
]


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


# ── Theme Configuration ───────────────────────────────────────────────────────


def _apply_modern_theme(root: tk.Tk) -> str:
    """
    Configure ttk styles for a dark, GitHub-inspired look matching the ToolBox app.

    Returns the resolved body font family name so callers can create additional
    Font objects without re-querying the available families list.

    Note: we create tkfont.Font objects and pass them to style.configure() rather
    than using raw tuples.  Python 3.14 changed how Tkinter converts tuples to Tcl
    font specs — family names that contain spaces (e.g. "Segoe UI") are no longer
    auto-quoted, causing a TclError.  Named Font objects bypass that code path.
    """
    style = ttk.Style(root)
    style.theme_use("clam")

    available_families = tkfont.families(root)
    body_family = "Segoe UI" if "Segoe UI" in available_families else "TkDefaultFont"
    mono_family = "Consolas" if "Consolas" in available_families else "TkFixedFont"

    # Named font objects — Tcl references them by name, avoiding any tuple-parsing issues.
    body_10 = tkfont.Font(family=body_family, size=10)
    body_10_bold = tkfont.Font(family=body_family, size=10, weight="bold")
    body_9 = tkfont.Font(family=body_family, size=9)
    mono_10 = tkfont.Font(family=mono_family, size=10)

    root.option_add("*Font", body_10)
    root.option_add("*Text.Font", mono_10)

    # Base dark background for all widgets
    style.configure(".", font=body_10, background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure("TFrame", background=COLOR_BG)
    style.configure("TLabel", background=COLOR_BG, foreground=COLOR_TEXT)
    style.configure(
        "TEntry",
        fieldbackground=COLOR_SURFACE2,
        foreground=COLOR_TEXT,
        insertcolor=COLOR_TEXT,
        bordercolor=COLOR_BORDER,
    )
    style.configure(
        "TCombobox",
        fieldbackground=COLOR_SURFACE2,
        background=COLOR_SURFACE3,
        foreground=COLOR_TEXT,
        arrowcolor=COLOR_TEXT,
        bordercolor=COLOR_BORDER,
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", COLOR_SURFACE2)],
        selectbackground=[("readonly", COLOR_SURFACE2)],
        selectforeground=[("readonly", COLOR_TEXT)],
    )
    style.configure(
        "TScrollbar",
        background=COLOR_SURFACE3,
        troughcolor=COLOR_CARD_BG,
        bordercolor=COLOR_BORDER,
        arrowcolor=COLOR_TEXT_MUTED,
    )

    # Notebook tabs — dark tab strip with accent highlight on selected
    style.configure(
        "TNotebook",
        background=COLOR_BG,
        borderwidth=0,
        tabmargins=(8, 6, 8, 0),
    )
    style.configure(
        "TNotebook.Tab",
        font=body_10_bold,
        padding=(18, 8),
        background=COLOR_SURFACE2,
        foreground=COLOR_TEXT_MUTED,
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLOR_CARD_BG)],
        foreground=[("selected", COLOR_ACCENT)],
    )

    # Card-style label frames — elevated dark surface with subtle border
    style.configure(
        "Card.TLabelframe",
        background=COLOR_CARD_BG,
        borderwidth=1,
        relief="solid",
        bordercolor=COLOR_BORDER,
    )
    style.configure(
        "Card.TLabelframe.Label",
        font=body_10_bold,
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT,
    )

    # Interior widgets that sit on card surfaces
    style.configure("Card.TFrame", background=COLOR_CARD_BG)
    style.configure("Card.TLabel", background=COLOR_CARD_BG, foreground=COLOR_TEXT)
    style.configure("CardMuted.TLabel", background=COLOR_CARD_BG, foreground=COLOR_MUTED_FG)

    # Section header labels
    style.configure(
        "SectionTitle.TLabel",
        font=body_10_bold,
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT,
    )

    # Primary action button — bold accent blue
    style.configure(
        "Primary.TButton",
        font=body_10_bold,
        padding=(16, 6),
        background=COLOR_ACCENT,
        foreground="#ffffff",
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLOR_ACCENT_HOVER), ("disabled", COLOR_TEXT_SUBTLE)],
    )

    # Secondary button — dark neutral
    style.configure(
        "Secondary.TButton",
        font=body_10,
        padding=(12, 5),
        background=COLOR_SURFACE2,
        foreground=COLOR_TEXT,
    )
    style.map(
        "Secondary.TButton",
        background=[("active", COLOR_SURFACE3)],
    )

    # PanedWindow sash — dark handle between panes
    style.configure(
        "TPanedwindow",
        background=COLOR_BG,
    )

    # Status bar — subtle dark strip
    style.configure(
        "StatusBar.TFrame",
        background=COLOR_STATUS_BG,
    )
    style.configure(
        "StatusBar.TLabel",
        font=body_9,
        background=COLOR_STATUS_BG,
        foreground=COLOR_MUTED_FG,
        padding=(12, 4),
    )

    # Treeview — dark sortable tables for component and connection lists
    style.configure(
        "Treeview",
        font=body_10,
        rowheight=30,
        fieldbackground=COLOR_CARD_BG,
        background=COLOR_CARD_BG,
        foreground=COLOR_TEXT,
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        font=body_10_bold,
        background=COLOR_SURFACE2,
        foreground=COLOR_TEXT_MUTED,
        padding=(8, 6),
        relief="flat",
    )
    style.map(
        "Treeview",
        background=[("selected", COLOR_ACCENT)],
        foreground=[("selected", "#ffffff")],
    )

    return body_family



# ── UI Data Constants ─────────────────────────────────────────────────────────

WIRE_COLORS = [
    "red", "black", "blue", "green", "yellow", "orange",
    "white", "brown", "purple", "pink", "gray", "tan",
]

AWG_OPTIONS = [
    "Auto", "8", "10", "12", "14", "16", "18", "20", "22", "24", "26",
]

POSITION_SUGGESTIONS = [
    "Engine bay", "Dashboard", "Passenger footwell", "Driver footwell",
    "Trunk", "Under hood", "Firewall", "Inside cabin", "Rear panel",
    "Control box", "Frame rail", "Fuse box area", "Center console",
    "Under seat", "Roof", "Door panel",
]

# Merge all known component types from every domain profile into one sorted list
_MERGED_COMPONENT_TYPES: set = set()
for _domain_profile_data in DOMAIN_PROFILES.values():
    _MERGED_COMPONENT_TYPES.update(_domain_profile_data.get("common_components", []))
ALL_COMPONENT_TYPES: List[str] = sorted(_MERGED_COMPONENT_TYPES)


def _generate_id_from_name(name: str) -> str:
    """Derive a short snake_case identifier from a human-readable name."""
    return name.lower().replace(" ", "_").replace("-", "_")[:24].strip("_") or "item"


# ── Modal Dialogs ─────────────────────────────────────────────────────────────


class ComponentDialog(tk.Toplevel):
    """Modal form for adding or editing a wiring component via dropdowns and spinboxes."""

    def __init__(
        self,
        parent: tk.Tk,
        body_font_family: str,
        domain: str = "automotive",
        existing: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        is_edit = existing is not None
        self.title("Edit Component" if is_edit else "Add Component")
        self.resizable(False, False)
        self.configure(background=COLOR_CARD_BG)
        self.result: Optional[Dict[str, Any]] = None

        label_font = tkfont.Font(family=body_font_family, size=10)
        entry_font = tkfont.Font(family=body_font_family, size=10)
        button_font = tkfont.Font(family=body_font_family, size=10, weight="bold")

        try:
            profile = get_domain_profile(domain)
            type_options = list(profile["common_components"])
        except KeyError:
            type_options = list(ALL_COMPONENT_TYPES)

        form = tk.Frame(self, background=COLOR_CARD_BG, padx=24, pady=20)
        form.pack(fill=tk.BOTH, expand=True)
        form.columnconfigure(1, weight=1)

        # Row 0 — Component name
        tk.Label(
            form, text="Name", font=label_font,
            bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self._name_var = tk.StringVar(
            value=existing["component_name"] if is_edit else "",
        )
        name_entry = tk.Entry(
            form, textvariable=self._name_var, font=entry_font, width=32,
            relief="solid", bd=1, highlightthickness=0,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
        )
        name_entry.grid(row=0, column=1, sticky="we", padx=(12, 0), pady=(0, 10))

        # Row 1 — Component type (dropdown)
        tk.Label(
            form, text="Type", font=label_font,
            bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        default_type = (
            existing["component_type"] if is_edit
            else (type_options[0] if type_options else "")
        )
        self._type_var = tk.StringVar(value=default_type)
        ttk.Combobox(
            form, textvariable=self._type_var, values=type_options, width=30,
        ).grid(row=1, column=1, sticky="we", padx=(12, 0), pady=(0, 10))

        # Row 2 — Current draw (spinbox with increment buttons)
        tk.Label(
            form, text="Current (A)", font=label_font,
            bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=2, column=0, sticky="w", pady=(0, 10))
        self._amps_var = tk.DoubleVar(
            value=existing["current_draw_amps"] if is_edit else 1.0,
        )
        tk.Spinbox(
            form, textvariable=self._amps_var, from_=0.01, to=200, increment=0.5,
            font=entry_font, width=12, relief="solid", bd=1, highlightthickness=0,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
            buttonbackground=COLOR_SURFACE3,
        ).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 10))

        # Row 3 — Position (editable dropdown with common suggestions)
        tk.Label(
            form, text="Position", font=label_font,
            bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=3, column=0, sticky="w", pady=(0, 10))
        self._position_var = tk.StringVar(
            value=existing.get("position_label", "") if is_edit else "",
        )
        ttk.Combobox(
            form, textvariable=self._position_var,
            values=POSITION_SUGGESTIONS, width=30,
        ).grid(row=3, column=1, sticky="we", padx=(12, 0), pady=(0, 10))

        self._existing_id = existing["component_id"] if is_edit else ""

        # Button bar
        button_bar = tk.Frame(self, background=COLOR_CARD_BG, padx=24, pady=(0, 20))
        button_bar.pack(fill=tk.X)
        tk.Button(
            button_bar, text="  Save  ", font=button_font,
            bg=COLOR_ACCENT, fg="white", activebackground=COLOR_ACCENT_HOVER,
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_save,
        ).pack(side=tk.RIGHT)
        tk.Button(
            button_bar, text="  Cancel  ", font=entry_font,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, activebackground=COLOR_SURFACE3,
            relief="flat", cursor="hand2", command=self.destroy,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.transient(parent)
        self.grab_set()
        name_entry.focus_set()
        self.update_idletasks()
        self._center_on(parent)
        parent.wait_window(self)

    def _on_save(self) -> None:
        """Validate form inputs and store the result dict."""
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing name", "Enter a component name.", parent=self)
            return
        component_type = self._type_var.get().strip()
        if not component_type:
            messagebox.showwarning("Missing type", "Select or enter a component type.", parent=self)
            return
        self.result = {
            "component_id": self._existing_id or _generate_id_from_name(name),
            "component_name": name,
            "component_type": component_type,
            "current_draw_amps": self._amps_var.get(),
            "position_label": self._position_var.get().strip(),
        }
        self.destroy()

    def _center_on(self, parent: tk.Tk) -> None:
        """Position this dialog at the center of its parent window."""
        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x_position = parent_x + (parent_width - dialog_width) // 2
        y_position = parent_y + (parent_height - dialog_height) // 2
        self.geometry(f"+{x_position}+{y_position}")


class ConnectionDialog(tk.Toplevel):
    """Modal form for adding or editing a wire connection via dropdowns and spinboxes."""

    def __init__(
        self,
        parent: tk.Tk,
        body_font_family: str,
        component_lookup: Dict[str, str],
        existing: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(parent)
        is_edit = existing is not None
        self.title("Edit Connection" if is_edit else "Add Connection")
        self.resizable(False, False)
        self.configure(background=COLOR_CARD_BG)
        self.result: Optional[Dict[str, Any]] = None
        self._component_lookup = component_lookup

        label_font = tkfont.Font(family=body_font_family, size=10)
        entry_font = tkfont.Font(family=body_font_family, size=10)
        button_font = tkfont.Font(family=body_font_family, size=10, weight="bold")

        # Build display list for component dropdowns: "Name (id)"
        component_display_options = [
            f"{comp_name} ({comp_id})"
            for comp_id, comp_name in component_lookup.items()
        ]

        form = tk.Frame(self, background=COLOR_CARD_BG, padx=24, pady=20)
        form.pack(fill=tk.BOTH, expand=True)
        form.columnconfigure(1, weight=1)
        form.columnconfigure(3, weight=1)

        # Row 0 — From component + From pin
        tk.Label(
            form, text="From", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        from_default = self._make_display(existing["from_component_id"]) if is_edit else ""
        self._from_var = tk.StringVar(value=from_default)
        ttk.Combobox(
            form, textvariable=self._from_var,
            values=component_display_options, width=22,
        ).grid(row=0, column=1, sticky="we", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="Pin", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=0, column=2, sticky="w", pady=(0, 10))
        self._from_pin_var = tk.StringVar(value=existing["from_pin"] if is_edit else "")
        tk.Entry(
            form, textvariable=self._from_pin_var, font=entry_font, width=14,
            relief="solid", bd=1, highlightthickness=0,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
        ).grid(row=0, column=3, sticky="we", padx=(12, 0), pady=(0, 10))

        # Row 1 — To component + To pin
        tk.Label(
            form, text="To", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        to_default = self._make_display(existing["to_component_id"]) if is_edit else ""
        self._to_var = tk.StringVar(value=to_default)
        ttk.Combobox(
            form, textvariable=self._to_var,
            values=component_display_options, width=22,
        ).grid(row=1, column=1, sticky="we", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="Pin", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=1, column=2, sticky="w", pady=(0, 10))
        self._to_pin_var = tk.StringVar(value=existing["to_pin"] if is_edit else "")
        tk.Entry(
            form, textvariable=self._to_pin_var, font=entry_font, width=14,
            relief="solid", bd=1, highlightthickness=0,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
        ).grid(row=1, column=3, sticky="we", padx=(12, 0), pady=(0, 10))

        # Row 2 — Current + Length
        tk.Label(
            form, text="Current (A)", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=2, column=0, sticky="w", pady=(0, 10))
        self._amps_var = tk.DoubleVar(value=existing["current_amps"] if is_edit else 1.0)
        tk.Spinbox(
            form, textvariable=self._amps_var, from_=0.01, to=200, increment=0.5,
            font=entry_font, width=10, relief="solid", bd=1, highlightthickness=0,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
            buttonbackground=COLOR_SURFACE3,
        ).grid(row=2, column=1, sticky="w", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="Length (ft)", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=2, column=2, sticky="w", pady=(0, 10))
        self._length_var = tk.DoubleVar(value=existing["run_length_ft"] if is_edit else 1.0)
        tk.Spinbox(
            form, textvariable=self._length_var, from_=0.1, to=500, increment=0.5,
            font=entry_font, width=10, relief="solid", bd=1, highlightthickness=0,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
            buttonbackground=COLOR_SURFACE3,
        ).grid(row=2, column=3, sticky="w", padx=(12, 0), pady=(0, 10))

        # Row 3 — Wire color + AWG override
        tk.Label(
            form, text="Wire Color", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=3, column=0, sticky="w", pady=(0, 10))
        self._color_var = tk.StringVar(
            value=existing.get("wire_color", "red") if is_edit else "red",
        )
        ttk.Combobox(
            form, textvariable=self._color_var,
            values=WIRE_COLORS, state="readonly", width=14,
        ).grid(row=3, column=1, sticky="w", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="AWG", font=label_font, bg=COLOR_CARD_BG, fg=COLOR_TEXT,
        ).grid(row=3, column=2, sticky="w", pady=(0, 10))
        awg_value = (existing.get("awg_override") or "Auto") if is_edit else "Auto"
        self._awg_var = tk.StringVar(value=awg_value)
        ttk.Combobox(
            form, textvariable=self._awg_var,
            values=AWG_OPTIONS, state="readonly", width=10,
        ).grid(row=3, column=3, sticky="w", padx=(12, 0), pady=(0, 10))

        self._existing_id = existing["connection_id"] if is_edit else ""

        # Button bar
        button_bar = tk.Frame(self, background=COLOR_CARD_BG, padx=24, pady=(0, 20))
        button_bar.pack(fill=tk.X)
        tk.Button(
            button_bar, text="  Save  ", font=button_font,
            bg=COLOR_ACCENT, fg="white", activebackground=COLOR_ACCENT_HOVER,
            activeforeground="white", relief="flat", cursor="hand2",
            command=self._on_save,
        ).pack(side=tk.RIGHT)
        tk.Button(
            button_bar, text="  Cancel  ", font=entry_font,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, activebackground=COLOR_SURFACE3,
            relief="flat", cursor="hand2", command=self.destroy,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.transient(parent)
        self.grab_set()
        self.update_idletasks()
        self._center_on(parent)
        parent.wait_window(self)

    def _make_display(self, component_id: str) -> str:
        """Build the 'Name (id)' display string for a component dropdown value."""
        comp_name = self._component_lookup.get(component_id, component_id)
        return f"{comp_name} ({component_id})"

    def _extract_component_id(self, display_value: str) -> str:
        """Extract the component_id from a 'Name (id)' display string."""
        trimmed = display_value.strip()
        if "(" in trimmed and trimmed.endswith(")"):
            return trimmed.rsplit("(", 1)[1][:-1].strip()
        return trimmed

    def _on_save(self) -> None:
        """Validate form and store connection result dict."""
        from_id = self._extract_component_id(self._from_var.get())
        to_id = self._extract_component_id(self._to_var.get())
        if not from_id or not to_id:
            messagebox.showwarning(
                "Missing endpoints",
                "Select both a From and To component.",
                parent=self,
            )
            return
        awg_selection = self._awg_var.get()
        awg_override = None if awg_selection == "Auto" else awg_selection
        self.result = {
            "connection_id": self._existing_id or "",
            "from_component_id": from_id,
            "from_pin": self._from_pin_var.get().strip(),
            "to_component_id": to_id,
            "to_pin": self._to_pin_var.get().strip(),
            "current_amps": self._amps_var.get(),
            "run_length_ft": self._length_var.get(),
            "wire_color": self._color_var.get(),
            "awg_override": awg_override,
        }
        self.destroy()

    def _center_on(self, parent: tk.Tk) -> None:
        """Position this dialog at the center of its parent window."""
        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_width = parent.winfo_width()
        parent_height = parent.winfo_height()
        x_position = parent_x + (parent_width - dialog_width) // 2
        y_position = parent_y + (parent_height - dialog_height) // 2
        self.geometry(f"+{x_position}+{y_position}")


# ── Interactive Wiring Diagram Canvas ─────────────────────────────────────────

# Visual color map for wire_color names → hex values for on-canvas rendering
WIRE_HEX_MAP: dict[str, str] = {
    "red": "#f85149",    "black": "#8b949e",  "white": "#e6edf3",
    "green": "#3fb950",  "blue": "#58a6ff",   "yellow": "#d29922",
    "orange": "#d18616", "purple": "#bc8cff",  "brown": "#a57040",
    "pink": "#f778ba",   "gray": "#6e7681",   "grey": "#6e7681",
}

# Color-coded component type badges for the diagram nodes
COMPONENT_TYPE_COLORS: dict[str, str] = {
    "ecu": "#58a6ff",       "sensor": "#3fb950",   "solenoid": "#d18616",
    "power": "#f85149",     "ground": "#6e7681",   "battery": "#f85149",
    "relay": "#d29922",     "fuse": "#d29922",     "switch": "#bc8cff",
    "motor": "#d18616",     "light": "#d29922",    "display": "#58a6ff",
    "connector": "#8b949e", "harness": "#8b949e",
}

# Layout constants for the diagram canvas
NODE_WIDTH = 220
NODE_HEADER_HEIGHT = 32
NODE_PIN_ROW_HEIGHT = 24
NODE_PADDING = 14
NODE_MARGIN_X = 80
NODE_MARGIN_Y = 50
SHADOW_OFFSET = 4
SHADOW_COLOR = "#010409"
GRID_SPACING = 30
GRID_COLOR = "#161b22"


class DiagramCanvas(tk.Canvas):
    """Interactive wiring diagram with clickable cards and circuit tracing.

    Click a component card to highlight only that component's direct wires
    and show a detail panel.  Click a wire to trace the full circuit end-to-end
    across every module in the path, highlighting every wire and node involved.
    Click the background to deselect.  Pan with drag, zoom with scroll wheel.
    Hover a wire for a quick tooltip.
    """

    def __init__(self, parent: tk.Widget, **kwargs):
        super().__init__(
            parent, background=COLOR_BG, highlightthickness=0, **kwargs,
        )
        self._component_data: list[dict[str, Any]] = []
        self._connection_data: list[dict[str, Any]] = []
        self._node_layout: dict[str, dict[str, Any]] = {}
        self._scale_factor = 1.0
        self._tooltip_items: list[int] = []
        self._overlay_items: list[int] = []
        self._is_selected = False

        self.bind("<ButtonPress-1>", self._on_click)
        self.bind("<B1-Motion>", self._on_pan_move)
        self.bind("<MouseWheel>", self._on_zoom)
        self.bind("<Button-4>", self._on_zoom)
        self.bind("<Button-5>", self._on_zoom)
        self.bind("<Motion>", self._on_hover)

    # ── Public API ────────────────────────────────────────────────────────

    def render_diagram(
        self,
        component_data: list[dict[str, Any]],
        connection_data: list[dict[str, Any]],
    ) -> None:
        """Clear the canvas and draw a complete wiring diagram."""
        self._component_data = component_data
        self._connection_data = connection_data
        self._scale_factor = 1.0
        self._is_selected = False
        self._tooltip_items.clear()
        self._overlay_items.clear()
        self.delete("all")
        self._node_layout.clear()

        if not component_data:
            self._draw_empty_state()
            return

        self._compute_layout()
        self._draw_dot_grid()
        self._draw_connections()
        self._draw_nodes()
        self._draw_legend()

        bbox = self.bbox("all")
        if bbox:
            self.configure(scrollregion=(
                bbox[0] - 60, bbox[1] - 60,
                bbox[2] + 60, bbox[3] + 60,
            ))

    # ── Layout ────────────────────────────────────────────────────────────

    def _compute_layout(self) -> None:
        """Three-column layout: power/ground left, ECU center, rest right."""
        LEFT_TYPES = {"power", "battery", "ground", "fuse"}
        CENTER_TYPES = {"ecu", "controller"}

        left_nodes: list[dict] = []
        center_nodes: list[dict] = []
        right_nodes: list[dict] = []

        for component in self._component_data:
            component_type = component.get("component_type", "").lower()
            if component_type in LEFT_TYPES:
                left_nodes.append(component)
            elif component_type in CENTER_TYPES:
                center_nodes.append(component)
            else:
                right_nodes.append(component)

        def _collect_pins(component_id: str) -> list[str]:
            """Gather the ordered list of pin labels for a component."""
            pins: list[str] = []
            seen: set[str] = set()
            for conn in self._connection_data:
                if conn["from_component_id"] == component_id:
                    pin = conn["from_pin"]
                    if pin not in seen:
                        pins.append(pin)
                        seen.add(pin)
                if conn["to_component_id"] == component_id:
                    pin = conn["to_pin"]
                    if pin not in seen:
                        pins.append(pin)
                        seen.add(pin)
            return pins or ["\u2014"]

        def _place_column(nodes: list[dict], col_x: int, start_y: int) -> None:
            """Stack component nodes vertically at *col_x*."""
            cur_y = start_y
            for comp in nodes:
                cid = comp["component_id"]
                pins = _collect_pins(cid)
                node_height = NODE_HEADER_HEIGHT + len(pins) * NODE_PIN_ROW_HEIGHT + NODE_PADDING
                pin_pos: dict[str, tuple[int, int]] = {}
                for idx, pin_name in enumerate(pins):
                    pin_y = (
                        cur_y + NODE_HEADER_HEIGHT
                        + idx * NODE_PIN_ROW_HEIGHT
                        + NODE_PIN_ROW_HEIGHT // 2
                    )
                    pin_pos[pin_name] = (col_x + NODE_WIDTH, pin_y)
                self._node_layout[cid] = {
                    "x": col_x, "y": cur_y, "width": NODE_WIDTH, "height": node_height,
                    "pins": pins, "pin_positions": pin_pos, "component": comp,
                }
                cur_y += node_height + NODE_MARGIN_Y

        COL_L = 60
        COL_C = COL_L + NODE_WIDTH + NODE_MARGIN_X + 120
        COL_R = COL_C + NODE_WIDTH + NODE_MARGIN_X + 120

        _place_column(left_nodes, COL_L, 80)
        _place_column(center_nodes, COL_C, 80)
        _place_column(right_nodes, COL_R, 80)

        # Route each pin toward the node it connects to
        for cid, layout in self._node_layout.items():
            node_x = layout["x"]
            adjusted_pins: dict[str, tuple[int, int]] = {}
            for pin_name, (_px, pin_y) in layout["pin_positions"].items():
                faces_left = False
                faces_right = False
                for conn in self._connection_data:
                    other_id = None
                    if conn["from_component_id"] == cid and conn["from_pin"] == pin_name:
                        other_id = conn["to_component_id"]
                    elif conn["to_component_id"] == cid and conn["to_pin"] == pin_name:
                        other_id = conn["from_component_id"]
                    if other_id and other_id in self._node_layout:
                        if self._node_layout[other_id]["x"] < node_x:
                            faces_left = True
                        else:
                            faces_right = True
                if faces_left and not faces_right:
                    adjusted_pins[pin_name] = (node_x, pin_y)
                else:
                    adjusted_pins[pin_name] = (node_x + NODE_WIDTH, pin_y)
            layout["pin_positions"] = adjusted_pins

    # ── Drawing ───────────────────────────────────────────────────────────

    def _draw_dot_grid(self) -> None:
        """Subtle dot grid for a professional schematic background."""
        min_x, min_y, max_x, max_y = 0, 0, 1400, 1200
        for layout in self._node_layout.values():
            min_x = min(min_x, layout["x"] - 80)
            min_y = min(min_y, layout["y"] - 80)
            max_x = max(max_x, layout["x"] + layout["width"] + 80)
            max_y = max(max_y, layout["y"] + layout["height"] + 80)
        for grid_x in range(int(min_x), int(max_x), GRID_SPACING):
            for grid_y in range(int(min_y), int(max_y), GRID_SPACING):
                self.create_oval(
                    grid_x - 1, grid_y - 1, grid_x + 1, grid_y + 1,
                    fill=GRID_COLOR, outline=GRID_COLOR, tags="grid",
                )

    def _draw_nodes(self) -> None:
        """Draw each component as a polished card with shadow and accent stripe."""
        header_font = tkfont.Font(family="Segoe UI", size=10, weight="bold")
        pin_font = tkfont.Font(family="Consolas", size=9)
        type_font = tkfont.Font(family="Segoe UI", size=7)

        for cid, layout in self._node_layout.items():
            node_x, node_y = layout["x"], layout["y"]
            node_width, node_height = layout["width"], layout["height"]
            comp = layout["component"]
            ctype = comp.get("component_type", "").lower()
            type_color = COMPONENT_TYPE_COLORS.get(ctype, COLOR_ACCENT)

            # Drop shadow
            self._smooth_rect(
                node_x + SHADOW_OFFSET, node_y + SHADOW_OFFSET,
                node_x + node_width + SHADOW_OFFSET, node_y + node_height + SHADOW_OFFSET,
                radius=10, fill=SHADOW_COLOR, outline=SHADOW_COLOR,
                tags=("shadow", cid),
            )
            # Card body
            self._smooth_rect(
                node_x, node_y, node_x + node_width, node_y + node_height,
                radius=10, fill=COLOR_CARD_BG, outline=COLOR_BORDER,
                tags=("node", cid),
            )
            # Accent stripe on left edge
            self.create_rectangle(
                node_x + 1, node_y + 6, node_x + 5, node_y + node_height - 6,
                fill=type_color, outline=type_color, tags=("accent", cid),
            )
            # Component name
            self.create_text(
                node_x + 14, node_y + NODE_HEADER_HEIGHT // 2,
                text=comp["component_name"], fill=COLOR_TEXT, font=header_font,
                anchor="w", tags=("node_label", cid),
            )
            # Type badge
            self.create_text(
                node_x + node_width - 10, node_y + NODE_HEADER_HEIGHT // 2,
                text=ctype.upper(), fill=type_color, font=type_font,
                anchor="e", tags=("type_badge", cid),
            )
            # Header separator
            sep_y = node_y + NODE_HEADER_HEIGHT
            self.create_line(
                node_x + 10, sep_y, node_x + node_width - 10, sep_y,
                fill=COLOR_BORDER, tags=("sep", cid),
            )
            # Pins with alternating row shading and connection dots
            for idx, pin_name in enumerate(layout["pins"]):
                pin_y = (
                    node_y + NODE_HEADER_HEIGHT
                    + idx * NODE_PIN_ROW_HEIGHT
                    + NODE_PIN_ROW_HEIGHT // 2
                )
                pin_pos = layout["pin_positions"].get(pin_name, (0, 0))
                is_right_edge = pin_pos[0] >= node_x + node_width - 1

                # Alternating row shade for readability
                if idx % 2 == 0:
                    row_top = node_y + NODE_HEADER_HEIGHT + idx * NODE_PIN_ROW_HEIGHT
                    self.create_rectangle(
                        node_x + 6, row_top, node_x + node_width - 6, row_top + NODE_PIN_ROW_HEIGHT,
                        fill="#1a2030", outline="", tags=("row_shade", cid),
                    )
                self.create_text(
                    (node_x + node_width - 18) if is_right_edge else (node_x + 18), pin_y,
                    text=pin_name, fill=COLOR_TEXT_MUTED, font=pin_font,
                    anchor="e" if is_right_edge else "w", tags=("pin_label", cid),
                )
                # Pin dot with outline ring
                dot_x, dot_y = pin_pos
                self.create_oval(
                    dot_x - 5, dot_y - 5, dot_x + 5, dot_y + 5,
                    fill=COLOR_SURFACE2, outline=COLOR_TEXT_MUTED, width=1,
                    tags=("pin_dot", cid, pin_name),
                )

    def _draw_connections(self) -> None:
        """Draw wire splines with glow effect between pin positions."""
        for conn in self._connection_data:
            from_id = conn["from_component_id"]
            to_id = conn["to_component_id"]
            from_pin = conn["from_pin"]
            to_pin = conn["to_pin"]
            wire_hex = WIRE_HEX_MAP.get(conn.get("wire_color", "red"), COLOR_ACCENT)
            conn_id = conn["connection_id"]

            if from_id not in self._node_layout or to_id not in self._node_layout:
                continue
            from_pos = self._node_layout[from_id]["pin_positions"].get(from_pin)
            to_pos = self._node_layout[to_id]["pin_positions"].get(to_pin)
            if not from_pos or not to_pos:
                continue

            spline_pts = self._spline_points(from_pos, to_pos)
            # Glow pass (wider, darker) for depth
            self.create_line(
                *spline_pts, fill=COLOR_BG, width=6, smooth=True,
                splinesteps=24, tags=("wire_glow", conn_id),
            )
            # Main wire
            self.create_line(
                *spline_pts, fill=wire_hex, width=2, smooth=True,
                splinesteps=24, tags=("wire", conn_id),
            )

    def _spline_points(
        self, start: tuple[int, int], end: tuple[int, int],
    ) -> list[float]:
        """Build a smooth 7-point spline for natural cable routing curves."""
        start_x, start_y = start
        end_x, end_y = end
        gap = abs(end_x - start_x)
        leg = max(gap * 0.35, 60)
        if start_x <= end_x:
            s1 = start_x + leg * 0.4
            s2 = start_x + leg
            e1 = end_x - leg
            e2 = end_x - leg * 0.4
        else:
            s1 = start_x - leg * 0.4
            s2 = start_x - leg
            e1 = end_x + leg
            e2 = end_x + leg * 0.4
        mid_y = (start_y + end_y) / 2
        return [
            start_x, start_y, s1, start_y, s2, start_y,
            (s2 + e1) / 2, mid_y,
            e1, end_y, e2, end_y, end_x, end_y,
        ]

    def _draw_legend(self) -> None:
        """Floating legend panel showing component type and wire colors."""
        used_types: dict[str, str] = {}
        for comp in self._component_data:
            comp_type = comp.get("component_type", "").lower()
            if comp_type not in used_types:
                used_types[comp_type] = COMPONENT_TYPE_COLORS.get(comp_type, COLOR_ACCENT)
        used_wires: dict[str, str] = {}
        for conn in self._connection_data:
            color_name = conn.get("wire_color", "red")
            if color_name not in used_wires:
                used_wires[color_name] = WIRE_HEX_MAP.get(color_name, COLOR_ACCENT)
        if not used_types and not used_wires:
            return

        title_font = tkfont.Font(family="Segoe UI", size=8, weight="bold")
        label_font = tkfont.Font(family="Segoe UI", size=8)
        legend_x, legend_y = 20, 20
        row_height = 20
        legend_width = 150
        total_rows = len(used_types) + len(used_wires) + 2
        legend_height = total_rows * row_height + 24

        # Shadow + panel
        self._smooth_rect(
            legend_x + 2, legend_y + 2,
            legend_x + legend_width + 2, legend_y + legend_height + 2,
            radius=8, fill=SHADOW_COLOR, outline=SHADOW_COLOR, tags="legend",
        )
        self._smooth_rect(
            legend_x, legend_y, legend_x + legend_width, legend_y + legend_height,
            radius=8, fill=COLOR_CARD_BG, outline=COLOR_BORDER, tags="legend",
        )

        cur_y = legend_y + 14
        self.create_text(legend_x + 14, cur_y, text="COMPONENTS", fill=COLOR_TEXT,
                         font=title_font, anchor="w", tags="legend")
        cur_y += row_height
        for type_name, type_color in used_types.items():
            self.create_rectangle(
                legend_x + 14, cur_y - 5, legend_x + 18, cur_y + 5,
                fill=type_color, outline=type_color, tags="legend",
            )
            self.create_text(legend_x + 24, cur_y, text=type_name.capitalize(),
                             fill=COLOR_TEXT_MUTED, font=label_font, anchor="w", tags="legend")
            cur_y += row_height
        self.create_text(legend_x + 14, cur_y, text="WIRES", fill=COLOR_TEXT,
                         font=title_font, anchor="w", tags="legend")
        cur_y += row_height
        for color_name, color_hex in used_wires.items():
            self.create_line(
                legend_x + 14, cur_y, legend_x + 30, cur_y,
                fill=color_hex, width=2, tags="legend",
            )
            self.create_text(legend_x + 36, cur_y, text=color_name.capitalize(),
                             fill=COLOR_TEXT_MUTED, font=label_font, anchor="w", tags="legend")
            cur_y += row_height

    def _draw_empty_state(self) -> None:
        """Show a helpful empty-state message when no components exist."""
        icon_font = tkfont.Font(family="Segoe UI", size=32)
        big_font = tkfont.Font(family="Segoe UI", size=16)
        hint_font = tkfont.Font(family="Segoe UI", size=10)
        center_x, center_y = 500, 220
        self.create_text(center_x, center_y - 40, text="\U0001f50c", font=icon_font, anchor="center")
        self.create_text(center_x, center_y + 10, text="No wiring diagram yet",
                         fill=COLOR_TEXT_MUTED, font=big_font, anchor="center")
        self.create_text(center_x, center_y + 40,
                         text="Add components in the Components & Wiring tab, then refresh.",
                         fill=COLOR_TEXT_SUBTLE, font=hint_font, anchor="center")

    def _smooth_rect(
        self, x1: float, y1: float, x2: float, y2: float,
        radius: int = 10, **kwargs,
    ) -> int:
        """High-quality rounded rectangle using 6-degree arc steps."""
        import math
        pts: list[float] = []
        for corner_x, corner_y, start_deg in [
            (x1 + radius, y1 + radius, 90),
            (x2 - radius, y1 + radius, 0),
            (x2 - radius, y2 - radius, 270),
            (x1 + radius, y2 - radius, 180),
        ]:
            for step in range(0, 91, 6):
                angle = math.radians(start_deg + step)
                pts.append(corner_x + radius * math.cos(angle))
                pts.append(corner_y - radius * math.sin(angle))
        return self.create_polygon(pts, smooth=False, **kwargs)

    # ── Circuit Tracing ───────────────────────────────────────────────────

    def _trace_circuit(self, start_connection_id: str) -> None:
        """Walk the connection graph from one wire to find every wire and node
        in the same electrical circuit, then highlight the full path.

        Uses breadth-first flood-fill: from the clicked wire, discover both
        endpoint nodes, then every other wire touching those nodes, then those
        wires' nodes, and so on.  This traces through any number of modules
        (fuse -> relay -> ECU -> solenoid) so the user sees the complete
        power path end-to-end.
        """
        visited_wires: set[str] = set()
        visited_nodes: set[str] = set()
        wire_queue: list[str] = [start_connection_id]

        while wire_queue:
            wire_id = wire_queue.pop(0)
            if wire_id in visited_wires:
                continue
            visited_wires.add(wire_id)

            # Find the connection record
            conn = None
            for candidate in self._connection_data:
                if candidate["connection_id"] == wire_id:
                    conn = candidate
                    break
            if not conn:
                continue

            # Mark both endpoint nodes and enqueue their other wires
            for node_id in (conn["from_component_id"], conn["to_component_id"]):
                if node_id in visited_nodes:
                    continue
                visited_nodes.add(node_id)
                for other_conn in self._connection_data:
                    if other_conn["connection_id"] not in visited_wires:
                        if (other_conn["from_component_id"] == node_id
                                or other_conn["to_component_id"] == node_id):
                            wire_queue.append(other_conn["connection_id"])

        self._apply_highlight(visited_nodes, visited_wires)
        self._show_circuit_panel(visited_nodes, visited_wires)

    def _select_component(self, component_id: str) -> None:
        """Highlight a single component and every wire directly attached to it."""
        connected_wires: set[str] = set()
        connected_nodes: set[str] = {component_id}
        for conn in self._connection_data:
            if conn["from_component_id"] == component_id or conn["to_component_id"] == component_id:
                connected_wires.add(conn["connection_id"])
                connected_nodes.add(conn["from_component_id"])
                connected_nodes.add(conn["to_component_id"])
        self._apply_highlight(connected_nodes, connected_wires)
        self._show_component_panel(component_id)

    def _apply_highlight(
        self, active_nodes: set[str], active_wires: set[str],
    ) -> None:
        """Dim everything not in the active sets, brighten what is."""
        self._clear_overlays()
        self._is_selected = True

        # Dim non-active nodes via stipple overlay
        for cid in self._node_layout:
            if cid in active_nodes:
                continue
            for item in self.find_withtag(cid):
                tags = self.gettags(item)
                if "grid" in tags or "legend" in tags:
                    continue
                try:
                    self.itemconfigure(item, stipple="gray25")
                except tk.TclError:
                    pass

        # Dim non-active wires
        for conn in self._connection_data:
            if conn["connection_id"] in active_wires:
                continue
            for item in self.find_withtag(conn["connection_id"]):
                tags = self.gettags(item)
                if "wire" in tags or "wire_glow" in tags:
                    try:
                        self.itemconfigure(item, stipple="gray25")
                    except tk.TclError:
                        pass

        # Highlight border on each active node
        for cid in active_nodes:
            layout = self._node_layout.get(cid)
            if not layout:
                continue
            type_color = COMPONENT_TYPE_COLORS.get(
                layout["component"].get("component_type", "").lower(), COLOR_ACCENT,
            )
            node_x, node_y = layout["x"], layout["y"]
            node_width, node_height = layout["width"], layout["height"]
            highlight_id = self._smooth_rect(
                node_x - 2, node_y - 2, node_x + node_width + 2, node_y + node_height + 2,
                radius=12, fill="", outline=type_color, width=2, tags=("highlight",),
            )
            self._overlay_items.append(highlight_id)

    def _clear_overlays(self) -> None:
        """Remove all highlights, panels, and restore full opacity."""
        self._is_selected = False
        for item_id in self._overlay_items:
            self.delete(item_id)
        self._overlay_items.clear()
        self.delete("highlight")
        self.delete("detail_panel")
        # Restore stipple on every canvas item
        for item in self.find_all():
            try:
                self.itemconfigure(item, stipple="")
            except tk.TclError:
                pass

    # ── Detail Panels ─────────────────────────────────────────────────────

    def _show_component_panel(self, component_id: str) -> None:
        """Floating card at top-right showing component details and wire list."""
        layout = self._node_layout.get(component_id)
        if not layout:
            return
        comp = layout["component"]
        comp_names = {c["component_id"]: c["component_name"] for c in self._component_data}

        title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        label_font = tkfont.Font(family="Segoe UI", size=9)
        value_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        wire_font = tkfont.Font(family="Consolas", size=8)

        wires = [c for c in self._connection_data
                 if c["from_component_id"] == component_id
                 or c["to_component_id"] == component_id]

        panel_width = 310
        panel_x = self.canvasx(self.winfo_width() - panel_width - 16)
        panel_y = self.canvasy(12)
        panel_height = 50 + 5 * 20 + len(wires) * 20

        self._draw_panel_bg(panel_x, panel_y, panel_width, panel_height)

        type_color = COMPONENT_TYPE_COLORS.get(
            comp.get("component_type", "").lower(), COLOR_ACCENT,
        )
        # Accent bar
        self._overlay_items.append(self.create_rectangle(
            panel_x + 10, panel_y + 8, panel_x + 14, panel_y + 28,
            fill=type_color, outline=type_color, tags="detail_panel",
        ))

        text_y = panel_y + 18
        self._overlay_items.append(self.create_text(
            panel_x + 20, text_y, text=comp["component_name"],
            fill=COLOR_TEXT, font=title_font, anchor="w", tags="detail_panel",
        ))
        self._overlay_items.append(self.create_text(
            panel_x + panel_width - 14, panel_y + 14, text="\u2715",
            fill=COLOR_TEXT_MUTED, font=label_font, anchor="e", tags="detail_panel",
        ))

        text_y += 28
        for label_text, value_text in [
            ("Type", comp.get("component_type", "").capitalize()),
            ("Current", f"{comp.get('current_draw_amps', 0)} A"),
            ("Position", comp.get("position_label", "\u2014")),
            ("Connections", str(len(wires))),
        ]:
            self._overlay_items.append(self.create_text(
                panel_x + 14, text_y, text=f"{label_text}:",
                fill=COLOR_TEXT_MUTED, font=label_font, anchor="w", tags="detail_panel",
            ))
            self._overlay_items.append(self.create_text(
                panel_x + 105, text_y, text=value_text,
                fill=COLOR_TEXT, font=value_font, anchor="w", tags="detail_panel",
            ))
            text_y += 20

        text_y += 6
        self._overlay_items.append(self.create_line(
            panel_x + 10, text_y - 4, panel_x + panel_width - 10, text_y - 4,
            fill=COLOR_BORDER, tags="detail_panel",
        ))
        self._overlay_items.append(self.create_text(
            panel_x + 14, text_y, text="CONNECTED WIRES", fill=COLOR_TEXT,
            font=label_font, anchor="w", tags="detail_panel",
        ))
        text_y += 20

        for wire in wires:
            wire_hex = WIRE_HEX_MAP.get(wire.get("wire_color", "red"), COLOR_ACCENT)
            self._overlay_items.append(self.create_line(
                panel_x + 14, text_y, panel_x + 28, text_y,
                fill=wire_hex, width=3, tags="detail_panel",
            ))
            if wire["from_component_id"] == component_id:
                other_name = comp_names.get(wire["to_component_id"], "?")
                desc = f"\u2192 {other_name}  {wire['current_amps']}A  {wire['run_length_ft']}ft"
            else:
                other_name = comp_names.get(wire["from_component_id"], "?")
                desc = f"\u2190 {other_name}  {wire['current_amps']}A  {wire['run_length_ft']}ft"
            self._overlay_items.append(self.create_text(
                panel_x + 34, text_y, text=desc, fill=COLOR_TEXT_MUTED,
                font=wire_font, anchor="w", tags="detail_panel",
            ))
            text_y += 20

    def _show_circuit_panel(
        self, circuit_nodes: set[str], circuit_wires: set[str],
    ) -> None:
        """Floating panel showing the full traced circuit path with every hop."""
        comp_names = {c["component_id"]: c["component_name"] for c in self._component_data}

        title_font = tkfont.Font(family="Segoe UI", size=11, weight="bold")
        label_font = tkfont.Font(family="Segoe UI", size=9)
        value_font = tkfont.Font(family="Segoe UI", size=9, weight="bold")
        wire_font = tkfont.Font(family="Consolas", size=8)

        circuit_wire_list = [
            c for c in self._connection_data if c["connection_id"] in circuit_wires
        ]
        peak_amps = max((c["current_amps"] for c in circuit_wire_list), default=0)
        total_length = sum(c["run_length_ft"] for c in circuit_wire_list)

        panel_width = 340
        panel_x = self.canvasx(self.winfo_width() - panel_width - 16)
        panel_y = self.canvasy(12)
        panel_height = 50 + 5 * 20 + len(circuit_wire_list) * 22

        self._draw_panel_bg(panel_x, panel_y, panel_width, panel_height)

        # Header accent
        self._overlay_items.append(self.create_rectangle(
            panel_x + 10, panel_y + 8, panel_x + 14, panel_y + 28,
            fill=COLOR_ACCENT, outline=COLOR_ACCENT, tags="detail_panel",
        ))
        text_y = panel_y + 18
        self._overlay_items.append(self.create_text(
            panel_x + 20, text_y, text="\u26a1 Circuit Trace",
            fill=COLOR_TEXT, font=title_font, anchor="w", tags="detail_panel",
        ))
        self._overlay_items.append(self.create_text(
            panel_x + panel_width - 14, panel_y + 14, text="\u2715",
            fill=COLOR_TEXT_MUTED, font=label_font, anchor="e", tags="detail_panel",
        ))

        text_y += 28
        for label_text, value_text in [
            ("Modules", str(len(circuit_nodes))),
            ("Wires", str(len(circuit_wires))),
            ("Peak current", f"{peak_amps} A"),
            ("Total length", f"{total_length:.1f} ft"),
        ]:
            self._overlay_items.append(self.create_text(
                panel_x + 14, text_y, text=f"{label_text}:",
                fill=COLOR_TEXT_MUTED, font=label_font, anchor="w", tags="detail_panel",
            ))
            self._overlay_items.append(self.create_text(
                panel_x + 120, text_y, text=value_text,
                fill=COLOR_TEXT, font=value_font, anchor="w", tags="detail_panel",
            ))
            text_y += 20

        text_y += 6
        self._overlay_items.append(self.create_line(
            panel_x + 10, text_y - 4, panel_x + panel_width - 10, text_y - 4,
            fill=COLOR_BORDER, tags="detail_panel",
        ))
        self._overlay_items.append(self.create_text(
            panel_x + 14, text_y, text="CIRCUIT PATH", fill=COLOR_TEXT,
            font=label_font, anchor="w", tags="detail_panel",
        ))
        text_y += 22

        for wire in circuit_wire_list:
            wire_hex = WIRE_HEX_MAP.get(wire.get("wire_color", "red"), COLOR_ACCENT)
            from_name = comp_names.get(wire["from_component_id"], "?")
            to_name = comp_names.get(wire["to_component_id"], "?")

            self._overlay_items.append(self.create_line(
                panel_x + 14, text_y, panel_x + 28, text_y,
                fill=wire_hex, width=3, tags="detail_panel",
            ))
            desc = f"{from_name} \u2192 {to_name}  [{wire['from_pin']}\u2192{wire['to_pin']}]"
            self._overlay_items.append(self.create_text(
                panel_x + 34, text_y, text=desc, fill=COLOR_TEXT_MUTED,
                font=wire_font, anchor="w", tags="detail_panel",
            ))
            text_y += 22

    def _draw_panel_bg(self, panel_x: float, panel_y: float, panel_width: int, panel_height: int) -> None:
        """Draw shadow + background for a floating detail panel."""
        self._overlay_items.append(self._smooth_rect(
            panel_x + 3, panel_y + 3,
            panel_x + panel_width + 3, panel_y + panel_height + 3,
            radius=10, fill=SHADOW_COLOR, outline=SHADOW_COLOR, tags="detail_panel",
        ))
        self._overlay_items.append(self._smooth_rect(
            panel_x, panel_y, panel_x + panel_width, panel_y + panel_height,
            radius=10, fill=COLOR_CARD_BG, outline=COLOR_BORDER, tags="detail_panel",
        ))

    # ── Interaction ───────────────────────────────────────────────────────

    def _on_click(self, event: tk.Event) -> None:
        """Route clicks: component card shows detail, wire traces circuit, bg deselects."""
        self.scan_mark(event.x, event.y)
        canvas_x = self.canvasx(event.x)
        canvas_y = self.canvasy(event.y)
        hits = self.find_overlapping(canvas_x - 3, canvas_y - 3, canvas_x + 3, canvas_y + 3)

        # Click on detail panel dismisses it
        for item in hits:
            if "detail_panel" in self.gettags(item):
                self._clear_overlays()
                return

        # Click on a wire triggers full circuit trace
        for item in hits:
            tags = self.gettags(item)
            if "wire" in tags:
                conn_id = next((t for t in tags if t not in ("wire", "current")), None)
                if conn_id:
                    self._trace_circuit(conn_id)
                    return

        # Click on a component node shows its detail panel
        for item in hits:
            tags = self.gettags(item)
            for tag in tags:
                if tag in self._node_layout:
                    self._select_component(tag)
                    return

        # Click empty background deselects
        if self._is_selected:
            self._clear_overlays()

    def _on_pan_move(self, event: tk.Event) -> None:
        """Pan the canvas by dragging."""
        self.scan_dragto(event.x, event.y, gain=1)

    def _on_zoom(self, event: tk.Event) -> None:
        """Zoom in/out centered on cursor position."""
        zoom_factor = 0.9 if (event.num == 5 or event.delta < 0) else 1.1
        new_scale = self._scale_factor * zoom_factor
        if new_scale < 0.3 or new_scale > 3.0:
            return
        self._scale_factor = new_scale
        self.scale("all", self.canvasx(event.x), self.canvasy(event.y), zoom_factor, zoom_factor)
        bbox = self.bbox("all")
        if bbox:
            self.configure(scrollregion=(bbox[0] - 60, bbox[1] - 60, bbox[2] + 60, bbox[3] + 60))

    def _on_hover(self, event: tk.Event) -> None:
        """Show a rich tooltip when hovering a wire."""
        for old_item in self._tooltip_items:
            self.delete(old_item)
        self._tooltip_items.clear()

        canvas_x, canvas_y = self.canvasx(event.x), self.canvasy(event.y)
        for item in self.find_overlapping(canvas_x - 5, canvas_y - 5, canvas_x + 5, canvas_y + 5):
            tags = self.gettags(item)
            if "wire" not in tags:
                continue
            conn_id = next((t for t in tags if t not in ("wire", "current")), None)
            if not conn_id:
                continue
            conn = next(
                (c for c in self._connection_data if c["connection_id"] == conn_id), None,
            )
            if not conn:
                continue

            comp_names = {c["component_id"]: c["component_name"] for c in self._component_data}
            from_name = comp_names.get(conn["from_component_id"], conn["from_component_id"])
            to_name = comp_names.get(conn["to_component_id"], conn["to_component_id"])
            wire_hex = WIRE_HEX_MAP.get(conn.get("wire_color", "red"), COLOR_ACCENT)
            tip_font = tkfont.Font(family="Segoe UI", size=9)

            tip_x, tip_y = canvas_x + 16, canvas_y - 30
            self._tooltip_items.append(self._smooth_rect(
                tip_x - 2, tip_y - 2, tip_x + 340, tip_y + 48,
                radius=6, fill=COLOR_SURFACE2, outline=COLOR_BORDER, tags="tooltip",
            ))
            self._tooltip_items.append(self.create_line(
                tip_x + 6, tip_y + 12, tip_x + 22, tip_y + 12,
                fill=wire_hex, width=3, tags="tooltip",
            ))
            self._tooltip_items.append(self.create_text(
                tip_x + 28, tip_y + 12, text=f"{from_name}  \u2192  {to_name}",
                fill=COLOR_TEXT, font=tip_font, anchor="w", tags="tooltip",
            ))
            self._tooltip_items.append(self.create_text(
                tip_x + 8, tip_y + 32,
                text=(f"Pins: {conn['from_pin']} \u2192 {conn['to_pin']}   "
                      f"{conn['current_amps']}A  \u2022  {conn['run_length_ft']}ft  \u2022  "
                      f"{conn.get('wire_color', 'red')}   (click to trace circuit)"),
                fill=COLOR_TEXT_MUTED, font=tip_font, anchor="w", tags="tooltip",
            ))
            return


# ── Application Shell ─────────────────────────────────────────────────────────


class WiringWizardApp(tk.Tk):
    """Modern desktop shell for building wiring plans via visual tables and AI assistance."""

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(1020, 700)
        self.configure(background=COLOR_SURFACE)
        self._current_project: Optional[WiringProject] = None
        self._component_data: List[Dict[str, Any]] = []
        self._connection_data: List[Dict[str, Any]] = []

        self._body_font_family: str = _apply_modern_theme(self)
        self._build_main_layout()
        self._load_draft_if_available()

    # ── Layout Skeleton ───────────────────────────────────────────────────────

    def _build_main_layout(self) -> None:
        """Assemble header, project bar, tabbed body, and status bar."""
        self._build_header_bar()
        self._build_project_bar()

        body_frame = ttk.Frame(self, style="TFrame")
        body_frame.pack(fill=tk.BOTH, expand=True, padx=16, pady=(0, 0))

        self.notebook = ttk.Notebook(body_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self.describe_tab = ttk.Frame(self.notebook, style="TFrame")
        self.build_tab = ttk.Frame(self.notebook, style="TFrame")
        self.diagram_tab = ttk.Frame(self.notebook, style="TFrame")
        self.plan_tab = ttk.Frame(self.notebook, style="TFrame")

        self.notebook.add(self.describe_tab, text="  \U0001f916 Describe Your Project  ")
        self.notebook.add(self.build_tab, text="  \U0001f4cb Components & Wiring  ")
        self.notebook.add(self.diagram_tab, text="  \U0001f4a1 Wiring Diagram  ")
        self.notebook.add(self.plan_tab, text="  \U0001f4ca Wiring Plan  ")

        self._build_describe_tab()
        self._build_build_tab()
        self._build_diagram_tab()
        self._build_plan_tab()
        self._build_status_bar()

    def _build_header_bar(self) -> None:
        """Branded header strip at the top of the window."""
        header_frame = tk.Frame(self, background=COLOR_HEADER_BG, height=48)
        header_frame.pack(fill=tk.X, side=tk.TOP)
        header_frame.pack_propagate(False)

        title_font = tkfont.Font(family=self._body_font_family, size=14, weight="bold")
        subtitle_font = tkfont.Font(family=self._body_font_family, size=10)

        tk.Label(
            header_frame, text="\u26a1  WiringWizard", font=title_font,
            background=COLOR_HEADER_BG, foreground=COLOR_HEADER_FG, padx=16,
        ).pack(side=tk.LEFT)
        tk.Label(
            header_frame, text="Wiring Diagram & Harness Planner", font=subtitle_font,
            background=COLOR_HEADER_BG, foreground=COLOR_TEXT_MUTED,
        ).pack(side=tk.LEFT, padx=(0, 12))

    def _build_project_bar(self) -> None:
        """Persistent bar showing project name, domain, and voltage class — always visible."""
        PROJECT_BAR_BG = COLOR_CARD_BG
        bar = tk.Frame(self, background=PROJECT_BAR_BG, height=44)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        inner = tk.Frame(bar, background=PROJECT_BAR_BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)

        label_font = tkfont.Font(family=self._body_font_family, size=9)
        entry_font = tkfont.Font(family=self._body_font_family, size=10)

        tk.Label(
            inner, text="Project:", font=label_font, bg=PROJECT_BAR_BG, fg=COLOR_TEXT_MUTED,
        ).pack(side=tk.LEFT, padx=(0, 4))
        self.project_name_var = tk.StringVar(value="My Wiring Project")
        tk.Entry(
            inner, textvariable=self.project_name_var, font=entry_font, width=24,
            relief="solid", bd=1, highlightthickness=0,
            bg=COLOR_SURFACE2, fg=COLOR_TEXT, insertbackground=COLOR_TEXT,
        ).pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(
            inner, text="Domain:", font=label_font, bg=PROJECT_BAR_BG, fg=COLOR_TEXT_MUTED,
        ).pack(side=tk.LEFT, padx=(0, 4))
        self.domain_var = tk.StringVar(value="automotive")
        self.domain_combo = ttk.Combobox(
            inner, textvariable=self.domain_var,
            values=list(DOMAIN_PROFILES.keys()), state="readonly", width=14,
        )
        self.domain_combo.pack(side=tk.LEFT, padx=(0, 20))
        self.domain_combo.bind("<<ComboboxSelected>>", self._on_domain_changed)

        tk.Label(
            inner, text="Voltage:", font=label_font, bg=PROJECT_BAR_BG, fg=COLOR_TEXT_MUTED,
        ).pack(side=tk.LEFT, padx=(0, 4))
        self.voltage_var = tk.StringVar(value="lv_12v")
        self.voltage_combo = ttk.Combobox(
            inner, textvariable=self.voltage_var, state="readonly", width=12,
        )
        self.voltage_combo.pack(side=tk.LEFT)
        self._refresh_voltage_options()

    def _build_status_bar(self) -> None:
        """Persistent status strip at the bottom of the window."""
        status_frame = ttk.Frame(self, style="StatusBar.TFrame")
        status_frame.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_var = tk.StringVar(
            value="Ready \u2014 describe your project or add components to get started.",
        )
        ttk.Label(
            status_frame, textvariable=self.status_var, style="StatusBar.TLabel",
        ).pack(side=tk.LEFT, fill=tk.X, expand=True)

    # ── Tab 1: Describe Your Project (AI-powered) ─────────────────────────────

    def _build_describe_tab(self) -> None:
        """Build the AI brief and token management interface."""
        # Main brief card — the primary interaction surface
        brief_card = ttk.LabelFrame(
            self.describe_tab, text="  Describe What You Need  ",
            style="Card.TLabelframe", padding=16,
        )
        brief_card.pack(fill=tk.BOTH, expand=True, padx=8, pady=(10, 4))

        ttk.Label(
            brief_card,
            text=(
                "Tell me about your project in plain English. What components do you have? "
                "What are you trying to build? Be as detailed as you like."
            ),
            style="CardMuted.TLabel", wraplength=900,
        ).pack(anchor="w", pady=(0, 10))

        brief_font = tkfont.Font(family=self._body_font_family, size=10)
        self.ai_brief_text = scrolledtext.ScrolledText(
            brief_card, height=10, wrap=tk.WORD,
            background=COLOR_EDITOR_BG, foreground=COLOR_EDITOR_FG,
            insertbackground=COLOR_TEXT, selectbackground=COLOR_ACCENT,
            relief="solid", borderwidth=1, highlightthickness=0,
            font=brief_font,
        )
        self.ai_brief_text.pack(fill=tk.BOTH, expand=True)

        # Pre-fill with example placeholder text
        _PLACEHOLDER = (
            "Example: I'm wiring a 1990 Miata with a MegaSquirt ECU, "
            "aftermarket fuse block, 4 relays for fans and fuel pump, "
            "and an electric power steering pump. All 12V. "
            "I need the full harness plan with wire sizes and a step-by-step guide."
        )
        self.ai_brief_text.insert(tk.END, _PLACEHOLDER)
        self.ai_brief_text.tag_add("placeholder", "1.0", tk.END)
        self.ai_brief_text.tag_configure("placeholder", foreground=COLOR_TEXT_SUBTLE)
        self.ai_brief_text.bind("<FocusIn>", self._on_brief_focus_in)

        # Action row
        action_frame = ttk.Frame(brief_card, style="Card.TFrame")
        action_frame.pack(fill=tk.X, pady=(12, 0))

        ttk.Button(
            action_frame, text="\u26a1  Generate from Description",
            style="Primary.TButton", command=self._on_ai_draft_from_brief,
        ).pack(side=tk.LEFT)
        self.ai_status_var = tk.StringVar(value="")
        ttk.Label(
            action_frame, textvariable=self.ai_status_var, style="CardMuted.TLabel",
        ).pack(side=tk.LEFT, padx=(14, 0))

        # Token management card (smaller, at bottom)
        token_card = ttk.LabelFrame(
            self.describe_tab,
            text="  API Token (optional \u2014 improves AI quality)  ",
            style="Card.TLabelframe", padding=12,
        )
        token_card.pack(fill=tk.X, padx=8, pady=(4, 10))

        token_row = ttk.Frame(token_card, style="Card.TFrame")
        token_row.pack(fill=tk.X)
        self.ai_token_var = tk.StringVar(value=get_saved_gui_api_token() or "")
        ttk.Entry(
            token_row, textvariable=self.ai_token_var, show="\u2022", width=50,
        ).pack(side=tk.LEFT)
        ttk.Button(
            token_row, text="Save", style="Secondary.TButton",
            command=self._on_save_ai_token,
        ).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(
            token_row, text="Clear", style="Secondary.TButton",
            command=self._on_clear_ai_token,
        ).pack(side=tk.LEFT, padx=(4, 0))

        initial_token_hint = (
            "Token loaded for this app."
            if self.ai_token_var.get().strip()
            else "No saved token \u2014 fallback parser will be used."
        )
        self._token_hint_var = tk.StringVar(value=initial_token_hint)
        ttk.Label(
            token_card, textvariable=self._token_hint_var, style="CardMuted.TLabel",
        ).pack(anchor="w", pady=(6, 0))

    def _on_brief_focus_in(self, _event: Any = None) -> None:
        """Clear placeholder text when the user clicks into the AI brief field."""
        if self.ai_brief_text.tag_ranges("placeholder"):
            self.ai_brief_text.delete("1.0", tk.END)

    # ── Tab 2: Components & Wiring (visual tables) ────────────────────────────

    def _build_build_tab(self) -> None:
        """Build the visual component/connection management tab with tables."""
        # Description at top
        description_card = ttk.LabelFrame(
            self.build_tab, text="  Project Goal / Description  ",
            style="Card.TLabelframe", padding=10,
        )
        description_card.pack(fill=tk.X, padx=8, pady=(10, 4))

        self.description_text = scrolledtext.ScrolledText(
            description_card, height=2, wrap=tk.WORD,
            background=COLOR_EDITOR_BG, foreground=COLOR_EDITOR_FG,
            insertbackground=COLOR_TEXT, selectbackground=COLOR_ACCENT,
            relief="solid", borderwidth=1, highlightthickness=0,
        )
        self.description_text.pack(fill=tk.X)

        # Vertical split: components on top, connections on bottom
        pane = ttk.PanedWindow(self.build_tab, orient=tk.VERTICAL)
        pane.pack(fill=tk.BOTH, expand=True, padx=8, pady=4)

        self._build_components_section(pane)
        self._build_connections_section(pane)

        # Action bar at the bottom
        action_bar = ttk.Frame(self.build_tab, style="TFrame")
        action_bar.pack(fill=tk.X, padx=8, pady=(6, 8))

        ttk.Button(
            action_bar, text="\u25b6  Generate Wiring Plan",
            style="Primary.TButton", command=self._on_generate_report,
        ).pack(side=tk.LEFT)
        ttk.Button(
            action_bar, text="\U0001f4be  Save Draft",
            style="Secondary.TButton", command=self._save_draft,
        ).pack(side=tk.LEFT, padx=(10, 0))
        ttk.Button(
            action_bar, text="\U0001f4c2  Load Draft",
            style="Secondary.TButton", command=self._load_draft_if_available,
        ).pack(side=tk.LEFT, padx=(6, 0))

    def _build_components_section(self, parent_pane: ttk.PanedWindow) -> None:
        """Build the components Treeview table with add/edit/delete toolbar."""
        frame = ttk.LabelFrame(
            parent_pane, text="  Components  ",
            style="Card.TLabelframe", padding=8,
        )

        # Toolbar
        toolbar = ttk.Frame(frame, style="Card.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(
            toolbar, text="\u2795 Add", style="Secondary.TButton",
            command=self._on_add_component,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            toolbar, text="\u270f\ufe0f Edit", style="Secondary.TButton",
            command=self._on_edit_component,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            toolbar, text="\U0001f5d1\ufe0f Delete", style="Secondary.TButton",
            command=self._on_delete_component,
        ).pack(side=tk.LEFT)

        # Treeview table
        columns = ("name", "type", "amps", "position")
        self.comp_tree = ttk.Treeview(frame, columns=columns, show="headings", height=5)
        self.comp_tree.heading("name", text="Name")
        self.comp_tree.heading("type", text="Type")
        self.comp_tree.heading("amps", text="Current (A)")
        self.comp_tree.heading("position", text="Position")
        self.comp_tree.column("name", width=200, minwidth=100)
        self.comp_tree.column("type", width=130, minwidth=80)
        self.comp_tree.column("amps", width=90, anchor="center", minwidth=60)
        self.comp_tree.column("position", width=160, minwidth=80)

        comp_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.comp_tree.yview)
        self.comp_tree.configure(yscrollcommand=comp_scrollbar.set)
        self.comp_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        comp_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Double-click to edit, Delete key to remove
        self.comp_tree.bind("<Double-1>", lambda _event: self._on_edit_component())
        self.comp_tree.bind("<Delete>", lambda _event: self._on_delete_component())

        parent_pane.add(frame, weight=1)

    def _build_connections_section(self, parent_pane: ttk.PanedWindow) -> None:
        """Build the connections Treeview table with add/edit/delete toolbar."""
        frame = ttk.LabelFrame(
            parent_pane, text="  Connections  ",
            style="Card.TLabelframe", padding=8,
        )

        toolbar = ttk.Frame(frame, style="Card.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(
            toolbar, text="\u2795 Add", style="Secondary.TButton",
            command=self._on_add_connection,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            toolbar, text="\u270f\ufe0f Edit", style="Secondary.TButton",
            command=self._on_edit_connection,
        ).pack(side=tk.LEFT, padx=(0, 4))
        ttk.Button(
            toolbar, text="\U0001f5d1\ufe0f Delete", style="Secondary.TButton",
            command=self._on_delete_connection,
        ).pack(side=tk.LEFT)

        columns = ("from_name", "from_pin", "to_name", "to_pin", "amps", "length", "color", "awg")
        self.conn_tree = ttk.Treeview(frame, columns=columns, show="headings", height=5)
        self.conn_tree.heading("from_name", text="From")
        self.conn_tree.heading("from_pin", text="Pin")
        self.conn_tree.heading("to_name", text="To")
        self.conn_tree.heading("to_pin", text="Pin")
        self.conn_tree.heading("amps", text="Amps")
        self.conn_tree.heading("length", text="Length (ft)")
        self.conn_tree.heading("color", text="Color")
        self.conn_tree.heading("awg", text="AWG")
        self.conn_tree.column("from_name", width=130, minwidth=80)
        self.conn_tree.column("from_pin", width=80, minwidth=50)
        self.conn_tree.column("to_name", width=130, minwidth=80)
        self.conn_tree.column("to_pin", width=80, minwidth=50)
        self.conn_tree.column("amps", width=60, anchor="center", minwidth=40)
        self.conn_tree.column("length", width=80, anchor="center", minwidth=50)
        self.conn_tree.column("color", width=70, anchor="center", minwidth=50)
        self.conn_tree.column("awg", width=60, anchor="center", minwidth=40)

        conn_scrollbar = ttk.Scrollbar(frame, orient="vertical", command=self.conn_tree.yview)
        self.conn_tree.configure(yscrollcommand=conn_scrollbar.set)
        self.conn_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        conn_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.conn_tree.bind("<Double-1>", lambda _event: self._on_edit_connection())
        self.conn_tree.bind("<Delete>", lambda _event: self._on_delete_connection())

        parent_pane.add(frame, weight=1)

    # ── Tab 3: Wiring Diagram (Interactive Canvas) ──────────────────────────

    def _build_diagram_tab(self) -> None:
        """Build the interactive visual wiring diagram tab with zoom/pan controls."""
        toolbar = ttk.Frame(self.diagram_tab, style="TFrame")
        toolbar.pack(fill=tk.X, padx=8, pady=(8, 4))

        ttk.Button(
            toolbar, text="\U0001f504  Refresh Diagram",
            style="Primary.TButton", command=self._refresh_diagram,
        ).pack(side=tk.LEFT)
        ttk.Button(
            toolbar, text="\U0001f50d  Fit to View",
            style="Secondary.TButton", command=self._fit_diagram_to_view,
        ).pack(side=tk.LEFT, padx=(10, 0))

        hint_font = tkfont.Font(family=self._body_font_family, size=9)
        ttk.Label(
            toolbar,
            text="Click card \u2192 details  •  Click wire \u2192 trace circuit  •  Scroll to zoom  •  Drag to pan",
            style="TLabel", font=hint_font,
        ).pack(side=tk.RIGHT, padx=(0, 8))

        self.diagram_canvas = DiagramCanvas(self.diagram_tab)
        self.diagram_canvas.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

    def _refresh_diagram(self) -> None:
        """Redraw the diagram canvas from the current component/connection data."""
        self.diagram_canvas.render_diagram(
            self._component_data, self._connection_data,
        )
        self._set_status("Diagram refreshed.")

    def _fit_diagram_to_view(self) -> None:
        """Reset zoom and pan to show the full diagram centered in the viewport."""
        self.diagram_canvas._scale_factor = 1.0
        self.diagram_canvas.render_diagram(
            self._component_data, self._connection_data,
        )
        self.diagram_canvas.xview_moveto(0)
        self.diagram_canvas.yview_moveto(0)

    # ── Tab 4: Wiring Plan ────────────────────────────────────────────────────

    def _build_plan_tab(self) -> None:
        """Build the generated wiring report output tab with copy-to-clipboard."""
        card = ttk.LabelFrame(
            self.plan_tab, text="  Generated Wiring Report  ",
            style="Card.TLabelframe", padding=12,
        )
        card.pack(fill=tk.BOTH, expand=True, padx=8, pady=10)

        toolbar = ttk.Frame(card, style="Card.TFrame")
        toolbar.pack(fill=tk.X, pady=(0, 8))
        ttk.Button(
            toolbar, text="\U0001f4cb  Copy to Clipboard",
            style="Secondary.TButton", command=self._on_copy_report,
        ).pack(side=tk.LEFT)

        self.output_text = scrolledtext.ScrolledText(
            card, wrap=tk.NONE,
            background=COLOR_EDITOR_BG, foreground=COLOR_EDITOR_FG,
            insertbackground=COLOR_TEXT, selectbackground=COLOR_ACCENT,
            relief="solid", borderwidth=1, highlightthickness=0,
        )
        self.output_text.pack(fill=tk.BOTH, expand=True)

    # ── Table Refresh ─────────────────────────────────────────────────────────

    def _refresh_component_table(self) -> None:
        """Rebuild the components Treeview rows from self._component_data."""
        self.comp_tree.delete(*self.comp_tree.get_children())
        for component in self._component_data:
            self.comp_tree.insert("", tk.END, iid=component["component_id"], values=(
                component["component_name"],
                component["component_type"],
                component["current_draw_amps"],
                component.get("position_label", ""),
            ))

    def _refresh_connection_table(self) -> None:
        """Rebuild the connections Treeview rows from self._connection_data."""
        component_names = {
            c["component_id"]: c["component_name"] for c in self._component_data
        }
        self.conn_tree.delete(*self.conn_tree.get_children())
        for connection in self._connection_data:
            awg_display = connection.get("awg_override") or "Auto"
            from_display = component_names.get(
                connection["from_component_id"], connection["from_component_id"],
            )
            to_display = component_names.get(
                connection["to_component_id"], connection["to_component_id"],
            )
            self.conn_tree.insert("", tk.END, iid=connection["connection_id"], values=(
                from_display,
                connection["from_pin"],
                to_display,
                connection["to_pin"],
                connection["current_amps"],
                connection["run_length_ft"],
                connection.get("wire_color", "red"),
                awg_display,
            ))

    def _build_component_lookup(self) -> Dict[str, str]:
        """Return a {component_id: component_name} dict for dialog dropdown population."""
        return {c["component_id"]: c["component_name"] for c in self._component_data}

    # ── Component CRUD ────────────────────────────────────────────────────────

    def _on_add_component(self) -> None:
        """Open the Add Component dialog and append the result to the data list."""
        dialog = ComponentDialog(
            self, self._body_font_family, domain=self.domain_var.get(),
        )
        if dialog.result is None:
            return
        # Ensure the auto-generated ID is unique
        existing_ids = {c["component_id"] for c in self._component_data}
        base_id = dialog.result["component_id"]
        if base_id in existing_ids:
            counter = 2
            while f"{base_id}_{counter}" in existing_ids:
                counter += 1
            dialog.result["component_id"] = f"{base_id}_{counter}"
        self._component_data.append(dialog.result)
        self._refresh_component_table()
        self._set_status(f"Added component: {dialog.result['component_name']}")

    def _on_edit_component(self) -> None:
        """Open the Edit Component dialog for the selected table row."""
        selection = self.comp_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a component to edit.", parent=self)
            return
        component_id = selection[0]
        existing = next(
            (c for c in self._component_data if c["component_id"] == component_id), None,
        )
        if not existing:
            return
        dialog = ComponentDialog(
            self, self._body_font_family,
            domain=self.domain_var.get(), existing=existing,
        )
        if dialog.result is None:
            return
        index = next(
            i for i, c in enumerate(self._component_data)
            if c["component_id"] == component_id
        )
        self._component_data[index] = dialog.result
        self._refresh_component_table()
        self._refresh_connection_table()
        self._set_status(f"Updated component: {dialog.result['component_name']}")

    def _on_delete_component(self) -> None:
        """Remove the selected component and any connections referencing it."""
        selection = self.comp_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a component to delete.", parent=self)
            return
        component_id = selection[0]
        component = next(
            (c for c in self._component_data if c["component_id"] == component_id), None,
        )
        if not component:
            return
        is_confirmed = messagebox.askyesno(
            "Delete component?",
            (
                f"Delete '{component['component_name']}'?\n\n"
                "Connections to/from this component will also be removed."
            ),
            parent=self,
        )
        if not is_confirmed:
            return
        self._component_data = [
            c for c in self._component_data if c["component_id"] != component_id
        ]
        self._connection_data = [
            c for c in self._connection_data
            if c["from_component_id"] != component_id
            and c["to_component_id"] != component_id
        ]
        self._refresh_component_table()
        self._refresh_connection_table()
        self._set_status(f"Deleted component: {component['component_name']}")

    # ── Connection CRUD ───────────────────────────────────────────────────────

    def _on_add_connection(self) -> None:
        """Open the Add Connection dialog, requiring at least one component first."""
        if not self._component_data:
            messagebox.showinfo(
                "No components", "Add at least one component first.", parent=self,
            )
            return
        dialog = ConnectionDialog(
            self, self._body_font_family, self._build_component_lookup(),
        )
        if dialog.result is None:
            return
        # Auto-generate a unique connection ID
        existing_ids = {c["connection_id"] for c in self._connection_data}
        counter = 1
        while f"conn_{counter:03d}" in existing_ids:
            counter += 1
        dialog.result["connection_id"] = f"conn_{counter:03d}"
        self._connection_data.append(dialog.result)
        self._refresh_connection_table()
        self._set_status("Added connection.")

    def _on_edit_connection(self) -> None:
        """Open the Edit Connection dialog for the selected table row."""
        selection = self.conn_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a connection to edit.", parent=self)
            return
        connection_id = selection[0]
        existing = next(
            (c for c in self._connection_data if c["connection_id"] == connection_id), None,
        )
        if not existing:
            return
        dialog = ConnectionDialog(
            self, self._body_font_family,
            self._build_component_lookup(), existing=existing,
        )
        if dialog.result is None:
            return
        dialog.result["connection_id"] = connection_id
        index = next(
            i for i, c in enumerate(self._connection_data)
            if c["connection_id"] == connection_id
        )
        self._connection_data[index] = dialog.result
        self._refresh_connection_table()
        self._set_status("Updated connection.")

    def _on_delete_connection(self) -> None:
        """Remove the selected connection from the data list."""
        selection = self.conn_tree.selection()
        if not selection:
            messagebox.showinfo("No selection", "Select a connection to delete.", parent=self)
            return
        connection_id = selection[0]
        is_confirmed = messagebox.askyesno(
            "Delete connection?", f"Delete connection '{connection_id}'?", parent=self,
        )
        if not is_confirmed:
            return
        self._connection_data = [
            c for c in self._connection_data if c["connection_id"] != connection_id
        ]
        self._refresh_connection_table()
        self._set_status(f"Deleted connection {connection_id}.")

    # ── Report Generation ─────────────────────────────────────────────────────

    def _on_generate_report(self) -> None:
        """Build a WiringProject from the current tables and generate the full report."""
        try:
            project = self._build_project_from_tables()
            report_text = build_report_for_project(project)
        except (ValueError, ValidationError) as error:
            messagebox.showerror("Cannot generate plan", str(error), parent=self)
            self._set_status("Generation failed \u2014 fix errors and retry.")
            return

        self._current_project = project
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, report_text)

        # Also refresh the visual diagram with the latest data
        self.diagram_canvas.render_diagram(
            self._component_data, self._connection_data,
        )

        self.notebook.select(self.plan_tab)
        self._set_status("Wiring plan generated \u2014 see the Plan tab.")

    def _on_copy_report(self) -> None:
        """Copy the generated wiring report text to the system clipboard."""
        report_content = self.output_text.get("1.0", tk.END).strip()
        if not report_content:
            messagebox.showinfo("Nothing to copy", "Generate a wiring plan first.", parent=self)
            return
        self.clipboard_clear()
        self.clipboard_append(report_content)
        self._set_status("Report copied to clipboard.")

    def _build_project_from_tables(self) -> WiringProject:
        """Construct a WiringProject from the in-memory component/connection data lists."""
        profile = ProjectProfile(
            project_name=self.project_name_var.get().strip(),
            domain=self.domain_var.get().strip(),
            voltage_class=self.voltage_var.get().strip(),
            description=self.description_text.get("1.0", tk.END).strip(),
        )
        components = [
            Component(
                component_id=c["component_id"],
                component_name=c["component_name"],
                component_type=c["component_type"],
                current_draw_amps=float(c["current_draw_amps"]),
                position_label=c.get("position_label", ""),
            )
            for c in self._component_data
        ]
        connections = [
            Connection(
                connection_id=c["connection_id"],
                from_component_id=c["from_component_id"],
                from_pin=c["from_pin"],
                to_component_id=c["to_component_id"],
                to_pin=c["to_pin"],
                current_amps=float(c["current_amps"]),
                run_length_ft=float(c["run_length_ft"]),
                wire_color=c.get("wire_color", "red"),
                awg_override=c.get("awg_override"),
            )
            for c in self._connection_data
        ]
        return WiringProject(profile=profile, components=components, connections=connections)

    # ── AI Draft ──────────────────────────────────────────────────────────────

    def _on_ai_draft_from_brief(self) -> None:
        """
        Read the user's plain-English brief, call AI to generate components and
        connections, populate the visual tables and description, then switch to the
        Build tab so the user can review.
        """
        brief_text = self.ai_brief_text.get("1.0", tk.END).strip()
        if not brief_text:
            messagebox.showwarning(
                "No description", "Enter a project description first.", parent=self,
            )
            return

        self._set_status("Generating draft\u2026")
        self.ai_status_var.set("Working\u2026")
        self.update_idletasks()

        try:
            draft_payload = draft_project_from_brief(
                brief_text=brief_text,
                requested_project_name=self.project_name_var.get().strip(),
                api_token_override=self.ai_token_var.get().strip() or None,
            )
        except Exception as draft_error:
            messagebox.showerror(
                "Draft failed",
                f"Could not generate draft: {draft_error}",
                parent=self,
            )
            self._set_status("Draft failed.")
            self.ai_status_var.set("")
            return

        # Apply the AI-generated project name (if non-empty)
        draft_project_name = str(draft_payload.get("project_name", "")).strip()
        if draft_project_name:
            self.project_name_var.set(draft_project_name)

        # Populate the description field on the Build tab
        draft_description = str(draft_payload.get("description", "")).strip()
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, draft_description)

        # Replace the in-memory data and refresh tables
        self._component_data = list(draft_payload.get("components", []))
        self._connection_data = list(draft_payload.get("connections", []))
        self._refresh_component_table()
        self._refresh_connection_table()

        # Switch to the Build tab so the user sees the populated tables
        self.notebook.select(self.build_tab)

        if draft_payload.get("used_ai"):
            self.ai_status_var.set(
                "\u2713 AI draft applied \u2014 review in Components & Wiring tab.",
            )
            self._set_status(
                "AI draft populated. Review components and connections, then generate your plan.",
            )
        else:
            self.ai_status_var.set(
                "Fallback parser used (add/save an API token for better results).",
            )
            self._set_status(
                "Fallback draft populated. Review and adjust, then generate your plan.",
            )

    # ── Token Management ──────────────────────────────────────────────────────

    def _on_save_ai_token(self) -> None:
        """Persist the AI token entered in the token panel."""
        token_value = self.ai_token_var.get().strip()
        if not token_value:
            messagebox.showwarning("Missing token", "Enter a token before saving.", parent=self)
            return
        try:
            save_gui_api_token(token_value)
        except OSError as error:
            messagebox.showerror("Save failed", f"Could not save token: {error}", parent=self)
            return
        self._token_hint_var.set("Token saved for this app.")
        self._set_status("AI token saved.")

    def _on_clear_ai_token(self) -> None:
        """Clear the saved AI token and the UI token field."""
        try:
            clear_saved_gui_api_token()
        except OSError as error:
            messagebox.showerror("Clear failed", f"Could not clear token: {error}", parent=self)
            return
        self.ai_token_var.set("")
        self._token_hint_var.set("Token cleared \u2014 fallback parser will be used.")
        self._set_status("AI token cleared.")

    # ── Domain / Voltage ──────────────────────────────────────────────────────

    def _on_domain_changed(self, _event: Optional[Any] = None) -> None:
        """Update voltage class options when the domain dropdown changes."""
        self._refresh_voltage_options()

    def _refresh_voltage_options(self) -> None:
        """Sync the voltage dropdown to the currently selected domain."""
        selected_domain = self.domain_var.get().strip()
        profile = get_domain_profile(selected_domain)
        allowed_classes = list(profile["allowed_voltage_classes"])
        self.voltage_combo["values"] = allowed_classes
        if self.voltage_var.get() not in allowed_classes:
            self.voltage_var.set(allowed_classes[0])

    # ── Draft Save / Load ─────────────────────────────────────────────────────

    def _build_draft_payload(self) -> Dict[str, Any]:
        """Serialize the current UI state to a dict for JSON persistence."""
        return {
            "project_name": self.project_name_var.get(),
            "domain": self.domain_var.get(),
            "voltage_class": self.voltage_var.get(),
            "description": self.description_text.get("1.0", tk.END).strip(),
            "components": list(self._component_data),
            "connections": list(self._connection_data),
        }

    def _save_draft(self) -> None:
        """Write the current project state to the draft JSON file."""
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(DRAFT_FILE_PATH, "w", encoding="utf-8") as draft_file:
                json.dump(self._build_draft_payload(), draft_file, indent=2)
        except OSError as error:
            messagebox.showerror("Save failed", f"Could not save draft: {error}", parent=self)
            self._set_status("Draft save failed.")
            return
        self._set_status(f"Draft saved to {DRAFT_FILE_PATH}")

    def _load_draft_if_available(self) -> None:
        """Load a previously saved draft if the file exists, populating all UI fields.

        When no draft file is found, the app pre-loads the built-in sample data
        (2G DSM SMART 150 harness) so the user sees a fully populated example on
        first launch rather than an empty canvas.
        """
        if not os.path.exists(DRAFT_FILE_PATH):
            self._load_sample_data()
            return
        try:
            with open(DRAFT_FILE_PATH, "r", encoding="utf-8") as draft_file:
                payload = json.load(draft_file)
        except OSError as error:
            messagebox.showerror("Load failed", f"Could not read draft: {error}", parent=self)
            self._set_status("Draft load failed.")
            return
        except json.JSONDecodeError as error:
            messagebox.showerror(
                "Load failed", f"Draft file is invalid JSON: {error.msg}", parent=self,
            )
            self._set_status("Draft load failed due to invalid JSON.")
            return

        self.project_name_var.set(str(payload.get("project_name", self.project_name_var.get())))
        self.domain_var.set(str(payload.get("domain", self.domain_var.get())))
        self._refresh_voltage_options()
        self.voltage_var.set(str(payload.get("voltage_class", self.voltage_var.get())))

        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, str(payload.get("description", "")))

        # Support both new format (list of dicts) and legacy format (JSON strings)
        raw_components = payload.get("components", [])
        if not raw_components:
            legacy_json = payload.get("components_json", "")
            if legacy_json:
                try:
                    raw_components = json.loads(legacy_json)
                except json.JSONDecodeError:
                    raw_components = []
        if isinstance(raw_components, str):
            try:
                raw_components = json.loads(raw_components)
            except json.JSONDecodeError:
                raw_components = []
        self._component_data = list(raw_components) if isinstance(raw_components, list) else []

        raw_connections = payload.get("connections", [])
        if not raw_connections:
            legacy_json = payload.get("connections_json", "")
            if legacy_json:
                try:
                    raw_connections = json.loads(legacy_json)
                except json.JSONDecodeError:
                    raw_connections = []
        if isinstance(raw_connections, str):
            try:
                raw_connections = json.loads(raw_connections)
            except json.JSONDecodeError:
                raw_connections = []
        self._connection_data = list(raw_connections) if isinstance(raw_connections, list) else []

        self._refresh_component_table()
        self._refresh_connection_table()
        self._set_status("Draft loaded.")

    # ── Sample Data Pre-Load ─────────────────────────────────────────────────

    def _load_sample_data(self) -> None:
        """Populate the UI with the built-in 2G DSM SMART 150 harness example.

        This gives first-time users a realistic, fully populated project so they
        can immediately see how components, connections, and the plan tab work
        without having to manually enter data.
        """
        import copy

        self.project_name_var.set(SAMPLE_PROJECT_NAME)
        self.domain_var.set(SAMPLE_DOMAIN)
        self._refresh_voltage_options()
        self.voltage_var.set(SAMPLE_VOLTAGE)

        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, SAMPLE_DESCRIPTION)

        self._component_data = copy.deepcopy(SAMPLE_COMPONENTS)
        self._connection_data = copy.deepcopy(SAMPLE_CONNECTIONS)

        self._refresh_component_table()
        self._refresh_connection_table()

        # Auto-generate the wiring plan so the Plan tab is ready immediately
        try:
            project = self._build_project_from_tables()
            report_text = build_report_for_project(project)
            self._current_project = project
            self.output_text.delete("1.0", tk.END)
            self.output_text.insert(tk.END, report_text)
        except (ValueError, ValidationError):
            pass  # Non-critical — user can generate manually later

        # Render the visual diagram and land on the Diagram tab
        self.diagram_canvas.render_diagram(
            self._component_data, self._connection_data,
        )
        self.notebook.select(self.diagram_tab)
        self._set_status(
            "Sample project loaded — 2G DSM SMART 150 harness.  Edit freely or "
            "clear and start your own project."
        )

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _set_status(self, status_message: str) -> None:
        """Update the persistent status bar text."""
        self.status_var.set(status_message)


def main() -> None:
    """Launch the WiringWizard desktop application."""
    app = WiringWizardApp()
    app.mainloop()


if __name__ == "__main__":
    main()

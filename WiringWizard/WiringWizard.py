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

# ── Theme Palette ─────────────────────────────────────────────────────────────

COLOR_HEADER_BG = "#1e293b"
COLOR_HEADER_FG = "#f8fafc"
COLOR_ACCENT = "#2563eb"
COLOR_ACCENT_HOVER = "#1d4ed8"
COLOR_SURFACE = "#f8fafc"
COLOR_CARD_BG = "#ffffff"
COLOR_MUTED_FG = "#64748b"
COLOR_STATUS_BG = "#f1f5f9"
COLOR_EDITOR_BG = "#fafbfc"
COLOR_EDITOR_FG = "#1e293b"

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
    Configure ttk styles for a modern, card-based look across the whole app.

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

    style.configure(".", font=body_10, background=COLOR_SURFACE)
    style.configure("TFrame", background=COLOR_SURFACE)
    style.configure("TLabel", background=COLOR_SURFACE, foreground="#334155")
    style.configure("TEntry", fieldbackground=COLOR_CARD_BG)

    # Notebook tabs — wider padding, subtle rounded-look via flat relief
    style.configure(
        "TNotebook",
        background=COLOR_SURFACE,
        borderwidth=0,
        tabmargins=(8, 6, 8, 0),
    )
    style.configure(
        "TNotebook.Tab",
        font=body_10_bold,
        padding=(18, 8),
        background="#e2e8f0",
        foreground="#475569",
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", COLOR_CARD_BG)],
        foreground=[("selected", COLOR_ACCENT)],
    )

    # Card-style label frames — white background, light border
    style.configure(
        "Card.TLabelframe",
        background=COLOR_CARD_BG,
        borderwidth=1,
        relief="solid",
        bordercolor="#e2e8f0",
    )
    style.configure(
        "Card.TLabelframe.Label",
        font=body_10_bold,
        background=COLOR_CARD_BG,
        foreground="#334155",
    )

    # Interior widgets that sit on card surfaces
    style.configure("Card.TFrame", background=COLOR_CARD_BG)
    style.configure("Card.TLabel", background=COLOR_CARD_BG, foreground="#334155")
    style.configure("CardMuted.TLabel", background=COLOR_CARD_BG, foreground=COLOR_MUTED_FG)

    # Section header labels
    style.configure(
        "SectionTitle.TLabel",
        font=body_10_bold,
        background=COLOR_CARD_BG,
        foreground="#334155",
    )

    # Primary action button — bold accent
    style.configure(
        "Primary.TButton",
        font=body_10_bold,
        padding=(16, 6),
        background=COLOR_ACCENT,
        foreground="#ffffff",
    )
    style.map(
        "Primary.TButton",
        background=[("active", COLOR_ACCENT_HOVER), ("disabled", "#94a3b8")],
    )

    # Secondary button — neutral
    style.configure(
        "Secondary.TButton",
        font=body_10,
        padding=(12, 5),
        background="#e2e8f0",
        foreground="#334155",
    )
    style.map(
        "Secondary.TButton",
        background=[("active", "#cbd5e1")],
    )

    # Status bar
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

    # Treeview — modern sortable tables for component and connection lists
    style.configure(
        "Treeview",
        font=body_10,
        rowheight=30,
        fieldbackground=COLOR_CARD_BG,
        background=COLOR_CARD_BG,
        foreground="#334155",
        borderwidth=0,
    )
    style.configure(
        "Treeview.Heading",
        font=body_10_bold,
        background="#e2e8f0",
        foreground="#475569",
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
            bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        self._name_var = tk.StringVar(
            value=existing["component_name"] if is_edit else "",
        )
        name_entry = tk.Entry(
            form, textvariable=self._name_var, font=entry_font, width=32,
            relief="solid", bd=1, highlightthickness=0,
        )
        name_entry.grid(row=0, column=1, sticky="we", padx=(12, 0), pady=(0, 10))

        # Row 1 — Component type (dropdown)
        tk.Label(
            form, text="Type", font=label_font,
            bg=COLOR_CARD_BG, fg="#334155",
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
            bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=2, column=0, sticky="w", pady=(0, 10))
        self._amps_var = tk.DoubleVar(
            value=existing["current_draw_amps"] if is_edit else 1.0,
        )
        tk.Spinbox(
            form, textvariable=self._amps_var, from_=0.01, to=200, increment=0.5,
            font=entry_font, width=12, relief="solid", bd=1, highlightthickness=0,
        ).grid(row=2, column=1, sticky="w", padx=(12, 0), pady=(0, 10))

        # Row 3 — Position (editable dropdown with common suggestions)
        tk.Label(
            form, text="Position", font=label_font,
            bg=COLOR_CARD_BG, fg="#334155",
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
            bg="#e2e8f0", fg="#334155", activebackground="#cbd5e1",
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
            form, text="From", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=0, column=0, sticky="w", pady=(0, 10))
        from_default = self._make_display(existing["from_component_id"]) if is_edit else ""
        self._from_var = tk.StringVar(value=from_default)
        ttk.Combobox(
            form, textvariable=self._from_var,
            values=component_display_options, width=22,
        ).grid(row=0, column=1, sticky="we", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="Pin", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=0, column=2, sticky="w", pady=(0, 10))
        self._from_pin_var = tk.StringVar(value=existing["from_pin"] if is_edit else "")
        tk.Entry(
            form, textvariable=self._from_pin_var, font=entry_font, width=14,
            relief="solid", bd=1, highlightthickness=0,
        ).grid(row=0, column=3, sticky="we", padx=(12, 0), pady=(0, 10))

        # Row 1 — To component + To pin
        tk.Label(
            form, text="To", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=1, column=0, sticky="w", pady=(0, 10))
        to_default = self._make_display(existing["to_component_id"]) if is_edit else ""
        self._to_var = tk.StringVar(value=to_default)
        ttk.Combobox(
            form, textvariable=self._to_var,
            values=component_display_options, width=22,
        ).grid(row=1, column=1, sticky="we", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="Pin", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=1, column=2, sticky="w", pady=(0, 10))
        self._to_pin_var = tk.StringVar(value=existing["to_pin"] if is_edit else "")
        tk.Entry(
            form, textvariable=self._to_pin_var, font=entry_font, width=14,
            relief="solid", bd=1, highlightthickness=0,
        ).grid(row=1, column=3, sticky="we", padx=(12, 0), pady=(0, 10))

        # Row 2 — Current + Length
        tk.Label(
            form, text="Current (A)", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=2, column=0, sticky="w", pady=(0, 10))
        self._amps_var = tk.DoubleVar(value=existing["current_amps"] if is_edit else 1.0)
        tk.Spinbox(
            form, textvariable=self._amps_var, from_=0.01, to=200, increment=0.5,
            font=entry_font, width=10, relief="solid", bd=1, highlightthickness=0,
        ).grid(row=2, column=1, sticky="w", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="Length (ft)", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=2, column=2, sticky="w", pady=(0, 10))
        self._length_var = tk.DoubleVar(value=existing["run_length_ft"] if is_edit else 1.0)
        tk.Spinbox(
            form, textvariable=self._length_var, from_=0.1, to=500, increment=0.5,
            font=entry_font, width=10, relief="solid", bd=1, highlightthickness=0,
        ).grid(row=2, column=3, sticky="w", padx=(12, 0), pady=(0, 10))

        # Row 3 — Wire color + AWG override
        tk.Label(
            form, text="Wire Color", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
        ).grid(row=3, column=0, sticky="w", pady=(0, 10))
        self._color_var = tk.StringVar(
            value=existing.get("wire_color", "red") if is_edit else "red",
        )
        ttk.Combobox(
            form, textvariable=self._color_var,
            values=WIRE_COLORS, state="readonly", width=14,
        ).grid(row=3, column=1, sticky="w", padx=(12, 16), pady=(0, 10))

        tk.Label(
            form, text="AWG", font=label_font, bg=COLOR_CARD_BG, fg="#334155",
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
            bg="#e2e8f0", fg="#334155", activebackground="#cbd5e1",
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
        self.plan_tab = ttk.Frame(self.notebook, style="TFrame")

        self.notebook.add(self.describe_tab, text="  \U0001f916 Describe Your Project  ")
        self.notebook.add(self.build_tab, text="  \U0001f4cb Components & Wiring  ")
        self.notebook.add(self.plan_tab, text="  \U0001f4ca Wiring Plan  ")

        self._build_describe_tab()
        self._build_build_tab()
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
            background=COLOR_HEADER_BG, foreground="#94a3b8",
        ).pack(side=tk.LEFT, padx=(0, 12))

    def _build_project_bar(self) -> None:
        """Persistent bar showing project name, domain, and voltage class — always visible."""
        PROJECT_BAR_BG = "#eef2f7"
        bar = tk.Frame(self, background=PROJECT_BAR_BG, height=44)
        bar.pack(fill=tk.X, side=tk.TOP)
        bar.pack_propagate(False)

        inner = tk.Frame(bar, background=PROJECT_BAR_BG)
        inner.pack(fill=tk.BOTH, expand=True, padx=16, pady=6)

        label_font = tkfont.Font(family=self._body_font_family, size=9)
        entry_font = tkfont.Font(family=self._body_font_family, size=10)

        tk.Label(
            inner, text="Project:", font=label_font, bg=PROJECT_BAR_BG, fg="#64748b",
        ).pack(side=tk.LEFT, padx=(0, 4))
        self.project_name_var = tk.StringVar(value="My Wiring Project")
        tk.Entry(
            inner, textvariable=self.project_name_var, font=entry_font, width=24,
            relief="solid", bd=1, highlightthickness=0,
        ).pack(side=tk.LEFT, padx=(0, 20))

        tk.Label(
            inner, text="Domain:", font=label_font, bg=PROJECT_BAR_BG, fg="#64748b",
        ).pack(side=tk.LEFT, padx=(0, 4))
        self.domain_var = tk.StringVar(value="automotive")
        self.domain_combo = ttk.Combobox(
            inner, textvariable=self.domain_var,
            values=list(DOMAIN_PROFILES.keys()), state="readonly", width=14,
        )
        self.domain_combo.pack(side=tk.LEFT, padx=(0, 20))
        self.domain_combo.bind("<<ComboboxSelected>>", self._on_domain_changed)

        tk.Label(
            inner, text="Voltage:", font=label_font, bg=PROJECT_BAR_BG, fg="#64748b",
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
        self.ai_brief_text.tag_configure("placeholder", foreground="#94a3b8")
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

    # ── Tab 3: Wiring Plan ────────────────────────────────────────────────────

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
        """Load a previously saved draft if the file exists, populating all UI fields."""
        if not os.path.exists(DRAFT_FILE_PATH):
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

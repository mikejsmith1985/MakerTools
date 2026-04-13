"""
WiringWizard desktop application for building low-voltage wiring plans and harness outputs.
"""

import json
import os
import sys
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk
from typing import Any, Dict, List, Optional

# Allow running from this folder directly with "python WiringWizard.py"
APP_DIR = os.path.dirname(os.path.abspath(__file__))
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

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
from core.step_builder import build_step_list
from core.validators import ValidationError, assert_project_valid

WINDOW_TITLE = "WiringWizard - Wiring Diagram and Harness Planner"
WINDOW_SIZE = "1120x760"

DATA_DIR = os.path.join(APP_DIR, "data")
DRAFT_FILE_PATH = os.path.join(DATA_DIR, "project_draft.json")

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


class WiringWizardApp(tk.Tk):
    """Tkinter desktop shell for building, reviewing, and remapping wiring plans."""

    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry(WINDOW_SIZE)
        self.minsize(1020, 700)
        self._current_project: Optional[WiringProject] = None

        self._build_main_layout()
        self._set_default_templates()
        self._load_draft_if_available()

    def _build_main_layout(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        self.intake_tab = ttk.Frame(notebook)
        self.output_tab = ttk.Frame(notebook)
        self.remap_tab = ttk.Frame(notebook)

        notebook.add(self.intake_tab, text="1. Project Intake")
        notebook.add(self.output_tab, text="2. Generated Plan")
        notebook.add(self.remap_tab, text="3. Re-map Changes")

        self._build_intake_tab()
        self._build_output_tab()
        self._build_remap_tab()

    def _build_intake_tab(self) -> None:
        self._build_ai_assist_area()

        profile_frame = ttk.LabelFrame(self.intake_tab, text="Project Profile", padding=10)
        profile_frame.pack(fill=tk.X, padx=10, pady=(0, 6))

        self.project_name_var = tk.StringVar(value="My Wiring Project")
        self.domain_var = tk.StringVar(value="automotive")
        self.voltage_var = tk.StringVar(value="lv_12v")

        ttk.Label(profile_frame, text="Project name").grid(row=0, column=0, sticky="w")
        ttk.Entry(profile_frame, textvariable=self.project_name_var, width=40).grid(row=0, column=1, sticky="w", padx=6)

        ttk.Label(profile_frame, text="Domain").grid(row=0, column=2, sticky="w", padx=(16, 0))
        self.domain_combo = ttk.Combobox(
            profile_frame,
            textvariable=self.domain_var,
            values=list(DOMAIN_PROFILES.keys()),
            state="readonly",
            width=20,
        )
        self.domain_combo.grid(row=0, column=3, sticky="w", padx=6)
        self.domain_combo.bind("<<ComboboxSelected>>", self._on_domain_changed)

        ttk.Label(profile_frame, text="Voltage class").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.voltage_combo = ttk.Combobox(profile_frame, textvariable=self.voltage_var, state="readonly", width=20)
        self.voltage_combo.grid(row=1, column=1, sticky="w", padx=6, pady=(8, 0))

        ttk.Label(profile_frame, text="Goal / description").grid(row=2, column=0, sticky="nw", pady=(8, 0))
        self.description_text = scrolledtext.ScrolledText(profile_frame, width=92, height=3, wrap=tk.WORD)
        self.description_text.grid(row=2, column=1, columnspan=3, sticky="we", padx=6, pady=(8, 0))

        payload_frame = ttk.LabelFrame(self.intake_tab, text="Components and Connections (JSON)", padding=10)
        payload_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        payload_frame.columnconfigure(0, weight=1)
        payload_frame.columnconfigure(1, weight=1)
        payload_frame.rowconfigure(1, weight=1)

        ttk.Label(payload_frame, text="Components").grid(row=0, column=0, sticky="w")
        ttk.Label(payload_frame, text="Connections").grid(row=0, column=1, sticky="w")

        self.components_text = scrolledtext.ScrolledText(payload_frame, wrap=tk.NONE)
        self.components_text.grid(row=1, column=0, sticky="nsew", padx=(0, 6), pady=(4, 0))

        self.connections_text = scrolledtext.ScrolledText(payload_frame, wrap=tk.NONE)
        self.connections_text.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(4, 0))

        action_frame = ttk.Frame(self.intake_tab, padding=(10, 6))
        action_frame.pack(fill=tk.X)
        ttk.Button(action_frame, text="Generate Wiring Plan", command=self._on_generate_report).pack(side=tk.LEFT)
        ttk.Button(action_frame, text="Save Draft", command=self._save_draft).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Button(action_frame, text="Load Draft", command=self._load_draft_if_available).pack(side=tk.LEFT, padx=(8, 0))

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(action_frame, textvariable=self.status_var).pack(side=tk.RIGHT)
        self._refresh_voltage_options()

    def _build_ai_assist_area(self) -> None:
        """
        Build the AI Assist panel at the top of the intake tab.

        The user enters a plain-English project brief and clicks "AI Draft from Brief"
        to populate the project name, description, components, and connections fields.
        When no API token is set the deterministic fallback parser runs automatically.
        """
        ai_assist_frame = ttk.LabelFrame(self.intake_tab, text="AI Assist", padding=10)
        ai_assist_frame.pack(fill=tk.X, padx=10, pady=(10, 0))
        ai_assist_frame.columnconfigure(1, weight=1)

        self.ai_token_var = tk.StringVar(value=get_saved_gui_api_token() or "")

        ttk.Label(ai_assist_frame, text="AI token").grid(
            row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 4)
        )
        ai_token_entry = ttk.Entry(ai_assist_frame, textvariable=self.ai_token_var, show="*", width=64)
        ai_token_entry.grid(row=0, column=1, sticky="w", pady=(0, 4))

        ai_token_button_row = ttk.Frame(ai_assist_frame)
        ai_token_button_row.grid(row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 4))
        ttk.Button(
            ai_token_button_row,
            text="Save Token",
            command=self._on_save_ai_token,
        ).pack(side=tk.LEFT)
        ttk.Button(
            ai_token_button_row,
            text="Clear Token",
            command=self._on_clear_ai_token,
        ).pack(side=tk.LEFT, padx=(6, 0))

        ttk.Label(ai_assist_frame, text="Project brief").grid(
            row=1, column=0, sticky="nw", padx=(0, 8), pady=(0, 4)
        )
        self.ai_brief_text = scrolledtext.ScrolledText(
            ai_assist_frame, width=90, height=4, wrap=tk.WORD
        )
        self.ai_brief_text.grid(row=1, column=1, columnspan=2, sticky="we", pady=(0, 4))

        ai_button_row = ttk.Frame(ai_assist_frame)
        ai_button_row.grid(row=2, column=0, columnspan=3, sticky="w")

        ttk.Button(
            ai_button_row,
            text="AI Draft from Brief",
            command=self._on_ai_draft_from_brief,
        ).pack(side=tk.LEFT)

        initial_ai_status = (
            "Token loaded for this app."
            if self.ai_token_var.get().strip()
            else "No saved token configured."
        )
        self.ai_status_var = tk.StringVar(value=initial_ai_status)
        ttk.Label(ai_button_row, textvariable=self.ai_status_var, foreground="gray").pack(
            side=tk.LEFT, padx=(12, 0)
        )

    def _on_ai_draft_from_brief(self) -> None:
        """
        Handle the "AI Draft from Brief" button click.

        Reads the free-text brief, calls draft_project_from_brief, and populates
        the project name, description, components, and connections fields.
        Displays a status message indicating whether the AI or fallback parser was used.
        """
        brief_text = self.ai_brief_text.get("1.0", tk.END).strip()
        if not brief_text:
            messagebox.showwarning(
                "No brief entered",
                "Please enter a project brief before drafting.",
            )
            return

        self._set_status("Generating draft…")
        self.ai_status_var.set("Working…")
        self.update_idletasks()

        try:
            draft_payload = draft_project_from_brief(
                brief_text=brief_text,
                requested_project_name=self.project_name_var.get().strip(),
                api_token_override=self.ai_token_var.get().strip() or None,
            )
        except Exception as draft_error:
            messagebox.showerror("Draft failed", f"Could not generate draft: {draft_error}")
            self._set_status("Draft failed.")
            self.ai_status_var.set("")
            return

        self._apply_ai_draft_payload(draft_payload)

        if draft_payload.get("used_ai"):
            self.ai_status_var.set("✓ AI draft applied.")
            self._set_status("AI draft populated. Review components and connections before generating plan.")
        else:
            self.ai_status_var.set("Fallback parser used (add/save token in AI Assist or use env token).")
            self._set_status("Fallback draft populated. Review and adjust before generating plan.")

    def _on_save_ai_token(self) -> None:
        """Persist the AI token entered in the AI Assist panel."""
        token_value = self.ai_token_var.get().strip()
        if not token_value:
            messagebox.showwarning("Missing token", "Enter a token before saving.")
            return
        try:
            save_gui_api_token(token_value)
        except OSError as write_error:
            messagebox.showerror("Token save failed", f"Could not save token: {write_error}")
            self._set_status("AI token save failed.")
            return

        self.ai_status_var.set("Token saved for this app.")
        self._set_status("AI token saved.")

    def _on_clear_ai_token(self) -> None:
        """Clear the saved AI token and UI token field."""
        try:
            clear_saved_gui_api_token()
        except OSError as write_error:
            messagebox.showerror("Token clear failed", f"Could not clear token: {write_error}")
            self._set_status("AI token clear failed.")
            return

        self.ai_token_var.set("")
        self.ai_status_var.set("Token cleared.")
        self._set_status("AI token cleared.")

    def _apply_ai_draft_payload(self, draft_payload: Dict[str, Any]) -> None:
        """
        Populate intake fields from a draft payload returned by draft_project_from_brief.

        Only overwrites the project name when the draft provides a non-empty name,
        preserving any name the user already typed. Components and connections are
        always replaced with pretty-printed JSON.

        Args:
            draft_payload: Dict as returned by draft_project_from_brief.
        """
        draft_project_name = str(draft_payload.get("project_name", "")).strip()
        if draft_project_name:
            self.project_name_var.set(draft_project_name)

        draft_description = str(draft_payload.get("description", "")).strip()
        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, draft_description)

        draft_components = draft_payload.get("components", [])
        self.components_text.delete("1.0", tk.END)
        self.components_text.insert(tk.END, json.dumps(draft_components, indent=2))

        draft_connections = draft_payload.get("connections", [])
        self.connections_text.delete("1.0", tk.END)
        self.connections_text.insert(tk.END, json.dumps(draft_connections, indent=2))

    def _build_output_tab(self) -> None:
        output_frame = ttk.LabelFrame(self.output_tab, text="Generated Wiring Report", padding=10)
        output_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.output_text = scrolledtext.ScrolledText(output_frame, wrap=tk.NONE)
        self.output_text.pack(fill=tk.BOTH, expand=True)

    def _build_remap_tab(self) -> None:
        remap_instructions = ttk.Label(
            self.remap_tab,
            text=(
                "Use change requests to re-map the harness. Each item must have operation + payload.\n"
                "Supported operations: add_component, update_component, remove_component, "
                "add_connection, update_connection, remove_connection."
            ),
            justify=tk.LEFT,
        )
        remap_instructions.pack(anchor="w", padx=10, pady=(10, 4))

        self.remap_text = scrolledtext.ScrolledText(self.remap_tab, wrap=tk.NONE)
        self.remap_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=4)

        remap_action_frame = ttk.Frame(self.remap_tab, padding=(10, 6))
        remap_action_frame.pack(fill=tk.X)
        ttk.Button(remap_action_frame, text="Apply Re-map Changes", command=self._on_apply_remap).pack(side=tk.LEFT)

    def _set_default_templates(self) -> None:
        self.components_text.delete("1.0", tk.END)
        self.components_text.insert(tk.END, DEFAULT_COMPONENTS_TEMPLATE)
        self.connections_text.delete("1.0", tk.END)
        self.connections_text.insert(tk.END, DEFAULT_CONNECTIONS_TEMPLATE)
        self.remap_text.delete("1.0", tk.END)
        self.remap_text.insert(tk.END, DEFAULT_REMAP_TEMPLATE)

    def _on_domain_changed(self, _event: Optional[Any] = None) -> None:
        self._refresh_voltage_options()

    def _refresh_voltage_options(self) -> None:
        selected_domain = self.domain_var.get().strip()
        profile = get_domain_profile(selected_domain)
        allowed_classes = list(profile["allowed_voltage_classes"])
        self.voltage_combo["values"] = allowed_classes
        if self.voltage_var.get() not in allowed_classes:
            self.voltage_var.set(allowed_classes[0])

    def _on_generate_report(self) -> None:
        try:
            project = self._build_project_from_ui()
            report_text = build_report_for_project(project)
        except (ValueError, ValidationError) as validation_error:
            messagebox.showerror("Cannot generate plan", str(validation_error))
            self._set_status("Generation failed. Fix errors and retry.")
            return

        self._current_project = project
        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, report_text)
        self._set_status("Wiring plan generated.")

    def _on_apply_remap(self) -> None:
        try:
            if self._current_project is None:
                self._current_project = self._build_project_from_ui()
            change_requests = json.loads(self.remap_text.get("1.0", tk.END).strip() or "[]")
            if not isinstance(change_requests, list):
                raise ValueError("Re-map changes JSON must be a JSON array.")
            self._current_project = apply_changes(self._current_project, change_requests)
            updated_report = build_report_for_project(self._current_project)
        except json.JSONDecodeError as parse_error:
            messagebox.showerror("Invalid JSON", f"Re-map JSON is invalid: {parse_error.msg}")
            self._set_status("Re-map failed due to invalid JSON.")
            return
        except (ValueError, ValidationError) as remap_error:
            messagebox.showerror("Cannot apply re-map", str(remap_error))
            self._set_status("Re-map failed. Check change payload.")
            return

        self.output_text.delete("1.0", tk.END)
        self.output_text.insert(tk.END, updated_report)
        self._set_status("Re-map changes applied and plan regenerated.")

    def _build_project_from_ui(self) -> WiringProject:
        components_json_text = self.components_text.get("1.0", tk.END)
        connections_json_text = self.connections_text.get("1.0", tk.END)
        description_text = self.description_text.get("1.0", tk.END)
        return create_project_from_input_strings(
            project_name=self.project_name_var.get(),
            domain=self.domain_var.get(),
            voltage_class=self.voltage_var.get(),
            description=description_text,
            components_json_text=components_json_text,
            connections_json_text=connections_json_text,
        )

    def _save_draft(self) -> None:
        try:
            os.makedirs(DATA_DIR, exist_ok=True)
            with open(DRAFT_FILE_PATH, "w", encoding="utf-8") as draft_file:
                json.dump(self._build_draft_payload(), draft_file, indent=2)
        except OSError as write_error:
            messagebox.showerror("Save failed", f"Could not save draft: {write_error}")
            self._set_status("Draft save failed.")
            return

        self._set_status(f"Draft saved to {DRAFT_FILE_PATH}")

    def _load_draft_if_available(self) -> None:
        if not os.path.exists(DRAFT_FILE_PATH):
            return
        try:
            with open(DRAFT_FILE_PATH, "r", encoding="utf-8") as draft_file:
                payload = json.load(draft_file)
        except OSError as read_error:
            messagebox.showerror("Load failed", f"Could not read draft: {read_error}")
            self._set_status("Draft load failed.")
            return
        except json.JSONDecodeError as parse_error:
            messagebox.showerror("Load failed", f"Draft file is invalid JSON: {parse_error.msg}")
            self._set_status("Draft load failed due to invalid JSON.")
            return

        self._apply_draft_payload(payload)
        self._set_status("Draft loaded.")

    def _build_draft_payload(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name_var.get(),
            "domain": self.domain_var.get(),
            "voltage_class": self.voltage_var.get(),
            "description": self.description_text.get("1.0", tk.END).strip(),
            "components_json": self.components_text.get("1.0", tk.END).strip(),
            "connections_json": self.connections_text.get("1.0", tk.END).strip(),
            "remap_json": self.remap_text.get("1.0", tk.END).strip(),
        }

    def _apply_draft_payload(self, payload: Dict[str, Any]) -> None:
        self.project_name_var.set(str(payload.get("project_name", self.project_name_var.get())))
        self.domain_var.set(str(payload.get("domain", self.domain_var.get())))
        self._refresh_voltage_options()
        self.voltage_var.set(str(payload.get("voltage_class", self.voltage_var.get())))

        self.description_text.delete("1.0", tk.END)
        self.description_text.insert(tk.END, str(payload.get("description", "")))

        self.components_text.delete("1.0", tk.END)
        self.components_text.insert(tk.END, str(payload.get("components_json", DEFAULT_COMPONENTS_TEMPLATE)))

        self.connections_text.delete("1.0", tk.END)
        self.connections_text.insert(tk.END, str(payload.get("connections_json", DEFAULT_CONNECTIONS_TEMPLATE)))

        self.remap_text.delete("1.0", tk.END)
        self.remap_text.insert(tk.END, str(payload.get("remap_json", DEFAULT_REMAP_TEMPLATE)))

    def _set_status(self, status_message: str) -> None:
        self.status_var.set(status_message)


def main() -> None:
    """Launch the WiringWizard desktop application."""
    app = WiringWizardApp()
    app.mainloop()


if __name__ == "__main__":
    main()


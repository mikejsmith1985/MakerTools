"""
AI-assisted intake module for WiringWizard — converts a free-text project brief into a
structured component/connection draft suitable for populating the WiringWizard UI.
"""

import json
import os
import re
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from core.runtime_paths import resolve_runtime_app_dir

# ── API Constants ──────────────────────────────────────────────────────────────

AI_API_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
AI_MODEL = "gpt-4o-mini"
AI_MAX_TOKENS = 2048

# Lower temperature keeps wiring output structured and repeatable.
AI_TEMPERATURE = 0.2

# ── Token Resolution ──────────────────────────────────────────────────────────

# Env-var names checked in priority order (first non-empty wins).
TOKEN_ENV_VARS: Tuple[str, ...] = (
    "WIRINGWIZARD_GITHUB_TOKEN",
    "GITHUB_MODELS_TOKEN",
    "GITHUB_AI_TOKEN",
)

# Use the shared runtime-path resolver so data paths survive PyInstaller freezing.
# ai_intake.py lives in core/, so source mode must step up one directory.
APP_DIR = resolve_runtime_app_dir(__file__, source_parent_levels=1)
DATA_DIR = os.path.join(APP_DIR, "data")
AI_SETTINGS_FILE_PATH = os.path.join(DATA_DIR, "ai_settings.json")


def resolve_api_token() -> Optional[str]:
    """
    Resolve the GitHub Models API bearer token from environment variables.

    Checks WIRINGWIZARD_GITHUB_TOKEN, GITHUB_MODELS_TOKEN, and GITHUB_AI_TOKEN
    in that order, returning the first non-empty value found.

    Returns:
        Token string if one is set, otherwise None.
    """
    for env_var_name in TOKEN_ENV_VARS:
        token_value = os.environ.get(env_var_name, "").strip()
        if token_value:
            return token_value
    return None


def get_saved_gui_api_token() -> Optional[str]:
    """
    Read the AI token saved by the WiringWizard GUI settings panel.

    Returns:
        Saved token string if present and non-empty, else None.
    """
    ai_settings = _load_ai_settings()
    token_value = str(ai_settings.get("api_token", "")).strip()
    return token_value if token_value else None


def save_gui_api_token(api_token: str) -> None:
    """
    Persist a GUI-entered API token to WiringWizard data settings.

    Args:
        api_token: Raw token string entered by the user.
    """
    normalized_token = api_token.strip()
    ai_settings = _load_ai_settings()
    ai_settings["api_token"] = normalized_token
    _save_ai_settings(ai_settings)


def clear_saved_gui_api_token() -> None:
    """Remove any GUI-saved API token from WiringWizard data settings."""
    ai_settings = _load_ai_settings()
    if "api_token" in ai_settings:
        del ai_settings["api_token"]
    _save_ai_settings(ai_settings)


def _load_ai_settings() -> Dict[str, Any]:
    """
    Load AI settings JSON from disk.

    Returns:
        Parsed settings dictionary, or {} when file is missing/invalid.
    """
    if not os.path.exists(AI_SETTINGS_FILE_PATH):
        return {}
    try:
        with open(AI_SETTINGS_FILE_PATH, "r", encoding="utf-8") as settings_file:
            loaded_settings = json.load(settings_file)
        if isinstance(loaded_settings, dict):
            return loaded_settings
    except (OSError, json.JSONDecodeError):
        return {}
    return {}


def _save_ai_settings(settings_payload: Dict[str, Any]) -> None:
    """
    Save AI settings JSON to disk.

    Args:
        settings_payload: Serializable dictionary of settings to persist.
    """
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(AI_SETTINGS_FILE_PATH, "w", encoding="utf-8") as settings_file:
        json.dump(settings_payload, settings_file, indent=2)


# ── Low-Voltage Component Keyword Map ────────────────────────────────────────

# Each entry: (regex_pattern, component_type, default_current_amps)
# The fallback parser scans the brief for these patterns and builds component stubs.
COMPONENT_KEYWORD_MAP: List[Tuple[str, str, float]] = [
    (r"\b(battery|batteries|lipo|li-ion|liion|lead.acid|agm|pb)\b", "battery", 60.0),
    (r"\b(power\s*supply|psu|bench\s*supply|wall\s*wart|adapter|charger)\b", "power_supply", 10.0),
    (r"\b(arduino|esp32|esp8266|esp-32|nano|uno|mega|raspberry\s*pi|pi\s*zero|rpi|microcontroller|mcu|teensy|pico)\b", "microcontroller", 0.5),
    (r"\b(ecu|engine\s*control\s*unit)\b", "ecu", 8.0),
    (r"\b(relay)\b", "relay", 0.15),
    (r"\b(fuse|fusebox|fuse\s*block|fuse\s*holder)\b", "fuse", 0.0),
    (r"\b(neopixel|ws2812|addressable\s*led|led\s*strip)\b", "led_load", 3.0),
    (r"\b(led|indicator\s*light)\b", "led_load", 0.05),
    (r"\b(headlight|taillight|lamp|bulb|light(?!\s*strip))\b", "light", 5.0),
    (r"\b(stepper\s*motor|stepper)\b", "stepper", 2.0),
    (r"\b(dc\s*motor|brushless|motor(?!\s*driver))\b", "motor", 5.0),
    (r"\b(servo)\b", "servo", 1.0),
    (r"\b(cooling\s*fan|fan|blower)\b", "fan", 0.5),
    (r"\b(water\s*pump|fuel\s*pump|pump)\b", "pump", 5.0),
    (r"\b(temp\s*sensor|ultrasonic|hall\s*effect|proximity\s*sensor|sensor)\b", "sensor", 0.02),
    (r"\b(toggle|pushbutton|push\s*button|button|switch)\b", "switch", 0.0),
    (r"\b(lcd|oled|tft|display|screen)\b", "display", 0.3),
    (r"\b(buzzer|piezo|alarm)\b", "buzzer", 0.05),
    (r"\b(solenoid)\b", "solenoid", 2.0),
    (r"\b(motor\s*driver|h.bridge|drv8825|a4988|l298)\b", "motor_driver", 1.5),
]

# Component types that supply power to the rest of the circuit.
POWER_SOURCE_TYPES = frozenset({"battery", "power_supply"})

# Component types that consume power (candidates for wiring from a source).
POWER_LOAD_TYPES = frozenset({
    "microcontroller", "ecu", "relay", "led_load", "light", "motor", "servo",
    "fan", "pump", "sensor", "display", "buzzer", "solenoid", "stepper", "motor_driver",
})

# ── AI Prompt Templates ───────────────────────────────────────────────────────

_AI_SYSTEM_PROMPT = (
    "You are an expert electronics and wiring engineer assistant for low-voltage maker projects. "
    "Given a free-text project brief, you produce a structured wiring project draft as JSON. "
    "Your output MUST be a single valid JSON object and nothing else — no markdown fences, no prose. "
    "Use conservative current values and realistic wire lengths for small maker projects. "
    "Component IDs must be simple snake_case identifiers (e.g. battery1, arduino1). "
    "Wire connections should only run from power-supplying components to consuming components."
)

_AI_USER_PROMPT_TEMPLATE = (
    "Convert this project brief into a WiringWizard JSON draft.\n\n"
    "BRIEF:\n{brief_text}\n\n"
    "Return a JSON object with EXACTLY these fields:\n"
    "{{\n"
    '  "project_name": "string — short human-readable project name",\n'
    '  "description": "string — one to two sentence summary of the project",\n'
    '  "components": [\n'
    "    {{\n"
    '      "component_id": "snake_case_id",\n'
    '      "component_name": "Human-Readable Name",\n'
    '      "component_type": "battery|power_supply|microcontroller|ecu|relay|fuse|'
    'led_load|light|motor|servo|fan|pump|sensor|switch|display|buzzer|solenoid|stepper|motor_driver",\n'
    '      "current_draw_amps": number,\n'
    '      "position_label": "location or TBD"\n'
    "    }}\n"
    "  ],\n"
    '  "connections": [\n'
    "    {{\n"
    '      "connection_id": "conn_001",\n'
    '      "from_component_id": "source_id",\n'
    '      "from_pin": "pin label",\n'
    '      "to_component_id": "load_id",\n'
    '      "to_pin": "pin label",\n'
    '      "current_amps": number,\n'
    '      "run_length_ft": number,\n'
    '      "wire_color": "color"\n'
    "    }}\n"
    "  ],\n"
    '  "notes": ["string warning or tip", "..."]\n'
    "}}\n\n"
    "Component IDs in connections MUST exactly match component_id values listed above."
)


# ── Network Layer ─────────────────────────────────────────────────────────────

def _call_github_models_api(
    system_prompt: str,
    user_prompt: str,
    api_token: str,
) -> Optional[str]:
    """
    Send a chat-completion request to the GitHub Models API.

    Returns the assistant's raw text response, or None if the request fails.
    Network and HTTP errors are caught here so callers can fall back gracefully;
    only programming errors (bad arguments) would propagate as exceptions.

    Args:
        system_prompt: The system role instruction for the model.
        user_prompt:   The user turn describing the task.
        api_token:     GitHub Models bearer token.

    Returns:
        Raw model response string, or None on failure.
    """
    encoded_request_body = json.dumps({
        "model": AI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "max_tokens": AI_MAX_TOKENS,
        "temperature": AI_TEMPERATURE,
    }).encode("utf-8")

    http_request = urllib.request.Request(
        AI_API_ENDPOINT,
        data=encoded_request_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_token}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(http_request, timeout=60) as response:
            response_body = json.loads(response.read().decode("utf-8"))
            choices = response_body.get("choices", [])
            if choices:
                return choices[0].get("message", {}).get("content", "")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        # Network or HTTP failure — the caller falls back to deterministic parser.
        return None

    return None


def _extract_json_from_response(raw_text: str) -> Optional[Dict[str, Any]]:
    """
    Extract a JSON object from an AI response that may include markdown code fences.

    Tries three strategies in order:
      1. Strip markdown fences and parse directly.
      2. Find the outermost { } block and parse it.
      3. Return None if all strategies fail.

    Args:
        raw_text: Raw text returned by the AI model.

    Returns:
        Parsed dict, or None if no valid JSON object can be found.
    """
    if not raw_text:
        return None

    cleaned_text = raw_text.strip()

    # Strategy 1: strip markdown fences (```json ... ``` or ``` ... ```)
    fence_match = re.search(r"```(?:json)?\s*([\s\S]+?)\s*```", cleaned_text)
    if fence_match:
        cleaned_text = fence_match.group(1).strip()

    try:
        parsed = json.loads(cleaned_text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # Strategy 2: locate the outermost { ... } block
    object_start_index = cleaned_text.find("{")
    if object_start_index >= 0:
        brace_depth = 0
        for char_index, char in enumerate(cleaned_text[object_start_index:], start=object_start_index):
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    try:
                        candidate = json.loads(cleaned_text[object_start_index: char_index + 1])
                        if isinstance(candidate, dict):
                            return candidate
                    except json.JSONDecodeError:
                        break

    return None


# ── Deterministic Fallback Parser ─────────────────────────────────────────────

def _slugify_to_component_id(label_text: str) -> str:
    """
    Convert a human-readable label into a safe snake_case component ID.

    Example: "LED Load" → "led_load"
    """
    slug = re.sub(r"[^a-z0-9]+", "_", label_text.lower().strip())
    return slug.strip("_") or "component"


def _infer_components_from_brief(brief_text: str) -> List[Dict[str, Any]]:
    """
    Scan the brief for low-voltage component keywords and build a component list.

    Each matched keyword type produces one component stub. Power-source types
    are collected first so they appear at the top of the list.

    A minimal fallback (power_supply + microcontroller) is guaranteed if no
    matching keywords are found, so the UI always has something to work with.

    Args:
        brief_text: Free-text project description.

    Returns:
        List of component dicts compatible with WiringWizard's Component schema.
    """
    lowered_brief = brief_text.lower()
    discovered_components: List[Dict[str, Any]] = []
    seen_component_types: set = set()

    for keyword_pattern, component_type, default_current_amps in COMPONENT_KEYWORD_MAP:
        if not re.search(keyword_pattern, lowered_brief, re.IGNORECASE):
            continue
        # One component per type in fallback mode keeps the output manageable.
        if component_type in seen_component_types:
            continue
        seen_component_types.add(component_type)

        component_id = f"{_slugify_to_component_id(component_type)}1"
        discovered_components.append({
            "component_id": component_id,
            "component_name": component_type.replace("_", " ").title(),
            "component_type": component_type,
            "current_draw_amps": default_current_amps,
            "position_label": "TBD",
        })

    has_power_source = any(
        comp["component_type"] in POWER_SOURCE_TYPES
        for comp in discovered_components
    )
    has_load = any(
        comp["component_type"] in POWER_LOAD_TYPES
        for comp in discovered_components
    )

    # Guarantee at least one power source and one load so connections can be built.
    if not has_power_source:
        discovered_components.insert(0, {
            "component_id": "power_supply1",
            "component_name": "Power Supply",
            "component_type": "power_supply",
            "current_draw_amps": 5.0,
            "position_label": "TBD",
        })
    if not has_load:
        discovered_components.append({
            "component_id": "microcontroller1",
            "component_name": "Microcontroller",
            "component_type": "microcontroller",
            "current_draw_amps": 0.5,
            "position_label": "TBD",
        })

    return discovered_components


def _build_fallback_connections(components: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Generate a starter set of positive-supply connections from the primary power
    source to each load component.

    Wire color follows common maker convention: red for +V supply runs.
    Ground return connections are noted but not generated to keep the starter
    set readable — the user is expected to add them.

    Args:
        components: List of component dicts as produced by _infer_components_from_brief.

    Returns:
        List of connection dicts compatible with WiringWizard's Connection schema.
    """
    power_source_components = [
        comp for comp in components if comp["component_type"] in POWER_SOURCE_TYPES
    ]
    load_components = [
        comp for comp in components if comp["component_type"] in POWER_LOAD_TYPES
    ]

    if not power_source_components or not load_components:
        return []

    # Route all starter connections from the first (primary) power source.
    primary_source = power_source_components[0]
    generated_connections: List[Dict[str, Any]] = []

    for connection_index, load_component in enumerate(load_components, start=1):
        generated_connections.append({
            "connection_id": f"conn_{connection_index:03d}",
            "from_component_id": primary_source["component_id"],
            "from_pin": "+V",
            "to_component_id": load_component["component_id"],
            "to_pin": "VCC",
            "current_amps": load_component.get("current_draw_amps", 0.5),
            "run_length_ft": 3.0,
            "wire_color": "red",
        })

    return generated_connections


def _run_fallback_parser(brief_text: str, requested_project_name: str) -> Dict[str, Any]:
    """
    Build a draft payload using only keyword inference — no AI required.

    Used when no API token is configured or when the AI call/parse fails.
    The result is intentionally conservative: it gives the user a plausible
    starting point that must be reviewed before any actual wiring.

    Args:
        brief_text:             Free-text brief (may be empty).
        requested_project_name: User-supplied project name (may be empty).

    Returns:
        Structured draft payload dict with used_ai set to False.
    """
    inferred_components = _infer_components_from_brief(brief_text)
    starter_connections = _build_fallback_connections(inferred_components)

    resolved_project_name = (
        requested_project_name.strip()
        if requested_project_name.strip()
        else "Wiring Project"
    )
    resolved_description = brief_text[:200].strip() if brief_text.strip() else "Low-voltage wiring project."

    return {
        "project_name": resolved_project_name,
        "description": resolved_description,
        "components": inferred_components,
        "connections": starter_connections,
        "notes": [
            "Generated by fallback keyword parser — AI was not used.",
            "Review all component types, current ratings, and positions before wiring.",
            "Add ground return connections as needed for each load.",
            "Verify pinouts and polarity for every component before connecting.",
        ],
        "used_ai": False,
    }


# ── AI Draft Attempt ──────────────────────────────────────────────────────────

def _attempt_ai_draft(
    brief_text: str,
    requested_project_name: str,
    api_token: str,
) -> Optional[Dict[str, Any]]:
    """
    Try to produce a structured draft using the GitHub Models API.

    Returns a valid payload dict on success, or None if the API call fails or
    the model returns a response that cannot be parsed into the required shape.
    The caller should fall back to _run_fallback_parser on a None return.

    Args:
        brief_text:             Free-text project brief (pre-validated as non-empty).
        requested_project_name: User-supplied project name override (may be empty).
        api_token:              Resolved GitHub Models bearer token.

    Returns:
        Payload dict with used_ai=True, or None on any failure.
    """
    user_prompt = _AI_USER_PROMPT_TEMPLATE.format(brief_text=brief_text[:3000])
    raw_response = _call_github_models_api(_AI_SYSTEM_PROMPT, user_prompt, api_token)

    if not raw_response:
        return None

    parsed_response = _extract_json_from_response(raw_response)
    if not isinstance(parsed_response, dict):
        return None

    # Both lists are required — reject partial responses.
    has_valid_components = isinstance(parsed_response.get("components"), list)
    has_valid_connections = isinstance(parsed_response.get("connections"), list)
    if not has_valid_components or not has_valid_connections:
        return None

    # User-supplied name takes precedence over the AI-suggested name.
    resolved_project_name = (
        requested_project_name.strip()
        or str(parsed_response.get("project_name", "Wiring Project")).strip()
    )

    raw_notes = parsed_response.get("notes", [])
    notes_list: List[str] = raw_notes if isinstance(raw_notes, list) else ([str(raw_notes)] if raw_notes else [])
    # Mandatory safety note appended to every AI-generated draft.
    notes_list.append(
        "AI-generated draft — always verify pinouts, polarities, and critical wiring details before use."
    )

    return {
        "project_name": resolved_project_name,
        "description": str(parsed_response.get("description", brief_text[:200])).strip(),
        "components": parsed_response["components"],
        "connections": parsed_response["connections"],
        "notes": notes_list,
        "used_ai": True,
    }


# ── Public API ────────────────────────────────────────────────────────────────

def draft_project_from_brief(
    brief_text: str,
    requested_project_name: str = "",
    api_token_override: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Convert a free-text project brief into a structured WiringWizard draft payload.

    Attempts to call the GitHub Models API when a token is available from:
      - api_token_override (GUI-provided token)
      - saved GUI token in WiringWizard data settings
      - environment variables (WIRINGWIZARD_GITHUB_TOKEN, GITHUB_MODELS_TOKEN, GITHUB_AI_TOKEN)
    Falls back to a deterministic keyword parser when AI is unavailable or fails.

    The returned payload is suitable for directly populating the WiringWizard UI
    fields — project name, description, components JSON, and connections JSON.
    Users must review and adjust component IDs, pinouts, and wire lengths before
    generating a final wiring plan.

    Args:
        brief_text:             Free-text description of the wiring project.
        requested_project_name: Optional project name. If non-empty, overrides the
                                name inferred by the AI or fallback parser.
        api_token_override:     Optional token supplied by the GUI.
                                When provided, this token is used before saved/env tokens.

    Returns:
        Dict with keys:
          project_name (str)    — short human-readable name
          description  (str)    — one-to-two sentence summary
          components   (list)   — list of component dicts
          connections  (list)   — list of connection dicts
          notes        (list)   — list of warning/tip strings
          used_ai      (bool)   — True if the AI produced the result
    """
    if not brief_text.strip():
        return _run_fallback_parser("", requested_project_name)

    resolved_override_token = (api_token_override or "").strip()
    api_token = resolved_override_token or get_saved_gui_api_token() or resolve_api_token()
    if api_token:
        ai_draft_result = _attempt_ai_draft(brief_text, requested_project_name, api_token)
        if ai_draft_result is not None:
            return ai_draft_result

    # AI unavailable, token missing, or AI returned an unusable response.
    return _run_fallback_parser(brief_text, requested_project_name)

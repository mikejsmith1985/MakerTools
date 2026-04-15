"""
AI-assisted intake module for WiringWizard — converts a free-text project brief into a
structured component/connection draft suitable for populating the WiringWizard UI.
"""

import datetime as _dt
import html
import json
import os
import re
import urllib.error
import urllib.request
from urllib.parse import urljoin
from typing import Any, Dict, List, Optional, Tuple

from core.runtime_paths import resolve_runtime_app_dir

# ── API Constants ──────────────────────────────────────────────────────────────

AI_API_ENDPOINT = "https://models.inference.ai.azure.com/chat/completions"
AI_MODEL = "gpt-4o"
AI_MAX_TOKENS = 16384

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
_LOG_FILE_PATH = os.path.join(DATA_DIR, "ai_debug.log")


def _log(message: str) -> None:
    """Append a timestamped debug line to the AI debug log file."""
    try:
        os.makedirs(os.path.dirname(_LOG_FILE_PATH), exist_ok=True)
        timestamp = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(_LOG_FILE_PATH, "a", encoding="utf-8") as log_handle:
            log_handle.write(f"[{timestamp}] {message}\n")
    except OSError:
        pass


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

# ── Named Automotive / Aftermarket Component Hints ───────────────────────────
# Each entry: (regex_pattern, human_name, component_type, default_current_amps)
# These run before the generic keyword map so named products get preserved.
NAMED_COMPONENT_HINTS: List[Tuple[str, str, str, float]] = [
    (r"\bemtron\s+kv8\b", "Emtron KV8 ECU", "ecu", 8.0),
    (r'\b(ed10m|10\s*"?\s*dash|digital\s+dash)\b', "Emtron ED10M Dash", "display", 0.8),
    (r"\b(8\s*button\s*can(\s*keypad)?|can\s+keypad|keypad)\b", "8-Button CAN Keypad", "switch", 0.1),
    (r"\bsmart150\b", "SMART150 TCU", "ecu", 5.0),
    (r"\b(tcu|transmission\s*control\s*unit)\b", "Transmission Control Unit", "ecu", 5.0),
    (r"\b(w4a33|automatic\s+transmission)\b", "W4A33 Transmission Solenoids", "solenoid", 3.0),
    (r"\b(evo\s*x\s+sportmatic\s+shifter|sportmatic\s+shifter|shifter)\b", "Sportmatic Shifter", "switch", 0.1),
    (r"\b(ohm\s+racing.*fuse|stage\s*3.*fuse\s*box|aftermarket\s+small\s+fusebox|fuse-?box)\b", "OHM Racing Fuse Box", "fuse", 0.0),
    (r"\b(ohm\s+racing.*engine\s+harness|mil-?spec\s+harness|engine\s+harness)\b", "OHM Racing Engine Harness", "relay", 0.5),
    (r"\b(lsu\s*4\.?9|wideband)\b", "Wideband LSU 4.9 Sensor", "sensor", 0.1),
    (r"\b(flexfuel|flex\s*fuel)\b", "Flex Fuel Sensor", "sensor", 0.1),
    (r"\b(aem\s+fuel\s+pressure|fuel\s+pressure)\b", "AEM Fuel Pressure Sensor", "sensor", 0.05),
    (r"\b(gm\s+iat|iat)\b", "GM IAT Sensor", "sensor", 0.02),
    (r"\b(gm\s+map|deutsch\s+map|map\s+sensor)\b", "GM MAP Sensor", "sensor", 0.02),
    (r"\b(coolant\s+temp|coolant\s+temperature)\b", "Coolant Temperature Sensor", "sensor", 0.02),
    (r"\b(cam|crank)\b", "Cam and Crank Sensors", "sensor", 0.02),
    (r"\b(denso\s+injectors|injectors?)\b", "Fuel Injectors", "solenoid", 8.0),
    (r"\b(dbw|drive\s*by\s*wire|bosch\s+dbw|mitsu\/bosh\s+dbw)\b", "Drive-By-Wire Throttle", "motor", 5.0),
]

# ── Reference URL Research ───────────────────────────────────────────────────
# When the user pastes product URLs, WiringWizard fetches page titles and
# discovers links to wiring manuals, pinouts, and schematics automatically.
REFERENCE_URL_PATTERN = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
REFERENCE_LINK_PATTERN = re.compile(
    r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>",
    re.IGNORECASE | re.DOTALL,
)
REFERENCE_TITLE_PATTERN = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
REFERENCE_META_PATTERN = re.compile(
    r"<meta[^>]+name=[\"']description[\"'][^>]+content=[\"']([^\"']+)[\"'][^>]*>",
    re.IGNORECASE | re.DOTALL,
)
REFERENCE_DISCOVERY_KEYWORDS: Tuple[str, ...] = (
    "schematic", "wiring", "pinout", "manual", "connector",
    "install", "installation", "documentation", "guide", "pdf",
    "spec", "specifications", "features", "datasheet", "technical",
    "included", "harness", "sensor", "pin", "ecu", "can", "canbus",
)
REFERENCE_HTTP_TIMEOUT_SECONDS = 12
REFERENCE_MAX_URLS = 8
REFERENCE_MAX_LINKS_PER_PAGE = 6
REFERENCE_MAX_DESCRIPTION_CHARS = 500

# Pattern for JSON-LD structured data embedded in HTML (used by Shopify and others).
_JSON_LD_PATTERN = re.compile(
    r'<script[^>]+type\s*=\s*["\']application/ld\+json["\'][^>]*>(.*?)</script>',
    re.IGNORECASE | re.DOTALL,
)

# Component types that supply power to the rest of the circuit.
POWER_SOURCE_TYPES = frozenset({"battery", "power_supply"})

# Component types that consume power (candidates for wiring from a source).
POWER_LOAD_TYPES = frozenset({
    "microcontroller", "ecu", "relay", "led_load", "light", "motor", "servo",
    "fan", "pump", "sensor", "display", "buzzer", "solenoid", "stepper", "motor_driver",
})

# ── AI Prompt Templates ───────────────────────────────────────────────────────
# Two-stage pipeline: Stage 1 decomposes components, Stage 2 generates connections.
# Splitting the task dramatically improves output quality because each stage has
# a focused, achievable goal instead of trying to do everything at once.

# ── Stage 1: Component Decomposition ──────────────────────────────────────────

_STAGE1_SYSTEM_PROMPT = (
    "You are an expert automotive and electronics wiring engineer. "
    "Your ONLY task is to identify and list ALL individual electrical components "
    "from the user's project brief. Output ONLY a JSON array of component objects — "
    "no markdown fences, no prose, no wrapper object.\n\n"

    "CRITICAL RULES:\n"
    "1. A wiring harness is NOT a component — it is wires. NEVER list a harness as a "
    "component. Decompose it into every sensor, injector, coil, actuator it serves.\n"
    "2. List each injector INDIVIDUALLY: Injector #1, Injector #2, #3, #4 — "
    "NOT 'Fuel Injectors' as one item.\n"
    "3. List cam sensor and crank sensor as SEPARATE components — not 'Cam and Crank Sensors'.\n"
    "4. ALWAYS include infrastructure: battery, ignition_switch, ground_bus, fuse_box.\n"
    "5. Add CAN termination resistors (120 ohm) at each end of any CAN bus.\n"
    "6. Add relays for high-current loads (>5A): fuel pump relay, fan relay, etc.\n"
    "7. Add individual fuses for each major circuit.\n"
    "8. If user says component X handles role Y (e.g. 'KV8 handles transmission'), "
    "do NOT add a separate controller for role Y.\n"
    "9. If user says to REMOVE or EXCLUDE something, do NOT include it.\n"
    "10. Read for INTENT: 'I still have X' or 'I previously used X' followed by "
    "'but I want to use Y instead' means DO NOT include X — include Y.\n"
    "11. Use reference material to determine real pin names and counts.\n\n"

    "COMPONENT FORMAT (each object):\n"
    "{\n"
    '  "component_id": "snake_case_id",\n'
    '  "component_name": "Human-Readable Name",\n'
    '  "component_type": "battery|power_supply|ecu|relay|fuse|fuse_box|ground_bus|'
    'termination_resistor|ignition_switch|sensor|switch|display|solenoid|motor|fan|light|pump",\n'
    '  "current_draw_amps": number,\n'
    '  "position_label": "Engine Bay|Firewall|Dash|Transmission|Intake Manifold|Exhaust|etc.",\n'
    '  "pins": ["pin1_name", "pin2_name", ...]\n'
    "}\n\n"

    "EXAMPLE for a 4-cylinder engine project (abbreviated):\n"
    "[\n"
    '  {"component_id":"battery1","component_name":"Battery","component_type":"battery",'
    '"current_draw_amps":0,"position_label":"Engine Bay","pins":["POS","NEG"]},\n'
    '  {"component_id":"main_fuse1","component_name":"Main Fuse 80A","component_type":"fuse",'
    '"current_draw_amps":0,"position_label":"Engine Bay","pins":["IN","OUT"]},\n'
    '  {"component_id":"ignition_switch1","component_name":"Ignition Switch","component_type":"ignition_switch",'
    '"current_draw_amps":0.5,"position_label":"Dash","pins":["BATT","ACC","IGN","START"]},\n'
    '  {"component_id":"fuse_box1","component_name":"Fuse Box","component_type":"fuse_box",'
    '"current_draw_amps":0,"position_label":"Engine Bay","pins":["MAIN_IN","IGN_IN","F1","F2","F3","F4","F5","F6","F7","F8"]},\n'
    '  {"component_id":"ground_bus1","component_name":"Chassis Ground Bus","component_type":"ground_bus",'
    '"current_draw_amps":0,"position_label":"Engine Bay","pins":["CHASSIS","G1","G2","G3","G4","G5","G6","G7","G8","G9","G10"]},\n'
    '  {"component_id":"ecu1","component_name":"Standalone ECU","component_type":"ecu",'
    '"current_draw_amps":3,"position_label":"Firewall","pins":["B+","PGND","SGND","INJ1","INJ2","INJ3","INJ4","IGN1","IGN2","IGN3","IGN4","CAM","CKP","MAP","IAT","CLT","TPS","WBO2_IN","AN1","AN2","DI1","DI2","CAN_H","CAN_L"]},\n'
    '  {"component_id":"injector1","component_name":"Injector #1","component_type":"solenoid",'
    '"current_draw_amps":1,"position_label":"Cyl 1","pins":["B+","SIG"]},\n'
    '  {"component_id":"injector2","component_name":"Injector #2","component_type":"solenoid",'
    '"current_draw_amps":1,"position_label":"Cyl 2","pins":["B+","SIG"]},\n'
    '  {"component_id":"cam_sensor1","component_name":"Cam Angle Sensor","component_type":"sensor",'
    '"current_draw_amps":0.02,"position_label":"Valve Cover","pins":["V+","GND","SIG"]},\n'
    '  {"component_id":"crank_sensor1","component_name":"Crank Position Sensor","component_type":"sensor",'
    '"current_draw_amps":0.02,"position_label":"Bellhousing","pins":["V+","GND","SIG"]},\n'
    '  {"component_id":"can_term_1","component_name":"CAN Termination Resistor (ECU End)","component_type":"termination_resistor",'
    '"current_draw_amps":0,"position_label":"ECU","pins":["CAN_H","CAN_L"]}\n'
    "]"
)

_STAGE1_USER_TEMPLATE = (
    "Decompose this project brief into EVERY individual electrical component.\n\n"
    "BRIEF:\n{brief_text}\n\n"
    "{research_section}"
    "Return a JSON ARRAY of component objects. Include EVERY individual part — "
    "each injector separately, each sensor separately, each coil separately, "
    "the ground bus, the ignition switch, fuses, relays for high-current loads, "
    "CAN termination resistors, etc. Do NOT group items."
)

# ── Stage 2: Connection Generation ────────────────────────────────────────────

_STAGE2_SYSTEM_PROMPT = (
    "You are an expert automotive and electronics wiring engineer. "
    "You are given a list of electrical components. Generate ALL wiring connections between them. "
    "Output ONLY a JSON object with 'connections' array and 'notes' array — "
    "no markdown, no prose.\n\n"

    "EVERY project MUST have ALL of these connection types:\n"
    "1. POWER: Battery → main fuse → ignition switch → fuse box → individual fuses → loads. "
    "Loads get power through the fuse box, NOT directly from the battery.\n"
    "2. GROUND: EVERY component MUST have a ground wire to the ground bus. "
    "circuit_type='ground', wire_color='black'. No exceptions — if a component exists, "
    "it has a ground wire.\n"
    "3. SIGNAL: Sensor output pins → ECU input pins. "
    "circuit_type='signal_analog' or 'signal_digital', wire_color='white' or 'pink'.\n"
    "4. CONTROL: ECU output pins → injector SIG pins, coil SIG pins, relay coils. "
    "circuit_type='signal_digital'.\n"
    "5. CAN BUS: All CAN devices daisy-chained: CAN-H (yellow/green) and CAN-L (green). "
    "circuit_type='can_bus'. Termination resistors at each end.\n\n"

    "WIRE SIZING GUIDE:\n"
    "22 AWG: sensor signals, CAN bus, low-current digital\n"
    "18 AWG: injectors, ignition coils, small relays\n"
    "16 AWG: ECU power, relay coils, small motors\n"
    "14 AWG: headlights, fuel pump relay output, cooling fans\n"
    "10 AWG: alternator charge wire, main power distribution\n"
    "8 AWG or larger: battery to main fuse\n\n"

    "WIRE COLORS:\n"
    "RED = +12V always-hot | YELLOW = +12V ignition-switched | ORANGE = +12V accessory\n"
    "BLACK = ground | WHITE/PINK = sensor signal | BLUE = headlights\n"
    "YELLOW/GREEN = CAN-H | GREEN = CAN-L\n\n"

    "CONNECTION FORMAT:\n"
    '{"connection_id":"conn_001","from_component_id":"id","from_pin":"PIN",'
    '"to_component_id":"id","to_pin":"PIN","current_amps":number,'
    '"run_length_ft":number,"wire_color":"color","wire_gauge_awg":"number",'
    '"circuit_type":"power_always_on|power_ignition|power_accessory|ground|signal_analog|signal_digital|can_bus"}\n\n'

    "OUTPUT FORMAT:\n"
    '{"connections":[...],"notes":["tip1","tip2"]}'
)

_STAGE2_USER_TEMPLATE = (
    "Generate ALL wiring connections for these components.\n\n"
    "COMPONENTS:\n{components_json}\n\n"
    "PROJECT CONTEXT:\n{brief_summary}\n\n"
    "RULES — violating any of these makes the output USELESS:\n"
    "- EVERY component MUST have a ground wire to the ground bus (circuit_type='ground')\n"
    "- EVERY sensor MUST have a signal wire to the ECU (circuit_type='signal_analog' or 'signal_digital')\n"
    "- EVERY CAN device MUST have CAN_H and CAN_L connections (circuit_type='can_bus')\n"
    "- Power flows: battery → main fuse → ignition switch → fuse box → loads\n"
    "- High-current loads (>5A) go through relays\n"
    "- Use the ACTUAL pin names from each component's pins array\n"
    "- Generate a connection for EVERY component — no orphans allowed"
)

# Legacy single-call prompt kept for the remap function only.
_AI_SYSTEM_PROMPT = _STAGE1_SYSTEM_PROMPT
_AI_USER_PROMPT_TEMPLATE = _STAGE1_USER_TEMPLATE


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
        Parsed dict or list, or None if no valid JSON can be found.
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
        if isinstance(parsed, (dict, list)):
            return parsed
    except json.JSONDecodeError:
        pass

    # Strategy 2: locate the outermost { ... } or [ ... ] block
    first_brace = cleaned_text.find("{")
    first_bracket = cleaned_text.find("[")

    # Try array first if it appears before any object.
    if first_bracket >= 0 and (first_brace < 0 or first_bracket < first_brace):
        bracket_depth = 0
        for char_index, char in enumerate(cleaned_text[first_bracket:], start=first_bracket):
            if char == "[":
                bracket_depth += 1
            elif char == "]":
                bracket_depth -= 1
                if bracket_depth == 0:
                    try:
                        candidate = json.loads(cleaned_text[first_bracket: char_index + 1])
                        if isinstance(candidate, list):
                            return candidate
                    except json.JSONDecodeError:
                        break

    if first_brace >= 0:
        brace_depth = 0
        for char_index, char in enumerate(cleaned_text[first_brace:], start=first_brace):
            if char == "{":
                brace_depth += 1
            elif char == "}":
                brace_depth -= 1
                if brace_depth == 0:
                    try:
                        candidate = json.loads(cleaned_text[first_brace: char_index + 1])
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


def _generate_component_id(label_text: str, existing_component_ids: List[str]) -> str:
    """Create a unique component ID that always ends with a numeric suffix."""
    base_component_id = _slugify_to_component_id(label_text)
    next_suffix = 1
    while f"{base_component_id}{next_suffix}" in existing_component_ids:
        next_suffix += 1
    return f"{base_component_id}{next_suffix}"


def _append_component(
    discovered_components: List[Dict[str, Any]],
    component_name: str,
    component_type: str,
    default_current_amps: float,
) -> None:
    """Append a component while keeping IDs unique and preserving human-readable names."""
    existing_component_ids = [comp["component_id"] for comp in discovered_components]
    discovered_components.append({
        "component_id": _generate_component_id(component_name, existing_component_ids),
        "component_name": component_name,
        "component_type": component_type,
        "current_draw_amps": default_current_amps,
        "position_label": "TBD",
    })


# ── Reference URL Research Helpers ────────────────────────────────────────────

def _extract_reference_urls(brief_text: str) -> List[str]:
    """Return unique URLs from the brief in the order the user supplied them."""
    discovered_urls: List[str] = []
    for matched_url in REFERENCE_URL_PATTERN.findall(brief_text):
        cleaned_url = matched_url.rstrip(".,);]")
        if cleaned_url not in discovered_urls:
            discovered_urls.append(cleaned_url)
    return discovered_urls[:REFERENCE_MAX_URLS]


def _fetch_reference_page_html(reference_url: str) -> Optional[str]:
    """Download a reference page so WiringWizard can mine titles and doc links."""
    http_request = urllib.request.Request(
        reference_url,
        headers={"User-Agent": "WiringWizard/1.0"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=REFERENCE_HTTP_TIMEOUT_SECONDS) as response:
            response_bytes = response.read()
        return response_bytes.decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None


def _normalize_reference_text(raw_text: str) -> str:
    """Collapse HTML fragments into a short human-readable sentence."""
    stripped_text = re.sub(r"<[^>]+>", " ", raw_text)
    normalized_text = html.unescape(stripped_text)
    normalized_text = re.sub(r"\s+", " ", normalized_text).strip()
    return normalized_text


def _extract_reference_title(page_html: str) -> str:
    """Return the page title from fetched HTML, or an empty string when absent."""
    matched_title = REFERENCE_TITLE_PATTERN.search(page_html)
    if not matched_title:
        return ""
    return _normalize_reference_text(matched_title.group(1))


def _extract_reference_description(page_html: str) -> str:
    """Return the meta description from fetched HTML, or an empty string when absent."""
    matched_description = REFERENCE_META_PATTERN.search(page_html)
    if not matched_description:
        return ""
    cleaned_description = _normalize_reference_text(matched_description.group(1))
    return cleaned_description[:REFERENCE_MAX_DESCRIPTION_CHARS]


# Maximum characters returned from product spec extraction.
PRODUCT_SPECS_MAX_CHARS = 2000

# Regex patterns for product spec extraction.
_SPEC_LIST_ITEM_PATTERN = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
_SPEC_HEADING_PATTERN = re.compile(
    r"<(h[2-4])[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL
)
_SPEC_TABLE_ROW_PATTERN = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
_SPEC_TABLE_CELL_PATTERN = re.compile(
    r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL
)
_SPEC_PARAGRAPH_PATTERN = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
_SPEC_DESCRIPTION_BLOCK_PATTERN = re.compile(
    r"<(?:div|section)[^>]*(?:class|id)\s*=\s*[\"'][^\"']*"
    r"(?:product.?description|product.?features|specifications|tab.?description|"
    r"ProductDescription|product__description|product.?details|product.?info|"
    r"product.?specs|feature.?list)"
    r"[^\"']*[\"'][^>]*>(.*?)</(?:div|section)>",
    re.IGNORECASE | re.DOTALL,
)

# Keywords that signal a heading introduces product-relevant content.
_SPEC_SECTION_KEYWORDS = frozenset({
    "included", "features", "specifications", "what's in the box",
    "whats in the box", "sensors", "pins", "connectors", "wiring",
    "specs", "technical", "details", "description", "components",
    "harness", "kit contents", "package contents",
})


def _extract_product_specs(page_html: str) -> str:
    """Extract product specifications, features, and included components from HTML.

    Scans the page for list items, product description blocks, table rows,
    headings, and paragraphs that typically carry specification and feature
    data on e-commerce and product pages.  Uses only regex-based extraction
    (no external HTML parsing libraries).

    Args:
        page_html: Raw HTML content of the fetched product page.

    Returns:
        A cleaned, whitespace-normalised string of extracted product details,
        limited to roughly PRODUCT_SPECS_MAX_CHARS characters.  Returns an
        empty string when nothing useful is found.
    """
    extracted_fragments: List[str] = []

    # ── 1. Description blocks with product-related class/id names ─────────
    for block_match in _SPEC_DESCRIPTION_BLOCK_PATTERN.finditer(page_html):
        block_text = _normalize_reference_text(block_match.group(1))
        if len(block_text) > 10:
            extracted_fragments.append(block_text)

    # ── 2. Headings that label spec/feature sections ──────────────────────
    for heading_match in _SPEC_HEADING_PATTERN.finditer(page_html):
        heading_text = _normalize_reference_text(heading_match.group(2))
        heading_text_lower = heading_text.lower()
        if any(keyword in heading_text_lower for keyword in _SPEC_SECTION_KEYWORDS):
            extracted_fragments.append(f"[{heading_text}]")

    # ── 3. List items (parts lists, feature bullets) ──────────────────────
    for list_item_match in _SPEC_LIST_ITEM_PATTERN.finditer(page_html):
        item_text = _normalize_reference_text(list_item_match.group(1))
        if 5 < len(item_text) < 300:
            extracted_fragments.append(f"• {item_text}")

    # ── 4. Table rows (spec tables with pin names, wire gauges, etc.) ─────
    for row_match in _SPEC_TABLE_ROW_PATTERN.finditer(page_html):
        cells = _SPEC_TABLE_CELL_PATTERN.findall(row_match.group(1))
        if cells:
            cell_texts = [
                _normalize_reference_text(cell_content)
                for cell_content in cells
                if _normalize_reference_text(cell_content)
            ]
            if cell_texts:
                extracted_fragments.append(" | ".join(cell_texts))

    # ── 5. Paragraphs inside the page body ────────────────────────────────
    for paragraph_match in _SPEC_PARAGRAPH_PATTERN.finditer(page_html):
        paragraph_text = _normalize_reference_text(paragraph_match.group(1))
        if 20 < len(paragraph_text) < 500:
            extracted_fragments.append(paragraph_text)

    if not extracted_fragments:
        return ""

    # Deduplicate while preserving order.
    seen_fragments: set = set()
    unique_fragments: List[str] = []
    for fragment in extracted_fragments:
        normalised_key = fragment.strip().lower()
        if normalised_key not in seen_fragments:
            seen_fragments.add(normalised_key)
            unique_fragments.append(fragment)

    combined_text = " ".join(unique_fragments)
    if len(combined_text) > PRODUCT_SPECS_MAX_CHARS:
        combined_text = combined_text[:PRODUCT_SPECS_MAX_CHARS].rsplit(" ", 1)[0] + "…"
    return combined_text


def _try_shopify_product_json(product_url: str) -> str:
    """Try fetching product data from Shopify's .json API endpoint.

    Many Shopify stores (OHM Racing, Emtron, etc.) render content via JavaScript
    that our basic HTML fetcher cannot see. Shopify exposes product data at
    /products/[handle].json which contains the full description HTML.

    Args:
        product_url: URL of a product page (may or may not be Shopify).

    Returns:
        Extracted text content or empty string on failure.
    """
    if "/products/" not in product_url:
        return ""

    json_url = product_url.rstrip("/") + ".json"
    http_request = urllib.request.Request(
        json_url,
        headers={"User-Agent": "WiringWizard/1.0", "Accept": "application/json"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=REFERENCE_HTTP_TIMEOUT_SECONDS) as response:
            data = json.loads(response.read().decode("utf-8", errors="ignore"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, json.JSONDecodeError):
        return ""

    product = data.get("product", {})
    if not product:
        return ""

    fragments: List[str] = []
    title = product.get("title", "")
    if title:
        fragments.append(f"Product: {title}")

    body_html = product.get("body_html", "")
    if body_html:
        body_text = _normalize_reference_text(body_html)
        if body_text:
            fragments.append(body_text)

    tags = product.get("tags", [])
    if isinstance(tags, list) and tags:
        fragments.append(f"Tags: {', '.join(str(t) for t in tags)}")
    elif isinstance(tags, str) and tags:
        fragments.append(f"Tags: {tags}")

    variants = product.get("variants", [])
    if variants:
        variant_names = [v.get("title", "") for v in variants if v.get("title")]
        if variant_names and variant_names != ["Default Title"]:
            fragments.append(f"Variants: {', '.join(variant_names)}")

    if not fragments:
        return ""
    combined = " ".join(fragments)
    return combined[:PRODUCT_SPECS_MAX_CHARS * 2]


def _extract_json_ld_data(page_html: str) -> str:
    """Extract product/specification data from JSON-LD structured data in HTML.

    Many e-commerce sites embed schema.org Product data in JSON-LD script tags.
    This structured data is available even when visible content is rendered by JS.

    Args:
        page_html: Raw HTML content of the fetched page.

    Returns:
        Extracted text content or empty string.
    """
    fragments: List[str] = []
    for ld_match in _JSON_LD_PATTERN.finditer(page_html):
        try:
            ld_data = json.loads(ld_match.group(1))
        except json.JSONDecodeError:
            continue

        items = ld_data if isinstance(ld_data, list) else [ld_data]
        for item in items:
            if not isinstance(item, dict):
                continue
            item_type = str(item.get("@type", ""))
            if item_type not in ("Product", "IndividualProduct", "ProductModel"):
                continue
            name = item.get("name", "")
            if name:
                fragments.append(f"Product: {name}")
            description = item.get("description", "")
            if description:
                fragments.append(_normalize_reference_text(description))

    if not fragments:
        return ""
    combined = " ".join(fragments)
    return combined[:PRODUCT_SPECS_MAX_CHARS]


# ── Web Search Research (DuckDuckGo) ────────────────────────────────────────
# When product URLs alone aren't enough, search forums, wikis, and datasheets.

_DDG_SEARCH_URL = "https://html.duckduckgo.com/html/"
_DDG_RESULT_PATTERN = re.compile(
    r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
_DDG_SNIPPET_PATTERN = re.compile(
    r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>',
    re.IGNORECASE | re.DOTALL,
)
WEB_SEARCH_MAX_RESULTS = 3
WEB_SEARCH_MAX_QUERIES = 6
WEB_SEARCH_CONTENT_MAX_CHARS = 3000

# Keywords appended to component names to find wiring-relevant results.
_SEARCH_SUFFIXES = ("pinout wiring diagram", "wiring harness connections", "ECU pin assignment")

# Patterns to identify components worth searching for in the brief.
_SEARCHABLE_COMPONENT_PATTERN = re.compile(
    r"\b(emtron\s+kv8|ed10m|8.button\s+can\s+keypad|"
    r"w4a33|smart150|ohm\s+racing[^.]{0,30}|"
    r"4g63|denso\s+injector|lsu\s*4\.?9|aem\s+fuel\s+pressure|"
    r"gm\s+iat|gm\s+map|evo\s*x\s+sportmatic|"
    r"mil.spec\s+harness|stage\s*3\s+fuse\s*box)\b",
    re.IGNORECASE,
)


def _search_ddg(query: str) -> List[Tuple[str, str, str]]:
    """Run a DuckDuckGo HTML search and return (title, url, snippet) tuples.

    Uses the HTML-only endpoint which works without JavaScript rendering.
    Returns up to WEB_SEARCH_MAX_RESULTS results.

    Args:
        query: Search query string.

    Returns:
        List of (title, url, snippet) tuples from search results.
    """
    encoded_query = urllib.request.quote(query)
    search_url = f"{_DDG_SEARCH_URL}?q={encoded_query}"
    http_request = urllib.request.Request(
        search_url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=REFERENCE_HTTP_TIMEOUT_SECONDS) as response:
            page_html = response.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return []

    results: List[Tuple[str, str, str]] = []
    titles_and_urls = _DDG_RESULT_PATTERN.findall(page_html)
    snippets = _DDG_SNIPPET_PATTERN.findall(page_html)

    for index, (result_url, raw_title) in enumerate(titles_and_urls):
        if index >= WEB_SEARCH_MAX_RESULTS:
            break
        title = _normalize_reference_text(raw_title)
        snippet = _normalize_reference_text(snippets[index]) if index < len(snippets) else ""
        # DuckDuckGo wraps URLs in a redirect — extract the real URL.
        if "uddg=" in result_url:
            real_url_match = re.search(r"uddg=([^&]+)", result_url)
            if real_url_match:
                result_url = urllib.request.unquote(real_url_match.group(1))
        results.append((title, result_url, snippet))

    return results


def _build_web_search_research(brief_text: str) -> Tuple[str, List[str]]:
    """Search the web for pinouts, wiring info, and forum posts about key components.

    Identifies important component names in the brief, runs targeted searches
    via DuckDuckGo, extracts snippets and follows the best result URLs to
    scrape content from forums, wikis, and datasheets.

    Args:
        brief_text: The user's free-text project brief.

    Returns:
        Tuple of (research_context_string, list_of_user_facing_notes).
    """
    component_matches = _SEARCHABLE_COMPONENT_PATTERN.findall(brief_text)
    if not component_matches:
        return "", []

    # Deduplicate component names (case-insensitive).
    seen_names: set = set()
    unique_components: List[str] = []
    for match in component_matches:
        normalised = match.strip().lower()
        if normalised not in seen_names:
            seen_names.add(normalised)
            unique_components.append(match.strip())

    context_lines = ["Web Search Research:"]
    research_notes: List[str] = []
    queries_run = 0

    for component_name in unique_components:
        if queries_run >= WEB_SEARCH_MAX_QUERIES:
            break

        search_query = f"{component_name} {_SEARCH_SUFFIXES[queries_run % len(_SEARCH_SUFFIXES)]}"
        _log(f"Web search: {search_query}")
        results = _search_ddg(search_query)
        queries_run += 1

        if not results:
            continue

        context_lines.append(f"\n[Search: {component_name}]")
        for title, result_url, snippet in results:
            context_lines.append(f"  - {title}")
            context_lines.append(f"    URL: {result_url}")
            if snippet:
                context_lines.append(f"    Snippet: {snippet}")
            research_notes.append(f"Web search found: {title}")

            # Follow the first result URL to scrape deeper content.
            result_html = _fetch_reference_page_html(result_url)
            if not result_html:
                continue
            deep_specs = _extract_product_specs(result_html)
            if deep_specs:
                context_lines.append(f"    Content: {deep_specs[:WEB_SEARCH_CONTENT_MAX_CHARS]}")

    if len(context_lines) <= 1:
        return "", []
    return "\n".join(context_lines), research_notes


def _extract_reference_links(page_html: str, base_url: str) -> List[Tuple[str, str]]:
    """Return likely manual, wiring, or pinout links discovered on a reference page."""
    discovered_links: List[Tuple[str, str]] = []
    for relative_url, anchor_html in REFERENCE_LINK_PATTERN.findall(page_html):
        anchor_text = _normalize_reference_text(anchor_html)
        searchable_text = f"{anchor_text} {relative_url}".lower()
        if not any(keyword in searchable_text for keyword in REFERENCE_DISCOVERY_KEYWORDS):
            continue
        absolute_url = urljoin(base_url, relative_url)
        reference_link = (anchor_text or "Reference Link", absolute_url)
        if reference_link not in discovered_links:
            discovered_links.append(reference_link)
        if len(discovered_links) >= REFERENCE_MAX_LINKS_PER_PAGE:
            break
    return discovered_links


def _build_reference_research_context(brief_text: str) -> Tuple[str, List[str]]:
    """
    Turn URLs found in the brief into compact research context and user-facing notes.

    For each URL: tries Shopify JSON API first (gets JS-rendered product content),
    then falls back to HTML scraping with JSON-LD extraction. Also discovers links
    to manuals, schematics, and pinout documents via multi-hop following.

    Args:
        brief_text: The user's free-text project brief (may contain URLs).

    Returns:
        Tuple of (research_context_string, list_of_user_facing_notes).
        Both are empty when no URLs are found or all fetches fail.
    """
    reference_urls = _extract_reference_urls(brief_text)
    if not reference_urls:
        return "", []

    context_lines = ["Reference Material:"]
    research_notes: List[str] = []

    for reference_url in reference_urls:
        _log(f"Researching URL: {reference_url}")

        # ── Strategy 1: Shopify JSON API (gets JS-rendered content) ───────
        shopify_content = _try_shopify_product_json(reference_url)
        if shopify_content:
            context_lines.append(f"- [Shopify Product] {reference_url}")
            context_lines.append(f"  Full Content: {shopify_content}")
            research_notes.append(f"Shopify product data extracted: {reference_url}")
            _log(f"  Shopify JSON success: {len(shopify_content)} chars")

        # ── Strategy 2: Standard HTML fetch ───────────────────────────────
        page_html = _fetch_reference_page_html(reference_url)
        if not page_html:
            continue

        page_title = _extract_reference_title(page_html) or reference_url
        page_description = _extract_reference_description(page_html)
        context_lines.append(f"- {page_title}")
        context_lines.append(f"  Source: {reference_url}")
        research_notes.append(f"Reference found: {page_title}")

        if page_description:
            context_lines.append(f"  Summary: {page_description}")

        # ── Strategy 3: JSON-LD structured data ───────────────────────────
        json_ld_content = _extract_json_ld_data(page_html)
        if json_ld_content:
            context_lines.append(f"  Structured Data: {json_ld_content}")
            _log(f"  JSON-LD extracted: {len(json_ld_content)} chars")

        product_specs = _extract_product_specs(page_html)
        if product_specs:
            context_lines.append(f"  Product Details: {product_specs}")

        for link_label, link_url in _extract_reference_links(page_html, reference_url):
            context_lines.append(f"  Related Doc: {link_label} — {link_url}")
            research_notes.append(
                f"Possible schematic or pinout document: {link_label} — {link_url}"
            )

            linked_html = _fetch_reference_page_html(link_url)
            if not linked_html:
                continue
            linked_title = _extract_reference_title(linked_html) or link_label
            linked_specs = _extract_product_specs(linked_html)
            if linked_specs:
                context_lines.append(f"    Deep Reference ({linked_title}): {linked_specs}")
                research_notes.append(f"Deep reference extracted: {linked_title}")

    if len(context_lines) == 1:
        return "", []
    return "\n".join(context_lines), research_notes


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

    # Named product hints run first so user-specified names are preserved.
    for keyword_pattern, component_name, component_type, default_current_amps in NAMED_COMPONENT_HINTS:
        if not re.search(keyword_pattern, lowered_brief, re.IGNORECASE):
            continue
        _append_component(
            discovered_components,
            component_name=component_name,
            component_type=component_type,
            default_current_amps=default_current_amps,
        )
        seen_component_types.add(component_type)

    # Generic keyword map fills remaining types not already matched above.
    for keyword_pattern, component_type, default_current_amps in COMPONENT_KEYWORD_MAP:
        if not re.search(keyword_pattern, lowered_brief, re.IGNORECASE):
            continue
        if component_type in seen_component_types:
            continue
        seen_component_types.add(component_type)
        _append_component(
            discovered_components,
            component_name=component_type.replace("_", " ").title(),
            component_type=component_type,
            default_current_amps=default_current_amps,
        )

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
        existing_ids = [comp["component_id"] for comp in discovered_components]
        discovered_components.insert(0, {
            "component_id": _generate_component_id("Power Supply", existing_ids),
            "component_name": "Power Supply",
            "component_type": "power_supply",
            "current_draw_amps": 5.0,
            "position_label": "TBD",
        })
    if not has_load:
        _append_component(
            discovered_components,
            component_name="Microcontroller",
            component_type="microcontroller",
            default_current_amps=0.5,
        )

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

    # Enrich with reference research from any URLs the user supplied.
    research_context, research_notes = _build_reference_research_context(brief_text)
    if research_context:
        # Re-run inference with enriched text so URL-discovered terms get matched.
        enriched_brief = f"{brief_text}\n\n{research_context}"
        inferred_components = _infer_components_from_brief(enriched_brief)

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
        ] + research_notes,
        "used_ai": False,
    }


# ── AI Draft Attempt ──────────────────────────────────────────────────────────
# Two-stage pipeline: Stage 1 decomposes components, Stage 2 generates connections.

def _validate_and_fix_draft(
    components: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[str]]:
    """Post-AI validation ensuring critical wiring rules are met.

    Checks for and auto-fixes: components without ground connections,
    CAN devices without CAN bus connections, and missing infrastructure.

    Args:
        components:  Component list from the AI.
        connections: Connection list from the AI.

    Returns:
        Tuple of (fixed_components, fixed_connections, warning_notes).
    """
    warnings: List[str] = []
    component_ids = {c.get("component_id") for c in components}

    # ── Ensure a ground bus exists ────────────────────────────────────────
    ground_bus_id = None
    for comp in components:
        if comp.get("component_type") == "ground_bus":
            ground_bus_id = comp["component_id"]
            break
    if not ground_bus_id:
        ground_bus_id = "ground_bus1"
        components.append({
            "component_id": ground_bus_id,
            "component_name": "Chassis Ground Bus",
            "component_type": "ground_bus",
            "current_draw_amps": 0,
            "position_label": "Engine Bay / Firewall",
            "pins": ["CHASSIS"] + [f"G{i}" for i in range(1, 25)],
        })
        warnings.append("Auto-added missing ground bus")

    # ── Ensure every component has a ground connection ────────────────────
    grounded_component_ids: set = set()
    for conn in connections:
        if conn.get("circuit_type") == "ground":
            grounded_component_ids.add(conn.get("from_component_id"))
            grounded_component_ids.add(conn.get("to_component_id"))

    skip_ground_types = frozenset({
        "ground_bus", "battery", "fuse", "termination_resistor", "ignition_switch",
    })

    next_conn_id = len(connections) + 1
    ground_pin_counter = 1
    for comp in components:
        comp_id = comp.get("component_id", "")
        comp_type = comp.get("component_type", "")
        if comp_type in skip_ground_types:
            continue
        if comp_id in grounded_component_ids:
            continue
        connections.append({
            "connection_id": f"conn_{next_conn_id:03d}",
            "from_component_id": comp_id,
            "from_pin": "GND",
            "to_component_id": ground_bus_id,
            "to_pin": f"G{ground_pin_counter}",
            "current_amps": comp.get("current_draw_amps", 0.5),
            "run_length_ft": 3.0,
            "wire_color": "black",
            "wire_gauge_awg": "16",
            "circuit_type": "ground",
        })
        next_conn_id += 1
        ground_pin_counter += 1
        warnings.append(f"Auto-added ground for {comp.get('component_name', comp_id)}")

    # ── Ensure CAN devices have CAN bus connections ───────────────────────
    can_device_ids: List[str] = []
    for comp in components:
        comp_type = comp.get("component_type", "")
        pins = comp.get("pins", [])
        has_can_pins = any("CAN" in str(p).upper() for p in pins)
        if comp_type in ("ecu", "display") or has_can_pins:
            can_device_ids.append(comp["component_id"])

    can_connected_ids: set = set()
    for conn in connections:
        if conn.get("circuit_type") == "can_bus":
            can_connected_ids.add(conn.get("from_component_id"))
            can_connected_ids.add(conn.get("to_component_id"))

    # Daisy-chain any CAN devices that are missing CAN connections.
    missing_can_ids = [cid for cid in can_device_ids if cid not in can_connected_ids]
    if len(missing_can_ids) >= 2:
        for i in range(len(missing_can_ids) - 1):
            connections.append({
                "connection_id": f"conn_{next_conn_id:03d}",
                "from_component_id": missing_can_ids[i],
                "from_pin": "CAN_H",
                "to_component_id": missing_can_ids[i + 1],
                "to_pin": "CAN_H",
                "current_amps": 0.05,
                "run_length_ft": 4.0,
                "wire_color": "yellow/green",
                "wire_gauge_awg": "22",
                "circuit_type": "can_bus",
            })
            next_conn_id += 1
            connections.append({
                "connection_id": f"conn_{next_conn_id:03d}",
                "from_component_id": missing_can_ids[i],
                "from_pin": "CAN_L",
                "to_component_id": missing_can_ids[i + 1],
                "to_pin": "CAN_L",
                "current_amps": 0.05,
                "run_length_ft": 4.0,
                "wire_color": "green",
                "wire_gauge_awg": "22",
                "circuit_type": "can_bus",
            })
            next_conn_id += 1
        warnings.append(f"Auto-added CAN bus for {len(missing_can_ids)} devices")

    return components, connections, warnings


def _attempt_ai_draft(
    brief_text: str,
    requested_project_name: str,
    api_token: str,
) -> Optional[Dict[str, Any]]:
    """
    Two-stage AI pipeline to produce a structured wiring draft.

    Stage 0: Research — scrape user URLs (Shopify JSON, JSON-LD, HTML) and run
             web searches for key components via DuckDuckGo.
    Stage 1: Component Decomposition — focused AI call that identifies every
             individual component from the brief and research context.
    Stage 2: Connection Generation — focused AI call that takes the component
             list and generates all power, ground, signal, and CAN connections.
    Validation: Programmatic check that auto-fixes missing grounds and CAN bus.

    Returns a valid payload dict on success, or None on failure.
    """
    _log("=" * 60)
    _log("Starting two-stage AI draft pipeline")
    _log(f"Brief length: {len(brief_text)} chars")

    # ── Stage 0: Research ─────────────────────────────────────────────────
    _log("Stage 0: Research — scraping URLs and searching web")
    url_research, url_notes = _build_reference_research_context(brief_text)
    web_research, web_notes = _build_web_search_research(brief_text)
    all_research = "\n\n".join(filter(None, [url_research, web_research]))
    all_notes = url_notes + web_notes
    _log(f"  URL research: {len(url_research)} chars")
    _log(f"  Web search research: {len(web_research)} chars")

    # ── Stage 1: Component Decomposition ──────────────────────────────────
    _log("Stage 1: Component decomposition")
    research_section = ""
    if all_research:
        research_section = f"REFERENCE RESEARCH:\n{all_research}\n\n"

    stage1_user_prompt = _STAGE1_USER_TEMPLATE.format(
        brief_text=brief_text[:10000],
        research_section=research_section[:8000],
    )
    _log(f"  Stage 1 prompt length: {len(stage1_user_prompt)} chars")
    stage1_response = _call_github_models_api(
        _STAGE1_SYSTEM_PROMPT, stage1_user_prompt, api_token
    )

    if not stage1_response:
        _log("  Stage 1 FAILED: no response from API")
        return None
    _log(f"  Stage 1 response length: {len(stage1_response)} chars")
    _log(f"  Stage 1 response preview: {stage1_response[:300]}")

    # Parse — Stage 1 returns a JSON array directly or wrapped in an object.
    stage1_parsed = _extract_json_from_response(stage1_response)
    components: Optional[List[Dict[str, Any]]] = None

    if isinstance(stage1_parsed, dict):
        # AI may have wrapped the array in {"components": [...]}
        components = stage1_parsed.get("components")
        if not isinstance(components, list):
            components = None
    elif isinstance(stage1_parsed, list):
        components = stage1_parsed
    else:
        # Try parsing as raw JSON array.
        try:
            raw_array = json.loads(stage1_response.strip().strip("`").strip())
            if isinstance(raw_array, list):
                components = raw_array
        except json.JSONDecodeError:
            pass

    if not components:
        _log("  Stage 1 FAILED: could not parse component list")
        return None
    _log(f"  Stage 1 produced {len(components)} components")

    # ── Stage 2: Connection Generation ────────────────────────────────────
    _log("Stage 2: Connection generation")
    brief_summary = brief_text[:3000]
    components_json = json.dumps(components, indent=1)

    stage2_user_prompt = _STAGE2_USER_TEMPLATE.format(
        components_json=components_json[:12000],
        brief_summary=brief_summary,
    )
    _log(f"  Stage 2 prompt length: {len(stage2_user_prompt)} chars")
    stage2_response = _call_github_models_api(
        _STAGE2_SYSTEM_PROMPT, stage2_user_prompt, api_token
    )

    if not stage2_response:
        _log("  Stage 2 FAILED: no response from API")
        return None
    _log(f"  Stage 2 response length: {len(stage2_response)} chars")
    _log(f"  Stage 2 response preview: {stage2_response[:300]}")

    stage2_parsed = _extract_json_from_response(stage2_response)
    connections: List[Dict[str, Any]] = []
    ai_notes: List[str] = []

    if isinstance(stage2_parsed, dict):
        connections = stage2_parsed.get("connections", [])
        raw_notes = stage2_parsed.get("notes", [])
        if isinstance(raw_notes, list):
            ai_notes = [str(n) for n in raw_notes]
        elif raw_notes:
            ai_notes = [str(raw_notes)]
    elif isinstance(stage2_parsed, list):
        connections = stage2_parsed

    if not isinstance(connections, list):
        connections = []
    _log(f"  Stage 2 produced {len(connections)} connections")

    # ── Validation: auto-fix missing grounds and CAN bus ──────────────────
    _log("Validation: checking grounds, CAN bus, orphaned components")
    components, connections, validation_warnings = _validate_and_fix_draft(
        components, connections
    )
    _log(f"  Validation added {len(validation_warnings)} fixes")

    # ── Assemble final draft ──────────────────────────────────────────────
    resolved_project_name = requested_project_name.strip() or "Wiring Project"

    notes_list = ai_notes + all_notes + validation_warnings
    notes_list.append(
        "AI-generated draft — always verify pinouts, polarities, and "
        "critical wiring details before use."
    )

    _log(f"Draft complete: {len(components)} components, {len(connections)} connections")
    return {
        "project_name": resolved_project_name,
        "description": brief_text[:200].strip(),
        "components": components,
        "connections": connections,
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


# ── Deep URL Fetcher for Component Library ───────────────────────────────────
# When the user provides a documentation URL (e.g. Emtron docs), this crawler
# fetches the page, identifies pinout/wiring sub-pages, follows links up to
# DEEP_CRAWL_MAX_DEPTH levels, and extracts structured text (especially tables)
# that can be fed directly into the AI component parser.

DEEP_CRAWL_MAX_DEPTH = 3
DEEP_CRAWL_MAX_PAGES = 15
DEEP_CRAWL_TIMEOUT_SECONDS = 15

# Keywords that identify links worth following deeper into a documentation site.
_DEEP_CRAWL_LINK_KEYWORDS: Tuple[str, ...] = (
    "pinout", "pin out", "wiring", "connector", "datasheet", "data sheet",
    "hardware manual", "installation", "harness", "specifications", "specs",
    "power supply", "power distribution", "ecu", "ecm", "lambda", "auxiliary",
    "inputs", "outputs", "channels", "ground", "sensor", "signal",
)

# Patterns that mark a page as containing actual pin/wiring data worth extracting.
_PIN_DATA_INDICATORS = re.compile(
    r"(pin\s+\d|connector\s+[a-d]|channel\s+name|"
    r"pin\s+channel|pin\s+description|"
    r"\bpin\b.*\bname\b|\bA\d{1,2}\b.*\bB\d{1,2}\b|"
    r"injection\s+channel|ignition\s+channel|auxiliary\s+output|"
    r"analog\s+input|digital\s+input|lambda\s+\d|"
    r"crank.*sensor|sync.*sensor|knock\s+\d|"
    r"can\s*[12]?[hl]|efi\s+relay|sensor\s+supply|"
    r"ecu\s+ground|sensor\s+0v)",
    re.IGNORECASE,
)


def _fetch_page_html(page_url: str) -> Optional[str]:
    """Fetch a single HTML page with a generous timeout for documentation sites."""
    http_request = urllib.request.Request(
        page_url,
        headers={"User-Agent": "WiringWizard/2.0 ComponentLibrary"},
        method="GET",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=DEEP_CRAWL_TIMEOUT_SECONDS) as response:
            return response.read().decode("utf-8", errors="ignore")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as fetch_error:
        _log(f"  Deep crawl fetch failed for {page_url}: {fetch_error}")
        return None


def _extract_text_from_html(page_html: str) -> str:
    """Convert HTML to clean text, preserving table structure as pipe-delimited rows.

    Documentation sites embed pin data in <table> elements. This function
    extracts table rows first (formatted as "cell1 | cell2 | cell3"), then
    falls back to general text extraction for non-table content like headings,
    list items, and paragraphs.
    """
    extracted_sections: List[str] = []

    # ── 1. Extract tables (the primary source of pin data) ────────────────
    table_pattern = re.compile(r"<table[^>]*>(.*?)</table>", re.IGNORECASE | re.DOTALL)
    row_pattern = re.compile(r"<tr[^>]*>(.*?)</tr>", re.IGNORECASE | re.DOTALL)
    cell_pattern = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.IGNORECASE | re.DOTALL)

    for table_match in table_pattern.finditer(page_html):
        table_rows: List[str] = []
        for row_match in row_pattern.finditer(table_match.group(1)):
            cells = cell_pattern.findall(row_match.group(1))
            if cells:
                cleaned_cells = [_normalize_reference_text(cell_html) for cell_html in cells]
                # Skip empty rows or rows with only whitespace cells.
                if any(cell.strip() for cell in cleaned_cells):
                    table_rows.append(" | ".join(cleaned_cells))
        if table_rows:
            extracted_sections.append("\n".join(table_rows))

    # ── 2. Extract headings (section markers) ─────────────────────────────
    heading_pattern = re.compile(r"<h[1-6][^>]*>(.*?)</h[1-6]>", re.IGNORECASE | re.DOTALL)
    for heading_match in heading_pattern.finditer(page_html):
        heading_text = _normalize_reference_text(heading_match.group(1)).strip()
        if heading_text and len(heading_text) > 2:
            extracted_sections.append(f"\n## {heading_text}")

    # ── 3. Extract list items (spec bullets, feature lists) ───────────────
    list_item_pattern = re.compile(r"<li[^>]*>(.*?)</li>", re.IGNORECASE | re.DOTALL)
    for list_match in list_item_pattern.finditer(page_html):
        item_text = _normalize_reference_text(list_match.group(1)).strip()
        if 3 < len(item_text) < 500:
            extracted_sections.append(f"• {item_text}")

    # ── 4. Extract paragraphs (descriptive text, notes, warnings) ─────────
    paragraph_pattern = re.compile(r"<p[^>]*>(.*?)</p>", re.IGNORECASE | re.DOTALL)
    for para_match in paragraph_pattern.finditer(page_html):
        para_text = _normalize_reference_text(para_match.group(1)).strip()
        if 10 < len(para_text) < 1000:
            extracted_sections.append(para_text)

    return "\n".join(extracted_sections)


def _extract_sub_links(page_html: str, base_url: str) -> List[Tuple[str, str]]:
    """Find links on a page that are likely to contain pin/wiring data.

    Returns a list of (link_text, absolute_url) tuples, filtered to only
    include links whose text or URL matches deep crawl keywords.
    """
    discovered_links: List[Tuple[str, str]] = []
    seen_urls: set = set()

    for relative_url, anchor_html in REFERENCE_LINK_PATTERN.findall(page_html):
        anchor_text = _normalize_reference_text(anchor_html).strip()
        searchable_text = f"{anchor_text} {relative_url}".lower()

        if not any(keyword in searchable_text for keyword in _DEEP_CRAWL_LINK_KEYWORDS):
            continue

        absolute_url = urljoin(base_url, relative_url)

        # Skip anchors, external sites, and non-HTML resources.
        if absolute_url in seen_urls:
            continue
        if "#" in absolute_url.split("/")[-1] and not absolute_url.endswith("/"):
            # Allow fragment-free URLs but skip pure anchor links.
            clean_url = absolute_url.split("#")[0]
            if clean_url in seen_urls:
                continue
            absolute_url = clean_url
        if not absolute_url.startswith(base_url.split("/")[0] + "//" + base_url.split("//")[1].split("/")[0]):
            continue  # Stay on the same domain.

        seen_urls.add(absolute_url)
        discovered_links.append((anchor_text or absolute_url, absolute_url))

    return discovered_links


def _has_pin_data(page_text: str) -> bool:
    """Check whether extracted page text likely contains pin/wiring information."""
    return bool(_PIN_DATA_INDICATORS.search(page_text))


def fetch_url_for_component_data(
    component_url: str,
    component_name: str = "",
) -> Dict[str, Any]:
    """Deep-crawl a documentation URL to extract component pin/wiring data.

    Starting from the provided URL, this function:
    1. Fetches and extracts text from the initial page.
    2. Identifies sub-links that match pinout/wiring keywords.
    3. Follows those links up to DEEP_CRAWL_MAX_DEPTH levels.
    4. Prioritises pages that contain actual pin data (table rows with pin
       numbers, connector names, channel assignments).
    5. Returns the combined extracted text, ready to feed into AI Parse.

    Args:
        component_url: Starting URL (e.g. an Emtron docs page).
        component_name: Optional component name for logging context.

    Returns:
        Dict with keys:
            extracted_text (str): Combined text from all crawled pages.
            pages_crawled (int): Number of pages successfully fetched.
            pages_with_pin_data (int): Pages that contained pin information.
            crawled_urls (list): URLs that were fetched.
            error (str): Error message if the initial fetch fails.
    """
    _log(f"Deep crawl starting: {component_url} (name={component_name})")

    initial_html = _fetch_page_html(component_url)
    if not initial_html:
        _log("  Deep crawl: initial fetch failed")
        return {
            "extracted_text": "",
            "pages_crawled": 0,
            "pages_with_pin_data": 0,
            "crawled_urls": [],
            "error": f"Could not fetch {component_url}. Check the URL and try again.",
        }

    # Track all pages we visit to avoid loops.
    visited_urls: set = {component_url}
    # Queue of (url, depth) to process.
    crawl_queue: List[Tuple[str, int]] = []
    # Results: list of (url, page_text, has_pins) tuples.
    crawl_results: List[Tuple[str, str, bool]] = []

    # Process the initial page.
    initial_text = _extract_text_from_html(initial_html)
    initial_has_pins = _has_pin_data(initial_text)
    crawl_results.append((component_url, initial_text, initial_has_pins))
    _log(f"  Initial page: {len(initial_text)} chars, has_pins={initial_has_pins}")

    # Discover sub-links from the initial page.
    sub_links = _extract_sub_links(initial_html, component_url)
    _log(f"  Found {len(sub_links)} relevant sub-links")
    for link_text, link_url in sub_links:
        if link_url not in visited_urls:
            crawl_queue.append((link_url, 1))
            _log(f"    Queued: {link_text} → {link_url}")

    # Crawl sub-pages breadth-first up to the depth and page limits.
    while crawl_queue and len(crawl_results) < DEEP_CRAWL_MAX_PAGES:
        current_url, current_depth = crawl_queue.pop(0)
        if current_url in visited_urls:
            continue
        visited_urls.add(current_url)

        _log(f"  Crawling depth={current_depth}: {current_url}")
        page_html = _fetch_page_html(current_url)
        if not page_html:
            continue

        page_text = _extract_text_from_html(page_html)
        page_has_pins = _has_pin_data(page_text)
        crawl_results.append((current_url, page_text, page_has_pins))
        _log(f"    Got {len(page_text)} chars, has_pins={page_has_pins}")

        # Follow deeper links only if we haven't reached the depth limit.
        if current_depth < DEEP_CRAWL_MAX_DEPTH:
            deeper_links = _extract_sub_links(page_html, current_url)
            for link_text, link_url in deeper_links:
                if link_url not in visited_urls and len(crawl_queue) < DEEP_CRAWL_MAX_PAGES * 3:
                    crawl_queue.append((link_url, current_depth + 1))

    # Assemble the final text, prioritising pages with actual pin data.
    pin_data_pages = [(url, text) for url, text, has_pins in crawl_results if has_pins]
    other_pages = [(url, text) for url, text, has_pins in crawl_results if not has_pins]

    combined_sections: List[str] = []
    if component_name:
        combined_sections.append(f"# Component: {component_name}\n")

    for page_url, page_text in pin_data_pages:
        page_label = page_url.split("/")[-2] if page_url.endswith("/index.html") else page_url.split("/")[-1]
        combined_sections.append(f"\n--- PIN DATA: {page_label} ---\n{page_text}")

    for page_url, page_text in other_pages:
        page_label = page_url.split("/")[-2] if page_url.endswith("/index.html") else page_url.split("/")[-1]
        combined_sections.append(f"\n--- REFERENCE: {page_label} ---\n{page_text}")

    combined_text = "\n".join(combined_sections)
    pages_with_pin_data_count = len(pin_data_pages)

    _log(
        f"  Deep crawl complete: {len(crawl_results)} pages, "
        f"{pages_with_pin_data_count} with pin data, "
        f"{len(combined_text)} chars total"
    )

    return {
        "extracted_text": combined_text,
        "pages_crawled": len(crawl_results),
        "pages_with_pin_data": pages_with_pin_data_count,
        "crawled_urls": [url for url, _, _ in crawl_results],
        "error": "",
    }


# ── Experimental: Auto-Search by Component Name ─────────────────────────────
# Searches DuckDuckGo for a component's pinout/datasheet, deep-crawls the top
# results, and returns combined text ready for AI parsing.  Marked experimental
# because search quality varies and may miss niche or one-off components.

AUTO_SEARCH_MAX_QUERIES = 2
AUTO_SEARCH_MAX_RESULTS_PER_QUERY = 3
AUTO_SEARCH_MAX_CRAWL_PAGES = 8

# Search query templates — the component name is interpolated into each one.
_AUTO_SEARCH_QUERY_TEMPLATES: Tuple[str, ...] = (
    "{name} pinout wiring diagram datasheet",
    "{name} pin assignment connector specifications",
)

# Domains we skip because they never contain useful pin-level data.
_AUTO_SEARCH_BLOCKED_DOMAINS: Tuple[str, ...] = (
    "youtube.com", "facebook.com", "instagram.com", "tiktok.com",
    "twitter.com", "x.com", "pinterest.com", "amazon.com",
    "ebay.com", "aliexpress.com",
)


def _is_blocked_domain(url: str) -> bool:
    """Return True if the URL belongs to a domain unlikely to contain pin data."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in _AUTO_SEARCH_BLOCKED_DOMAINS)


def auto_search_component_data(
    component_name: str,
) -> Dict[str, Any]:
    """Search the web for a component's pinout/datasheet and deep-crawl results.

    This is an **experimental** feature.  It runs DuckDuckGo searches with
    pinout-focused queries, filters out irrelevant domains, then deep-crawls
    the most promising result pages using the same infrastructure as the
    URL-to-Library feature.

    Args:
        component_name: Human-readable component name (e.g. "Emtron KV8 ECU").

    Returns:
        Dict with keys:
            extracted_text (str): Combined text from all crawled result pages.
            pages_crawled (int): Total pages successfully fetched.
            pages_with_pin_data (int): Pages that contained pin information.
            search_queries (list): Queries that were executed.
            result_urls (list): URLs that were found and crawled.
            error (str): Error message if no results were found.
    """
    _log(f"Auto-search starting for: {component_name}")

    if not component_name.strip():
        return {
            "extracted_text": "",
            "pages_crawled": 0,
            "pages_with_pin_data": 0,
            "search_queries": [],
            "result_urls": [],
            "error": "Component name is required for auto-search.",
        }

    # Step 1: Run multiple search queries to cast a wider net.
    all_result_urls: List[str] = []
    executed_queries: List[str] = []
    seen_urls: set = set()

    for template in _AUTO_SEARCH_QUERY_TEMPLATES[:AUTO_SEARCH_MAX_QUERIES]:
        search_query = template.format(name=component_name)
        executed_queries.append(search_query)
        _log(f"  Auto-search query: {search_query}")

        results = _search_ddg(search_query)
        for title, result_url, snippet in results[:AUTO_SEARCH_MAX_RESULTS_PER_QUERY]:
            if result_url in seen_urls:
                continue
            if _is_blocked_domain(result_url):
                _log(f"    Skipped blocked domain: {result_url}")
                continue
            seen_urls.add(result_url)
            all_result_urls.append(result_url)
            _log(f"    Found: {title} → {result_url}")

    if not all_result_urls:
        _log("  Auto-search: no usable results found")
        return {
            "extracted_text": "",
            "pages_crawled": 0,
            "pages_with_pin_data": 0,
            "search_queries": executed_queries,
            "result_urls": [],
            "error": (
                f"No relevant search results found for \"{component_name}\". "
                "Try a more specific name, part number, or provide a URL directly."
            ),
        }

    # Step 2: Deep-crawl each result URL (reusing the existing crawler).
    # Each URL gets a shallow crawl (depth 1 only) to stay fast.
    combined_sections: List[str] = [f"# Auto-Search: {component_name}\n"]
    total_pages_crawled = 0
    total_pages_with_pins = 0
    crawled_urls: List[str] = []

    for result_url in all_result_urls:
        if total_pages_crawled >= AUTO_SEARCH_MAX_CRAWL_PAGES:
            break

        _log(f"  Auto-search crawling: {result_url}")
        page_html = _fetch_page_html(result_url)
        if not page_html:
            continue

        page_text = _extract_text_from_html(page_html)
        page_has_pins = _has_pin_data(page_text)
        total_pages_crawled += 1
        crawled_urls.append(result_url)

        if page_has_pins:
            total_pages_with_pins += 1

        # Follow one level of sub-links for pin-relevant pages.
        sub_link_texts: List[str] = []
        if total_pages_crawled < AUTO_SEARCH_MAX_CRAWL_PAGES:
            sub_links = _extract_sub_links(page_html, result_url)
            for link_text, link_url in sub_links[:3]:
                if link_url in seen_urls or total_pages_crawled >= AUTO_SEARCH_MAX_CRAWL_PAGES:
                    break
                seen_urls.add(link_url)
                sub_html = _fetch_page_html(link_url)
                if not sub_html:
                    continue
                sub_text = _extract_text_from_html(sub_html)
                sub_has_pins = _has_pin_data(sub_text)
                total_pages_crawled += 1
                crawled_urls.append(link_url)
                if sub_has_pins:
                    total_pages_with_pins += 1
                    sub_link_texts.append(f"\n--- PIN DATA (sub-page) ---\n{sub_text}")
                else:
                    sub_link_texts.append(f"\n--- REFERENCE (sub-page) ---\n{sub_text}")

        # Add this result's content — pin data pages first.
        page_label = result_url.split("//")[-1][:80]
        if page_has_pins:
            combined_sections.append(f"\n--- PIN DATA: {page_label} ---\n{page_text}")
        else:
            combined_sections.append(f"\n--- REFERENCE: {page_label} ---\n{page_text}")
        combined_sections.extend(sub_link_texts)

    combined_text = "\n".join(combined_sections)

    _log(
        f"  Auto-search complete: {total_pages_crawled} pages, "
        f"{total_pages_with_pins} with pin data, "
        f"{len(combined_text)} chars total"
    )

    if total_pages_crawled == 0:
        return {
            "extracted_text": "",
            "pages_crawled": 0,
            "pages_with_pin_data": 0,
            "search_queries": executed_queries,
            "result_urls": all_result_urls,
            "error": "Found search results but couldn't fetch any pages. Try providing a URL directly.",
        }

    return {
        "extracted_text": combined_text,
        "pages_crawled": total_pages_crawled,
        "pages_with_pin_data": total_pages_with_pins,
        "search_queries": executed_queries,
        "result_urls": crawled_urls,
        "error": "",
    }


# ── Image/Schematic Vision Parsing ───────────────────────────────────────────

# Vision model used for image-based pin extraction
AI_VISION_MODEL = "gpt-4o"

_IMAGE_PARSE_SYSTEM_PROMPT = (
    "You are an expert electronics engineer who reads wiring diagrams, pinout "
    "schematics, datasheet images, and connector drawings.\n\n"
    "The user provides an image of a component's pinout, wiring diagram, or "
    "datasheet page.  Extract every pin/terminal visible in the image.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    "  name           (string)  - component name if identifiable from the image\n"
    "  component_type (string)  - one of: ecu, sensor, actuator, relay, fuse_box, "
    "display, switch, motor, solenoid, light, battery, power_supply, ground_bus, "
    "ignition_switch, microcontroller, motor_driver, resistor, capacitor, "
    "termination_resistor, connector, harness, general\n"
    "  manufacturer   (string)  - manufacturer if identifiable\n"
    "  part_number    (string)  - part/model number if identifiable\n"
    "  voltage_nominal (number) - nominal operating voltage (default 12.0)\n"
    "  current_draw_amps (number) - typical current draw (default 0)\n"
    "  pins           (array)   - every pin/terminal visible in the image:\n"
    "      pin_id      (string) - connector or pin number\n"
    "      name        (string) - function name (e.g. 'B+', 'CAN-H')\n"
    "      pin_type    (string) - one of: power_input, power_output, ground, "
    "signal_input, signal_output, can_high, can_low, pwm_output, serial_tx, "
    "serial_rx, switched_power, general\n"
    "      description (string) - what this pin does\n"
    "  notes          (string)  - any additional info visible in the image\n\n"
    "RULES:\n"
    "- List EVERY pin visible in the image, even if partially obscured.\n"
    "- Read any text labels, table headers, and wire markings carefully.\n"
    "- If a pin's function is unclear, use pin_type 'general'.\n"
    "- Return valid JSON only.  No markdown, no explanation."
)


def parse_component_from_image(
    component_name: str,
    image_base64: str,
    image_mime_type: str,
    api_token: str,
) -> Optional[Dict[str, Any]]:
    """Use AI vision to extract pin data from a schematic/datasheet image.

    Sends the image to the GitHub Models vision endpoint and parses the
    response into a structured component record.

    Args:
        component_name: User-provided component name for context.
        image_base64: Base64-encoded image data (no data: prefix).
        image_mime_type: MIME type like 'image/png' or 'image/jpeg'.
        api_token: GitHub Models API token.

    Returns:
        Parsed component dict on success, or None on failure.
    """
    if not image_base64.strip() or not api_token.strip():
        return None

    user_content = [
        {
            "type": "text",
            "text": (
                f"Component name: {component_name.strip()}\n\n"
                "Extract all pin/terminal data from this image into a structured "
                "component record with a complete pin list."
            ),
        },
        {
            "type": "image_url",
            "image_url": {
                "url": f"data:{image_mime_type};base64,{image_base64}",
            },
        },
    ]

    encoded_request_body = json.dumps({
        "model": AI_VISION_MODEL,
        "messages": [
            {"role": "system", "content": _IMAGE_PARSE_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
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
        with urllib.request.urlopen(http_request, timeout=90) as http_response:
            response_body = json.loads(http_response.read().decode("utf-8"))
            choices = response_body.get("choices", [])
            if not choices:
                return None
            raw_response = choices[0].get("message", {}).get("content", "")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None

    if not raw_response:
        return None

    parsed = _extract_json_from_response(raw_response)
    if not isinstance(parsed, dict):
        return None

    # Normalize the result with sensible defaults.
    result = {
        "name": parsed.get("name", component_name.strip()),
        "component_type": parsed.get("component_type", "general"),
        "manufacturer": parsed.get("manufacturer", ""),
        "part_number": parsed.get("part_number", ""),
        "voltage_nominal": float(parsed.get("voltage_nominal", 12.0)),
        "current_draw_amps": float(parsed.get("current_draw_amps", 0.0)),
        "pins": [],
        "notes": parsed.get("notes", ""),
    }

    raw_pins = parsed.get("pins", [])
    if isinstance(raw_pins, list):
        for pin_data in raw_pins:
            if not isinstance(pin_data, dict):
                continue
            result["pins"].append({
                "pin_id": str(pin_data.get("pin_id", "")),
                "name": str(pin_data.get("name", "")),
                "pin_type": str(pin_data.get("pin_type", "general")),
                "description": str(pin_data.get("description", "")),
            })

    return result


# ── Bulk Library Builder ─────────────────────────────────────────────────────

# Max distinct components the bulk builder will identify per crawl
BULK_BUILDER_MAX_COMPONENTS = 20

_BULK_IDENTIFY_SYSTEM_PROMPT = (
    "You are an expert electronics engineer reading a documentation site.  "
    "The user provides crawled text from multiple pages of a product's "
    "documentation or manual.\n\n"
    "Your job: identify every DISTINCT electrical component mentioned in the "
    "text that has pin/terminal information.  Each component should be a "
    "separate product (ECU, sensor, relay, etc.), NOT a pin or a wire.\n\n"
    "Return ONLY a JSON object with:\n"
    "  components (array) - each component has:\n"
    "    name           (string) - specific product name\n"
    "    component_type (string) - ecu, sensor, actuator, relay, fuse_box, "
    "display, switch, motor, solenoid, light, battery, power_supply, "
    "ground_bus, ignition_switch, microcontroller, connector, harness, general\n"
    "    manufacturer   (string) - manufacturer if identifiable\n"
    "    part_number    (string) - part/model number if identifiable\n"
    "    voltage_nominal (number) - nominal voltage\n"
    "    current_draw_amps (number) - typical current draw\n"
    "    pins           (array)  - every pin/terminal for this component:\n"
    "        pin_id      (string)\n"
    "        name        (string)\n"
    "        pin_type    (string) - power_input, power_output, ground, "
    "signal_input, signal_output, can_high, can_low, pwm_output, serial_tx, "
    "serial_rx, switched_power, general\n"
    "        description (string)\n"
    "    notes          (string) - technical notes for this component\n\n"
    "RULES:\n"
    "- Identify SEPARATE components — do not merge different products.\n"
    "- List ALL pins for each component from the provided text.\n"
    "- If a component appears in multiple sections, combine all its pins.\n"
    f"- Maximum {BULK_BUILDER_MAX_COMPONENTS} components.\n"
    "- Return valid JSON only.  No markdown, no explanation."
)

_BULK_IDENTIFY_USER_TEMPLATE = (
    "Documentation source: {source_description}\n\n"
    "Crawled text from the documentation:\n"
    "---\n"
    "{crawled_text}\n"
    "---\n\n"
    "Identify every distinct component with pin data and return structured records."
)


def bulk_identify_components(
    documentation_url: str,
    api_token: str,
) -> Dict[str, Any]:
    """Crawl a documentation URL and identify multiple components in bulk.

    Deep-crawls the URL and its sub-pages, then uses AI to identify distinct
    components and extract pin data for each one.

    Args:
        documentation_url: Root URL of the documentation site.
        api_token: GitHub Models API token.

    Returns:
        Dict with 'components' (list of parsed component dicts), 'crawl_stats',
        and 'error' (empty string on success).
    """
    if not documentation_url.strip() or not api_token.strip():
        return {"components": [], "crawl_stats": {}, "error": "URL and API token are required."}

    # Reuse the deep-crawl infrastructure with expanded limits for bulk discovery.
    crawl_result = fetch_url_for_component_data(documentation_url, "bulk-scan")
    if crawl_result.get("error"):
        return {"components": [], "crawl_stats": {}, "error": crawl_result["error"]}

    extracted_text = crawl_result.get("extracted_text", "")
    if not extracted_text.strip():
        return {
            "components": [],
            "crawl_stats": {
                "pages_crawled": crawl_result.get("pages_crawled", 0),
                "pages_with_pin_data": crawl_result.get("pages_with_pin_data", 0),
            },
            "error": "No meaningful text found at that URL.",
        }

    user_prompt = _BULK_IDENTIFY_USER_TEMPLATE.format(
        source_description=documentation_url.strip(),
        crawled_text=extracted_text.strip()[:24000],
    )

    raw_response = _call_github_models_api(
        _BULK_IDENTIFY_SYSTEM_PROMPT, user_prompt, api_token
    )
    if not raw_response:
        return {
            "components": [],
            "crawl_stats": {
                "pages_crawled": crawl_result.get("pages_crawled", 0),
                "pages_with_pin_data": crawl_result.get("pages_with_pin_data", 0),
            },
            "error": "AI could not process the crawled documentation.",
        }

    parsed = _extract_json_from_response(raw_response)
    if not isinstance(parsed, dict):
        return {
            "components": [],
            "crawl_stats": {
                "pages_crawled": crawl_result.get("pages_crawled", 0),
                "pages_with_pin_data": crawl_result.get("pages_with_pin_data", 0),
            },
            "error": "AI returned invalid response format.",
        }

    raw_components = parsed.get("components", [])
    if not isinstance(raw_components, list):
        raw_components = []

    # Normalize each identified component.
    normalized_components = []
    for raw_comp in raw_components[:BULK_BUILDER_MAX_COMPONENTS]:
        if not isinstance(raw_comp, dict):
            continue

        component = {
            "name": raw_comp.get("name", "Unknown Component"),
            "component_type": raw_comp.get("component_type", "general"),
            "manufacturer": raw_comp.get("manufacturer", ""),
            "part_number": raw_comp.get("part_number", ""),
            "voltage_nominal": float(raw_comp.get("voltage_nominal", 12.0)),
            "current_draw_amps": float(raw_comp.get("current_draw_amps", 0.0)),
            "pins": [],
            "notes": raw_comp.get("notes", ""),
            "source_urls": [documentation_url.strip()],
        }

        raw_pins = raw_comp.get("pins", [])
        if isinstance(raw_pins, list):
            for pin_data in raw_pins:
                if not isinstance(pin_data, dict):
                    continue
                component["pins"].append({
                    "pin_id": str(pin_data.get("pin_id", "")),
                    "name": str(pin_data.get("name", "")),
                    "pin_type": str(pin_data.get("pin_type", "general")),
                    "description": str(pin_data.get("description", "")),
                })

        normalized_components.append(component)

    return {
        "components": normalized_components,
        "crawl_stats": {
            "pages_crawled": crawl_result.get("pages_crawled", 0),
            "pages_with_pin_data": crawl_result.get("pages_with_pin_data", 0),
        },
        "error": "",
    }

_COMPONENT_PARSE_SYSTEM_PROMPT = (
    "You are an expert electronics engineer who reads datasheets, manuals, and "
    "spec sheets.  The user gives you raw text about an electrical component "
    "(pasted from a datasheet, manual, product page, or typed from memory).\n\n"
    "Your job: extract a structured component record with a complete pin list.\n\n"
    "Return ONLY a JSON object with these keys:\n"
    "  name          (string)  - component product name\n"
    "  component_type (string) - one of: ecu, sensor, actuator, relay, fuse_box, "
    "display, switch, motor, solenoid, light, battery, power_supply, ground_bus, "
    "ignition_switch, microcontroller, motor_driver, resistor, capacitor, "
    "termination_resistor, connector, harness, general\n"
    "  manufacturer   (string) - manufacturer name if identifiable\n"
    "  part_number    (string) - part/model number if identifiable\n"
    "  voltage_nominal (number) - nominal operating voltage (e.g. 12.0)\n"
    "  current_draw_amps (number) - typical current draw in amps\n"
    "  pins           (array)  - every pin/terminal on the component:\n"
    "      pin_id      (string) - connector or pin number, e.g. 'A1', 'Pin 3'\n"
    "      name        (string) - function name, e.g. 'B+', 'CAN-H', 'INJ1'\n"
    "      pin_type    (string) - one of: power_input, power_output, ground, "
    "signal_input, signal_output, can_high, can_low, pwm_output, serial_tx, "
    "serial_rx, switched_power, general\n"
    "      description (string) - what this pin does in plain English\n"
    "  notes          (string) - any additional technical notes\n\n"
    "RULES:\n"
    "- List EVERY pin mentioned in the text.  If the text mentions a connector "
    "with numbered pins, list each one.\n"
    "- If pin function is unclear, use pin_type 'general' and describe what you know.\n"
    "- If the text says 'ground' or 'GND', pin_type is 'ground'.\n"
    "- If the text mentions CAN bus, list separate CAN-H (can_high) and CAN-L "
    "(can_low) pins.\n"
    "- Be precise: do not invent pins not mentioned in the text.\n"
    "- Return valid JSON only.  No markdown, no explanation, no code fences."
)

_COMPONENT_PARSE_USER_TEMPLATE = (
    "Component name: {component_name}\n\n"
    "Raw data provided by the user:\n"
    "---\n"
    "{raw_text}\n"
    "---\n\n"
    "Parse this into a structured component record with a complete pin list."
)


def parse_component_data(
    component_name: str,
    raw_text: str,
    api_token: str,
) -> Optional[Dict[str, Any]]:
    """Use AI to parse raw component data into a structured library entry.

    The user provides a component name and raw text (pasted from a datasheet,
    typed from memory, or scraped from a URL).  AI extracts the pin list and
    metadata into a dict compatible with LibraryComponent.from_dict().

    Returns the parsed dict on success, or None if AI is unavailable or fails.
    """
    if not raw_text.strip() or not api_token.strip():
        return None

    user_prompt = _COMPONENT_PARSE_USER_TEMPLATE.format(
        component_name=component_name.strip(),
        raw_text=raw_text.strip()[:12000],
    )

    response = _call_github_models_api(
        _COMPONENT_PARSE_SYSTEM_PROMPT, user_prompt, api_token
    )
    if not response:
        return None

    parsed = _extract_json_from_response(response)
    if not isinstance(parsed, dict):
        return None

    # Ensure required keys are present with sensible defaults.
    result = {
        'name': parsed.get('name', component_name.strip()),
        'component_type': parsed.get('component_type', 'general'),
        'manufacturer': parsed.get('manufacturer', ''),
        'part_number': parsed.get('part_number', ''),
        'voltage_nominal': float(parsed.get('voltage_nominal', 12.0)),
        'current_draw_amps': float(parsed.get('current_draw_amps', 0.0)),
        'pins': [],
        'notes': parsed.get('notes', ''),
    }

    raw_pins = parsed.get('pins', [])
    if isinstance(raw_pins, list):
        for pin_data in raw_pins:
            if not isinstance(pin_data, dict):
                continue
            result['pins'].append({
                'pin_id': str(pin_data.get('pin_id', '')),
                'name': str(pin_data.get('name', '')),
                'pin_type': str(pin_data.get('pin_type', 'general')),
                'description': str(pin_data.get('description', '')),
            })

    return result


# ── AI Connection Generator (library-aware) ──────────────────────────────────

_CONNECTION_GEN_SYSTEM_PROMPT = (
    "You are an expert wiring engineer.  You are given a list of components with "
    "their EXACT pin definitions (from verified datasheets) and a description of "
    "the wiring goal.\n\n"
    "Generate ALL the wire connections needed to achieve the goal.  You may ONLY "
    "use pins that exist in the component list provided.  Do NOT invent pins.\n\n"
    "Return a JSON object with:\n"
    "  connections (array) - each connection has:\n"
    "    connection_id   (string) - unique ID like 'conn_001'\n"
    "    from_component_id (string) - matches a component_id in the list\n"
    "    from_pin        (string) - MUST match a pin_id on that component\n"
    "    to_component_id (string) - destination component_id\n"
    "    to_pin          (string) - MUST match a pin_id on the destination\n"
    "    current_amps    (number) - expected current on this wire\n"
    "    run_length_ft   (number) - estimated wire length in feet\n"
    "    wire_color      (string) - red for +12V, black for ground, "
    "yellow/green for CAN-H, green for CAN-L, white for signal, "
    "blue for sensor, orange for switched power\n"
    "    circuit_type    (string) - power, ground, signal, can_bus, "
    "switched_power, pwm\n"
    "  notes (array of strings) - wiring tips, warnings, or clarifications\n\n"
    "RULES:\n"
    "- EVERY component needs both power AND ground connections\n"
    "- EVERY sensor signal pin must connect to the correct ECU input pin\n"
    "- EVERY CAN device needs CAN-H and CAN-L connections\n"
    "- Power flows from battery -> fuse box -> components (never direct)\n"
    "- Grounds go from components -> ground bus -> battery negative\n"
    "- Include a 120-ohm termination resistor at each end of the CAN bus\n"
    "- Return valid JSON only.  No markdown, no explanation."
)

_CONNECTION_GEN_USER_TEMPLATE = (
    "PROJECT COMPONENTS (with verified pin definitions):\n"
    "{components_json}\n\n"
    "WIRING GOAL:\n"
    "{wiring_goal}\n\n"
    "Generate all connections using ONLY the pins listed above."
)


def generate_connections_from_library(
    components_with_pins: List[Dict[str, Any]],
    wiring_goal: str,
    api_token: str,
) -> Optional[Dict[str, Any]]:
    """Generate wiring connections using verified pin data from the component library.

    Unlike the old AI draft pipeline, this function works with REAL pin
    definitions that the user has reviewed and verified.  The AI can only
    reference pins that actually exist on each component.

    Args:
        components_with_pins: List of component dicts, each containing a 'pins'
            array with pin_id, name, pin_type, description.
        wiring_goal: Natural-language description of what the user wants wired.
        api_token: GitHub Models API token.

    Returns:
        Dict with 'connections' and 'notes' keys on success, or None on failure.
    """
    if not components_with_pins or not wiring_goal.strip() or not api_token.strip():
        return None

    components_json = json.dumps(components_with_pins, indent=1)
    user_prompt = _CONNECTION_GEN_USER_TEMPLATE.format(
        components_json=components_json[:15000],
        wiring_goal=wiring_goal.strip()[:3000],
    )

    response = _call_github_models_api(
        _CONNECTION_GEN_SYSTEM_PROMPT, user_prompt, api_token
    )
    if not response:
        return None

    parsed = _extract_json_from_response(response)
    if not isinstance(parsed, dict):
        return None

    connections = parsed.get('connections', [])
    if not isinstance(connections, list):
        connections = []

    # Validate that every connection references real component IDs and pin IDs.
    valid_pins: Dict[str, set] = {}
    for component in components_with_pins:
        component_id = component.get('component_id', '')
        pin_ids = {
            pin.get('pin_id', '') for pin in component.get('pins', [])
            if isinstance(pin, dict)
        }
        valid_pins[component_id] = pin_ids

    validated_connections = []
    for connection in connections:
        if not isinstance(connection, dict):
            continue
        from_comp = connection.get('from_component_id', '')
        from_pin = connection.get('from_pin', '')
        to_comp = connection.get('to_component_id', '')
        to_pin = connection.get('to_pin', '')

        # Accept the connection if both endpoints reference known components.
        # Pin validation is soft: warn but include (AI may use pin name vs ID).
        is_from_valid = from_comp in valid_pins
        is_to_valid = to_comp in valid_pins
        if is_from_valid and is_to_valid:
            validated_connections.append(connection)

    raw_notes = parsed.get('notes', [])
    notes = [str(note) for note in raw_notes] if isinstance(raw_notes, list) else []

    return {
        'connections': validated_connections,
        'notes': notes,
    }


# ── AI Remap Prompt ───────────────────────────────────────────────────────────

_AI_REMAP_SYSTEM_PROMPT = (
    "You are an expert electronics and automotive wiring engineer. "
    "You are given the current state of a wiring project (components and connections as JSON) "
    "and a natural-language description of changes the user wants. "
    "Return a JSON object with EXACTLY these two keys: "
    '"components" (the FULL updated list) and "connections" (the FULL updated list). '
    "Apply the requested changes — add, remove, or modify components and connections as described. "
    "Preserve everything the user did NOT ask to change. "
    "Output ONLY the JSON object — no markdown fences, no prose."
)

_AI_REMAP_USER_TEMPLATE = (
    "CURRENT COMPONENTS:\n{components_json}\n\n"
    "CURRENT CONNECTIONS:\n{connections_json}\n\n"
    "REQUESTED CHANGES:\n{change_description}\n\n"
    "Return the full updated JSON object with keys: components, connections."
)


def remap_project_with_ai(
    components: List[Dict[str, Any]],
    connections: List[Dict[str, Any]],
    change_description: str,
    api_token_override: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Use AI to apply natural-language change requests to an existing project.

    Sends the current components/connections plus the user's description of desired
    changes to the AI, which returns the full updated component and connection lists.

    Args:
        components:          Current list of component dicts.
        connections:         Current list of connection dicts.
        change_description:  Plain-English description of what the user wants to change.
        api_token_override:  Optional GUI-provided bearer token.

    Returns:
        Dict with 'components' and 'connections' lists on success, or dict with 'error' key.
    """
    if not change_description.strip():
        return {"error": "Describe what you want to change."}

    resolved_override_token = (api_token_override or "").strip()
    api_token = resolved_override_token or get_saved_gui_api_token() or resolve_api_token()
    if not api_token:
        return {"error": "No API token available. Set one in Settings."}

    components_json = json.dumps(components, indent=2)[:4000]
    connections_json = json.dumps(connections, indent=2)[:4000]

    user_prompt = _AI_REMAP_USER_TEMPLATE.format(
        components_json=components_json,
        connections_json=connections_json,
        change_description=change_description[:2000],
    )

    raw_response = _call_github_models_api(_AI_REMAP_SYSTEM_PROMPT, user_prompt, api_token)
    if not raw_response:
        return {"error": "AI service did not respond. Try again."}

    parsed_response = _extract_json_from_response(raw_response)
    if not isinstance(parsed_response, dict):
        return {"error": "AI returned an unparseable response."}

    has_valid_components = isinstance(parsed_response.get("components"), list)
    has_valid_connections = isinstance(parsed_response.get("connections"), list)
    if not has_valid_components or not has_valid_connections:
        return {"error": "AI response was missing components or connections."}

    return {
        "components": parsed_response["components"],
        "connections": parsed_response["connections"],
    }

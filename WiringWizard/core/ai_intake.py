"""
AI-assisted intake module for WiringWizard — converts a free-text project brief into a
structured component/connection draft suitable for populating the WiringWizard UI.
"""

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

# Component types that supply power to the rest of the circuit.
POWER_SOURCE_TYPES = frozenset({"battery", "power_supply"})

# Component types that consume power (candidates for wiring from a source).
POWER_LOAD_TYPES = frozenset({
    "microcontroller", "ecu", "relay", "led_load", "light", "motor", "servo",
    "fan", "pump", "sensor", "display", "buzzer", "solenoid", "stepper", "motor_driver",
})

# ── AI Prompt Templates ───────────────────────────────────────────────────────

_AI_SYSTEM_PROMPT = (
    "You are an expert electronics and automotive wiring engineer assistant. "
    "Given a free-text project brief, you produce a structured wiring project draft as JSON. "
    "Your output MUST be a single valid JSON object and nothing else — no markdown fences, no prose. "
    "Component IDs must be simple snake_case identifiers (e.g. battery1, ecu1, fuse_box1). "
    "Preserve the user's named products and modules as component_name values whenever possible. "
    "If reference material is supplied, use it to identify modules, dashboards, keypads, harnesses, manuals, and pinouts.\n\n"

    "AUTOMOTIVE POWER DISTRIBUTION:\n"
    "Model realistic power distribution: Battery positive → main fuse → ignition switch → fuse box → relays → loads. "
    "Not every load connects directly to the battery. "
    "Always-hot circuits (clock, alarm, ECU keep-alive) tap before the ignition switch. "
    "Ignition-ON circuits (ECU main, fuel pump, sensors) tap after the ignition switch in the RUN position. "
    "Accessory circuits (radio, USB, interior lights) tap from the ACC position.\n\n"

    "GROUND CONNECTIONS ARE MANDATORY:\n"
    "Every component MUST have a ground return path — either to a chassis ground point or a ground bus bar. "
    "Never omit ground wires. Use dedicated ground wires; do not assume chassis return unless the user specifies it. "
    "Ground connections use circuit_type 'ground'.\n\n"

    "FUSE PROTECTION:\n"
    "Every power circuit MUST include an appropriately sized fuse. "
    "Fuse rating should be approximately 125-150% of the circuit's maximum expected current draw. "
    "Include the fuse as a component and wire it in-line on the power feed to each load or load group.\n\n"

    "RELAY-CONTROLLED LOADS:\n"
    "High-current loads drawing more than 5 amps (headlights, cooling fans, fuel pump, starter, horns) "
    "MUST be switched through a relay. Wire the relay coil from the control source (switch, ECU output) "
    "and the relay contacts on the high-current path from fused power to the load.\n\n"

    "CAN BUS WIRING:\n"
    "When the project includes CAN bus devices (ECUs, dashboards, keypads, body controllers), "
    "wire CAN-H and CAN-L as a daisy-chained bus between all CAN nodes. "
    "Place 120-ohm termination resistors at each physical end of the bus. "
    "Use circuit_type 'can_bus' for CAN-H and CAN-L connections. "
    "CAN wires should be a twisted pair (typically CAN-H = YELLOW, CAN-L = GREEN or BLUE).\n\n"

    "PIN-LEVEL CONNECTIONS:\n"
    "Specify actual pin names or numbers whenever the component datasheet or reference material provides them "
    "(e.g. 'ECU Pin A1', 'Relay Pin 87', 'Sensor Pin SIG'). "
    "When pin information is unavailable, use descriptive functional labels "
    "(e.g. 'V+', 'GND', 'SIG_OUT', 'CAN_H', 'CAN_L', 'COIL+', 'NO', 'NC', 'COM').\n\n"

    "WIRE COLORS:\n"
    "Use standard automotive wire color conventions: "
    "RED = +12V always-hot, YELLOW = +12V ignition-switched, ORANGE = +12V accessory, "
    "BLACK = ground, WHITE/BLACK = ground return, BLUE = headlights/high-beam, "
    "GREEN = CAN-L or right-turn, YELLOW/GREEN = CAN-H, "
    "PINK or WHITE = signal/sensor wires, BROWN = tail/parking lights. "
    "For non-automotive projects, use RED = V+, BLACK = GND, and distinct colors per signal.\n\n"

    "SIGNAL vs POWER WIRES:\n"
    "Distinguish signal wires (low-current analog/digital sensor lines, communication buses) from power wires. "
    "Signal wires are typically 20-22 AWG; power wires are sized for the load current. "
    "Use wire_gauge_awg 'auto' when the system should calculate gauge from current and run length.\n\n"

    "HARNESS AND KIT DECOMPOSITION (CRITICAL):\n"
    "A wiring harness, harness kit, or engine harness is NOT a single component — it is a bundle of wires "
    "that connects MANY individual components. When the user mentions a harness (e.g. 'OHM Racing Engine Harness', "
    "'mil-spec harness', 'fusebox harness'), do NOT list it as one component. Instead, decompose it into "
    "EVERY individual component the harness connects:\n"
    "  - For a typical 4-cylinder engine harness (e.g. 4g63, 4g64, 2JZ-GE, LS1): list each injector individually "
    "(Injector #1, Injector #2, Injector #3, Injector #4), the cam angle sensor, the crank angle sensor, "
    "the ignition coil pack or individual coils, the coolant temperature sensor, the intake air temperature sensor, "
    "the manifold absolute pressure sensor or MAP sensor, the throttle position sensor or drive-by-wire throttle body, "
    "the alternator, the wideband O2 sensor, the oil pressure sensor, the fuel pump relay, and any other sensors "
    "the user specifies (flex fuel, fuel pressure, knock sensor, etc.).\n"
    "  - For a fusebox/relay box harness: list the fuse box, each relay (fuel pump relay, fan relay, headlight relay, etc.), "
    "the ignition switch input, the alternator charge wire, and all switched and always-on power distribution circuits.\n"
    "  - A harness is infrastructure — the COMPONENTS it connects are what go in the diagram.\n"
    "  - Wire each decomposed component with its power supply pin, ground pin, signal pins, and any CAN or data pins.\n\n"

    "COMMON ENGINE KNOWLEDGE:\n"
    "Use this domain knowledge when the user mentions these engines/platforms:\n"
    "  4g63 (Mitsubishi Eclipse/Eagle Talon/Evo): 4 high-impedance fuel injectors, CAS (cam angle sensor) or "
    "individual cam+crank sensors (97-99), coil pack (waste-spark), MAP sensor, IAT sensor, coolant temp sensor, "
    "TPS or DBW throttle body, alternator, oil pressure switch. The 7-bolt (95-99 2G) uses a 97-99 cam and crank "
    "trigger pattern. Denso high-impedance injectors are a common upgrade.\n"
    "  W4A33 transmission: solenoid pack (shift solenoids A/B, TCC solenoid, pressure control solenoid), "
    "input/output speed sensors, gear select switch, neutral safety switch, ATF temperature sensor.\n"
    "  Emtron KV8: standalone ECU with 8 injector drivers, 8 ignition outputs, CAN bus, wideband controller input, "
    "analog and digital inputs for sensors. Can control engine AND transmission when properly configured — "
    "no separate TCU required if user says so. CAN bus connects to ED10M dash and CAN keypad.\n"
    "  ED10M dash + 8-button CAN keypad: connects via CAN bus to ECU. Keypad buttons can be mapped to "
    "functions (launch control, traction control, pit limiter, etc.). Both need +12V power, ground, CAN-H, CAN-L.\n\n"

    "RESPECT USER COMPONENT CHOICES:\n"
    "Do NOT add components the user did not request. "
    "If the user says one component handles multiple roles (e.g. 'KV8 handles engine and transmission'), "
    "do NOT add a separate controller for the handled role — do NOT add a TCU or SMART150. "
    "If the user says to remove or exclude a component (e.g. 'remove knock sensor', 'no ABS', 'remove boost controller'), "
    "do NOT include it. "
    "Match the user's parts list exactly — only add required infrastructure "
    "(fuses, relays, ground bus, termination resistors) that the user's build implicitly needs.\n\n"

    "NON-AUTOMOTIVE PROJECTS:\n"
    "For general electronics projects (CNC machines, 3D printers, home electrical, LED installations), "
    "apply the same principles: proper power distribution from the supply through fusing to loads, "
    "mandatory ground returns, relay control for high-current loads, and pin-level connections where known."
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
    '      "component_type": "battery|power_supply|microcontroller|ecu|relay|fuse|fuse_box|'
    'ground_bus|termination_resistor|ignition_switch|'
    'led_load|light|motor|servo|fan|pump|sensor|switch|display|buzzer|solenoid|stepper|motor_driver",\n'
    '      "current_draw_amps": number,\n'
    '      "position_label": "location or TBD",\n'
    '      "pins": ["pin1_name", "pin2_name"]\n'
    "    }}\n"
    "  ],\n"
    '  "connections": [\n'
    "    {{\n"
    '      "connection_id": "conn_001",\n'
    '      "from_component_id": "source_id",\n'
    '      "from_pin": "specific pin name/number",\n'
    '      "to_component_id": "destination_id",\n'
    '      "to_pin": "specific pin name/number",\n'
    '      "current_amps": number,\n'
    '      "run_length_ft": number,\n'
    '      "wire_color": "color",\n'
    '      "wire_gauge_awg": "number or auto",\n'
    '      "circuit_type": "power_always_on|power_ignition|power_accessory|ground|signal_analog|signal_digital|can_bus|data"\n'
    "    }}\n"
    "  ],\n"
    '  "notes": ["string warning or tip", "..."]\n'
    "}}\n\n"
    "MANDATORY RULES — every output MUST satisfy ALL of these:\n"
    "1. EVERY component MUST have at least one ground connection (circuit_type 'ground') back to a ground bus or chassis ground point.\n"
    "2. CAN bus devices MUST have CAN-H and CAN-L connections (circuit_type 'can_bus') with 120-ohm termination resistors at each end of the bus.\n"
    "3. High-current loads drawing more than 5A MUST route through a relay — wire the relay coil from the control source and relay contacts on the power path.\n"
    "4. Every power connection MUST pass through an appropriately sized fuse (125-150%% of max expected current).\n"
    "5. Do NOT add components the user did not ask for — respect their parts list exactly. Only add essential infrastructure (fuses, relays, ground bus, termination resistors).\n"
    "6. If the user says one component handles multiple roles (e.g. 'KV8 handles engine and transmission'), do NOT add a separate controller for the handled role.\n"
    "7. Pin names MUST be as specific as possible — use actual datasheet pin names/numbers when reference material is available; otherwise use descriptive functional labels (V+, GND, SIG_OUT, CAN_H, CAN_L, COIL+, NO, COM).\n"
    "8. Component IDs in connections MUST exactly match component_id values listed in the components array.\n"
    "9. List each component's known or expected pins in the 'pins' array so the diagram is self-documenting.\n"
    "10. NEVER list a wiring harness as a single component — ALWAYS decompose it into individual sensors, injectors, coils, actuators, and other components that the harness connects. A harness is wires, not a device.\n"
    "11. Each individual injector, ignition coil, and sensor MUST be listed as its own component (e.g. Injector #1, Injector #2, Injector #3, Injector #4 — not just 'Fuel Injectors').\n"
    "12. Use reference material and domain knowledge to determine realistic current draws, wire gauges, and run lengths — do NOT default everything to the same values."
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

    Fetches each URL, extracts page title / meta description, and discovers links
    to manuals, schematics, and pinout documents.  The research context string is
    appended to the AI prompt; the notes list is shown to the user in the draft.

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

        product_specs = _extract_product_specs(page_html)
        if product_specs:
            context_lines.append(f"  Product Details: {product_specs}")

        for link_label, link_url in _extract_reference_links(page_html, reference_url):
            context_lines.append(f"  Related Doc: {link_label} — {link_url}")
            research_notes.append(
                f"Possible schematic or pinout document: {link_label} — {link_url}"
            )

            # Multi-hop: fetch linked manuals/datasheets and extract their content
            linked_html = _fetch_reference_page_html(link_url)
            if not linked_html:
                continue
            linked_title = _extract_reference_title(linked_html) or link_label
            linked_specs = _extract_product_specs(linked_html)
            if linked_specs:
                context_lines.append(f"    Deep Reference ({linked_title}): {linked_specs}")
                research_notes.append(f"Deep reference extracted: {linked_title}")

    # If no pages were fetched successfully, return empty.
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
    # Enrich the brief with any reference material from supplied URLs.
    research_context, _ = _build_reference_research_context(brief_text)
    enriched_brief = brief_text
    if research_context:
        enriched_brief = f"{brief_text}\n\n{research_context}"

    user_prompt = _AI_USER_PROMPT_TEMPLATE.format(brief_text=enriched_brief[:12000])
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

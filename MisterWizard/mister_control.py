"""
Mister/Coolant Control Logic for FusionCam.
Manages configuration, G-code injection, and test sequencing
for a solenoid-driven mist coolant system on the Onefinity Machinist.

Hardware context:
  - Buildbotics controller (Onefinity) has M7 (mist) and M8 (flood) outputs
  - GPIO pins are 5V logic — solenoid MUST be wired through a relay/opto-isolator
  - M7 → Mist coolant ON | M8 → Flood coolant ON | M9 → All coolant OFF

G-code injection strategy:
  1. Fusion 360 CAM sets coolant type per-operation (cleanest)
  2. Post-process then inject into .nc file (fallback for manual control)
"""

import json
import os
import re
import shutil

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ADDIN_DIR, 'data')
CONFIG_DIR = os.path.join(ADDIN_DIR, 'config')

# Buildbotics output pin definitions
BUILDBOTICS_PINS = {
    'M7_mist': {
        'label': 'M7 — Mist Coolant (recommended)',
        'gcode_on': 'M7',
        'gcode_off': 'M9',
        'description': 'Standard mist coolant output. Mapped to the Buildbotics mist GPIO pin.',
        'voltage': '5V TTL (requires relay for solenoid)',
        'notes': 'Most compatible. Fusion 360 CAM natively supports mist coolant per-operation.'
    },
    'M8_flood': {
        'label': 'M8 — Flood Coolant',
        'gcode_on': 'M8',
        'gcode_off': 'M9',
        'description': 'Flood coolant output. Use if your relay is wired to the flood pin.',
        'voltage': '5V TTL (requires relay for solenoid)',
        'notes': 'Use if M7 pin is unavailable or already in use.'
    },
    'custom_m': {
        'label': 'Custom M-Code (advanced)',
        'gcode_on': None,  # User-specified
        'gcode_off': None,
        'description': 'Use a custom M-code if you have modified your controller firmware.',
        'voltage': 'Depends on firmware configuration',
        'notes': 'Advanced users only. Requires firmware customization.'
    }
}

# Default mister configuration
DEFAULT_CONFIG = {
    'enabled': False,
    'pin_mode': 'M7_mist',
    'custom_gcode_on': '',
    'custom_gcode_off': '',
    'pre_mist_delay_seconds': 2.0,
    'post_mist_delay_seconds': 5.0,
    'apply_to_materials': ['aluminum_6061_t6', 'aluminum_6063'],
    'apply_to_all_metals': True,
    'solenoid_voltage': '12V',
    'relay_type': 'normally_open',
    'wiring_confirmed': False,
    'test_completed': False,
    'notes': ''
}


def load_mister_config():
    """Load the mister configuration from user settings."""
    path = os.path.join(DATA_DIR, 'user_settings.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings.get('mister', dict(DEFAULT_CONFIG))
    return dict(DEFAULT_CONFIG)


def save_mister_config(config):
    """Save the mister configuration to user settings."""
    path = os.path.join(DATA_DIR, 'user_settings.json')
    settings = {}
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            settings = json.load(f)
    settings['mister'] = config
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)


def get_gcode_commands(config=None):
    """
    Get the G-code ON/OFF commands based on current configuration.
    Returns (on_command, off_command) tuple.
    """
    if config is None:
        config = load_mister_config()

    pin_mode = config.get('pin_mode', 'M7_mist')

    if pin_mode == 'custom_m':
        on_cmd = config.get('custom_gcode_on', 'M7').strip() or 'M7'
        off_cmd = config.get('custom_gcode_off', 'M9').strip() or 'M9'
    else:
        pin_def = BUILDBOTICS_PINS.get(pin_mode, BUILDBOTICS_PINS['M7_mist'])
        on_cmd = pin_def['gcode_on']
        off_cmd = pin_def['gcode_off']

    return on_cmd, off_cmd


def should_use_mister(material_key, config=None):
    """
    Determine if the mister should be used for a given material.
    Returns True/False.
    """
    if config is None:
        config = load_mister_config()

    if not config.get('enabled', False):
        return False

    # Check if this material needs coolant
    materials_path = os.path.join(CONFIG_DIR, 'materials.json')
    if os.path.exists(materials_path):
        with open(materials_path, 'r', encoding='utf-8') as f:
            materials = json.load(f)

        mat = materials.get('materials', {}).get(material_key, {})
        coolant = mat.get('coolant', 'none')
        mat_category = mat.get('category', '')

        # Apply to metals if configured
        if config.get('apply_to_all_metals') and mat_category == 'metal':
            return True

        # Check per-material list
        if material_key in config.get('apply_to_materials', []):
            return True

        # Apply if material requires or recommends coolant
        if coolant in ('required', 'recommended'):
            return True

    return False


def get_coolant_mode_for_material(material_key):
    """
    Get the recommended Fusion 360 coolant mode for a material.
    Returns 'mist', 'flood', or 'none'.
    """
    materials_path = os.path.join(CONFIG_DIR, 'materials.json')
    if not os.path.exists(materials_path):
        return 'none'

    with open(materials_path, 'r', encoding='utf-8') as f:
        materials = json.load(f)

    mat = materials.get('materials', {}).get(material_key, {})
    coolant = mat.get('coolant', 'none')

    if coolant in ('required', 'recommended'):
        return 'mist'  # We use mist (M7) for hobby CNC
    return 'none'


def inject_into_gcode(nc_file_path, config=None, output_path=None):
    """
    Inject mister ON/OFF commands into an existing .nc G-code file.

    Strategy: Insert M7 before every M3 (spindle on) with a delay,
    and M9 after every M5 (spindle off) with a delay.

    Args:
        nc_file_path: Path to the source .nc file
        config: Mister config dict (loads from settings if None)
        output_path: Output path (overwrites source if None)

    Returns:
        Path to the modified file, and a summary of changes made.
    """
    if config is None:
        config = load_mister_config()

    if not config.get('enabled', False):
        return nc_file_path, 'Mister disabled — no changes made.'

    on_cmd, off_cmd = get_gcode_commands(config)
    pre_delay = config.get('pre_mist_delay_seconds', 2.0)
    post_delay = config.get('post_mist_delay_seconds', 5.0)

    # G4 P<seconds> = dwell/wait command
    pre_dwell = f'G4 P{pre_delay:.1f}' if pre_delay > 0 else ''
    post_dwell = f'G4 P{post_delay:.1f}' if post_delay > 0 else ''

    with open(nc_file_path, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    injections = 0

    for line in lines:
        stripped = line.strip().upper()

        # Before spindle ON (M3 or M4)
        if re.match(r'^M0*[34]\b', stripped):
            new_lines.append(f'; FusionCam Mister: coolant ON\n')
            new_lines.append(f'{on_cmd}\n')
            if pre_dwell:
                new_lines.append(f'{pre_dwell} ; Wait {pre_delay}s for mist to flow before cutting\n')
            new_lines.append(line)
            injections += 1
            continue

        # After spindle OFF (M5)
        if re.match(r'^M0*5\b', stripped):
            new_lines.append(line)
            if post_dwell:
                new_lines.append(f'{post_dwell} ; Wait {post_delay}s for final cooling\n')
            new_lines.append(f'{off_cmd} ; FusionCam Mister: coolant OFF\n')
            injections += 1
            continue

        new_lines.append(line)

    if output_path is None:
        output_path = nc_file_path

    with open(output_path, 'w', encoding='utf-8') as f:
        f.writelines(new_lines)

    summary = (
        f'Mister commands injected:\n'
        f'  {on_cmd} added before {injections // 2} spindle-on events (with {pre_delay}s pre-delay)\n'
        f'  {off_cmd} added after {injections // 2} spindle-off events (with {post_delay}s post-delay)\n'
        f'  Output: {output_path}'
    )
    return output_path, summary


def generate_test_gcode(config=None):
    """
    Generate a short test G-code sequence to verify mister operation.
    This file can be sent to the Onefinity to test the solenoid
    without any actual cutting.

    Returns: G-code string and output file path.
    """
    if config is None:
        config = load_mister_config()

    on_cmd, off_cmd = get_gcode_commands(config)
    pre_delay = config.get('pre_mist_delay_seconds', 2.0)
    post_delay = config.get('post_mist_delay_seconds', 5.0)

    gcode = f"""; FusionCam Mister Test Sequence
; Generated by MisterWizard
; Machine: Onefinity Machinist
; Pin Mode: {config.get('pin_mode', 'M7_mist')}
; Coolant ON: {on_cmd}  Coolant OFF: {off_cmd}
;
; DO NOT RUN WITH A TOOL INSTALLED — this is a solenoid test only
; Safety: Router/spindle is NOT started in this test
;
G21           ; Metric mode
G90           ; Absolute coordinates
G17           ; XY plane

; --- TEST 1: Basic ON/OFF ---
; Turn mist ON
{on_cmd}
G4 P3.0       ; Hold for 3 seconds — verify mist is flowing
; Turn mist OFF
{off_cmd}
G4 P2.0       ; Wait 2 seconds

; --- TEST 2: Simulate Pre/Post spindle delays ---
; (Spindle NOT actually started — M3 commented out)
{on_cmd}
G4 P{pre_delay:.1f}  ; Pre-mist delay ({pre_delay}s) — mist should be flowing before this ends
; M3 S18000   ; <-- Spindle would start here (commented for safety)
G4 P3.0       ; Simulate 3 seconds of cutting
; M5           ; <-- Spindle would stop here
G4 P{post_delay:.1f}  ; Post-mist delay ({post_delay}s) — continued cooling
{off_cmd}
G4 P1.0

; --- TEST COMPLETE ---
; If mist fired and stopped correctly, your wiring is good!
M2            ; End program
"""

    output_dir = os.path.join(os.path.expanduser('~'), 'Documents', 'FusionCam', 'GCode')
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, 'mister_test.nc')

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(gcode)

    return gcode, output_path


def validate_config(config):
    """
    Validate a mister configuration dict.
    Returns (is_valid: bool, errors: list[str], warnings: list[str]).
    """
    errors = []
    warnings = []

    if config.get('pin_mode') == 'custom_m':
        if not config.get('custom_gcode_on', '').strip():
            errors.append('Custom ON G-code command is required when using custom M-code mode.')
        if not config.get('custom_gcode_off', '').strip():
            errors.append('Custom OFF G-code command is required when using custom M-code mode.')

    pre = config.get('pre_mist_delay_seconds', 0)
    post = config.get('post_mist_delay_seconds', 0)

    if pre < 1.0:
        warnings.append(
            f'Pre-mist delay is {pre}s — mist may not reach the cut zone before cutting starts. '
            'Recommend at least 1-2 seconds.'
        )
    if pre > 10.0:
        warnings.append(f'Pre-mist delay of {pre}s is very long — cycle times will increase significantly.')

    if post < 2.0:
        warnings.append(
            f'Post-mist delay is {post}s — the workpiece may not cool fully. '
            'Recommend at least 2-5 seconds for aluminum.'
        )

    if not config.get('wiring_confirmed', False):
        warnings.append(
            'Wiring has not been confirmed. Run the physical test sequence before machining.'
        )

    return len(errors) == 0, errors, warnings


def get_wiring_diagram(solenoid_voltage='12V', relay_type='normally_open'):
    """
    Return a text-based wiring diagram for the mister solenoid.
    """
    return f"""
╔══════════════════════════════════════════════════════════════════════════╗
║              MISTER SOLENOID WIRING — ONEFINITY MACHINIST               ║
║                   Solenoid: {solenoid_voltage}  Relay: {relay_type.replace('_',' ').title()}                    ║
╠══════════════════════════════════════════════════════════════════════════╣
║                                                                          ║
║  BUILDBOTICS BOARD                                                       ║
║  ┌─────────────┐                                                         ║
║  │  M7 / Mist  │──── 220Ω ────┬──── [LED Indicator] ──── GND           ║
║  │  GPIO (5V)  │              │                                          ║
║  │             │              └──── [Opto-Isolator Input+]              ║
║  │     GND     │─────────────────── [Opto-Isolator Input-]              ║
║  └─────────────┘                                                         ║
║                          OPTO-ISOLATOR (TLP291 or PC817)                 ║
║                          ┌─────────────────────────────┐                 ║
║                          │  Input+  →  LED anode        │                ║
║                          │  Input-  →  LED cathode      │                ║
║                          │                              │                ║
║                          │  Output (collector) ─────────┼──→ Relay+     ║
║                          │  Output (emitter) ───────────┼──→ Relay-     ║
║                          └─────────────────────────────┘                 ║
║                                                                          ║
║  EXTERNAL {solenoid_voltage} CIRCUIT                                           ║
║  ┌───────────────────────────────────────────────────────────┐           ║
║  │                                                           │           ║
║  │  {solenoid_voltage} PSU (+) ──── Relay Common ──[Relay Contact]──┐       │           ║
║  │                                                  │       │           ║
║  │  [1N4007 Diode] ←──────────────┐               │       │           ║
║  │  (Cathode to +, Anode to -)   │               ↓       │           ║
║  │                               ├──── Solenoid Coil (+) │           ║
║  │  {solenoid_voltage} PSU (-) ──────────────────────── Solenoid Coil (-) │           ║
║  │                                                           │           ║
║  └───────────────────────────────────────────────────────────┘           ║
║                                                                          ║
║  ⚠️  CRITICAL SAFETY NOTES:                                              ║
║  • NEVER connect solenoid directly to GPIO — relay/opto required         ║
║  • The 1N4007 flyback diode protects relay from solenoid back-EMF        ║
║  • Share GND between Buildbotics and {solenoid_voltage} supply (common ground)    ║
║  • Test with multimeter BEFORE connecting solenoid                       ║
║  • If using 24V, ensure relay coil rating matches PSU voltage            ║
╚══════════════════════════════════════════════════════════════════════════╝

PARTS LIST:
  • Opto-isolator: TLP291, PC817, or 4N25 (cheap, widely available)
  • Resistor: 220Ω ¼W (current limiter for opto LED)
  • Relay: 5V coil, {solenoid_voltage} contacts, 10A rated (SRD-05VDC-SL-C, HiLetgo)
    NOTE: If opto output voltage is 3.3V, use 3.3V coil relay
  • Flyback diode: 1N4007 (standard rectifier diode)
  • {solenoid_voltage} power supply: 2A minimum for solenoid
  • Solenoid valve: Normally-closed pneumatic solenoid (opens when energized)
    Example: SMC VX210 or generic 2-port NC 1/4" NPT solenoid

MIST SYSTEM OPTIONS:
  • Loc-Line mist system with solenoid valve (most common hobbyist setup)
  • Fog Buster / SuperMist (self-contained, just needs solenoid trigger)
  • DIY: Aquarium air pump + solenoid + 1/4" tubing
  • Recommended lubricant: Isopropyl alcohol (IPA) 70-99% for aluminum
    (WD-40 works too but leaves more residue)
"""


def get_checklist():
    """Return the pre-machining mister checklist."""
    return [
        "☐ Solenoid valve is connected to mist/coolant supply line",
        "☐ Solenoid wiring verified with wiring diagram",
        "☐ Test G-code run successfully — mist fires and stops on command",
        "☐ Mist nozzle aimed at the cutting zone (not at the operator)",
        "☐ Coolant reservoir has sufficient fluid (IPA/WD-40)",
        "☐ Drain/catch tray in place for coolant runoff",
        "☐ M7 command tested manually from Onefinity MDI console",
        "☐ Post-mist delay is long enough for chip cooling",
        "☐ Relay LED indicator confirmed working",
        "☐ No coolant dripping onto controller or electronics",
    ]

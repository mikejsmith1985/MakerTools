"""
Feeds & Speeds Calculator for FusionCam.
Provides deterministic (heuristic) calculation as the primary method,
with AI-powered calculation as an enhancement for edge cases.
"""

import math
import json
import os

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ADDIN_DIR, 'config')


def _load_machine_profile():
    """Load the active machine profile."""
    path = os.path.join(CONFIG_DIR, 'machine_profiles.json')
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    active = data.get('active_machine', 'onefinity_machinist')
    return data['machines'][active]


def _load_materials():
    """Load the materials database."""
    path = os.path.join(CONFIG_DIR, 'materials.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _nearest_rpm_setting(target_rpm, speed_settings):
    """Find the nearest Makita RT0701C dial RPM setting."""
    return min(speed_settings, key=lambda s: abs(s - target_rpm))


def _diameter_to_chipload_key(diameter_inches):
    """Map a tool diameter to the nearest chipload table key."""
    standard_sizes = {
        0.125: '1/8',
        0.1875: '3/16',
        0.25: '1/4',
        0.375: '3/8',
        0.5: '1/2'
    }

    # Find nearest standard size
    nearest = min(standard_sizes.keys(), key=lambda s: abs(s - diameter_inches))
    return standard_sizes[nearest]


def calculate(tool, material_key, operation_type='roughing', quality='standard'):
    """
    Calculate feeds and speeds using deterministic formulas.

    Args:
        tool: Tool dict with at minimum diameter_inches, flute_count, flute_length_inches
        material_key: Key into the materials database (e.g., 'aluminum_6061_t6')
        operation_type: 'roughing', 'finishing', 'drilling', or 'adaptive'
        quality: 'draft', 'standard', or 'fine'

    Returns:
        Dict with rpm, feed_rate, doc, woc, etc.
    """
    machine = _load_machine_profile()
    materials_db = _load_materials()

    material = materials_db['materials'].get(material_key)
    if not material:
        raise ValueError(f'Unknown material: {material_key}')

    # Load quality presets
    templates_path = os.path.join(CONFIG_DIR, 'operation_templates.json')
    with open(templates_path, 'r', encoding='utf-8') as f:
        templates = json.load(f)
    quality_preset = templates['quality_presets'].get(quality, templates['quality_presets']['standard'])

    diameter_in = tool.get('diameter_inches', 0.25)
    diameter_mm = diameter_in * 25.4
    flute_count = tool.get('flute_count', 2)
    flute_length_in = tool.get('flute_length_inches', diameter_in * 3)
    flute_length_mm = flute_length_in * 25.4

    rigidity = machine['rigidity_factor']
    spindle = machine['spindle']
    max_feed_xy = machine['max_feed_rate']['xy']
    max_feed_z = machine['max_feed_rate']['z']

    # --- RPM Calculation ---
    # SFM = π × D × RPM / 12  →  RPM = SFM × 12 / (π × D)
    sfm_range = material['sfm_range']
    # Use midpoint of SFM range for standard, lower for conservative
    if operation_type == 'roughing' or operation_type == 'adaptive':
        target_sfm = sfm_range['min'] + (sfm_range['max'] - sfm_range['min']) * 0.4
    elif operation_type == 'finishing':
        target_sfm = sfm_range['min'] + (sfm_range['max'] - sfm_range['min']) * 0.7
    else:
        target_sfm = sfm_range['min'] + (sfm_range['max'] - sfm_range['min']) * 0.5

    target_rpm = (target_sfm * 12) / (math.pi * diameter_in)

    # Clamp to spindle range
    target_rpm = max(spindle['min_rpm'], min(spindle['max_rpm'], target_rpm))
    actual_rpm = _nearest_rpm_setting(target_rpm, spindle['speed_settings'])
    actual_sfm = (math.pi * diameter_in * actual_rpm) / 12

    # Determine which dial setting
    dial_setting = spindle['speed_settings'].index(actual_rpm) + 1

    # --- Chipload ---
    chipload_key = _diameter_to_chipload_key(diameter_in)
    chipload_table = material.get('chipload_table', {})
    chipload_entry = chipload_table.get(chipload_key, {'min': 0.001, 'max': 0.003, 'recommended': 0.002})

    if operation_type == 'finishing':
        chipload = chipload_entry['min'] + (chipload_entry['recommended'] - chipload_entry['min']) * 0.5
    elif operation_type == 'adaptive':
        # Adaptive can use higher chipload due to reduced engagement
        chipload = chipload_entry['recommended'] * 1.1
    else:
        chipload = chipload_entry['recommended']

    # --- Feed Rate ---
    # Feed = RPM × chipload × flute_count × rigidity_factor × quality_multiplier
    feed_ipm = actual_rpm * chipload * flute_count * rigidity * quality_preset.get('feed_multiplier', 1.0)
    feed_mm_min = feed_ipm * 25.4

    # Clamp to machine limits
    feed_mm_min = min(feed_mm_min, max_feed_xy)
    feed_ipm = feed_mm_min / 25.4

    # Recalculate actual chipload after clamping
    actual_chipload = feed_mm_min / (actual_rpm * flute_count * 25.4) if actual_rpm > 0 else 0

    # --- Depth of Cut ---
    doc_multiplier = material.get('doc_multiplier', 0.5)
    doc_mm = diameter_mm * doc_multiplier * rigidity * quality_preset.get('doc_multiplier', 1.0)

    # Ensure DOC doesn't exceed flute length
    doc_mm = min(doc_mm, flute_length_mm * 0.8)
    doc_in = doc_mm / 25.4

    # --- Width of Cut (Stepover) ---
    if operation_type in ('roughing', 'adaptive'):
        woc_multiplier = material.get('woc_multiplier_roughing', 0.4)
    else:
        woc_multiplier = material.get('woc_multiplier_finishing', 0.1)

    woc_mm = diameter_mm * woc_multiplier * quality_preset.get('stepover_multiplier', 1.0)
    woc_in = woc_mm / 25.4

    # --- Plunge Rate ---
    plunge_mm_min = feed_mm_min * 0.35  # 35% of XY feed
    plunge_mm_min = min(plunge_mm_min, max_feed_z)
    plunge_ipm = plunge_mm_min / 25.4

    # --- Ramp angle ---
    safety = machine.get('safety_defaults', {})
    max_ramp = safety.get('max_plunge_angle_degrees', 3.0)

    # --- Build result ---
    result = {
        'rpm': actual_rpm,
        'rpm_dial_setting': dial_setting,
        'sfm': round(actual_sfm, 1),
        'feed_rate_mm_min': round(feed_mm_min, 1),
        'feed_rate_ipm': round(feed_ipm, 2),
        'plunge_rate_mm_min': round(plunge_mm_min, 1),
        'plunge_rate_ipm': round(plunge_ipm, 2),
        'doc_mm': round(doc_mm, 2),
        'doc_inches': round(doc_in, 4),
        'woc_mm': round(woc_mm, 2),
        'woc_inches': round(woc_in, 4),
        'chipload_inches': round(actual_chipload, 5),
        'flute_count': flute_count,
        'ramp_angle_degrees': max_ramp,
        'operation_type': operation_type,
        'quality': quality,
        'material': material.get('name', material_key),
        'tool_diameter_mm': round(diameter_mm, 2),
        'tool_diameter_inches': diameter_in,
        'source': 'calculated',
        'notes': _generate_notes(material, operation_type, actual_chipload, chipload_entry)
    }

    return result


def _generate_notes(material, operation_type, actual_chipload, chipload_entry):
    """Generate human-readable notes about the calculation."""
    notes = []

    # Coolant reminder
    coolant = material.get('coolant', 'none')
    if coolant in ('required', 'recommended'):
        coolant_notes = material.get('coolant_notes', 'Use appropriate coolant/lubricant.')
        notes.append(f'⚠️ Coolant {coolant}: {coolant_notes}')

    # Chipload warnings
    if actual_chipload < chipload_entry.get('min', 0):
        notes.append('⚠️ Chipload below minimum — risk of rubbing instead of cutting. '
                     'Consider fewer flutes or higher feed rate.')
    elif actual_chipload > chipload_entry.get('max', 999):
        notes.append('⚠️ Chipload above maximum — risk of tool breakage. '
                     'Consider more flutes or lower feed rate.')

    # Material-specific tips
    material_notes = material.get('notes', '')
    if material_notes:
        notes.append(f'💡 {material_notes}')

    return ' | '.join(notes) if notes else 'Parameters within recommended range.'


def calculate_for_drilling(tool, material_key, hole_depth_mm, quality='standard'):
    """
    Specialized feeds/speeds for drilling operations.

    Drilling has different rules:
    - No stepover (full engagement)
    - Peck depth instead of DOC
    - Lower feed rate due to full engagement
    """
    machine = _load_machine_profile()
    materials_db = _load_materials()
    material = materials_db['materials'].get(material_key)
    if not material:
        raise ValueError(f'Unknown material: {material_key}')

    diameter_in = tool.get('diameter_inches', 0.25)
    diameter_mm = diameter_in * 25.4
    rigidity = machine['rigidity_factor']
    spindle = machine['spindle']

    sfm_range = material['sfm_range']
    target_sfm = sfm_range['min'] + (sfm_range['max'] - sfm_range['min']) * 0.3

    target_rpm = (target_sfm * 12) / (math.pi * diameter_in)
    target_rpm = max(spindle['min_rpm'], min(spindle['max_rpm'], target_rpm))
    actual_rpm = _nearest_rpm_setting(target_rpm, spindle['speed_settings'])

    chipload_key = _diameter_to_chipload_key(diameter_in)
    chipload_table = material.get('chipload_table', {})
    chipload_entry = chipload_table.get(chipload_key, {'recommended': 0.001})

    # Drilling chipload is typically 50-70% of milling chipload
    chipload = chipload_entry['recommended'] * 0.6

    feed_ipm = actual_rpm * chipload * 2 * rigidity  # 2 flutes for drill
    feed_mm_min = feed_ipm * 25.4
    feed_mm_min = min(feed_mm_min, machine['max_feed_rate']['z'])

    # Peck depth: typically 1-3x drill diameter
    peck_mm = diameter_mm * 1.5 * rigidity

    return {
        'rpm': actual_rpm,
        'rpm_dial_setting': spindle['speed_settings'].index(actual_rpm) + 1,
        'feed_rate_mm_min': round(feed_mm_min, 1),
        'feed_rate_ipm': round(feed_mm_min / 25.4, 2),
        'peck_depth_mm': round(peck_mm, 2),
        'peck_depth_inches': round(peck_mm / 25.4, 4),
        'hole_depth_mm': hole_depth_mm,
        'retract_mm': 2.0,
        'dwell_seconds': 0.5 if material.get('category') == 'metal' else 0,
        'operation_type': 'drilling',
        'source': 'calculated'
    }

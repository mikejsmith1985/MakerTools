"""
WiringWizard domain profiles — per-domain rules, typical wire colours, common component
types, and safety notes for automotive, CNC/control, 3D printer, and home electrical wiring.
"""

from typing import Any, Dict, List

# ── Domain profile registry ──
# Each entry describes one supported wiring domain.
DOMAIN_PROFILES: Dict[str, Dict[str, Any]] = {
    'automotive': {
        'display_name': 'Automotive / 12V–24V',
        'default_voltage_class': 'lv_12v',
        'allowed_voltage_classes': ('lv_5v', 'lv_12v', 'lv_24v'),
        'wire_standard': 'chassis_wiring',
        'typical_wire_colors': {
            'positive': 'red',
            'negative': 'black',
            'ground': 'black',
            'signal': 'yellow',
            'lighting': 'orange',
            'ignition': 'pink',
        },
        'common_components': [
            'battery', 'fuse_block', 'relay', 'switch', 'motor',
            'light', 'sensor', 'ecu',
        ],
        'fuse_required': True,
        'is_mains': False,
        'notes': (
            'Use marine-grade or automotive-rated GXL/TXL wire. '
            'Chassis ground is standard — connect to clean bare metal. '
            'Always fuse within 18" of the power source.'
        ),
    },
    'cnc_control': {
        'display_name': 'CNC / Control Panel Wiring',
        'default_voltage_class': 'lv_24v',
        'allowed_voltage_classes': ('lv_5v', 'lv_12v', 'lv_24v', 'lv_48v'),
        'wire_standard': 'control_wiring',
        'typical_wire_colors': {
            'power': 'red',
            'ground': 'black',
            'signal': 'yellow',
            'estop': 'red',
            'step': 'green',
            'direction': 'white',
            'enable': 'blue',
        },
        'common_components': [
            'controller', 'stepper_driver', 'stepper_motor', 'limit_switch',
            'e_stop', 'power_supply', 'relay', 'spindle_driver',
        ],
        'fuse_required': True,
        'is_mains': False,
        'notes': (
            'Use shielded cable for step/dir signals to reduce EMI. '
            'Keep signal and power wires physically separated by at least 2 inches. '
            'Use ferrules on all stranded wires in screw terminals.'
        ),
    },
    '3d_printer': {
        'display_name': '3D Printer Electronics',
        'default_voltage_class': 'lv_24v',
        'allowed_voltage_classes': ('lv_5v', 'lv_12v', 'lv_24v'),
        'wire_standard': 'control_wiring',
        'typical_wire_colors': {
            'power': 'red',
            'ground': 'black',
            'thermistor': 'yellow',
            'heater': 'white',
            'fan': 'blue',
            'step': 'green',
            'endstop': 'orange',
        },
        'common_components': [
            'mainboard', 'hotend', 'heated_bed', 'stepper_motor',
            'thermistor', 'fan', 'endstop', 'power_supply', 'probe',
        ],
        'fuse_required': True,
        'is_mains': False,
        'notes': (
            'Use silicone wire for hotend and bed connections (high-flex, heat-tolerant). '
            'Always fuse the heated bed circuit. '
            'Route thermistor wires away from heater wires to avoid noise.'
        ),
    },
    'home_electrical': {
        'display_name': 'Home Electrical (Mains)',
        'default_voltage_class': 'mains_120v',
        'allowed_voltage_classes': ('mains_120v', 'mains_240v'),
        'wire_standard': 'nec',
        'typical_wire_colors': {
            'hot': 'black',
            'neutral': 'white',
            'ground': 'green',
            'traveler': 'red',
        },
        'common_components': [
            'outlet', 'switch', 'breaker', 'junction_box', 'light_fixture',
        ],
        'fuse_required': True,
        'is_mains': True,
        'notes': (
            'SAFETY: Full mains circuit plans are out of scope for WiringWizard v1. '
            'A safety checklist is provided instead. '
            'Always hire a licensed electrician for mains wiring work.'
        ),
    },
}


def get_domain_profile(domain: str) -> Dict[str, Any]:
    """Return the profile dict for the given domain name. Raises KeyError if unknown."""
    if domain not in DOMAIN_PROFILES:
        raise KeyError(
            f'Unknown domain: {domain!r}. '
            f'Supported domains: {list(DOMAIN_PROFILES.keys())}'
        )
    return DOMAIN_PROFILES[domain]


def list_domains() -> List[str]:
    """Return a list of all supported domain identifier strings."""
    return list(DOMAIN_PROFILES.keys())


def is_mains_domain(domain: str) -> bool:
    """Return True if the given domain involves mains (AC line-voltage) wiring."""
    profile = get_domain_profile(domain)
    return bool(profile.get('is_mains', False))

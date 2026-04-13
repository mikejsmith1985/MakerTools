"""
WiringWizard wire sizing — recommends AWG wire gauge based on current load,
run length, and voltage class using SAE J1128 chassis-wiring ampacity values
and a 3% maximum voltage-drop limit.
"""

from typing import Any, Dict

# ── AWG ampacity and resistance table ──
# Ampacity values from SAE J1128 (open-air chassis wiring).
# Resistance values in ohms per 1 000 ft at 20 °C for annealed copper.
AWG_TABLE: Dict[str, Dict[str, float]] = {
    '22':  {'ampacity': 3.0,   'resistance_ohms_per_1000ft': 16.14},
    '20':  {'ampacity': 5.0,   'resistance_ohms_per_1000ft': 10.15},
    '18':  {'ampacity': 7.0,   'resistance_ohms_per_1000ft': 6.385},
    '16':  {'ampacity': 13.0,  'resistance_ohms_per_1000ft': 4.016},
    '14':  {'ampacity': 20.0,  'resistance_ohms_per_1000ft': 2.525},
    '12':  {'ampacity': 27.0,  'resistance_ohms_per_1000ft': 1.588},
    '10':  {'ampacity': 40.0,  'resistance_ohms_per_1000ft': 0.9989},
    '8':   {'ampacity': 55.0,  'resistance_ohms_per_1000ft': 0.6282},
    '6':   {'ampacity': 75.0,  'resistance_ohms_per_1000ft': 0.3951},
    '4':   {'ampacity': 100.0, 'resistance_ohms_per_1000ft': 0.2485},
    '2':   {'ampacity': 130.0, 'resistance_ohms_per_1000ft': 0.1563},
    '1/0': {'ampacity': 165.0, 'resistance_ohms_per_1000ft': 0.09827},
    '2/0': {'ampacity': 195.0, 'resistance_ohms_per_1000ft': 0.07793},
    '3/0': {'ampacity': 225.0, 'resistance_ohms_per_1000ft': 0.06180},
    '4/0': {'ampacity': 260.0, 'resistance_ohms_per_1000ft': 0.04901},
}

# AWG sizes ordered from smallest to largest for iterative selection
AWG_ORDER = [
    '22', '20', '18', '16', '14', '12', '10',
    '8', '6', '4', '2', '1/0', '2/0', '3/0', '4/0',
]

# Maximum allowable voltage drop percentage per voltage class.
# 5V systems are the most sensitive because even a small drop is a large percentage.
MAX_VOLTAGE_DROP_PERCENT: Dict[str, float] = {
    'lv_5v':      3.0,
    'lv_12v':     3.0,
    'lv_24v':     3.0,
    'lv_48v':     3.0,
    'mains_120v': 3.0,
    'mains_240v': 3.0,
}

# Nominal voltage for each voltage class — used to convert drop percentage to volts
NOMINAL_VOLTAGE: Dict[str, float] = {
    'lv_5v':      5.0,
    'lv_12v':     12.0,
    'lv_24v':     24.0,
    'lv_48v':     48.0,
    'mains_120v': 120.0,
    'mains_240v': 240.0,
}


def recommend_awg(
    current_amps: float,
    run_length_ft: float,
    voltage_class: str,
) -> Dict[str, Any]:
    """
    Recommend the smallest AWG wire gauge that satisfies both:
      1. Ampacity — the wire can handle the current without overheating.
      2. Voltage drop — the round-trip drop stays within the allowed percentage.

    Returns a dict with keys:
      recommended_awg       (str)   e.g. '14'
      ampacity              (float) ampacity of the chosen gauge
      voltage_drop_volts    (float) calculated round-trip voltage drop
      voltage_drop_percent  (float) drop as % of nominal voltage
      is_ampacity_limited   (bool)  True when ampacity drove the selection
      notes                 (str)   human-readable explanation
    """
    nominal_voltage = NOMINAL_VOLTAGE.get(voltage_class, 12.0)
    max_drop_pct = MAX_VOLTAGE_DROP_PERCENT.get(voltage_class, 3.0)
    max_drop_volts = nominal_voltage * (max_drop_pct / 100.0)

    # Voltage drop uses the round-trip conductor length (out + return path)
    round_trip_ft = run_length_ft * 2.0

    selected_awg = None
    is_ampacity_limited = False

    for awg in AWG_ORDER:
        row = AWG_TABLE[awg]

        if row['ampacity'] < current_amps:
            continue  # Insufficient ampacity — try the next heavier gauge

        resistance_ohms = (row['resistance_ohms_per_1000ft'] / 1000.0) * round_trip_ft
        voltage_drop = current_amps * resistance_ohms

        if voltage_drop <= max_drop_volts:
            selected_awg = awg
            is_ampacity_limited = _check_if_ampacity_limited(awg, current_amps)
            break

    if selected_awg is None:
        # Largest gauge in the table is still insufficient — use it with a warning
        selected_awg = AWG_ORDER[-1]
        is_ampacity_limited = True

    row = AWG_TABLE[selected_awg]
    resistance_ohms = (row['resistance_ohms_per_1000ft'] / 1000.0) * round_trip_ft
    voltage_drop_volts = round(current_amps * resistance_ohms, 4)
    voltage_drop_percent = round((voltage_drop_volts / nominal_voltage) * 100.0, 2)

    notes = _build_sizing_notes(
        selected_awg, current_amps, voltage_drop_percent, max_drop_pct, row['ampacity']
    )

    return {
        'recommended_awg': selected_awg,
        'ampacity': row['ampacity'],
        'voltage_drop_volts': voltage_drop_volts,
        'voltage_drop_percent': voltage_drop_percent,
        'is_ampacity_limited': is_ampacity_limited,
        'notes': notes,
    }


def calculate_voltage_drop(awg: str, current_amps: float, run_length_ft: float) -> float:
    """
    Calculate the round-trip voltage drop in volts for a known AWG gauge, current, and
    one-way run length.  Uses both outgoing and return conductors.
    """
    if awg not in AWG_TABLE:
        raise ValueError(f'Unknown AWG: {awg!r}. Supported gauges: {AWG_ORDER}')

    round_trip_ft = run_length_ft * 2.0
    resistance_ohms = (AWG_TABLE[awg]['resistance_ohms_per_1000ft'] / 1000.0) * round_trip_ft
    return round(current_amps * resistance_ohms, 4)


def _check_if_ampacity_limited(selected_awg: str, current_amps: float) -> bool:
    """
    Return True if the previous (smaller) gauge would fail the ampacity check,
    meaning ampacity — not voltage drop — is the binding constraint.
    """
    current_index = AWG_ORDER.index(selected_awg)
    if current_index == 0:
        return True  # Already at the smallest gauge
    smaller_awg = AWG_ORDER[current_index - 1]
    return AWG_TABLE[smaller_awg]['ampacity'] < current_amps


def _build_sizing_notes(
    awg: str,
    current_amps: float,
    drop_percent: float,
    max_drop_pct: float,
    ampacity: float,
) -> str:
    """Build a plain-English note explaining the wire sizing recommendation."""
    headroom_pct = round(((ampacity - current_amps) / ampacity) * 100)
    notes = [
        f'AWG {awg}: {ampacity}A capacity, {headroom_pct}% current headroom.',
        f'Voltage drop: {drop_percent}% (limit {max_drop_pct}%).',
    ]

    if drop_percent > max_drop_pct * 0.8:
        notes.append(
            '\u26a0 Approaching voltage-drop limit — '
            'consider a heavier gauge for this run.'
        )

    if awg in ('22', '20') and current_amps > 2.0:
        notes.append(
            '\U0001f4a1 Tip: Use crimped insulated terminals for small-gauge connections.'
        )

    return ' '.join(notes)

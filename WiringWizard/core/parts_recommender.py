"""
WiringWizard parts recommender — suggests wire types, connectors, terminals,
fuse/relay sizing, and tooling based on the project domain, voltage class,
and the connection records produced by the planner.
"""

from typing import Any, Dict, List

from .domain_profiles import get_domain_profile
from .planner import build_connection_records
from .project_schema import WiringProject

# ── Standard fuse sizes (amps) — blade-type automotive / panel-mount ──
# A fuse is chosen at >= 125% of maximum sustained load current (SAE J1284).
STANDARD_FUSE_SIZES_AMPS = [
    1, 2, 3, 5, 7.5, 10, 15, 20, 25, 30, 40, 50, 60, 80, 100, 125, 150, 200,
]


def recommend_fuse_amps(max_current_amps: float) -> float:
    """
    Return the smallest standard fuse rating >= 125% of max_current_amps.
    Follows the NEC / SAE convention of sizing the overcurrent device to 125% of load.
    """
    target_amps = max_current_amps * 1.25
    for fuse_size in STANDARD_FUSE_SIZES_AMPS:
        if fuse_size >= target_amps:
            return fuse_size
    # Load exceeds the table — return the largest available and warn in calling code
    return STANDARD_FUSE_SIZES_AMPS[-1]


def build_wire_bom(project: WiringProject) -> List[Dict[str, Any]]:
    """
    Build a Bill of Materials for wire by collecting unique AWG + colour combinations
    from all connections and summing run lengths.  Adds 20% extra for routing slack
    and re-termination allowance.
    Returns a list of BOM line-item dicts sorted from smallest to largest AWG.
    """
    connection_records = build_connection_records(project)

    # Accumulate totals keyed by 'awg_colour'
    wire_totals: Dict[str, Dict[str, Any]] = {}
    for record in connection_records:
        bom_key = f"{record['effective_awg']}_{record['wire_color']}"
        if bom_key not in wire_totals:
            wire_totals[bom_key] = {
                'awg':              record['effective_awg'],
                'color':            record['wire_color'],
                'total_run_ft':     0.0,
                'connection_count': 0,
            }
        wire_totals[bom_key]['total_run_ft'] += record['run_length_ft']
        wire_totals[bom_key]['connection_count'] += 1

    bom_items = []
    for entry in wire_totals.values():
        purchase_ft = round(entry['total_run_ft'] * 1.2, 1)
        bom_items.append({
            'item':             f"AWG {entry['awg']} {entry['color']} wire",
            'awg':              entry['awg'],
            'color':            entry['color'],
            'net_run_ft':       round(entry['total_run_ft'], 1),
            'purchase_ft':      purchase_ft,
            'connection_count': entry['connection_count'],
        })

    bom_items.sort(key=lambda item: _awg_sort_key(item['awg']))
    return bom_items


def build_tooling_recommendations(project: WiringProject) -> List[str]:
    """
    Return a list of tool and supply recommendations tailored to the project domain.
    Always starts with the universal minimum toolkit, then appends domain-specific items.
    """
    domain_name = project.profile.domain

    tools = [
        'Wire stripper — auto-adjusting, suitable for AWG 10–22',
        'Ratcheting crimping tool — for insulated terminals and ring/spade lugs',
        'Digital multimeter — continuity, voltage, and resistance modes',
        'Heat gun — for heat-shrink tubing',
        'Electrical tape or split-loom conduit — for wire protection and routing',
    ]

    if domain_name == 'automotive':
        tools += [
            'Fuse puller and spare blade-fuse assortment (ATC/ATO and mini)',
            'Ring terminal set — for chassis ground connections',
            'Wire loom / split conduit — for under-dash and under-hood routing',
            'Heat-shrink butt splice connectors',
        ]
    elif domain_name == 'cnc_control':
        tools += [
            'Ferrule crimper and ferrule assortment — for stranded wires in screw terminals',
            'DIN rail terminal blocks and end caps',
            'Shielded cable for step/dir signal runs',
            'Cable ties and DIN-rail mounting clips',
            'Panel labels or heat-shrink wire markers',
        ]
    elif domain_name == '3d_printer':
        tools += [
            'Silicone wire assortment — high-flex and heat-tolerant for hotend/bed',
            'JST-XH and JST-PH crimp connector kits with pin removal tool',
            'Cable drag chain — for X/Y/Z moving-axis cable management',
            'Kapton tape — for securing thermistor wires near heat sources',
        ]
    elif domain_name == 'home_electrical':
        tools += [
            'Non-contact voltage tester — ALWAYS verify power is OFF before touching wires',
            'Circuit breaker lockout / tagout devices',
            'Wire nuts or Wago 221 lever-nut connectors',
        ]

    return tools


def build_connector_recommendations(project: WiringProject) -> List[str]:
    """
    Return a list of connector and terminal type recommendations based on the domain
    and the AWG gauges used in the project.
    """
    connection_records = build_connection_records(project)
    awg_values_used = {record['effective_awg'] for record in connection_records}
    domain_name = project.profile.domain

    recommendations: List[str] = []

    if domain_name == 'automotive':
        recommendations.append(
            'Use weatherproof Deutsch DT or TE AMP connectors for any outdoor or underhood runs.'
        )
        recommendations.append(
            'Use nylon-insulated ring terminals for battery and chassis-ground connections.'
        )
        heavy_gauges = {'4', '2', '1/0', '2/0', '3/0', '4/0'}
        if awg_values_used & heavy_gauges:
            recommendations.append(
                'AWG 4 and larger: use copper compression lugs, not regular crimp terminals.'
            )

    elif domain_name in ('cnc_control', '3d_printer'):
        recommendations.append(
            'Use ferrules on all stranded wire ends that insert into screw-terminal blocks.'
        )
        recommendations.append(
            'Use JST-XH 2.54 mm pitch connectors for small signal connections '
            '(endstops, thermistors, fans).'
        )
        recommendations.append(
            'Use XT30 or XT60 connectors for high-current (> 10A) power connections.'
        )

    elif domain_name == 'home_electrical':
        recommendations.append(
            'Use Wago 221 lever-nut connectors (preferred) or wire nuts for junction-box splices.'
        )
        recommendations.append(
            'Use insulated spade terminals for device screw-terminal connections.'
        )

    return recommendations


def build_fuse_relay_recommendations(project: WiringProject) -> List[str]:
    """
    Return fuse and relay sizing recommendations by examining the total current
    leaving each identified power-source component.
    """
    domain_profile = get_domain_profile(project.profile.domain)
    recommendations: List[str] = []

    if not domain_profile.get('fuse_required', False):
        return recommendations

    # Sum current for each source component
    source_currents: Dict[str, float] = {}
    for conn in project.connections:
        source_currents[conn.from_component_id] = (
            source_currents.get(conn.from_component_id, 0.0) + conn.current_amps
        )

    # Identify power-source components by their type keyword
    power_type_keywords = {'battery', 'power_supply', 'psu'}
    found_power_source = False

    for component in project.components:
        normalized_type = component.component_type.lower().replace(' ', '_').replace('-', '_')
        is_power_source = any(keyword in normalized_type for keyword in power_type_keywords)
        if is_power_source:
            found_power_source = True
            total_current = source_currents.get(
                component.component_id, component.current_draw_amps
            )
            fuse_rating = recommend_fuse_amps(total_current)
            recommendations.append(
                f'{component.component_name}: total load = {total_current:.1f}A '
                f'\u2192 install a {fuse_rating}A fuse within 18" of this source.'
            )

    if not found_power_source:
        recommendations.append(
            'Add a fuse or circuit breaker at the power source. '
            'Size to 125% of the maximum sustained load current.'
        )

    return recommendations


def _awg_sort_key(awg: str) -> float:
    """Return a numeric sort key for AWG strings so that BOM entries sort small-to-large."""
    special_cases = {'1/0': 105.0, '2/0': 110.0, '3/0': 115.0, '4/0': 120.0}
    if awg in special_cases:
        return special_cases[awg]
    try:
        return float(awg)
    except ValueError:
        return 999.0

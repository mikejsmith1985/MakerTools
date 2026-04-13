"""
WiringWizard step builder — generates a numbered list of child-friendly, plain-English
installation steps for completing the wiring project.  For mains (home electrical)
domains, only the safety checklist is returned per the v1 scope limitation.
"""

from typing import Any, Dict, List

from .domain_profiles import get_domain_profile, is_mains_domain
from .planner import build_connection_records
from .project_schema import WiringProject

# ── Mains safety checklist ──
# Replaces a full wiring plan for home-electrical projects in v1.
MAINS_SAFETY_CHECKLIST: List[str] = [
    '\u26a0  STOP: WiringWizard v1 does NOT generate full mains (120V/240V AC) circuit plans.',
    '\u26a0  Working with mains voltage is dangerous and can cause fire, injury, or death.',
    '\u26a0  Always hire a licensed electrician for any new mains circuit work.',
    '',
    'SAFETY CHECKLIST (reference only \u2014 not a substitute for professional work):',
    '  1. Turn off the circuit breaker for the circuit you are working on.',
    '  2. Use a non-contact voltage tester to CONFIRM the circuit is dead before touching wires.',
    '  3. Tag the breaker with a lockout device so nobody can turn it back on while you work.',
    '  4. Never work alone on mains wiring.',
    '  5. Use wire rated for the application (NM-B/Romex for dry residential runs, etc.).',
    '  6. Do not exceed 80% of the breaker rating for continuous loads (NEC 210.20).',
    '  7. All splices must be inside accessible, covered junction boxes.',
    '  8. Connect all ground wires. Never leave a ground disconnected.',
    '  9. Have your work inspected by a licensed electrician before restoring power.',
    ' 10. Check local permit requirements \u2014 many jurisdictions require a permit for new circuits.',
]


def build_step_list(
    project: WiringProject,
    connection_records: List[Dict[str, Any]] = None,
) -> List[str]:
    """
    Generate a numbered list of plain-language installation steps for the wiring project.

    For mains (home electrical) domains: returns only MAINS_SAFETY_CHECKLIST.
    For low-voltage domains: returns actionable, child-friendly wiring steps.

    If connection_records is not provided it is generated automatically from the project.
    """
    if is_mains_domain(project.profile.domain):
        return list(MAINS_SAFETY_CHECKLIST)

    if connection_records is None:
        connection_records = build_connection_records(project)

    domain_profile = get_domain_profile(project.profile.domain)
    steps: List[str] = []
    step_number = 1

    steps.append(
        f'Step {step_number}: SAFETY FIRST \u2014 Disconnect all power before you start. '
        f'Unplug the power supply or disconnect the battery terminal.'
    )
    step_number += 1

    steps.append(
        f'Step {step_number}: Gather all your wires, terminals, connectors, and tools before '
        f'you begin. Check that you have the correct AWG wire for each connection '
        f'(see the Connection Table for details).'
    )
    step_number += 1

    steps.append(
        f'Step {step_number}: Cut each wire to the length shown in the Connection Table, '
        f'adding 6\u201312 inches of extra length for routing and working room. '
        f'Label both ends of every wire with a marker or label maker.'
    )
    step_number += 1

    steps.append(
        f'Step {step_number}: Strip about 1/4 inch (6 mm) of insulation from each end '
        f'of every wire. Be careful not to nick the copper strands inside.'
    )
    step_number += 1

    steps.append(
        f'Step {step_number}: Crimp the correct terminal or connector pin onto each wire end. '
        f'Give each crimp a firm tug to confirm it is secure. '
        f'Slide heat-shrink tubing over the joint and shrink it with a heat gun.'
    )
    step_number += 1

    steps.append(
        f'Step {step_number}: Make each connection one at a time, in the order listed below:'
    )
    step_number += 1

    for conn_index, record in enumerate(connection_records):
        steps.append(
            f'  Connection {conn_index + 1} ({record["connection_id"]}): '
            f'Connect the {record["wire_color"]} AWG\u202f{record["effective_awg"]} wire from '
            f'{record["from_component_name"]} pin \u201c{record["from_pin"]}\u201d '
            f'to {record["to_component_name"]} pin \u201c{record["to_pin"]}\u201d. '
            f'This wire carries {record["current_amps"]}A over {record["run_length_ft"]} ft.'
        )

    # Fuse installation reminder for domains that require it
    if domain_profile.get('fuse_required'):
        steps.append(
            f'Step {step_number}: Install fuses or circuit breakers as shown in the '
            f'Fuse/Protection section. Always fuse within 18 inches of the power source. '
            f'NEVER skip this step \u2014 a missing fuse can cause fire.'
        )
        step_number += 1

    steps.append(
        f'Step {step_number}: Before applying power, check that: '
        f'(a) every connection matches the Connection Table, '
        f'(b) no bare wire is exposed or touching metal chassis, '
        f'(c) all terminals are fully seated and crimps are tight.'
    )
    step_number += 1

    steps.append(
        f'Step {step_number}: Apply power carefully. '
        f'Watch for smoke, sparks, or a burning smell. '
        f'If anything seems wrong, disconnect power immediately and re-check your connections. '
        f'Use a multimeter to verify voltage at each component before connecting loads.'
    )

    return steps

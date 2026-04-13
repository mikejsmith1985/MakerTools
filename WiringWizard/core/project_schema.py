"""
WiringWizard project schema — defines the data structures for a wiring project,
including the project profile, individual components, and wire connections.
"""

from dataclasses import dataclass, field
from typing import List, Optional

# Supported domain identifiers (human labels live in domain_profiles.py)
SUPPORTED_DOMAINS = ('automotive', 'cnc_control', '3d_printer', 'home_electrical')

# Voltage class identifiers — lv = low-voltage DC, mains = AC
SUPPORTED_VOLTAGE_CLASSES = ('lv_5v', 'lv_12v', 'lv_24v', 'lv_48v', 'mains_120v', 'mains_240v')


@dataclass
class ProjectProfile:
    """High-level description of a wiring project — name, domain, and voltage class."""

    project_name: str
    domain: str          # one of SUPPORTED_DOMAINS
    voltage_class: str   # one of SUPPORTED_VOLTAGE_CLASSES
    description: str = ''


@dataclass
class Component:
    """A single electrical component (device, module, or node) in the wiring system."""

    component_id: str         # unique short identifier, e.g. 'psu1'
    component_name: str       # human-readable name, e.g. 'Main Power Supply'
    component_type: str       # functional type, e.g. 'power_supply', 'motor', 'sensor'
    current_draw_amps: float  # maximum sustained current draw in amps
    position_label: str = ''  # optional human-readable location, e.g. 'rear-panel'


@dataclass
class Connection:
    """A single wire run between two component pins."""

    connection_id: str           # unique short identifier, e.g. 'conn_01'
    from_component_id: str       # source component ID
    from_pin: str                # source pin label, e.g. '+12V' or 'OUT_A'
    to_component_id: str         # destination component ID
    to_pin: str                  # destination pin label
    current_amps: float          # maximum current this wire must carry
    run_length_ft: float         # wire run length in feet
    wire_color: str = 'red'
    awg_override: Optional[str] = None  # user-specified gauge; None = auto-size


@dataclass
class WiringProject:
    """The complete wiring project — profile, component list, and connection list."""

    profile: ProjectProfile
    components: List[Component] = field(default_factory=list)
    connections: List[Connection] = field(default_factory=list)

    def find_component(self, component_id: str) -> Optional[Component]:
        """Return the Component with the given ID, or None if not found."""
        for component in self.components:
            if component.component_id == component_id:
                return component
        return None

    def find_connection(self, connection_id: str) -> Optional[Connection]:
        """Return the Connection with the given ID, or None if not found."""
        for connection in self.connections:
            if connection.connection_id == connection_id:
                return connection
        return None

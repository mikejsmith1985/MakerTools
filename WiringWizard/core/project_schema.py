"""
WiringWizard project schema — defines the data structures for a wiring project,
including the project profile, individual components, wire connections, and the
reusable component library with pin-level detail.
"""

from dataclasses import dataclass, field
from typing import List, Optional

# Supported domain identifiers (human labels live in domain_profiles.py)
SUPPORTED_DOMAINS = ('automotive', 'cnc_control', '3d_printer', 'home_electrical')

# Voltage class identifiers — lv = low-voltage DC, mains = AC
SUPPORTED_VOLTAGE_CLASSES = ('lv_5v', 'lv_12v', 'lv_24v', 'lv_48v', 'mains_120v', 'mains_240v')

# Standardised pin electrical types — used by the library and the AI connection
# generator to understand what each pin does without guessing.
PIN_TYPES = (
    'power_input',     # receives +V from external source
    'power_output',    # provides +V to other components
    'ground',          # chassis or signal ground return
    'signal_input',    # analog or digital sensor input
    'signal_output',   # analog or digital driver output
    'can_high',        # CAN bus high line
    'can_low',         # CAN bus low line
    'pwm_output',      # pulse-width modulation driver (injectors, coils)
    'serial_tx',       # serial transmit
    'serial_rx',       # serial receive
    'switched_power',  # ignition-switched / relay-switched +V
    'general',         # unclassified or multi-purpose
)


# ── Component Library Structures ──────────────────────────────────────────────

@dataclass
class Pin:
    """A single electrical pin on a library component."""

    pin_id: str            # connector/pin identifier, e.g. 'A1', 'Pin 3'
    name: str              # human-readable function, e.g. 'B+', 'CAN1-H'
    pin_type: str = 'general'   # one of PIN_TYPES
    description: str = ''  # free-text explanation of what this pin does


@dataclass
class LibraryComponent:
    """A reusable component template stored in the component library.

    Users build the library over time by providing datasheets, manual excerpts,
    or raw text which AI parses into structured pin lists.  When a library
    component is added to a project the pin definitions travel with it so the
    AI connection generator works with verified data instead of guessing.
    """

    library_id: str              # unique slug, e.g. 'emtron-kv8'
    name: str                    # human-readable name, e.g. 'Emtron KV8 ECU'
    component_type: str          # functional type: ecu, sensor, fuse_box, etc.
    pins: List[Pin] = field(default_factory=list)

    manufacturer: str = ''
    part_number: str = ''
    voltage_nominal: float = 12.0
    current_draw_amps: float = 0.0
    notes: str = ''              # technical notes from datasheet
    user_notes: str = ''         # owner's personal notes
    source_urls: List[str] = field(default_factory=list)
    is_verified: bool = False    # True after the user confirms pin accuracy
    created_at: str = ''         # ISO-8601 date string
    updated_at: str = ''         # ISO-8601 date string

    # ── Convenience helpers ───────────────────────────────────────────────

    def find_pin(self, pin_id: str) -> Optional[Pin]:
        """Return the Pin with the given pin_id, or None if not found."""
        for pin in self.pins:
            if pin.pin_id == pin_id:
                return pin
        return None

    def pins_by_type(self, pin_type: str) -> List[Pin]:
        """Return all pins matching the requested electrical type."""
        return [pin for pin in self.pins if pin.pin_type == pin_type]

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for JSON storage."""
        return {
            'library_id': self.library_id,
            'name': self.name,
            'component_type': self.component_type,
            'pins': [
                {
                    'pin_id': pin.pin_id,
                    'name': pin.name,
                    'pin_type': pin.pin_type,
                    'description': pin.description,
                }
                for pin in self.pins
            ],
            'manufacturer': self.manufacturer,
            'part_number': self.part_number,
            'voltage_nominal': self.voltage_nominal,
            'current_draw_amps': self.current_draw_amps,
            'notes': self.notes,
            'user_notes': self.user_notes,
            'source_urls': list(self.source_urls),
            'is_verified': self.is_verified,
            'created_at': self.created_at,
            'updated_at': self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LibraryComponent':
        """Deserialise from a plain dict (e.g. loaded from JSON)."""
        raw_pins = data.get('pins', [])
        pin_objects = [
            Pin(
                pin_id=pin_data.get('pin_id', ''),
                name=pin_data.get('name', ''),
                pin_type=pin_data.get('pin_type', 'general'),
                description=pin_data.get('description', ''),
            )
            for pin_data in raw_pins
            if isinstance(pin_data, dict)
        ]
        return cls(
            library_id=data.get('library_id', ''),
            name=data.get('name', ''),
            component_type=data.get('component_type', ''),
            pins=pin_objects,
            manufacturer=data.get('manufacturer', ''),
            part_number=data.get('part_number', ''),
            voltage_nominal=float(data.get('voltage_nominal', 12.0)),
            current_draw_amps=float(data.get('current_draw_amps', 0.0)),
            notes=data.get('notes', ''),
            user_notes=data.get('user_notes', ''),
            source_urls=list(data.get('source_urls', [])),
            is_verified=bool(data.get('is_verified', False)),
            created_at=data.get('created_at', ''),
            updated_at=data.get('updated_at', ''),
        )


# ── Project-Level Structures (unchanged API) ─────────────────────────────────


@dataclass
class ProjectProfile:
    """High-level description of a wiring project — name, domain, and voltage class."""

    project_name: str
    domain: str          # one of SUPPORTED_DOMAINS
    voltage_class: str   # one of SUPPORTED_VOLTAGE_CLASSES
    description: str = ''


@dataclass
class Component:
    """A single electrical component (device, module, or node) in the wiring system.

    When sourced from the component library the ``pins`` list carries verified
    pin definitions.  The ``library_id`` links back to the original library
    entry so updates can be propagated.
    """

    component_id: str         # unique short identifier, e.g. 'psu1'
    component_name: str       # human-readable name, e.g. 'Main Power Supply'
    component_type: str       # functional type, e.g. 'power_supply', 'motor', 'sensor'
    current_draw_amps: float  # maximum sustained current draw in amps
    position_label: str = ''  # optional human-readable location, e.g. 'rear-panel'
    library_id: str = ''      # library component this was sourced from (empty if manual)
    pins: List[Pin] = field(default_factory=list)  # pin definitions from library


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

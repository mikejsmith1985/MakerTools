"""
Unit tests for the component library module — CRUD operations, search,
default seeding, schema serialisation, and AI parse mocking.
"""

import json
import os
import shutil
import tempfile
import unittest
from unittest.mock import patch

from core.project_schema import LibraryComponent, Pin, PIN_TYPES
from core.component_library import (
    load_library,
    save_library,
    add_component,
    update_component,
    delete_component,
    get_component,
    search_library,
    list_component_types,
)


def _make_component(
    library_id: str = "test-comp",
    name: str = "Test Component",
    component_type: str = "sensor",
    pins: list = None,
) -> LibraryComponent:
    """Helper to create a minimal LibraryComponent for testing."""
    if pins is None:
        pins = [
            Pin(pin_id="1", name="VCC", pin_type="power_input", description="Power"),
            Pin(pin_id="2", name="GND", pin_type="ground", description="Ground"),
            Pin(pin_id="3", name="SIG", pin_type="signal_output", description="Signal"),
        ]
    return LibraryComponent(
        library_id=library_id,
        name=name,
        component_type=component_type,
        pins=pins,
        manufacturer="TestCorp",
        voltage_nominal=12.0,
        current_draw_amps=0.5,
    )


class TestPinSchema(unittest.TestCase):
    """Verify Pin dataclass behaviour."""

    def test_pin_defaults(self) -> None:
        pin = Pin(pin_id="A1", name="Test")
        self.assertEqual(pin.pin_type, "general")
        self.assertEqual(pin.description, "")

    def test_pin_types_constant_is_tuple(self) -> None:
        self.assertIsInstance(PIN_TYPES, tuple)
        self.assertIn("power_input", PIN_TYPES)
        self.assertIn("can_high", PIN_TYPES)


class TestLibraryComponentSchema(unittest.TestCase):
    """Verify LibraryComponent serialisation round-trip."""

    def test_to_dict_and_from_dict_roundtrip(self) -> None:
        original = _make_component()
        as_dict = original.to_dict()
        restored = LibraryComponent.from_dict(as_dict)
        self.assertEqual(restored.library_id, original.library_id)
        self.assertEqual(restored.name, original.name)
        self.assertEqual(len(restored.pins), len(original.pins))
        self.assertEqual(restored.pins[0].pin_id, "1")
        self.assertEqual(restored.pins[0].pin_type, "power_input")

    def test_from_dict_handles_missing_keys(self) -> None:
        minimal = {"library_id": "x", "name": "X", "component_type": "sensor"}
        comp = LibraryComponent.from_dict(minimal)
        self.assertEqual(comp.pins, [])
        self.assertEqual(comp.voltage_nominal, 12.0)

    def test_find_pin_by_id(self) -> None:
        comp = _make_component()
        self.assertIsNotNone(comp.find_pin("2"))
        self.assertIsNone(comp.find_pin("nonexistent"))

    def test_pins_by_type(self) -> None:
        comp = _make_component()
        grounds = comp.pins_by_type("ground")
        self.assertEqual(len(grounds), 1)
        self.assertEqual(grounds[0].name, "GND")


class TestLibraryCRUD(unittest.TestCase):
    """Test load, save, add, update, delete operations with temp directory."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self._patcher = patch(
            "core.component_library.get_data_dir",
            return_value=self.temp_dir,
        )
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_load_empty_library_returns_empty_list(self) -> None:
        result = load_library()
        self.assertEqual(result, [])

    def test_save_and_load_roundtrip(self) -> None:
        components = [_make_component("a"), _make_component("b")]
        save_library(components)
        loaded = load_library()
        self.assertEqual(len(loaded), 2)
        self.assertEqual(loaded[0].library_id, "a")

    def test_add_component(self) -> None:
        comp = _make_component("new-item")
        result = add_component(comp)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].library_id, "new-item")
        self.assertNotEqual(result[0].created_at, "")

    def test_add_duplicate_raises_value_error(self) -> None:
        add_component(_make_component("dup"))
        with self.assertRaises(ValueError):
            add_component(_make_component("dup"))

    def test_update_component(self) -> None:
        add_component(_make_component("upd", name="Original"))
        updated = _make_component("upd", name="Updated")
        result = update_component(updated)
        self.assertEqual(result[0].name, "Updated")
        self.assertNotEqual(result[0].updated_at, "")

    def test_update_nonexistent_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            update_component(_make_component("ghost"))

    def test_delete_component(self) -> None:
        add_component(_make_component("del-me"))
        result = delete_component("del-me")
        self.assertEqual(len(result), 0)

    def test_delete_nonexistent_raises_value_error(self) -> None:
        with self.assertRaises(ValueError):
            delete_component("ghost")

    def test_get_component_found(self) -> None:
        add_component(_make_component("find-me", name="Found"))
        comp = get_component("find-me")
        self.assertIsNotNone(comp)
        self.assertEqual(comp.name, "Found")

    def test_get_component_not_found(self) -> None:
        self.assertIsNone(get_component("nope"))


class TestLibrarySearch(unittest.TestCase):
    """Test search and filtering."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self._patcher = patch(
            "core.component_library.get_data_dir",
            return_value=self.temp_dir,
        )
        self._patcher.start()
        add_component(_make_component("ecu-1", name="Emtron KV8", component_type="ecu"))
        add_component(_make_component("sensor-1", name="GM IAT Sensor", component_type="sensor"))
        add_component(_make_component("relay-1", name="Main Relay", component_type="relay"))

    def tearDown(self) -> None:
        self._patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_search_by_name(self) -> None:
        results = search_library(query="emtron")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].library_id, "ecu-1")

    def test_search_by_type(self) -> None:
        results = search_library(component_type="sensor")
        self.assertEqual(len(results), 1)

    def test_search_combined(self) -> None:
        results = search_library(query="relay", component_type="relay")
        self.assertEqual(len(results), 1)

    def test_search_no_match(self) -> None:
        results = search_library(query="nonexistent")
        self.assertEqual(len(results), 0)

    def test_list_component_types(self) -> None:
        types = list_component_types()
        self.assertEqual(sorted(types), ["ecu", "relay", "sensor"])


class TestDefaultSeeding(unittest.TestCase):
    """Test that defaults file seeds the library on first load."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.mkdtemp()
        self._patcher = patch(
            "core.component_library.get_data_dir",
            return_value=self.temp_dir,
        )
        self._patcher.start()

    def tearDown(self) -> None:
        self._patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_seeds_from_defaults_file(self) -> None:
        defaults = [
            {"library_id": "default-1", "name": "Default", "component_type": "battery",
             "pins": [{"pin_id": "P", "name": "Pos", "pin_type": "power_output"}]},
        ]
        defaults_path = os.path.join(self.temp_dir, "component_library_defaults.json")
        with open(defaults_path, "w") as fh:
            json.dump(defaults, fh)

        result = load_library()
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].library_id, "default-1")


class TestAiParseComponentData(unittest.TestCase):
    """Test the AI-assisted component data parser."""

    def test_parse_returns_structured_dict(self) -> None:
        mock_response = json.dumps({
            "name": "Emtron KV8",
            "component_type": "ecu",
            "manufacturer": "Emtron",
            "part_number": "KV8",
            "voltage_nominal": 12.0,
            "current_draw_amps": 3.0,
            "pins": [
                {"pin_id": "A1", "name": "B+", "pin_type": "power_input",
                 "description": "Main 12V power"},
                {"pin_id": "A2", "name": "PGND", "pin_type": "ground",
                 "description": "Power ground"},
            ],
            "notes": "8-cylinder ECU",
        })

        with patch("core.ai_intake._call_github_models_api", return_value=mock_response):
            from core.ai_intake import parse_component_data
            result = parse_component_data("Emtron KV8", "Pin A1: B+, Pin A2: PGND", "token")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Emtron KV8")
        self.assertEqual(len(result["pins"]), 2)
        self.assertEqual(result["pins"][0]["pin_type"], "power_input")

    def test_parse_returns_none_when_no_token(self) -> None:
        from core.ai_intake import parse_component_data
        result = parse_component_data("Test", "some data", "")
        self.assertIsNone(result)

    def test_parse_returns_none_when_api_fails(self) -> None:
        with patch("core.ai_intake._call_github_models_api", return_value=None):
            from core.ai_intake import parse_component_data
            result = parse_component_data("Test", "some data", "token")
        self.assertIsNone(result)


class TestAiGenerateConnections(unittest.TestCase):
    """Test the library-aware AI connection generator."""

    def test_generates_validated_connections(self) -> None:
        components = [
            {
                "component_id": "bat1",
                "component_name": "Battery",
                "pins": [
                    {"pin_id": "POS", "name": "Positive", "pin_type": "power_output"},
                    {"pin_id": "NEG", "name": "Negative", "pin_type": "ground"},
                ],
            },
            {
                "component_id": "ecu1",
                "component_name": "ECU",
                "pins": [
                    {"pin_id": "B+", "name": "Power", "pin_type": "power_input"},
                    {"pin_id": "GND", "name": "Ground", "pin_type": "ground"},
                ],
            },
        ]
        mock_response = json.dumps({
            "connections": [
                {
                    "connection_id": "conn_001",
                    "from_component_id": "bat1",
                    "from_pin": "POS",
                    "to_component_id": "ecu1",
                    "to_pin": "B+",
                    "current_amps": 3.0,
                    "run_length_ft": 4.0,
                    "wire_color": "red",
                    "circuit_type": "power",
                },
                {
                    "connection_id": "conn_bad",
                    "from_component_id": "ghost",
                    "from_pin": "X",
                    "to_component_id": "ecu1",
                    "to_pin": "GND",
                    "current_amps": 1.0,
                    "run_length_ft": 2.0,
                    "wire_color": "black",
                    "circuit_type": "ground",
                },
            ],
            "notes": ["Check fuse rating"],
        })

        with patch("core.ai_intake._call_github_models_api", return_value=mock_response):
            from core.ai_intake import generate_connections_from_library
            result = generate_connections_from_library(components, "Wire ECU to battery", "token")

        self.assertIsNotNone(result)
        # conn_bad references 'ghost' which is not in components — should be filtered.
        self.assertEqual(len(result["connections"]), 1)
        self.assertEqual(result["connections"][0]["connection_id"], "conn_001")
        self.assertEqual(len(result["notes"]), 1)

    def test_returns_none_when_no_components(self) -> None:
        from core.ai_intake import generate_connections_from_library
        result = generate_connections_from_library([], "Wire stuff", "token")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

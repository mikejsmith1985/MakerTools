"""
Tests for WiringWizard core/ai_intake.py — covers token resolution, keyword inference,
fallback connection building, JSON extraction, and the public draft_project_from_brief API.
"""

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.ai_intake import (
    _attempt_ai_draft,
    _build_fallback_connections,
    _extract_json_from_response,
    _infer_components_from_brief,
    _run_fallback_parser,
    _slugify_to_component_id,
    clear_saved_gui_api_token,
    draft_project_from_brief,
    get_saved_gui_api_token,
    resolve_api_token,
    save_gui_api_token,
)


# ── Token Resolution ──────────────────────────────────────────────────────────

class TestResolveApiToken(unittest.TestCase):
    """Verify that the correct env var is returned in priority order."""

    def test_returns_none_when_no_token_vars_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            # Explicitly clear all three vars so other env state cannot interfere.
            for var_name in ("WIRINGWIZARD_GITHUB_TOKEN", "GITHUB_MODELS_TOKEN", "GITHUB_AI_TOKEN"):
                os.environ.pop(var_name, None)
            self.assertIsNone(resolve_api_token())

    def test_returns_wiringwizard_token_when_set(self) -> None:
        env_overrides = {
            "WIRINGWIZARD_GITHUB_TOKEN": "ww_token",
            "GITHUB_MODELS_TOKEN": "models_token",
            "GITHUB_AI_TOKEN": "ai_token",
        }
        with patch.dict(os.environ, env_overrides):
            self.assertEqual(resolve_api_token(), "ww_token")

    def test_falls_through_to_github_models_token(self) -> None:
        env_overrides = {
            "GITHUB_MODELS_TOKEN": "models_token",
            "GITHUB_AI_TOKEN": "ai_token",
        }
        with patch.dict(os.environ, env_overrides):
            os.environ.pop("WIRINGWIZARD_GITHUB_TOKEN", None)
            self.assertEqual(resolve_api_token(), "models_token")

    def test_falls_through_to_github_ai_token(self) -> None:
        with patch.dict(os.environ, {"GITHUB_AI_TOKEN": "fallback_token"}):
            os.environ.pop("WIRINGWIZARD_GITHUB_TOKEN", None)
            os.environ.pop("GITHUB_MODELS_TOKEN", None)
            self.assertEqual(resolve_api_token(), "fallback_token")

    def test_ignores_whitespace_only_token(self) -> None:
        env_overrides = {
            "WIRINGWIZARD_GITHUB_TOKEN": "   ",
            "GITHUB_MODELS_TOKEN": "real_token",
        }
        with patch.dict(os.environ, env_overrides):
            os.environ.pop("GITHUB_AI_TOKEN", None)
            self.assertEqual(resolve_api_token(), "real_token")


# ── Slug Helper ───────────────────────────────────────────────────────────────

class TestSlugifyToComponentId(unittest.TestCase):

    def test_converts_spaces_to_underscores(self) -> None:
        self.assertEqual(_slugify_to_component_id("Power Supply"), "power_supply")

    def test_strips_special_characters(self) -> None:
        self.assertEqual(_slugify_to_component_id("LED-Load!"), "led_load")

    def test_empty_string_returns_component(self) -> None:
        self.assertEqual(_slugify_to_component_id(""), "component")

    def test_already_snake_case_is_unchanged(self) -> None:
        self.assertEqual(_slugify_to_component_id("battery"), "battery")


# ── Component Inference ───────────────────────────────────────────────────────

class TestInferComponentsFromBrief(unittest.TestCase):
    """Verify that keywords map to expected component types."""

    def _get_types(self, brief: str) -> list:
        return [comp["component_type"] for comp in _infer_components_from_brief(brief)]

    def test_detects_battery(self) -> None:
        self.assertIn("battery", self._get_types("I have a lipo battery"))

    def test_detects_arduino(self) -> None:
        self.assertIn("microcontroller", self._get_types("Arduino Nano controls the motors"))

    def test_detects_esp32(self) -> None:
        self.assertIn("microcontroller", self._get_types("Using an ESP32 for WiFi"))

    def test_detects_relay(self) -> None:
        self.assertIn("relay", self._get_types("5V relay switches the pump"))

    def test_detects_led_strip(self) -> None:
        self.assertIn("led_load", self._get_types("NeoPixel strip on the helmet"))

    def test_detects_motor(self) -> None:
        self.assertIn("motor", self._get_types("DC motor spins the wheel"))

    def test_detects_fan(self) -> None:
        self.assertIn("fan", self._get_types("cooling fan keeps the PSU cool"))

    def test_each_type_appears_at_most_once(self) -> None:
        brief = "arduino arduino arduino battery battery"
        component_types = self._get_types(brief)
        self.assertEqual(len(component_types), len(set(component_types)))

    def test_guarantees_power_source_when_none_detected(self) -> None:
        # A brief with only a motor has no power source — fallback inserts one.
        types = self._get_types("just a fan")
        self.assertTrue(
            any(t in ("battery", "power_supply") for t in types),
            msg="Expected a power source to be inserted automatically",
        )

    def test_guarantees_load_when_none_detected(self) -> None:
        # A brief with only a battery has no load — fallback inserts one.
        types = self._get_types("12V lead-acid battery")
        self.assertTrue(
            any(t not in ("battery", "power_supply") for t in types),
            msg="Expected a load component to be inserted automatically",
        )

    def test_empty_brief_returns_minimal_starter_set(self) -> None:
        components = _infer_components_from_brief("")
        self.assertGreaterEqual(len(components), 2)
        all_types = [comp["component_type"] for comp in components]
        has_source = any(t in ("battery", "power_supply") for t in all_types)
        self.assertTrue(has_source)

    def test_component_ids_are_snake_case(self) -> None:
        components = _infer_components_from_brief("Arduino and a battery")
        for component in components:
            component_id = component["component_id"]
            self.assertRegex(
                component_id,
                r"^[a-z][a-z0-9_]*[0-9]$",
                msg=f"component_id '{component_id}' is not snake_case with trailing digit",
            )

    def test_current_draw_is_non_negative(self) -> None:
        components = _infer_components_from_brief("ESP32, relay, and battery")
        for component in components:
            self.assertGreaterEqual(component["current_draw_amps"], 0.0)


# ── Fallback Connection Builder ───────────────────────────────────────────────

class TestBuildFallbackConnections(unittest.TestCase):

    def _make_components(self, type_list: list) -> list:
        return [
            {
                "component_id": f"{t}1",
                "component_name": t.title(),
                "component_type": t,
                "current_draw_amps": 1.0,
                "position_label": "TBD",
            }
            for t in type_list
        ]

    def test_generates_connections_from_source_to_loads(self) -> None:
        components = self._make_components(["battery", "microcontroller", "fan"])
        connections = _build_fallback_connections(components)
        self.assertEqual(len(connections), 2)
        for conn in connections:
            self.assertEqual(conn["from_component_id"], "battery1")

    def test_connection_ids_are_unique(self) -> None:
        components = self._make_components(["power_supply", "motor", "led_load", "sensor"])
        connections = _build_fallback_connections(components)
        connection_ids = [conn["connection_id"] for conn in connections]
        self.assertEqual(len(connection_ids), len(set(connection_ids)))

    def test_returns_empty_list_when_no_power_source(self) -> None:
        components = self._make_components(["microcontroller", "fan"])
        self.assertEqual(_build_fallback_connections(components), [])

    def test_returns_empty_list_when_no_loads(self) -> None:
        components = self._make_components(["battery", "power_supply"])
        self.assertEqual(_build_fallback_connections(components), [])

    def test_wire_color_is_red_for_positive_supply(self) -> None:
        components = self._make_components(["battery", "microcontroller"])
        connections = _build_fallback_connections(components)
        self.assertTrue(all(conn["wire_color"] == "red" for conn in connections))

    def test_run_length_is_positive(self) -> None:
        components = self._make_components(["battery", "motor"])
        connections = _build_fallback_connections(components)
        self.assertTrue(all(conn["run_length_ft"] > 0 for conn in connections))


# ── Fallback Parser ───────────────────────────────────────────────────────────

class TestRunFallbackParser(unittest.TestCase):

    def test_returns_correct_top_level_keys(self) -> None:
        result = _run_fallback_parser("LED and battery project", "My LED Project")
        expected_keys = {"project_name", "description", "components", "connections", "notes", "used_ai"}
        self.assertEqual(set(result.keys()), expected_keys)

    def test_used_ai_is_false(self) -> None:
        result = _run_fallback_parser("some brief", "Project")
        self.assertFalse(result["used_ai"])

    def test_project_name_uses_supplied_name(self) -> None:
        result = _run_fallback_parser("brief", "Supplied Name")
        self.assertEqual(result["project_name"], "Supplied Name")

    def test_project_name_defaults_when_empty(self) -> None:
        result = _run_fallback_parser("some brief", "")
        self.assertEqual(result["project_name"], "Wiring Project")

    def test_description_is_non_empty_string(self) -> None:
        result = _run_fallback_parser("Arduino controls LEDs via relay", "")
        self.assertIsInstance(result["description"], str)
        self.assertTrue(result["description"])

    def test_components_is_list(self) -> None:
        result = _run_fallback_parser("battery and fan", "")
        self.assertIsInstance(result["components"], list)

    def test_connections_is_list(self) -> None:
        result = _run_fallback_parser("battery and fan", "")
        self.assertIsInstance(result["connections"], list)

    def test_notes_is_list_of_strings(self) -> None:
        result = _run_fallback_parser("brief", "")
        self.assertIsInstance(result["notes"], list)
        for note in result["notes"]:
            self.assertIsInstance(note, str)

    def test_empty_brief_produces_well_formed_result(self) -> None:
        result = _run_fallback_parser("", "")
        self.assertIsInstance(result["components"], list)
        self.assertGreaterEqual(len(result["components"]), 1)


# ── JSON Extraction from AI Response ─────────────────────────────────────────

class TestExtractJsonFromResponse(unittest.TestCase):

    def test_extracts_plain_json_object(self) -> None:
        raw = '{"project_name": "Test", "components": []}'
        result = _extract_json_from_response(raw)
        self.assertEqual(result, {"project_name": "Test", "components": []})

    def test_strips_markdown_json_fence(self) -> None:
        raw = '```json\n{"project_name": "Fenced", "components": []}\n```'
        result = _extract_json_from_response(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["project_name"], "Fenced")

    def test_strips_plain_code_fence(self) -> None:
        raw = '```\n{"project_name": "Plain fence"}\n```'
        result = _extract_json_from_response(raw)
        self.assertIsNotNone(result)
        self.assertEqual(result["project_name"], "Plain fence")

    def test_extracts_embedded_object_after_prose(self) -> None:
        raw = 'Here is the result:\n{"components": [], "connections": []}\nEnd.'
        result = _extract_json_from_response(raw)
        self.assertIsNotNone(result)
        self.assertIn("components", result)

    def test_returns_none_for_empty_string(self) -> None:
        self.assertIsNone(_extract_json_from_response(""))

    def test_returns_none_for_invalid_json(self) -> None:
        self.assertIsNone(_extract_json_from_response("{bad json"))

    def test_returns_none_when_top_level_is_array_not_dict(self) -> None:
        # A bare JSON array with no embedded object should return None.
        self.assertIsNone(_extract_json_from_response('["string_only", "another"]'))


# ── Public API — draft_project_from_brief ────────────────────────────────────

class TestDraftProjectFromBrief(unittest.TestCase):
    """End-to-end tests for the public function, all running without a real API call."""

    def setUp(self) -> None:
        # Ensure no machine-local GUI token can cause accidental real API calls in tests.
        self.saved_token_patch = patch("core.ai_intake.get_saved_gui_api_token", return_value=None)
        self.saved_token_patch.start()

    def tearDown(self) -> None:
        self.saved_token_patch.stop()

    def test_fallback_used_when_no_token_set(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            for var in ("WIRINGWIZARD_GITHUB_TOKEN", "GITHUB_MODELS_TOKEN", "GITHUB_AI_TOKEN"):
                os.environ.pop(var, None)
            result = draft_project_from_brief("LED and battery project", "LED Test")
        self.assertFalse(result["used_ai"])
        self.assertEqual(result["project_name"], "LED Test")

    def test_fallback_for_empty_brief(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            for var in ("WIRINGWIZARD_GITHUB_TOKEN", "GITHUB_MODELS_TOKEN", "GITHUB_AI_TOKEN"):
                os.environ.pop(var, None)
            result = draft_project_from_brief("", "")
        self.assertFalse(result["used_ai"])
        self.assertIsInstance(result["components"], list)

    def test_fallback_used_when_api_call_returns_none(self) -> None:
        with patch("core.ai_intake._call_github_models_api", return_value=None):
            with patch.dict(os.environ, {"WIRINGWIZARD_GITHUB_TOKEN": "test_token"}):
                result = draft_project_from_brief("Arduino fan controller", "Fan Project")
        self.assertFalse(result["used_ai"])

    def test_fallback_used_when_api_returns_malformed_json(self) -> None:
        with patch("core.ai_intake._call_github_models_api", return_value="not json at all"):
            with patch.dict(os.environ, {"WIRINGWIZARD_GITHUB_TOKEN": "test_token"}):
                result = draft_project_from_brief("Arduino fan controller", "")
        self.assertFalse(result["used_ai"])

    def test_ai_path_used_when_api_returns_valid_response(self) -> None:
        valid_ai_response = json.dumps({
            "project_name": "Smart Fan",
            "description": "Arduino controls a fan based on temperature.",
            "components": [
                {
                    "component_id": "battery1",
                    "component_name": "Battery",
                    "component_type": "battery",
                    "current_draw_amps": 20.0,
                    "position_label": "Enclosure",
                },
                {
                    "component_id": "arduino1",
                    "component_name": "Arduino Nano",
                    "component_type": "microcontroller",
                    "current_draw_amps": 0.5,
                    "position_label": "PCB",
                },
            ],
            "connections": [
                {
                    "connection_id": "conn_001",
                    "from_component_id": "battery1",
                    "from_pin": "+V",
                    "to_component_id": "arduino1",
                    "to_pin": "VIN",
                    "current_amps": 0.5,
                    "run_length_ft": 2.0,
                    "wire_color": "red",
                }
            ],
            "notes": ["Check fan voltage rating."],
        })
        with patch("core.ai_intake._call_github_models_api", return_value=valid_ai_response):
            with patch.dict(os.environ, {"WIRINGWIZARD_GITHUB_TOKEN": "test_token"}):
                result = draft_project_from_brief("Arduino fan controller", "")
        self.assertTrue(result["used_ai"])
        self.assertEqual(result["project_name"], "Smart Fan")
        self.assertEqual(len(result["components"]), 2)

    def test_ai_safety_note_always_appended_to_ai_result(self) -> None:
        valid_ai_response = json.dumps({
            "project_name": "Project",
            "description": "Desc",
            "components": [{"component_id": "b1", "component_name": "Battery",
                            "component_type": "battery", "current_draw_amps": 5.0,
                            "position_label": "Box"}],
            "connections": [],
            "notes": [],
        })
        with patch("core.ai_intake._call_github_models_api", return_value=valid_ai_response):
            with patch.dict(os.environ, {"WIRINGWIZARD_GITHUB_TOKEN": "test_token"}):
                result = draft_project_from_brief("battery project", "")
        safety_note = "AI-generated draft — always verify pinouts"
        self.assertTrue(any(safety_note in note for note in result["notes"]))

    def test_requested_project_name_overrides_ai_name(self) -> None:
        valid_ai_response = json.dumps({
            "project_name": "AI Suggested Name",
            "description": "Desc",
            "components": [{"component_id": "b1", "component_name": "Battery",
                            "component_type": "battery", "current_draw_amps": 5.0,
                            "position_label": "Box"}],
            "connections": [],
            "notes": [],
        })
        with patch("core.ai_intake._call_github_models_api", return_value=valid_ai_response):
            with patch.dict(os.environ, {"WIRINGWIZARD_GITHUB_TOKEN": "test_token"}):
                result = draft_project_from_brief("battery project", "User Name Override")
        self.assertEqual(result["project_name"], "User Name Override")

    def test_result_has_all_required_keys(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            for var in ("WIRINGWIZARD_GITHUB_TOKEN", "GITHUB_MODELS_TOKEN", "GITHUB_AI_TOKEN"):
                os.environ.pop(var, None)
            result = draft_project_from_brief("battery and fan project", "Test")
        required_keys = {"project_name", "description", "components", "connections", "notes", "used_ai"}
        self.assertEqual(set(result.keys()), required_keys)

    def test_uses_api_token_override_before_saved_or_env(self) -> None:
        with patch("core.ai_intake._attempt_ai_draft", return_value=None) as mock_attempt_ai_draft:
            with patch("core.ai_intake.get_saved_gui_api_token", return_value="saved_token"):
                with patch.dict(os.environ, {"WIRINGWIZARD_GITHUB_TOKEN": "env_token"}):
                    draft_project_from_brief(
                        "fan project",
                        "Override Project",
                        api_token_override="override_token",
                    )

        mock_attempt_ai_draft.assert_called_once_with("fan project", "Override Project", "override_token")

    def test_uses_saved_gui_token_when_no_override_or_env(self) -> None:
        with patch("core.ai_intake._attempt_ai_draft", return_value=None) as mock_attempt_ai_draft:
            with patch("core.ai_intake.get_saved_gui_api_token", return_value="saved_token"):
                with patch.dict(os.environ, {}, clear=True):
                    draft_project_from_brief("fan project", "Saved Token Project")

        mock_attempt_ai_draft.assert_called_once_with("fan project", "Saved Token Project", "saved_token")


class TestGuiTokenSettings(unittest.TestCase):
    """Verify GUI token save/load helpers persist and clear token values correctly."""

    def test_save_then_load_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            settings_path = os.path.join(temporary_dir, "ai_settings.json")
            with patch("core.ai_intake.DATA_DIR", temporary_dir), patch(
                "core.ai_intake.AI_SETTINGS_FILE_PATH", settings_path
            ):
                save_gui_api_token("abc123")
                self.assertEqual(get_saved_gui_api_token(), "abc123")

    def test_clear_saved_token_removes_value(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            settings_path = os.path.join(temporary_dir, "ai_settings.json")
            with patch("core.ai_intake.DATA_DIR", temporary_dir), patch(
                "core.ai_intake.AI_SETTINGS_FILE_PATH", settings_path
            ):
                save_gui_api_token("abc123")
                clear_saved_gui_api_token()
                self.assertIsNone(get_saved_gui_api_token())

    def test_missing_settings_file_returns_none(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_dir:
            settings_path = os.path.join(temporary_dir, "ai_settings.json")
            with patch("core.ai_intake.DATA_DIR", temporary_dir), patch(
                "core.ai_intake.AI_SETTINGS_FILE_PATH", settings_path
            ):
                self.assertIsNone(get_saved_gui_api_token())


# ── _attempt_ai_draft Validation ──────────────────────────────────────────────

class TestAttemptAiDraft(unittest.TestCase):

    def test_returns_none_when_components_key_missing(self) -> None:
        malformed_response = json.dumps({"project_name": "X", "connections": []})
        with patch("core.ai_intake._call_github_models_api", return_value=malformed_response):
            result = _attempt_ai_draft("brief", "", "token")
        self.assertIsNone(result)

    def test_returns_none_when_connections_key_missing(self) -> None:
        malformed_response = json.dumps({"project_name": "X", "components": []})
        with patch("core.ai_intake._call_github_models_api", return_value=malformed_response):
            result = _attempt_ai_draft("brief", "", "token")
        self.assertIsNone(result)

    def test_returns_none_when_api_returns_none(self) -> None:
        with patch("core.ai_intake._call_github_models_api", return_value=None):
            result = _attempt_ai_draft("brief", "", "token")
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()

"""
Tests for new v2.2.0 features: image vision parsing, bulk library builder, and auto-updater.
"""

import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.ai_intake import parse_component_from_image, bulk_identify_components
from core.updater import (
    _parse_version_tuple,
    _is_newer,
    check_latest_release,
    CURRENT_VERSION,
)


# ── Image Vision Parsing Tests ───────────────────────────────────────────────


class TestParseComponentFromImage(unittest.TestCase):
    """Verify parse_component_from_image handles various inputs correctly."""

    def test_returns_none_when_image_is_empty(self) -> None:
        """Empty base64 should return None immediately."""
        result = parse_component_from_image("test", "", "image/png", "token123")
        self.assertIsNone(result)

    def test_returns_none_when_token_is_empty(self) -> None:
        """Missing token should return None."""
        result = parse_component_from_image("test", "aGVsbG8=", "image/png", "")
        self.assertIsNone(result)

    @patch("core.ai_intake.urllib.request.urlopen")
    def test_returns_parsed_result_on_success(self, mock_urlopen) -> None:
        """Successful vision call should return normalized component dict."""
        ai_response = {
            "choices": [{
                "message": {
                    "content": json.dumps({
                        "name": "Test ECU",
                        "component_type": "ecu",
                        "manufacturer": "TestCorp",
                        "part_number": "TC100",
                        "voltage_nominal": 12.0,
                        "current_draw_amps": 2.5,
                        "pins": [
                            {"pin_id": "A1", "name": "B+", "pin_type": "power_input", "description": "12V power"},
                            {"pin_id": "A2", "name": "GND", "pin_type": "ground", "description": "Ground"},
                        ],
                        "notes": "Test notes",
                    })
                }
            }]
        }

        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(ai_response).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = parse_component_from_image("Test ECU", "aGVsbG8=", "image/png", "token123")

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Test ECU")
        self.assertEqual(result["component_type"], "ecu")
        self.assertEqual(len(result["pins"]), 2)
        self.assertEqual(result["pins"][0]["pin_id"], "A1")

    @patch("core.ai_intake.urllib.request.urlopen")
    def test_sends_correct_content_type_in_request(self, mock_urlopen) -> None:
        """The request body should include the image as a data URL with correct MIME type."""
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps({"choices": [{"message": {"content": "{}"}}]}).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        parse_component_from_image("comp", "dGVzdA==", "image/jpeg", "token")

        # Verify the request was made
        self.assertTrue(mock_urlopen.called)
        call_args = mock_urlopen.call_args
        request_obj = call_args[0][0]
        request_body = json.loads(request_obj.data.decode("utf-8"))
        user_content = request_body["messages"][1]["content"]

        # Should contain an image_url block with the correct MIME type
        image_block = [block for block in user_content if block.get("type") == "image_url"]
        self.assertEqual(len(image_block), 1)
        self.assertIn("data:image/jpeg;base64,dGVzdA==", image_block[0]["image_url"]["url"])

    @patch("core.ai_intake.urllib.request.urlopen")
    def test_returns_none_on_network_failure(self, mock_urlopen) -> None:
        """Network errors should be caught and return None."""
        mock_urlopen.side_effect = OSError("Connection refused")
        result = parse_component_from_image("comp", "aGVsbG8=", "image/png", "token")
        self.assertIsNone(result)


# ── Bulk Library Builder Tests ───────────────────────────────────────────────


class TestBulkIdentifyComponents(unittest.TestCase):
    """Verify bulk_identify_components processes URLs and AI results correctly."""

    def test_returns_error_when_url_is_empty(self) -> None:
        """Empty URL should return an error dict."""
        result = bulk_identify_components("", "token123")
        self.assertIn("error", result)
        self.assertTrue(result["error"])

    def test_returns_error_when_token_is_empty(self) -> None:
        """Empty token should return an error dict."""
        result = bulk_identify_components("https://example.com", "")
        self.assertIn("error", result)
        self.assertTrue(result["error"])

    @patch("core.ai_intake._call_github_models_api")
    @patch("core.ai_intake.fetch_url_for_component_data")
    def test_returns_components_on_success(self, mock_crawl, mock_ai) -> None:
        """Successful crawl+AI should return normalized component list."""
        mock_crawl.return_value = {
            "extracted_text": "Pin A1: Power, Pin A2: GND",
            "pages_crawled": 3,
            "pages_with_pin_data": 2,
            "error": "",
        }
        mock_ai.return_value = json.dumps({
            "components": [
                {
                    "name": "ECU Alpha",
                    "component_type": "ecu",
                    "pins": [{"pin_id": "A1", "name": "B+", "pin_type": "power_input", "description": "12V"}],
                },
                {
                    "name": "Sensor Beta",
                    "component_type": "sensor",
                    "pins": [{"pin_id": "1", "name": "Signal", "pin_type": "signal_output", "description": "Output"}],
                },
            ]
        })

        result = bulk_identify_components("https://docs.example.com/", "token")
        self.assertEqual(result["error"], "")
        self.assertEqual(len(result["components"]), 2)
        self.assertEqual(result["components"][0]["name"], "ECU Alpha")
        self.assertEqual(result["components"][1]["name"], "Sensor Beta")
        self.assertEqual(result["crawl_stats"]["pages_crawled"], 3)

    @patch("core.ai_intake.fetch_url_for_component_data")
    def test_returns_error_when_crawl_fails(self, mock_crawl) -> None:
        """Crawl failure should propagate the error."""
        mock_crawl.return_value = {"error": "Connection timeout", "extracted_text": ""}
        result = bulk_identify_components("https://example.com", "token")
        self.assertIn("timeout", result["error"].lower())

    @patch("core.ai_intake._call_github_models_api")
    @patch("core.ai_intake.fetch_url_for_component_data")
    def test_limits_max_components(self, mock_crawl, mock_ai) -> None:
        """Should not return more than BULK_BUILDER_MAX_COMPONENTS."""
        mock_crawl.return_value = {
            "extracted_text": "lots of data here",
            "pages_crawled": 1,
            "pages_with_pin_data": 1,
            "error": "",
        }
        # AI returns 25 components but limit is 20
        many_components = [{"name": f"Comp {i}", "pins": []} for i in range(25)]
        mock_ai.return_value = json.dumps({"components": many_components})

        result = bulk_identify_components("https://example.com", "token")
        self.assertLessEqual(len(result["components"]), 20)


# ── Updater Tests ────────────────────────────────────────────────────────────


class TestVersionParsing(unittest.TestCase):
    """Verify version string parsing and comparison logic."""

    def test_parses_standard_tag(self) -> None:
        """'v2.1.0' should parse to (2, 1, 0)."""
        self.assertEqual(_parse_version_tuple("v2.1.0"), (2, 1, 0))

    def test_parses_without_v_prefix(self) -> None:
        """'2.1.0' without v prefix should still parse."""
        self.assertEqual(_parse_version_tuple("2.1.0"), (2, 1, 0))

    def test_returns_none_for_invalid(self) -> None:
        """Invalid version strings should return None."""
        self.assertIsNone(_parse_version_tuple("not-a-version"))
        self.assertIsNone(_parse_version_tuple(""))

    def test_newer_version_detected(self) -> None:
        """Higher version should be detected as newer."""
        self.assertTrue(_is_newer("v3.0.0", "2.1.0"))
        self.assertTrue(_is_newer("v2.2.0", "2.1.0"))
        self.assertTrue(_is_newer("v2.1.1", "2.1.0"))

    def test_same_version_not_newer(self) -> None:
        """Same version should not be flagged as newer."""
        self.assertFalse(_is_newer("v2.1.0", "2.1.0"))

    def test_older_version_not_newer(self) -> None:
        """Older version should not be flagged as newer."""
        self.assertFalse(_is_newer("v1.0.0", "2.1.0"))


class TestCheckLatestRelease(unittest.TestCase):
    """Verify the GitHub API integration for update checking."""

    @patch("core.updater.urllib.request.urlopen")
    def test_returns_update_available_when_newer(self, mock_urlopen) -> None:
        """When GitHub has a newer release, is_update_available should be True."""
        release_data = {
            "tag_name": "v99.0.0",
            "html_url": "https://github.com/test/repo/releases/tag/v99.0.0",
            "body": "Test release notes",
            "assets": [
                {"name": "WiringWizard-v99.0.0.exe", "browser_download_url": "https://example.com/test.exe"},
            ],
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(release_data).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = check_latest_release()
        self.assertTrue(result["is_update_available"])
        self.assertEqual(result["latest_version"], "v99.0.0")
        self.assertIn("test.exe", result["exe_download_url"])

    @patch("core.updater.urllib.request.urlopen")
    def test_returns_no_update_when_current(self, mock_urlopen) -> None:
        """When GitHub version matches current, is_update_available should be False."""
        release_data = {
            "tag_name": f"v{CURRENT_VERSION}",
            "html_url": "https://example.com",
            "body": "",
            "assets": [],
        }
        mock_response = MagicMock()
        mock_response.read.return_value = json.dumps(release_data).encode("utf-8")
        mock_response.__enter__ = lambda s: s
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_response

        result = check_latest_release()
        self.assertFalse(result["is_update_available"])

    @patch("core.updater.urllib.request.urlopen")
    def test_handles_network_failure_gracefully(self, mock_urlopen) -> None:
        """Network errors should return an error message, not crash."""
        mock_urlopen.side_effect = OSError("No internet")
        result = check_latest_release()
        self.assertIn("error", result)
        self.assertTrue(result["error"])
        self.assertFalse(result["is_update_available"])

    def test_current_version_is_set(self) -> None:
        """CURRENT_VERSION should be a valid semver string."""
        version_tuple = _parse_version_tuple(CURRENT_VERSION)
        self.assertIsNotNone(version_tuple)
        self.assertEqual(len(version_tuple), 3)


if __name__ == "__main__":
    unittest.main()

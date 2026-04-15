"""
Tests for the deep URL crawler functions in core/ai_intake.py — covers HTML text
extraction, sub-link discovery, pin data detection, and the main crawl orchestrator.
"""

import os
import sys
import unittest
from unittest.mock import patch, MagicMock

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from core.ai_intake import (
    _extract_text_from_html,
    _extract_sub_links,
    _has_pin_data,
    fetch_url_for_component_data,
)


class TestExtractTextFromHtml(unittest.TestCase):
    """Verify _extract_text_from_html converts HTML into readable text."""

    def test_extracts_table_rows_as_pipe_delimited(self) -> None:
        """Pin tables should be converted to pipe-delimited rows."""
        html = """
        <table>
          <tr><th>Pin</th><th>Name</th><th>Type</th></tr>
          <tr><td>A1</td><td>B+</td><td>Power</td></tr>
          <tr><td>A2</td><td>PGND</td><td>Ground</td></tr>
        </table>
        """
        result = _extract_text_from_html(html)
        self.assertIn("A1", result)
        self.assertIn("B+", result)
        self.assertIn("PGND", result)
        # Pipe-delimited format.
        self.assertIn("|", result)

    def test_extracts_headings(self) -> None:
        html = "<h2>KV8 Pinout</h2><p>Some details here about pin mapping.</p>"
        result = _extract_text_from_html(html)
        self.assertIn("KV8 Pinout", result)

    def test_extracts_list_items(self) -> None:
        html = "<ul><li>8 injector outputs PWM capable</li><li>4 ignition outputs</li></ul>"
        result = _extract_text_from_html(html)
        self.assertIn("8 injector outputs", result)
        self.assertIn("4 ignition outputs", result)

    def test_extracts_paragraphs(self) -> None:
        html = "<p>The KV8 ECU supports sequential injection and direct ignition for engines up to 8 cylinders.</p>"
        result = _extract_text_from_html(html)
        self.assertIn("sequential injection", result)

    def test_skips_empty_table_rows(self) -> None:
        html = "<table><tr><td></td><td></td></tr><tr><td>A1</td><td>Power</td></tr></table>"
        result = _extract_text_from_html(html)
        self.assertIn("A1", result)

    def test_returns_empty_string_for_empty_html(self) -> None:
        result = _extract_text_from_html("")
        self.assertEqual(result, "")

    def test_strips_nested_html_tags_from_cell_content(self) -> None:
        """HTML tags inside cells should be removed, leaving clean text."""
        html = "<table><tr><td><strong>A1</strong></td><td><a href='#'>B+</a></td></tr></table>"
        result = _extract_text_from_html(html)
        self.assertIn("A1", result)
        self.assertIn("B+", result)
        self.assertNotIn("<strong>", result)
        self.assertNotIn("<a ", result)


class TestExtractSubLinks(unittest.TestCase):
    """Verify _extract_sub_links finds relevant pin/wiring links on a page."""

    def test_finds_pinout_links(self) -> None:
        html = '<a href="/wiring/kv8-pinout/">KV8 Pinout Rev2</a>'
        base_url = "https://docs.example.com/engine-management/"
        links = _extract_sub_links(html, base_url)
        self.assertTrue(len(links) >= 1)
        self.assertTrue(any("pinout" in url.lower() for _, url in links))

    def test_finds_wiring_links(self) -> None:
        html = '<a href="/wiring/power-supply-wiring/">Power Supply Wiring</a>'
        base_url = "https://docs.example.com/"
        links = _extract_sub_links(html, base_url)
        self.assertTrue(len(links) >= 1)

    def test_ignores_unrelated_links(self) -> None:
        """Links about pricing or support should be ignored."""
        html = """
        <a href="/pricing/">Pricing</a>
        <a href="/support/contact-us/">Contact Support</a>
        <a href="/blog/latest-news/">Blog</a>
        """
        base_url = "https://docs.example.com/"
        links = _extract_sub_links(html, base_url)
        self.assertEqual(len(links), 0)

    def test_ignores_external_domain_links(self) -> None:
        """Links to different domains should be filtered out."""
        html = '<a href="https://otherdomain.com/pinout/">External Pinout</a>'
        base_url = "https://docs.example.com/"
        links = _extract_sub_links(html, base_url)
        self.assertEqual(len(links), 0)

    def test_resolves_relative_urls_to_absolute(self) -> None:
        html = '<a href="../connector-pinout/">Connector Pinout</a>'
        base_url = "https://docs.example.com/wiring/overview/"
        links = _extract_sub_links(html, base_url)
        if links:
            _, absolute_url = links[0]
            self.assertTrue(absolute_url.startswith("https://docs.example.com/"))

    def test_returns_empty_list_for_no_html(self) -> None:
        links = _extract_sub_links("", "https://example.com/")
        self.assertEqual(links, [])


class TestHasPinData(unittest.TestCase):
    """Verify _has_pin_data detects pages containing pin/wiring information."""

    def test_detects_pin_table_content(self) -> None:
        text = "Pin 1 | B+ | Power Input\nPin 2 | PGND | ECU Ground"
        self.assertTrue(_has_pin_data(text))

    def test_detects_connector_references(self) -> None:
        text = "Connector A (26-pin): Lambda inputs\nConnector B (34-pin): Output drivers"
        self.assertTrue(_has_pin_data(text))

    def test_rejects_generic_marketing_text(self) -> None:
        text = "The KV8 is a powerful standalone engine management system with advanced features."
        self.assertFalse(_has_pin_data(text))

    def test_rejects_empty_text(self) -> None:
        self.assertFalse(_has_pin_data(""))


class TestFetchUrlForComponentData(unittest.TestCase):
    """Verify the main deep-crawl orchestrator with mocked HTTP."""

    @patch("core.ai_intake._fetch_page_html")
    def test_returns_error_when_initial_fetch_fails(self, mock_fetch: MagicMock) -> None:
        """If the initial URL can't be fetched, return a descriptive error."""
        mock_fetch.return_value = ""
        result = fetch_url_for_component_data("https://example.com/broken", "Test ECU")
        self.assertTrue(result["error"])
        self.assertEqual(result["pages_crawled"], 0)

    @patch("core.ai_intake._fetch_page_html")
    def test_crawls_single_page_without_sub_links(self, mock_fetch: MagicMock) -> None:
        """A page with no relevant sub-links should still return its content."""
        mock_fetch.return_value = """
        <html><body>
          <h1>ECU Pinout</h1>
          <table>
            <tr><th>Pin</th><th>Name</th><th>Function</th></tr>
            <tr><td>A1</td><td>B+</td><td>12V Power</td></tr>
            <tr><td>A2</td><td>PGND</td><td>Power Ground</td></tr>
          </table>
        </body></html>
        """
        result = fetch_url_for_component_data("https://docs.example.com/pinout/", "Test ECU")
        self.assertEqual(result["error"], "")
        self.assertEqual(result["pages_crawled"], 1)
        self.assertIn("A1", result["extracted_text"])
        self.assertIn("B+", result["extracted_text"])

    @patch("core.ai_intake._fetch_page_html")
    def test_follows_sub_links_to_find_pin_data(self, mock_fetch: MagicMock) -> None:
        """The crawler should follow links with pinout keywords to deeper pages."""
        index_html = """
        <html><body>
          <h1>Engine Management</h1>
          <a href="https://docs.example.com/wiring/pinout/">KV8 Pinout</a>
          <a href="https://docs.example.com/pricing/">Pricing</a>
        </body></html>
        """
        pinout_html = """
        <html><body>
          <h2>KV8 Pinout Rev2</h2>
          <table>
            <tr><th>Pin</th><th>Name</th></tr>
            <tr><td>C1</td><td>CAN-H</td></tr>
            <tr><td>C2</td><td>CAN-L</td></tr>
          </table>
        </body></html>
        """

        def side_effect(url: str) -> str:
            if "pinout" in url:
                return pinout_html
            return index_html

        mock_fetch.side_effect = side_effect
        result = fetch_url_for_component_data("https://docs.example.com/", "KV8 ECU")
        self.assertEqual(result["error"], "")
        self.assertGreaterEqual(result["pages_crawled"], 2)
        self.assertIn("CAN-H", result["extracted_text"])

    @patch("core.ai_intake._fetch_page_html")
    def test_prioritises_pages_with_pin_data(self, mock_fetch: MagicMock) -> None:
        """Pages with detected pin data should appear before reference pages."""
        index_html = """
        <html><body>
          <p>Welcome to the documentation for this powerful engine management system.</p>
          <a href="https://docs.example.com/wiring/connector-info/">Connector Info</a>
        </body></html>
        """
        pin_page_html = """
        <html><body>
          <table>
            <tr><td>Pin D1</td><td>Sensor Ground</td></tr>
            <tr><td>Pin D2</td><td>5V Reference</td></tr>
          </table>
        </body></html>
        """

        def side_effect(url: str) -> str:
            if "connector" in url:
                return pin_page_html
            return index_html

        mock_fetch.side_effect = side_effect
        result = fetch_url_for_component_data("https://docs.example.com/", "Sensor")
        self.assertEqual(result["error"], "")
        # Pin data pages are labelled and come before reference pages.
        text = result["extracted_text"]
        pin_data_position = text.find("PIN DATA")
        reference_position = text.find("REFERENCE")
        if pin_data_position >= 0 and reference_position >= 0:
            self.assertLess(pin_data_position, reference_position)

    @patch("core.ai_intake._fetch_page_html")
    def test_component_name_appears_in_output_header(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = "<html><body><p>Some documentation content goes here for testing purposes.</p></body></html>"
        result = fetch_url_for_component_data("https://example.com/docs/", "Emtron KV8")
        self.assertIn("Emtron KV8", result["extracted_text"])

    @patch("core.ai_intake._fetch_page_html")
    def test_crawled_urls_list_is_populated(self, mock_fetch: MagicMock) -> None:
        mock_fetch.return_value = "<html><body><p>Simple page with enough content for extraction purposes.</p></body></html>"
        result = fetch_url_for_component_data("https://example.com/test/", "Widget")
        self.assertIn("https://example.com/test/", result["crawled_urls"])


if __name__ == "__main__":
    unittest.main()

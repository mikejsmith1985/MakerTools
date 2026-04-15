"""
Auto-update checker for WiringWizard — queries GitHub releases for newer versions.

Compares the running app version against the latest GitHub release tag and
returns update status information for the UI to display.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

# GitHub repository coordinates for release checking
GITHUB_OWNER = "mikejsmith1985"
GITHUB_REPO = "MakerTools"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"

# Current app version — updated at release time
CURRENT_VERSION = "2.2.0"

# Regex to extract semver components from a tag like "v2.1.0"
_VERSION_PATTERN = re.compile(r"v?(\d+)\.(\d+)\.(\d+)")


def _parse_version_tuple(version_string: str) -> Optional[tuple]:
    """Parse a version string like 'v2.1.0' into a (major, minor, patch) tuple."""
    match = _VERSION_PATTERN.search(version_string)
    if not match:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def _is_newer(latest_tag: str, current_version: str) -> bool:
    """Return True if latest_tag represents a newer version than current_version."""
    latest_tuple = _parse_version_tuple(latest_tag)
    current_tuple = _parse_version_tuple(current_version)
    if latest_tuple is None or current_tuple is None:
        return False
    return latest_tuple > current_tuple


def check_latest_release() -> Dict[str, Any]:
    """Check GitHub for the latest release and compare against current version.

    Returns:
        Dict with keys:
            current_version (str): Running version
            latest_version (str): Latest release tag, or '' if check fails
            is_update_available (bool): True if a newer version exists
            download_url (str): Browser URL for the latest release
            exe_download_url (str): Direct URL to the .exe asset, or ''
            release_notes (str): Release body text
            error (str): Error message if the check failed, empty on success
    """
    result = {
        "current_version": CURRENT_VERSION,
        "latest_version": "",
        "is_update_available": False,
        "download_url": "",
        "exe_download_url": "",
        "release_notes": "",
        "error": "",
    }

    http_request = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": f"WiringWizard/{CURRENT_VERSION}",
        },
    )

    try:
        with urllib.request.urlopen(http_request, timeout=10) as http_response:
            release_data = json.loads(http_response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as network_error:
        result["error"] = f"Could not reach GitHub: {network_error}"
        return result

    latest_tag = release_data.get("tag_name", "")
    result["latest_version"] = latest_tag
    result["download_url"] = release_data.get("html_url", "")
    result["release_notes"] = release_data.get("body", "")[:2000]
    result["is_update_available"] = _is_newer(latest_tag, CURRENT_VERSION)

    # Find the .exe asset for direct download
    for asset in release_data.get("assets", []):
        asset_name = asset.get("name", "")
        if asset_name.lower().endswith(".exe") and "wiringwizard" in asset_name.lower():
            result["exe_download_url"] = asset.get("browser_download_url", "")
            break

    return result

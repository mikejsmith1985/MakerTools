"""
Runtime path helpers for WiringWizard source and packaged executable builds.
"""

import os
import sys

# Stable application name used for the user data directory on all platforms.
_APP_DATA_FOLDER_NAME = "WiringWizard"


def resolve_runtime_app_dir(module_file_path: str, source_parent_levels: int = 0) -> str:
    """
    Resolve the persistent app directory for both source and frozen runtimes.

    In frozen (PyInstaller exe) builds, data is stored in a stable per-user
    location (%APPDATA%/WiringWizard on Windows, ~/.wiringwizard elsewhere)
    so that project drafts and library data survive across exe updates.

    In source mode, data is stored relative to the module file path so that
    developers can run multiple copies side-by-side.

    Args:
        module_file_path: Absolute or relative module file path used as the
            source-runtime fallback location.
        source_parent_levels: Number of parent directory levels to ascend when
            running from source. Use 0 for module directory, 1 for parent, etc.

    Returns:
        Directory path where WiringWizard should store user data files.
    """
    is_frozen_runtime = bool(getattr(sys, "frozen", False))
    if is_frozen_runtime:
        return _get_stable_user_data_dir()

    resolved_source_dir = os.path.dirname(os.path.abspath(module_file_path))
    sanitized_parent_levels = max(0, int(source_parent_levels))
    for _ in range(sanitized_parent_levels):
        resolved_source_dir = os.path.dirname(resolved_source_dir)
    return resolved_source_dir


def _get_stable_user_data_dir() -> str:
    """Return a stable, per-user directory for persistent WiringWizard data.

    Uses %APPDATA%/WiringWizard on Windows and ~/.wiringwizard on Unix-like
    systems.  The directory is created if it does not exist.
    """
    if sys.platform == "win32":
        appdata_root = os.environ.get("APPDATA", "")
        if appdata_root:
            stable_directory = os.path.join(appdata_root, _APP_DATA_FOLDER_NAME)
        else:
            # Fallback: use home directory if APPDATA is somehow missing.
            stable_directory = os.path.join(os.path.expanduser("~"), f".{_APP_DATA_FOLDER_NAME.lower()}")
    else:
        stable_directory = os.path.join(os.path.expanduser("~"), f".{_APP_DATA_FOLDER_NAME.lower()}")

    os.makedirs(stable_directory, exist_ok=True)
    return stable_directory


def get_data_dir() -> str:
    """Return the absolute path to the WiringWizard ``data/`` directory.

    Works in both source and PyInstaller-frozen runtimes.  Creates the
    directory if it does not yet exist.
    """
    app_dir = resolve_runtime_app_dir(__file__, source_parent_levels=1)
    data_directory = os.path.join(app_dir, "data")
    os.makedirs(data_directory, exist_ok=True)
    return data_directory

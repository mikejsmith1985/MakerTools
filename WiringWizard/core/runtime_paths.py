"""
Runtime path helpers for WiringWizard source and packaged executable builds.
"""

import os
import sys


def resolve_runtime_app_dir(module_file_path: str, source_parent_levels: int = 0) -> str:
    """
    Resolve the persistent app directory for both source and frozen runtimes.

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
        executable_file_path = str(getattr(sys, "executable", "")).strip()
        if executable_file_path:
            return os.path.dirname(os.path.abspath(executable_file_path))

    resolved_source_dir = os.path.dirname(os.path.abspath(module_file_path))
    sanitized_parent_levels = max(0, int(source_parent_levels))
    for _ in range(sanitized_parent_levels):
        resolved_source_dir = os.path.dirname(resolved_source_dir)
    return resolved_source_dir


def get_data_dir() -> str:
    """Return the absolute path to the WiringWizard ``data/`` directory.

    Works in both source and PyInstaller-frozen runtimes.  Creates the
    directory if it does not yet exist.
    """
    app_dir = resolve_runtime_app_dir(__file__, source_parent_levels=1)
    data_directory = os.path.join(app_dir, "data")
    os.makedirs(data_directory, exist_ok=True)
    return data_directory

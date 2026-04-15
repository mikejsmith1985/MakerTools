"""
Component library — persistent storage for reusable component templates with
pin-level detail.

Users build the library over time by entering component data (from datasheets,
manuals, or free-text descriptions) which AI parses into structured pin lists.
When a library component is added to a project its pin definitions travel with
it, giving the AI connection generator verified data to work with.
"""

import json
import os
from datetime import date
from typing import Dict, List, Optional

from core.project_schema import LibraryComponent
from core.runtime_paths import get_data_dir

# ── File Paths ────────────────────────────────────────────────────────────────

_LIBRARY_FILENAME = "component_library.json"
_DEFAULTS_FILENAME = "component_library_defaults.json"


def _library_file_path() -> str:
    """Return the absolute path to the user's component library JSON file."""
    return os.path.join(get_data_dir(), _LIBRARY_FILENAME)


def _defaults_file_path() -> str:
    """Return the absolute path to the shipped default components JSON file."""
    return os.path.join(get_data_dir(), _DEFAULTS_FILENAME)


# ── CRUD Operations ──────────────────────────────────────────────────────────

def load_library() -> List[LibraryComponent]:
    """Load all components from the user's library file.

    If the user library does not exist yet, seeds it from the shipped defaults
    file.  Returns an empty list if neither file is found.
    """
    library_path = _library_file_path()

    if not os.path.isfile(library_path):
        _seed_from_defaults()

    if not os.path.isfile(library_path):
        return []

    try:
        with open(library_path, "r", encoding="utf-8") as file_handle:
            raw_data = json.load(file_handle)
    except (json.JSONDecodeError, OSError):
        return []

    if not isinstance(raw_data, list):
        return []

    return [LibraryComponent.from_dict(entry) for entry in raw_data if isinstance(entry, dict)]


def save_library(components: List[LibraryComponent]) -> None:
    """Persist the full component list to the library JSON file."""
    library_path = _library_file_path()
    data_dir = os.path.dirname(library_path)
    os.makedirs(data_dir, exist_ok=True)

    serialised = [component.to_dict() for component in components]
    with open(library_path, "w", encoding="utf-8") as file_handle:
        json.dump(serialised, file_handle, indent=2, ensure_ascii=False)


def add_component(new_component: LibraryComponent) -> List[LibraryComponent]:
    """Add a component to the library. Raises ValueError if the ID already exists."""
    library = load_library()
    existing_ids = {component.library_id for component in library}

    if new_component.library_id in existing_ids:
        raise ValueError(
            f"Component with library_id '{new_component.library_id}' already exists."
        )

    today = date.today().isoformat()
    if not new_component.created_at:
        new_component.created_at = today
    if not new_component.updated_at:
        new_component.updated_at = today

    library.append(new_component)
    save_library(library)
    return library


def update_component(updated_component: LibraryComponent) -> List[LibraryComponent]:
    """Replace an existing library entry by library_id. Raises ValueError if not found."""
    library = load_library()

    found_index = None
    for index, component in enumerate(library):
        if component.library_id == updated_component.library_id:
            found_index = index
            break

    if found_index is None:
        raise ValueError(
            f"Component with library_id '{updated_component.library_id}' not found."
        )

    updated_component.updated_at = date.today().isoformat()
    if not updated_component.created_at:
        updated_component.created_at = library[found_index].created_at

    library[found_index] = updated_component
    save_library(library)
    return library


def delete_component(library_id: str) -> List[LibraryComponent]:
    """Remove a component by library_id. Raises ValueError if not found."""
    library = load_library()
    original_count = len(library)
    library = [component for component in library if component.library_id != library_id]

    if len(library) == original_count:
        raise ValueError(f"Component with library_id '{library_id}' not found.")

    save_library(library)
    return library


def get_component(library_id: str) -> Optional[LibraryComponent]:
    """Return a single component by library_id, or None if not found."""
    library = load_library()
    for component in library:
        if component.library_id == library_id:
            return component
    return None


def search_library(
    query: str = "",
    component_type: str = "",
) -> List[LibraryComponent]:
    """Search the library by name/manufacturer substring and optional type filter."""
    library = load_library()
    results = library

    if component_type:
        lowered_type = component_type.lower()
        results = [
            component for component in results
            if component.component_type.lower() == lowered_type
        ]

    if query:
        lowered_query = query.lower()
        results = [
            component for component in results
            if (lowered_query in component.name.lower()
                or lowered_query in component.manufacturer.lower()
                or lowered_query in component.library_id.lower()
                or lowered_query in component.part_number.lower())
        ]

    return results


def list_component_types() -> List[str]:
    """Return a sorted list of distinct component_type values in the library."""
    library = load_library()
    return sorted({component.component_type for component in library})


# ── Seeding ───────────────────────────────────────────────────────────────────

def _seed_from_defaults() -> None:
    """Copy the shipped defaults file into the user library if available."""
    defaults_path = _defaults_file_path()
    if not os.path.isfile(defaults_path):
        return

    try:
        with open(defaults_path, "r", encoding="utf-8") as file_handle:
            raw_data = json.load(file_handle)
    except (json.JSONDecodeError, OSError):
        return

    if not isinstance(raw_data, list):
        return

    components = [
        LibraryComponent.from_dict(entry) for entry in raw_data if isinstance(entry, dict)
    ]
    if components:
        save_library(components)

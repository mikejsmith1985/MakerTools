# Changelog — MakerTools

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **WiringWizard — complete UX redesign**: replaced all JSON text editors with visual Treeview tables and modal form dialogs. Components and connections are now managed via Add/Edit/Delete toolbars with dropdowns, spinboxes, and editable combo boxes — virtually no typing required. AI-first "Describe Your Project" tab is the default landing surface. Copy-to-clipboard on the plan output tab. Persistent project bar (name, domain, voltage) always visible. Legacy draft format backward-compatible on load.

### Added
- **WiringWizard — modernized desktop UI refresh**: Intake, Output, and Re-map surfaces were redesigned with a card-based layout, clearer hierarchy, polished theming, and a persistent status bar so the workflow is more intuitive and engaging.
- **WiringWizard — frozen-runtime data path support**: runtime paths now resolve from the executable directory in packaged builds so draft and AI token settings persist correctly when running `WiringWizard.exe`.
- **WiringWizard — standalone executable distribution**: `release.ps1` now builds a `WiringWizard-<version>.exe` via PyInstaller and uploads it as a dedicated release asset alongside the existing zip archives. Users can download and run WiringWizard without installing Python.
- **WiringWizard — robust launcher fallback chain**: `start.bat` now checks for `WiringWizard.exe` first, then falls back through `pythonw` → `pyw` → `python` → `py`, with a clear error message pointing to both the exe download and Python install pages when nothing is found.

### Added
- **WiringWizard — GUI-first AI setup and launch flow**: users can configure AI access entirely in the desktop UI and start the app without a console window on Windows.
  - `WiringWizard/WiringWizard.py` — AI Assist now includes masked token entry with **Save Token**/**Clear Token** actions; saved token is passed directly to AI draft generation
  - `WiringWizard/core/ai_intake.py` — added GUI token persistence helpers (`get_saved_gui_api_token`, `save_gui_api_token`, `clear_saved_gui_api_token`) backed by `WiringWizard/data/ai_settings.json`; `draft_project_from_brief` now accepts an `api_token_override`
  - `WiringWizard/start.bat` — launcher now prefers `pythonw` and starts WiringWizard in GUI mode by default, with `python` fallback
  - `WiringWizard/tests/test_ai_intake.py` — added tests for token override precedence and token settings persistence helpers
  - `WiringWizard/README.md` — updated AI token setup docs for GUI-first workflow

- **WiringWizard — AI Assist intake element**: free-text project brief field with "AI Draft from Brief" button that populates the project name, description, components JSON, and connections JSON fields automatically.
  - `WiringWizard/core/ai_intake.py` — new module; calls GitHub Models API (`gpt-4o-mini`) when a token is available (`WIRINGWIZARD_GITHUB_TOKEN`, `GITHUB_MODELS_TOKEN`, or `GITHUB_AI_TOKEN`); deterministic keyword-based fallback parser when AI is unavailable
  - `WiringWizard/WiringWizard.py` — AI Assist panel added above the Project Profile section; status label reports whether AI or fallback was used
  - `WiringWizard/tests/test_ai_intake.py` — 57 new unit tests covering token resolution, component inference, connection builder, JSON extraction, fallback parser, and `draft_project_from_brief` public API
  - `WiringWizard/tests/test_wiringwizard_ui.py` — two new cross-module compatibility tests verifying fallback draft output is accepted by `create_project_from_input_strings`
  - `WiringWizard/README.md` — new AI Assist section documenting token setup, fallback behaviour, and safety notes

### Added
- **WiringWizard v1** — new standalone Python/Tkinter app for low-voltage wiring planning (automotive, CNC/control, 3D printer). Generates ASCII wiring diagrams, connection tables with auto-sized AWG gauges, wire BOM with 20% slack, fuse/relay sizing, connector/tooling recommendations, and plain-English step-by-step installation guide. Home-electrical domain returns a safety checklist only (full mains plans out of v1 scope). Supports add/update/remove revisions via the revision engine. 96 unit tests — all passing.
  - `WiringWizard/WiringWizard.py` — Tkinter UI (JSON-based component/connection entry, draft save/load, re-map tab)
  - `WiringWizard/core/project_schema.py` — `ProjectProfile`, `Component`, `Connection`, `WiringProject` dataclasses
  - `WiringWizard/core/domain_profiles.py` — per-domain rules, wire colours, safety notes
  - `WiringWizard/core/validators.py` — required-field, numeric-range, and domain/voltage compatibility checks
  - `WiringWizard/core/wire_sizing.py` — AWG recommendation using SAE J1128 ampacity and 3% voltage-drop limit
  - `WiringWizard/core/planner.py` — deterministic connection records and component current summaries
  - `WiringWizard/core/parts_recommender.py` — wire BOM, tooling, connector, and fuse/relay recommendations
  - `WiringWizard/core/diagram_renderer.py` — ASCII diagram + formatted connection table + full report assembly
  - `WiringWizard/core/step_builder.py` — numbered installation steps; mains safety checklist for home-electrical
  - `WiringWizard/core/revision_engine.py` — apply add/update/remove change requests with post-change validation
- Enterprise workflow initialized with Forge Terminal Workflow Architect
- PathMaker setup wizard extended with 5 usage walkthrough steps (Enable Add-In, API Token, Add Tools, Generate Toolpaths, All Done summary) — wizard now guides users from install through first toolpath
- `_open_url` helper in setup wizard for launching browser links directly from the wizard
- `release.ps1` — self-contained release script that clears stale `GH_TOKEN`, verifies auth, merges to main, tags, creates GitHub release, builds all three tool zips, and uploads assets in one command
- Generate Toolpaths dialog now offers two stock modes: **Relative Offset** (padding around model bounding box) and **Fixed Dimensions** (enter exact W×H×D in mm) — no second body required
- `GenerateCamInputChangedHandler` in `handlers.py` toggles stock input visibility when the mode dropdown changes

### Fixed
- **WiringWizard — Python 3.14 Tkinter font crash on startup**: Font specifications were passed as raw Python tuples (e.g. `("Segoe UI", 14, "bold")`). Python 3.14 changed how Tkinter serializes these tuples into Tcl font specs — family names containing spaces are no longer auto-quoted, causing a `TclError: expected integer but got "UI"` crash on every launch. Fixed by replacing all raw tuple fonts with `tkfont.Font` objects (referenced by their Tcl name) and converting `_apply_modern_theme` to return the resolved font family so `_build_header_bar` can create matching objects without re-querying the family list.
- `release.ps1` now builds and uploads a dedicated `WiringWizard-<version>.zip` release asset alongside the other MakerTools packages.
- Setup wizard content area now uses a scrollable Canvas so no step is ever clipped
- Setup wizard step 5 now queries Forge Vault HTTP API as a fallback when wizard is run outside Forge Terminal, so the AI token is auto-detected regardless of how the wizard was launched
- **"No active design" crash in Manufacturing workspace** — `handlers.py` now resolves the Fusion Design product via `activeDocument.products.itemByProductType('DesignProductType')` instead of `activeProduct`, which returns the CAM product when in the Manufacturing workspace
- `cam_generator._create_setup()` fixed-size stock branch now applies physical dimensions (W×H×D) via Fusion's CAM parameters API after setup creation
- Wizard step 7 updated to clarify: no second body needed — stock is defined inside PathMaker's CAM Setup automatically

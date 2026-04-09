# Changelog — MakerTools

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Enterprise workflow initialized with Forge Terminal Workflow Architect
- PathMaker setup wizard extended with 5 usage walkthrough steps (Enable Add-In, API Token, Add Tools, Generate Toolpaths, All Done summary) — wizard now guides users from install through first toolpath
- `_open_url` helper in setup wizard for launching browser links directly from the wizard
- `release.ps1` — self-contained release script that clears stale `GH_TOKEN`, verifies auth, merges to main, tags, creates GitHub release, builds all three tool zips, and uploads assets in one command
- Generate Toolpaths dialog now offers two stock modes: **Relative Offset** (padding around model bounding box) and **Fixed Dimensions** (enter exact W×H×D in mm) — no second body required
- `GenerateCamInputChangedHandler` in `handlers.py` toggles stock input visibility when the mode dropdown changes

### Fixed
- Setup wizard content area now uses a scrollable Canvas so no step is ever clipped
- Setup wizard step 5 now queries Forge Vault HTTP API as a fallback when wizard is run outside Forge Terminal, so the AI token is auto-detected regardless of how the wizard was launched
- **"No active design" crash in Manufacturing workspace** — `handlers.py` now resolves the Fusion Design product via `activeDocument.products.itemByProductType('DesignProductType')` instead of `activeProduct`, which returns the CAM product when in the Manufacturing workspace
- `cam_generator._create_setup()` fixed-size stock branch now applies physical dimensions (W×H×D) via Fusion's CAM parameters API after setup creation
- Wizard step 7 updated to clarify: no second body needed — stock is defined inside PathMaker's CAM Setup automatically

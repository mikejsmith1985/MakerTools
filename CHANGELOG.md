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

### Fixed
- Setup wizard content area now uses a scrollable Canvas so no step is ever clipped
- Setup wizard step 5 auto-detects `GITHUB_AI_TOKEN` from Forge Vault and writes it to PathMaker settings automatically

### Changed

### Fixed

### Removed

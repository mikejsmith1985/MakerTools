# WiringWizard

**Build wiring diagrams and harness plans for low-voltage maker projects.**

WiringWizard is a standalone desktop app that helps you plan wiring safely and clearly. You describe your project, add components with real pin data, and it generates:

- Interactive SVG wiring diagram with pin-level connections
- Connection table with wire details
- Wire gauge/length suggestions
- Fuse/relay, connector, and tooling recommendations
- Step-by-step instructions written in simple language
- Component Library with AI-assisted pin parsing
- AI Wire generation using verified pin data

## V2 — Component Library Architecture

WiringWizard v2 uses a **Component Library** to produce accurate, pin-level wiring diagrams:

1. **You provide real component data** — paste pinout tables from datasheets, manuals, or product pages
2. **AI structures it** — click "Parse Pins with AI" and it extracts pin definitions into an editable table
3. **You verify and save** — review the parsed pins, correct any errors, save to your local library
4. **AI generates connections** — the "AI Wire" feature routes connections using ONLY verified pin data
5. **Diagram shows real pins** — component cards display all defined pins, color-coded by type

This approach replaces the v1 method where AI tried to guess pin-level wiring for components it didn't know.

### Supported domains

- Automotive harness planning
- CNC control wiring
- 3D printer electronics
- Home electronics (low-voltage)
- Similar low-voltage control projects

### Household mains (important)

For home electrical mains (120V/240V), WiringWizard provides **checklist-only safety guidance** and **does not generate full mains wiring plans**. Use a licensed electrician for mains work.

## Start WiringWizard

### Option A — Standalone Executable (no Python needed)

Download **`WiringWizard-<version>.exe`** from
[GitHub Releases](https://github.com/mikejsmith1985/MakerTools/releases) and
double-click it. No installation or Python runtime required.

You can also place the exe in the `WiringWizard/` folder — `start.bat` will
detect it automatically and launch it instead of the Python script.

### Option B — Windows (Python)

Double-click **`start.bat`**. The launcher tries interpreters in this order:

1. **WiringWizard.exe** — standalone executable (if present in the folder)
2. **pythonw** — GUI mode, no console window (best UX)
3. **pyw** — Python launcher for Windows, windowless mode
4. **python** — standard interpreter (console window visible)
5. **py** — Python launcher for Windows (console fallback)

If none are found, the launcher prints download links for both the exe and
Python.

### Mac / Linux

```bash
cd WiringWizard
python WiringWizard.py
```

## Basic Workflow

1. **Open the Component Library** (📚 button) — browse starter components or add your own
2. **Add components to your library** — paste datasheet text, click "Parse Pins with AI", review and save
3. **Add library components to your project** — click 📚 in the sidebar to pick from your library
4. **AI Wire** — click ⚡ AI Wire, describe your wiring goal, and AI generates connections using real pins
5. **Review diagram** — component cards show all pins, color-coded by type; wires connect specific pins
6. **Generate Wiring Plan** — get BOM, step-by-step instructions, and recommendations
7. **Iterate** — use Re-map to refine, or add/edit components and re-wire

### Legacy workflow (still supported)

1. Enter your project profile (name, domain, voltage class)
2. Use **AI Assist** to draft components from a text brief
3. Manually adjust components and connections
4. Click **Generate Wiring Plan**

## AI Features

### Component Library + AI Pin Parser

The **Component Library** is a persistent local database of components with verified pin definitions. When adding a new component:

1. Enter the component name and paste raw data (pinout table, datasheet text, manual excerpts)
2. Click **🤖 Parse Pins with AI** — the AI extracts structured pin definitions
3. Review the editable pin table — correct any errors, add missing pins
4. Save to the library — the component is now available for all future projects

The library ships with 5 starter components (battery, fuse box, ground bus, ignition switch, relay).

### AI Wire Generation

The **⚡ AI Wire** feature generates connections between project components using ONLY their verified pin data:

1. Add components from your library to the project
2. Click AI Wire in the toolbar
3. Describe your wiring goal in plain English
4. AI generates connections — each wire references specific pin IDs from your library data
5. Invalid connections (referencing non-existent pins) are automatically filtered out

### AI Assist (legacy)

The **AI Assist** panel provides a quick-draft workflow: type a plain-English project brief and click **AI Draft from Brief**. This uses GPT-4o to generate a starter set of components and connections. Note: these components won't have library pin data unless you add them to the library separately.

### Setting up the AI token

Use the **AI token** field in the AI Assist panel and click **Save Token**. WiringWizard
stores it in `WiringWizard/data/ai_settings.json` for this app.
Click **Clear Token** any time to remove it.

You can also use environment variables. WiringWizard checks these when no saved GUI token
is provided:

| Variable | Notes |
|---|---|
| `WIRINGWIZARD_GITHUB_TOKEN` | Highest priority |
| `GITHUB_MODELS_TOKEN` | Shared with other MakerTools |
| `GITHUB_AI_TOKEN` | Lowest priority fallback |

A GitHub personal access token with **GitHub Models** access works for all three.

### Important safety notes

- **Verify all pin data** — AI pin parsing is a starting point. Always confirm against the actual datasheet before wiring.
- **Check current ratings** — Default current values are conservative estimates; confirm against your component datasheets.
- **Never use for mains wiring** — WiringWizard is scoped to low-voltage systems only. Consult a licensed electrician for household mains work.

## Run Tests

```bash
cd WiringWizard
python -m unittest discover -s tests -p "test_*.py" -v
```

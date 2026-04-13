# WiringWizard

**Build wiring diagrams and harness plans for low-voltage maker projects.**

WiringWizard is a standalone desktop app that helps you plan wiring safely and clearly. You describe your project, components, and goals, and it generates:

- ASCII wiring diagram output
- Connection table with wire details
- Wire gauge/length suggestions
- Fuse/relay, connector, and tooling recommendations
- Step-by-step instructions written in simple language
- Re-map workflow for iterative changes

## V1 Scope

WiringWizard v1 is designed for **low-voltage systems**, including:

- Automotive harness planning
- CNC control wiring
- 3D printer electronics
- Similar low-voltage control projects

### Household mains (important)

For home electrical mains (120V/240V), WiringWizard v1 provides **checklist-only safety guidance** and **does not generate full mains wiring plans**. Use a licensed electrician for mains work.

## Start WiringWizard

### Windows

Double-click **`start.bat`**. It launches WiringWizard in GUI mode (no console window when
`pythonw` is available).

### Mac / Linux

```bash
cd WiringWizard
python WiringWizard.py
```

## Basic Workflow

1. Enter your project profile (name, domain, voltage class)
2. (Optional) In **AI Assist**, save your GitHub Models token once
3. Type a brief and click **AI Draft from Brief** (or paste/edit JSON manually)
4. Review and adjust components and connections
5. Click **Generate Wiring Plan**
6. Review diagram, table, BOM, and step-by-step outputs
7. Use Re-map Changes to refine and regenerate

## AI Assist

The **AI Assist** panel sits at the top of the **Project Intake** tab. Type a plain-English
project brief (e.g. *"Arduino Nano fan controller powered by a 12 V battery with a relay
switch"*) and click **AI Draft from Brief**.

### How it works

1. **If an API token is available** — WiringWizard calls the GitHub Models API
   (`gpt-4o-mini`) and asks it to produce a structured component/connection draft.
   The status bar shows **✓ AI draft applied.** when this succeeds.

2. **If no token is set or the API call fails** — a deterministic keyword parser scans
   the brief for known low-voltage component terms (battery, Arduino, relay, LED, motor,
   fan, sensor, etc.) and builds a plausible starter set of components and power
   connections automatically. The status bar shows that the fallback parser was used.

Either way, the generated draft is written into the **Project Name**, **Description**,
**Components**, and **Connections** fields. You can edit any field before clicking
**Generate Wiring Plan**.

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

- **Always verify pinouts** — AI-generated component connections show likely pin labels
  but cannot know your specific hardware revision.
- **Check current ratings** — Default current values are conservative estimates; confirm
  against your component datasheets.
- **Add ground returns** — The draft includes positive supply connections; you must add
  ground return wires for each load.
- **Never use the draft for mains wiring** — WiringWizard is scoped to low-voltage
  systems only. Consult a licensed electrician for household mains work.

## Run Tests

```bash
cd WiringWizard
python -m unittest discover -s tests -p "test_*.py" -v
```

# 💧 MisterWizard

**Step-by-step setup guide for mist coolant on your Onefinity CNC.**

MisterWizard is a simple app that walks you through wiring up a mist coolant solenoid to your Onefinity CNC controller (Buildbotics). It also helps you add coolant start/stop commands to your G-code so the mist turns on automatically when your spindle starts and turns off when it stops.

No soldering experience needed. No coding. Just follow the steps.

---

## What MisterWizard Does

- 🔌 **Wiring guide** — shows you exactly how to connect your solenoid to the Buildbotics controller
- ⚡ **Safety diagram** — explains why you need a relay (you do — never connect a solenoid directly!)
- 🧪 **Test your setup** — sends a test command to your Onefinity to make sure the solenoid fires
- 🔧 **Adds coolant to your G-code** — automatically inserts `M7` (mist on) and `M9` (coolant off) into your existing G-code files
- ⏱ **Timing settings** — set a delay before mist starts so your spindle gets up to speed first

---

## What You Need

- ✅ An Onefinity CNC with Buildbotics controller
- ✅ A mist coolant solenoid (12V or 24V — most common options work)
- ✅ A relay module (5V input, rated for your solenoid voltage) — about $5–10 on Amazon
- ✅ An opto-isolator (for safety) — included in most relay modules
- ✅ Python 3.7 or newer (free at python.org) — **check "Add to PATH" during install!**
- ✅ Your Onefinity connected to your computer's network (same WiFi or ethernet)

> ⚠️ **Never connect a solenoid directly to the controller's GPIO pins.** The pins output 5V at very low current — a solenoid will damage them. Always use a relay. MisterWizard reminds you of this at every step.

---

## How to Start MisterWizard

### On Windows

Double-click **`start.bat`**

That's it. A window opens and walks you through everything.

### On Mac / Linux

```bash
cd MisterWizard
python MisterWizard.py
```

---

## The 5 Tabs Explained

MisterWizard has 5 tabs. Work through them in order, left to right.

### Tab 1 — Controller Setup
Enter your Onefinity's IP address (usually `192.168.1.xxx` — shown on the Buildbotics web page). MisterWizard will connect and let you send test commands.

### Tab 2 — Wiring Guide
Shows you a diagram of exactly how to wire your solenoid. Includes:
- Which GPIO pin to use on the Buildbotics board
- How to wire the relay
- Wire color suggestions
- Voltage options (12V vs 24V solenoid)

### Tab 3 — Timing Settings
Set how long to wait before the mist starts (usually 0.5–2 seconds after spindle on). Also set how long to keep the mist running after the spindle stops.

### Tab 4 — Test G-Code
Generate a short test G-code file that:
1. Turns the mist ON
2. Waits 5 seconds
3. Turns the mist OFF

Upload it to your Onefinity and run it to confirm the solenoid fires.

### Tab 5 — Inject G-Code
Point MisterWizard at an existing G-code file from your CAM software. It will:
- Add `M7` (mist ON) after your spindle-start commands
- Add `M9` (mist OFF) before your spindle-stop commands
- Save a new file (your original is never changed)

---

## G-Code Reference

| Command | What It Does |
|---------|-------------|
| `M7` | Turn mist coolant ON |
| `M8` | Turn flood coolant ON |
| `M9` | Turn ALL coolant OFF |

These are standard G-code commands that Buildbotics supports natively — no firmware changes needed.

---

## Wiring Overview

```
Buildbotics GPIO Pin (5V signal)
         │
         ▼
   [Opto-Isolator]
         │
         ▼
   [Relay Module]
    /          \
  NO            NC
   │
   ▼
Power Supply (12V or 24V)
   │
   ▼
Solenoid Valve
```

MisterWizard's Tab 2 shows this with more detail and the actual pin numbers for your Buildbotics version.

---

## Common Problems

**"MisterWizard won't connect to my Onefinity"**
→ Make sure your computer and Onefinity are on the same WiFi network. Try typing `http://onefinity.local` in a web browser — if that opens the Buildbotics page, you're connected.

**"The solenoid isn't firing"**
→ Check your wiring using the diagram in Tab 2. Make sure you're using the correct GPIO pin. Use a multimeter to check for 5V on the output pin when you send `M7`.

**"start.bat says Python is not installed"**
→ Download Python from [python.org](https://www.python.org/downloads/). During install, **check the box "Add Python to PATH"**. Then try again.

**"My G-code file already has coolant commands"**
→ MisterWizard checks for existing coolant commands before adding new ones. It won't duplicate them.

---

## FAQ

**Do I need a specific solenoid brand?**
No. Any 12V or 24V normally-closed solenoid valve works. Search Amazon for "mist coolant solenoid valve 12V" or "air solenoid valve 24V."

**What if I have a 24V solenoid but a 12V power supply?**
Use a 24V power supply for the solenoid. Your relay module handles the voltage — the Buildbotics controller only sees 5V logic.

**Does this work with PathMaker G-code?**
Yes! Run your G-code through MisterWizard's Tab 5 (Inject G-Code) after generating it in PathMaker.

**Will this work on machines other than Onefinity?**
MisterWizard is designed for Buildbotics-based controllers. The G-code injection (Tab 5) works with any machine that supports `M7`/`M9`.

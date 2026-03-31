# 🛤 PathMaker

**AI-powered 1-click CNC toolpath generator for Fusion 360.**

PathMaker lives inside Fusion 360's Manufacturing workspace. You tell it what material you're cutting, it looks at your model and your tool library, and it figures out the rest.

---

## What PathMaker Does For You

- 📦 **Builds your tool library automatically** — paste an Amazon link for any endmill or router bit and PathMaker reads the specs for you
- ⚡ **Picks the right feeds and speeds** — no more Googling "what speed for aluminum with a 1/4 inch bit"
- 🔄 **Guides 2-sided carving** — tells you exactly where to put your dowel pins and flip the stock
- 🤖 **Generates toolpaths** — looks at your model geometry and creates operations automatically
- 🗃 **Saves your materials** — once you add "Baltic Birch Plywood," it remembers forever

---

## What You Need

- ✅ Fusion 360 (free hobbyist license at autodesk.com/fusion360)
- ✅ Python 3.7 or newer (free at python.org) — **check "Add to PATH" during install!**
- ✅ A free GitHub Models API token (for the AI features — takes 2 minutes to get)
- ✅ An Onefinity Machinist CNC with Makita RT0701C router (settings are pre-configured)

---

## How to Install

### Step 1 — Double-click `install.bat`

A setup wizard will open. Click through it — it finds Fusion 360 automatically and installs PathMaker in the right place.

> **If `install.bat` doesn't work:** Right-click it → "Run as administrator"

### Step 2 — Turn on PathMaker in Fusion 360

1. Open Fusion 360
2. Click the top menu: **Tools → Add-Ins**
3. Click the **Add-Ins** tab
4. Find **PathMaker** in the list
5. Click the slider to turn it **ON** ✅
6. Check the box **"Run on Startup"** so it loads automatically

### Step 3 — Get Your Free AI Token

PathMaker uses GitHub's free AI to read Amazon listings and suggest feeds/speeds.

1. Go to [github.com/marketplace/models](https://github.com/marketplace/models)
2. Sign in (or create a free GitHub account)
3. Click your profile picture → **Settings → Developer Settings → Personal Access Tokens**
4. Create a new token — you only need to check **"models"** scope
5. Copy the token
6. In Fusion 360, open PathMaker → click **Settings** → paste your token

---

## How to Use PathMaker

### Adding Your First Endmill

1. Buy an endmill from Amazon (or find one you already own on Amazon)
2. Copy the Amazon product URL
3. Switch to the **Manufacturing** workspace in Fusion 360
4. Click **Import Tool** in the PathMaker toolbar
5. Paste the URL and click OK
6. PathMaker reads the listing and adds the bit to your library ✅

> **Do this for every bit you own.** The more tools you add, the smarter PathMaker gets at picking the right one.

### Generating Toolpaths (The Main Event)

1. Open your model in Fusion 360
2. Switch to **Manufacturing** workspace
3. Set up a CAM Setup (stock size, zero point — Fusion's normal CAM setup step)
4. Click **Generate Toolpaths** in the PathMaker toolbar
5. Select your material from the dropdown (or type it)
6. Click **OK** — PathMaker analyzes the geometry and creates operations

That's it. Review the toolpaths in the simulation, then post-process as usual.

### 2-Sided Carving

1. Click **2-Sided Carve** in the PathMaker toolbar
2. The wizard asks you where to put dowel pins (it suggests locations based on your stock size)
3. Machine side 1
4. Flip the stock using the dowel pins to align perfectly
5. Machine side 2

### Adding a New Material

1. Click **Add Material** in the toolbar
2. Type the material name (e.g., "1/4 inch Baltic Birch Plywood")
3. PathMaker generates feeds and speeds using AI and saves them

---

## The PathMaker Toolbar

| Button | What It Does |
|--------|-------------|
| **Generate Toolpaths** | Main event — analyzes geometry, picks tools, creates CAM operations |
| **Import Tool** | Paste an Amazon URL → tool added to your library |
| **Manage Tools** | See all your tools, edit or delete them |
| **Add Material** | Add a material with AI-generated feeds and speeds |
| **2-Sided Carve** | Set up a flip operation with dowel pin alignment |
| **Settings** | API token, machine profile, preferences |

---

## Your Machine Settings (Pre-configured)

PathMaker is already set up for:

| Setting | Value |
|---------|-------|
| Machine | Onefinity Machinist |
| Router | Makita RT0701C |
| Speed Range | 9,600 – 30,000 RPM |
| Rigidity Factor | 0.6 (belt-drive compensation) |

If you use a different machine, you can adjust these in **Settings**.

---

## Makita RT0701C Dial Reference

| Dial Position | Spindle Speed |
|:---:|:---:|
| 1 | ~9,600 RPM |
| 2 | ~12,000 RPM |
| 3 | ~16,500 RPM |
| 4 | ~21,500 RPM |
| 5 | ~26,500 RPM |
| 6 | ~30,000 RPM |

---

## Common Problems

**"PathMaker doesn't show up in Fusion 360"**
→ Go to Tools → Add-Ins → Add-Ins tab → make sure PathMaker is toggled ON

**"The AI token isn't working"**
→ Make sure you copied the full token (starts with `github_pat_`). It expires — generate a new one if needed.

**"Toolpaths look wrong"**
→ Check your CAM Setup — make sure the stock size and zero point (WCS origin) are set correctly before clicking Generate Toolpaths.

**"The install.bat said Access Denied"**
→ Right-click `install.bat` → Run as Administrator

---

## Running Tests (For Developers)

```bash
cd PathMaker
python tests/run_tests.py
```

All tests run offline — no Fusion 360 needed.

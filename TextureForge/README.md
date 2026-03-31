# 🎨 TextureForge

**Stamp surface textures onto any Fusion 360 model face — for 3D printing and CNC milling.**

TextureForge adds a panel to Fusion 360's Design workspace. Select a face on your model, pick a texture, and click OK. The texture becomes real geometry in your model — it shows up in your prints and can be milled on a CNC.

---

## What TextureForge Does

- **5 built-in patterns** — carbon fiber, diamond knurl, wood grain, brushed metal, leather
- **Import your own image** — SVG vector files, PNG photos, or BMP images
- **Works for 3D printing** — texture shows up in your STL file
- **Works for CNC milling** — scale the pattern to fit your end mill (TextureForge warns you if the pattern is too small for your bit)
- **Boss or deboss** — raise the texture up, or cut it into the surface

---

## What You Need

- ✅ Fusion 360 (free hobbyist license at autodesk.com/fusion360)
- ✅ Python 3.7 or newer (free at python.org) — **check "Add to PATH" during install!**

---

## How to Install

### Step 1 — Double-click `install.bat`

A setup wizard opens. Click Next → Next → Finish. It finds Fusion 360 automatically.

> **If `install.bat` doesn't work:** Right-click → "Run as administrator"

### Step 2 — Turn on TextureForge in Fusion 360

1. Open Fusion 360
2. Click **Tools → Add-Ins → Add-Ins tab**
3. Find **TextureForge** in the list
4. Toggle it **ON** ✅
5. Check **"Run on Startup"**

TextureForge will now appear in the **Design** workspace toolbar (not Manufacturing — textures are a design step).

---

## How to Use TextureForge

### Stamping a Built-In Texture

1. Open your model in Fusion 360's **Design** workspace
2. Find the **TextureForge** panel in the toolbar
3. Click **Stamp Texture**
4. **Click a face** on your model (the face turns highlighted)
5. Pick your texture from the dropdown:
   - 🔲 Carbon Fiber (2×2 Twill)
   - 💎 Diamond Knurl
   - 🌲 Wood Grain
   - ✨ Brushed Metal
   - 👜 Leather Hex Bumps
6. Choose **Output Mode:**
   - **3D Print** — smaller scale, shallower depth, perfect for FDM printing
   - **CNC Mill** — larger scale, deeper cut, picked to match your end mill size
7. Set **Pattern Scale** (how big each repeat is, in mm)
8. Set **Emboss Depth** (how deep/tall the texture is, in mm)
9. Check **Deboss** if you want the texture cut INTO the surface instead of raised
10. Click **OK**

The texture is now part of your model. You'll see it in the timeline as an "Emboss" feature.

> **To remove the texture:** Find the Emboss in the timeline at the bottom of Fusion 360 and right-click → Suppress (or delete it).

### Stamping a Texture From Your Own Image

1. Click **Texture From Image** in the TextureForge panel
2. A file browser opens — pick your file:
   - `.svg` — best quality, vector graphics (logos, patterns from Inkscape)
   - `.png` — photos or drawings (gets converted to a pixel-stamp effect)
   - `.bmp` — same as PNG
3. Click a face on your model
4. Adjust the settings (depth, boss/deboss)
5. For PNG/BMP: adjust **Threshold** — lower = only the darkest areas stamp, higher = more of the image stamps
6. Click OK

#### Tips for SVG Files
- Use **simple filled shapes** — not just outlines/strokes
- **Convert text to paths** in Inkscape first: Path → Object to Path
- Don't use SVGs that have photos embedded inside them

---

## Scale Guide — How Big Should the Pattern Be?

If you're **CNC milling**, the pattern must be bigger than your end mill. Here's a quick guide:

| Texture | Minimum Scale | Best Tool |
|---------|:---:|---------|
| Carbon Fiber | 4 mm | 1/16" flat end mill or V-bit |
| Diamond Knurl | 3 mm | V-bit |
| Wood Grain | 6 mm | 1/8" ball-nose end mill |
| Brushed Metal | 1.5 mm | 1/32" ball-nose or V-bit |
| Leather | 5 mm | 1/8" ball-nose end mill |

TextureForge will warn you if the scale is too small for CNC milling.

If you're **3D printing**, any scale works — go as small as your layer height allows.

---

## Common Problems

**"I don't see TextureForge in the toolbar"**
→ Make sure you're in the **Design** workspace (not Manufacturing). TextureForge lives in Design.

**"The Emboss failed"**
→ Try increasing the Pattern Scale. Very small patterns can fail. Also make sure the face is flat or gently curved — very tight curves can cause issues.

**"My SVG didn't stamp anything"**
→ Open the SVG in Inkscape and make sure all text is converted to paths (Path → Object to Path). Then make sure shapes are filled, not just outlined.

**"The PNG texture looks like random dots"**
→ That's normal for PNG! It's a pixel-stamp effect. Try adjusting the Threshold slider — move it lower to stamp fewer, darker pixels.

**"install.bat said Access Denied"**
→ Right-click `install.bat` → Run as Administrator

---

## Running Tests (For Developers)

```bash
cd TextureForge
python -m unittest discover -s tests -p "test_*.py" -v
```

All 39 tests run offline — no Fusion 360 needed.

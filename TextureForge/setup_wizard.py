"""
TextureForge Setup Wizard
=========================
Double-click this file (or run: python setup_wizard.py) to install
TextureForge into Fusion 360.

No command-line knowledge needed. Just click Next!
"""

import sys
import os
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ── Tool info ────────────────────────────────────────────────────────────────
TOOL_NAME    = "TextureForge"
TOOL_FOLDER  = "TextureForge"
TOOL_VERSION = "1.0.6"
ADDIN_DIR    = os.path.dirname(os.path.abspath(__file__))

FUSION_ADDIN_PATHS = [
    os.path.expandvars(r"%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns"),
    os.path.expanduser("~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns"),
]

BG      = "#1e1e2e"
FG      = "#cdd6f4"
ACCENT  = "#cba6f7"   # purple — matches "forge" creative theme
GREEN   = "#a6e3a1"
YELLOW  = "#f9e2af"
RED_C   = "#f38ba8"
CARD_BG = "#313244"

STEPS = [
    "Welcome",
    "Check Your Computer",
    "Find Fusion 360",
    "Install TextureForge",
    "First Steps",
]


def find_fusion_addin_path():
    for p in FUSION_ADDIN_PATHS:
        if os.path.isdir(p):
            return p
    return None


def install_addin(dest_base):
    dest = os.path.join(dest_base, TOOL_FOLDER)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(
        ADDIN_DIR, dest,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '*.pyd'),
        dirs_exist_ok=False,
    )
    # Belt-and-suspenders: remove any __pycache__ that slipped through
    for root, dirs, _ in os.walk(dest):
        for d in dirs:
            if d == '__pycache__':
                shutil.rmtree(os.path.join(root, d))
    return dest


class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"🎨 {TOOL_NAME} Setup Wizard  v{TOOL_VERSION}")
        self.geometry("680x520")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.step        = 0
        self.fusion_path = tk.StringVar()
        self._detected   = find_fusion_addin_path()
        if self._detected:
            self.fusion_path.set(self._detected)

        self._build_header()
        self._build_progress()
        self._content_frame = tk.Frame(self, bg=BG)
        self._content_frame.pack(fill="both", expand=True, padx=24, pady=8)
        self._build_nav()
        self._show_step()

    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=6)
        hdr.pack(fill="x")
        tk.Label(self, text=f"🎨  {TOOL_NAME} Setup Wizard",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 18, "bold")).pack(pady=(18, 0))
        tk.Label(self, text="Stamp textures onto any 3D model face • Part of MakerTools",
                 bg=BG, fg=FG, font=("Segoe UI", 10)).pack(pady=(2, 10))
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=24)

    def _build_progress(self):
        self._prog_frame = tk.Frame(self, bg=BG)
        self._prog_frame.pack(fill="x", padx=24, pady=8)
        self._step_labels = []
        for i, name in enumerate(STEPS):
            lbl = tk.Label(self._prog_frame, text=f"{'●' if i==0 else '○'} {name}",
                           bg=BG, fg=ACCENT if i == 0 else FG,
                           font=("Segoe UI", 9))
            lbl.pack(side="left", padx=6)
            self._step_labels.append(lbl)

    def _update_progress(self):
        for i, lbl in enumerate(self._step_labels):
            if i < self.step:
                lbl.config(text=f"✓ {STEPS[i]}", fg=GREEN)
            elif i == self.step:
                lbl.config(text=f"● {STEPS[i]}", fg=ACCENT)
            else:
                lbl.config(text=f"○ {STEPS[i]}", fg=FG)

    def _build_nav(self):
        nav = tk.Frame(self, bg=BG)
        nav.pack(fill="x", padx=24, pady=12, side="bottom")
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=24, side="bottom")
        self._back_btn = tk.Button(nav, text="← Back", width=10,
                                   bg=CARD_BG, fg=FG, relief="flat",
                                   font=("Segoe UI", 10), command=self._prev)
        self._back_btn.pack(side="left")
        self._next_btn = tk.Button(nav, text="Next →", width=14,
                                   bg=ACCENT, fg=BG, relief="flat",
                                   font=("Segoe UI", 10, "bold"), command=self._next)
        self._next_btn.pack(side="right")

    def _clear_content(self):
        for w in self._content_frame.winfo_children():
            w.destroy()

    def _card(self):
        f = tk.Frame(self._content_frame, bg=CARD_BG, padx=18, pady=14)
        f.pack(fill="x", pady=6)
        return f

    def _h(self, parent, text, color=ACCENT):
        tk.Label(parent, text=text, bg=CARD_BG, fg=color,
                 font=("Segoe UI", 12, "bold"), wraplength=580,
                 justify="left").pack(anchor="w")

    def _p(self, parent, text, color=FG):
        tk.Label(parent, text=text, bg=CARD_BG, fg=color,
                 font=("Segoe UI", 10), wraplength=580,
                 justify="left").pack(anchor="w", pady=2)

    def _show_step(self):
        self._clear_content()
        self._update_progress()
        [self._step0, self._step1, self._step2,
         self._step3, self._step4][self.step]()
        self._back_btn.config(state="normal" if self.step > 0 else "disabled")
        self._next_btn.config(text="Close" if self.step == len(STEPS)-1 else "Next →")

    def _step0(self):
        c = self._card()
        self._h(c, "👋  Welcome!  Let's install TextureForge.")
        self._p(c, "TextureForge adds a 'TextureForge' panel to Fusion 360's Design workspace.")
        self._p(c, "With it you can stamp textures directly onto your 3D models:")
        for item in [
            "🔲  Carbon fiber weave",
            "💎  Diamond knurl grip pattern",
            "🌲  Wood grain",
            "✨  Brushed metal lines",
            "👜  Leather hex bumps",
            "🖼  Import your own image (SVG, PNG, BMP)",
        ]:
            self._p(c, f"    {item}")
        self._p(c, "\nTextures work for 3D printing AND CNC milling!", YELLOW)

    def _step1(self):
        c = self._card()
        self._h(c, "🔍  Checking Your Computer...")
        py_ok  = sys.version_info >= (3, 7)
        fus_ok = self._detected is not None
        self._p(c, f"  {'✅' if py_ok else '❌'}  Python {sys.version.split()[0]}  "
                f"{'(Good!)' if py_ok else '(Need Python 3.7+)'}")
        self._p(c, f"  {'✅' if fus_ok else '⚠️ '}  Fusion 360  "
                f"{'add-ins folder found' if fus_ok else 'not found — set path next'}")
        if not py_ok:
            self._p(c, "\n⚠  Please install Python from python.org and re-run.", RED_C)
            self._next_btn.config(state="disabled")
        if fus_ok:
            self._p(c, f"\n  Found at: {self._detected}", GREEN)

    def _step2(self):
        c = self._card()
        self._h(c, "📁  Where Is Fusion 360 Installed?")
        if self._detected:
            self._p(c, "Found automatically! ✅", GREEN)
        else:
            self._p(c, "Couldn't find it automatically — click Browse.", YELLOW)
        ef = tk.Frame(c, bg=CARD_BG)
        ef.pack(fill="x", pady=8)
        tk.Entry(ef, textvariable=self.fusion_path, bg="#45475a", fg=FG,
                 insertbackground=FG, font=("Segoe UI", 9), width=52).pack(side="left", padx=(0,8))
        tk.Button(ef, text="Browse…", bg=CARD_BG, fg=ACCENT, relief="flat",
                  font=("Segoe UI", 9),
                  command=lambda: self.fusion_path.set(
                      filedialog.askdirectory(title="Select Fusion 360 AddIns folder") or self.fusion_path.get()
                  )).pack(side="left")
        self._p(c, r"  Default: %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns", YELLOW)

    def _step3(self):
        c = self._card()
        self._h(c, "📦  Installing TextureForge...")
        dest_base = self.fusion_path.get().strip()
        if not dest_base or not os.path.isdir(dest_base):
            self._p(c, "❌  Folder path is not valid. Go Back and set it.", RED_C)
            self._next_btn.config(state="disabled")
            return
        try:
            dest = install_addin(dest_base)
            self._p(c, f"✅  TextureForge installed to:\n  {dest}", GREEN)
            self._p(c, "\nInstallation successful! 🎉", GREEN)
        except Exception as e:
            self._p(c, f"❌  Failed: {e}", RED_C)
            self._p(c, "Try running as Administrator.", YELLOW)
            self._next_btn.config(state="disabled")

    def _step4(self):
        c = self._card()
        self._h(c, "🎉  All Done!  TextureForge is Installed.")
        self._p(c, "How to turn it on in Fusion 360:", YELLOW)
        for i, step in enumerate([
            "Open Fusion 360",
            "Click: Tools → Add-Ins → Add-Ins tab",
            "Find 'TextureForge' and toggle it ON  ✅",
            "Switch to the Design workspace",
            "Look for the 'TextureForge' panel in the toolbar",
            "Select a face on your model, then click 'Stamp Texture'!",
        ], 1):
            self._p(c, f"  Step {i}:  {step}")

    def _next(self):
        if self.step == len(STEPS) - 1:
            self.destroy()
        else:
            self.step += 1
            self._show_step()

    def _prev(self):
        if self.step > 0:
            self.step -= 1
            self._next_btn.config(state="normal")
            self._show_step()


if __name__ == "__main__":
    app = SetupWizard()
    app.mainloop()

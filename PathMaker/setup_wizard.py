"""
PathMaker Setup Wizard
======================
Double-click this file (or run: python setup_wizard.py) to install
PathMaker into Fusion 360.

No command-line knowledge needed. Just click Next!
"""

import sys
import os
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ── Tool info ────────────────────────────────────────────────────────────────
TOOL_NAME    = "PathMaker"
TOOL_FOLDER  = "PathMaker"          # folder name = Fusion add-in name
TOOL_VERSION = "1.0.6"
ADDIN_DIR    = os.path.dirname(os.path.abspath(__file__))

FUSION_ADDIN_PATHS = [
    os.path.expandvars(r"%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns"),
    os.path.expandvars(r"%APPDATA%\Autodesk\webdeploy\production"),  # alternate
    os.path.expanduser("~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns"),  # Mac
]

BG      = "#1e1e2e"
FG      = "#cdd6f4"
ACCENT  = "#89b4fa"
GREEN   = "#a6e3a1"
YELLOW  = "#f9e2af"
RED_C   = "#f38ba8"
CARD_BG = "#313244"

STEPS = [
    "Welcome",
    "Check Your Computer",
    "Find Fusion 360",
    "Install PathMaker",
    "First Steps",
]


def find_fusion_addin_path():
    for p in FUSION_ADDIN_PATHS:
        if os.path.isdir(p):
            return p
    return None


def check_python():
    return sys.version_info >= (3, 7)


def check_fusion():
    return find_fusion_addin_path() is not None


def install_addin(dest_base):
    """Copy PathMaker folder into Fusion's add-ins directory."""
    dest = os.path.join(dest_base, TOOL_FOLDER)
    if os.path.exists(dest):
        shutil.rmtree(dest)
    shutil.copytree(
        ADDIN_DIR, dest,
        ignore=shutil.ignore_patterns('__pycache__', '*.pyc', '*.pyo', '*.pyd'),
        dirs_exist_ok=False,
    )
    for root, dirs, _ in os.walk(dest):
        for d in dirs:
            if d == '__pycache__':
                shutil.rmtree(os.path.join(root, d))
    return dest


# ── Wizard UI ─────────────────────────────────────────────────────────────────

class SetupWizard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"🔧 {TOOL_NAME} Setup Wizard  v{TOOL_VERSION}")
        self.geometry("680x520")
        self.resizable(False, False)
        self.configure(bg=BG)

        self.step       = 0
        self.fusion_path = tk.StringVar()
        self.status_msgs = []

        self._detected = find_fusion_addin_path()
        if self._detected:
            self.fusion_path.set(self._detected)

        self._build_header()
        self._build_progress()
        self._content_frame = tk.Frame(self, bg=BG)
        self._content_frame.pack(fill="both", expand=True, padx=24, pady=8)
        self._build_nav()
        self._show_step()

    # ── Layout helpers ─────────────────────────────────────────────────────

    def _build_header(self):
        hdr = tk.Frame(self, bg=ACCENT, height=6)
        hdr.pack(fill="x")
        tk.Label(self, text=f"🛤  {TOOL_NAME} Setup Wizard",
                 bg=BG, fg=ACCENT,
                 font=("Segoe UI", 18, "bold")).pack(pady=(18, 0))
        tk.Label(self, text="AI-powered 1-click CAM for Fusion 360 • Part of MakerTools",
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
                                   font=("Segoe UI", 10),
                                   command=self._prev)
        self._back_btn.pack(side="left")

        self._next_btn = tk.Button(nav, text="Next →", width=14,
                                   bg=ACCENT, fg=BG, relief="flat",
                                   font=("Segoe UI", 10, "bold"),
                                   command=self._next)
        self._next_btn.pack(side="right")

    def _clear_content(self):
        for w in self._content_frame.winfo_children():
            w.destroy()

    def _card(self, parent=None):
        if parent is None:
            parent = self._content_frame
        f = tk.Frame(parent, bg=CARD_BG, padx=18, pady=14)
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

    # ── Steps ──────────────────────────────────────────────────────────────

    def _show_step(self):
        self._clear_content()
        self._update_progress()
        [self._step0, self._step1, self._step2,
         self._step3, self._step4][self.step]()
        self._back_btn.config(state="normal" if self.step > 0 else "disabled")
        last = self.step == len(STEPS) - 1
        self._next_btn.config(text="Close" if last else "Next →")

    def _step0(self):
        c = self._card()
        self._h(c, "👋  Welcome!  Let's install PathMaker.")
        self._p(c, "PathMaker adds a 'PathMaker' button to Fusion 360's Manufacturing workspace.")
        self._p(c, "It will:")
        for item in [
            "🔧  Build your tool library from Amazon links (no more manual entry!)",
            "⚡  Auto-pick feeds and speeds for your material",
            "🔄  Guide you through 2-sided carving",
            "🤖  Use AI to generate your CNC toolpaths",
        ]:
            self._p(c, f"    {item}")
        self._p(c, "\nThis wizard will install PathMaker in about 30 seconds.", YELLOW)

    def _step1(self):
        c = self._card()
        self._h(c, "🔍  Checking Your Computer...")

        py_ok = check_python()
        fus_ok = check_fusion()

        self._p(c, f"  {'✅' if py_ok else '❌'}  Python {sys.version.split()[0]}  "
                f"{'(Good!)' if py_ok else '(Need Python 3.7 or newer)'}")
        self._p(c, f"  {'✅' if fus_ok else '⚠️ '}  Fusion 360  "
                f"{'add-ins folder found' if fus_ok else 'not found — set path on next screen'}")

        if not py_ok:
            self._p(c, "\n⚠  Please install Python 3.7+ from python.org then re-run this wizard.", RED_C)
            self._next_btn.config(state="disabled")
        if fus_ok:
            self._p(c, f"\n  Found at: {self._detected}", GREEN)
        else:
            self._p(c, "\n  That's OK — you can set the folder manually on the next screen.", YELLOW)

    def _step2(self):
        c = self._card()
        self._h(c, "📁  Where Is Fusion 360 Installed?")
        self._p(c, "PathMaker needs to go into Fusion 360's add-ins folder.")

        if self._detected:
            self._p(c, "We found it automatically! ✅", GREEN)
        else:
            self._p(c, "We couldn't find it automatically. Click Browse to locate it.", YELLOW)

        entry_frame = tk.Frame(c, bg=CARD_BG)
        entry_frame.pack(fill="x", pady=8)
        tk.Entry(entry_frame, textvariable=self.fusion_path,
                 bg="#45475a", fg=FG, insertbackground=FG,
                 font=("Segoe UI", 9), width=52).pack(side="left", padx=(0, 8))
        tk.Button(entry_frame, text="Browse…",
                  bg=CARD_BG, fg=ACCENT, relief="flat",
                  font=("Segoe UI", 9),
                  command=self._browse_fusion).pack(side="left")

        self._p(c, "\nDefault location on Windows:", FG)
        self._p(c, r"  %APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns", YELLOW)

    def _browse_fusion(self):
        d = filedialog.askdirectory(title="Select Fusion 360 AddIns folder")
        if d:
            self.fusion_path.set(d)

    def _step3(self):
        c = self._card()
        self._h(c, "📦  Installing PathMaker...")

        dest_base = self.fusion_path.get().strip()
        if not dest_base or not os.path.isdir(dest_base):
            self._p(c, "❌  The Fusion 360 add-ins folder path is not valid.", RED_C)
            self._p(c, "Please go Back and set the correct path.", YELLOW)
            self._next_btn.config(state="disabled")
            return

        try:
            dest = install_addin(dest_base)
            self._p(c, f"✅  PathMaker installed to:\n  {dest}", GREEN)
            self._p(c, "\nInstallation successful! 🎉", GREEN)
            self._next_btn.config(state="normal")
        except Exception as e:
            self._p(c, f"❌  Installation failed:\n{e}", RED_C)
            self._p(c, "Try running this wizard as Administrator.", YELLOW)
            self._next_btn.config(state="disabled")

    def _step4(self):
        c = self._card()
        self._h(c, "🎉  All Done!  PathMaker is Installed.")
        self._p(c, "Here's how to turn it on in Fusion 360:", YELLOW)

        for i, step in enumerate([
            "Open Fusion 360",
            "Click the top menu: Tools → Add-Ins",
            "Click the 'Add-Ins' tab",
            "Find 'PathMaker' in the list",
            "Click the toggle to turn it ON  ✅",
            "Switch to the Manufacturing workspace — PathMaker is in the toolbar!",
        ], 1):
            self._p(c, f"  Step {i}:  {step}")

        self._p(c, "\n🔑  First thing to do in PathMaker:", YELLOW)
        self._p(c, "  Click 'Settings' → paste your GitHub Models API token.")
        self._p(c, "  Get a free token at: github.com/marketplace/models")

        tk.Button(self._content_frame, text="Open Fusion 360 Now →",
                  bg=GREEN, fg=BG, font=("Segoe UI", 11, "bold"),
                  relief="flat", padx=12, pady=6,
                  command=self._open_fusion).pack(pady=10)

    def _open_fusion(self):
        try:
            if sys.platform == "win32":
                os.startfile("fusion360://")
            else:
                subprocess.Popen(["open", "fusion360://"])
        except Exception:
            messagebox.showinfo("Open Fusion 360",
                                "Please open Fusion 360 manually from your Start Menu / Applications.")

    # ── Navigation ─────────────────────────────────────────────────────────

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

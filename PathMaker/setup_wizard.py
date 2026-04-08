"""
PathMaker Setup Wizard
======================
Double-click this file (or run: python setup_wizard.py) to install
PathMaker into Fusion 360.

No command-line knowledge needed. Just click Next!
"""

import sys
import os
import json
import shutil
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# ── Tool info ────────────────────────────────────────────────────────────────
TOOL_NAME    = "PathMaker"
TOOL_FOLDER  = "PathMaker"          # folder name = Fusion add-in name
TOOL_VERSION = "1.0.7"
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
    "Check",
    "Find Fusion",
    "Install",
    "Enable",
    "API Token",
    "Add Tools",
    "Toolpaths",
    "All Done!",
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
        self.geometry("820x560")
        self.resizable(False, True)   # allow vertical resize so nothing is ever clipped
        self.configure(bg=BG)

        self.step       = 0
        self.fusion_path = tk.StringVar()
        self.status_msgs = []

        self._detected = find_fusion_addin_path()
        if self._detected:
            self.fusion_path.set(self._detected)

        self._build_header()
        self._build_progress()
        self._build_scrollable_content()
        self._build_nav()
        self._show_step()

    def _build_scrollable_content(self):
        """Build the main content area as a scrollable canvas so no step is ever clipped."""
        container = tk.Frame(self, bg=BG)
        container.pack(fill="both", expand=True, padx=24, pady=8)

        self._scroll_canvas = tk.Canvas(container, bg=BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=self._scroll_canvas.yview)

        self._content_frame = tk.Frame(self._scroll_canvas, bg=BG)
        self._scroll_frame_id = self._scroll_canvas.create_window(
            (0, 0), window=self._content_frame, anchor="nw"
        )

        self._scroll_canvas.configure(yscrollcommand=scrollbar.set)

        # Keep inner frame width flush with the canvas as the window resizes
        self._scroll_canvas.bind(
            "<Configure>",
            lambda e: self._scroll_canvas.itemconfig(self._scroll_frame_id, width=e.width)
        )
        # Recompute scroll region whenever content is added or removed
        self._content_frame.bind(
            "<Configure>",
            lambda e: self._scroll_canvas.configure(
                scrollregion=self._scroll_canvas.bbox("all")
            )
        )

        self.bind_all("<MouseWheel>", self._on_mousewheel)

        scrollbar.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

    def _on_mousewheel(self, event):
        """Scroll the content canvas with the mouse wheel."""
        self._scroll_canvas.yview_scroll(-1 * (event.delta // 120), "units")

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
        self._scroll_canvas.yview_moveto(0)  # always start each step at the top

    def _card(self, parent=None):
        if parent is None:
            parent = self._content_frame
        f = tk.Frame(parent, bg=CARD_BG, padx=18, pady=14)
        f.pack(fill="x", pady=6)
        return f

    def _h(self, parent, text, color=ACCENT):
        tk.Label(parent, text=text, bg=CARD_BG, fg=color,
                 font=("Segoe UI", 12, "bold"), wraplength=720,
                 justify="left").pack(anchor="w")

    def _p(self, parent, text, color=FG):
        tk.Label(parent, text=text, bg=CARD_BG, fg=color,
                 font=("Segoe UI", 10), wraplength=720,
                 justify="left").pack(anchor="w", pady=2)

    # ── Steps ──────────────────────────────────────────────────────────────

    def _show_step(self):
        self._clear_content()
        self._update_progress()
        [self._step0, self._step1, self._step2, self._step3,
         self._step4, self._step5, self._step6, self._step7, self._step8][self.step]()
        self._back_btn.config(state="normal" if self.step > 0 else "disabled")
        last = self.step == len(STEPS) - 1
        self._next_btn.config(text="Finish ✓" if last else "Next →")

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
        """Step 4: Walk the user through enabling the add-in inside Fusion 360."""
        c = self._card()
        self._h(c, "🔌  Enable PathMaker Inside Fusion 360")
        self._p(c, "PathMaker is installed — now you need to turn it on. Follow these steps:", YELLOW)

        for stepNumber, instruction in enumerate([
            "Open Fusion 360  (use the button below if it's not open yet)",
            "Click the top menu:  Tools → Add-Ins  (or press  Shift + S)",
            "Click the  'Add-Ins'  tab  (not 'Scripts')",
            "Find  PathMaker  in the list",
            "Click the  toggle slider  to turn it  ON  ✅",
            "Check the box  'Run on Startup'  so it loads every time automatically",
            "Switch to the  Manufacturing  workspace — the PathMaker toolbar will be there!",
        ], 1):
            self._p(c, f"  {stepNumber}.  {instruction}")

        tk.Button(self._content_frame, text="Open Fusion 360 →",
                  bg=ACCENT, fg=BG, font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=10, pady=5,
                  command=self._open_fusion).pack(anchor="w", pady=(8, 0))

    def _step5(self):
        """Step 5: Configure the AI token.

        If GITHUB_AI_TOKEN is already in the environment (injected by Forge Vault),
        we write it straight into PathMaker's settings file and skip all manual steps.
        Otherwise we walk the user through getting a free token from GitHub.
        """
        detectedToken = os.environ.get('GITHUB_AI_TOKEN', '').strip()

        if detectedToken:
            c = self._card()
            self._h(c, "🔑  AI Token — Detected Automatically ✅")
            self._p(c, "Your GITHUB_AI_TOKEN was found in Forge Vault.", GREEN)
            self._p(c, "PathMaker will use it — no manual setup needed.", FG)

            wasWritten = self._write_token_to_settings(detectedToken)
            if wasWritten:
                self._p(c, "\n✅  Token saved to PathMaker's settings.", GREEN)
                self._p(c, "     You can skip the 'Settings → paste token' step inside Fusion 360.", FG)
            else:
                self._p(c, "\n⚠️   Token detected but not yet saved — PathMaker isn't installed to a path yet.", YELLOW)
                self._p(c, "     Go Back and confirm the Fusion 360 folder, then return here.", FG)
        else:
            # No vault token found — show the manual walkthrough
            c = self._card()
            self._h(c, "🔑  Get Your Free AI Token  (takes ~2 minutes)")
            self._p(c, "PathMaker uses GitHub's free AI to read Amazon tool listings and suggest feeds & speeds.")
            self._p(c, "You need a free GitHub account and a Personal Access Token with the 'models' scope.", YELLOW)

            self._p(c, "\nSteps to get your token:")
            for stepNumber, instruction in enumerate([
                "Go to:  github.com/marketplace/models  (button below)",
                "Sign in, or create a free GitHub account",
                "Click your profile picture  →  Settings",
                "Go to  Developer Settings  →  Personal Access Tokens  →  Fine-grained tokens",
                "Click  'Generate new token' — give it any name",
                "Under  'Permissions', enable the  models  scope  (read-only is enough)",
                "Click  Generate — copy the token that starts with  github_pat_",
                "In Fusion 360:  PathMaker toolbar  →  Settings  →  paste your token  →  Save",
            ], 1):
                self._p(c, f"  {stepNumber}.  {instruction}")

            self._p(c, "\n💡  Tip: tokens expire — if AI stops working, generate a new one here.", FG)

            tk.Button(self._content_frame, text="Open github.com/marketplace/models →",
                      bg=ACCENT, fg=BG, font=("Segoe UI", 10, "bold"),
                      relief="flat", padx=10, pady=5,
                      command=lambda: self._open_url("https://github.com/marketplace/models")).pack(anchor="w", pady=(8, 0))

    def _write_token_to_settings(self, token):
        """Write the AI token into PathMaker's settings file at the installed location.

        Creates the data directory and settings file if they don't exist yet,
        mirroring what PathMaker's _ensure_data_dir() does at add-in startup.
        Returns True on success, False if the install path is not set or write fails.
        """
        fusionPath = self.fusion_path.get().strip()
        if not fusionPath:
            return False

        settingsDir  = os.path.join(fusionPath, 'PathMaker', 'data')
        settingsPath = os.path.join(settingsDir, 'user_settings.json')

        try:
            os.makedirs(settingsDir, exist_ok=True)

            # Load existing settings so we don't wipe any other saved preferences
            if os.path.exists(settingsPath):
                with open(settingsPath, 'r', encoding='utf-8') as settingsFile:
                    settings = json.load(settingsFile)
            else:
                settings = {
                    'ai_token':           '',
                    'ai_token_validated': False,
                    'default_material':   'aluminum_6061_t6',
                    'default_quality':    'standard',
                    'two_sided_method':   'dowel_pins',
                    'show_review_dialog': True,
                    'first_run_complete': False,
                }

            settings['ai_token']           = token
            settings['ai_token_validated'] = False  # PathMaker validates on first use

            with open(settingsPath, 'w', encoding='utf-8') as settingsFile:
                json.dump(settings, settingsFile, indent=2)

            return True
        except Exception:
            return False

    def _step6(self):
        """Step 6: Show the user how to add their CNC tools from Amazon links."""
        c = self._card()
        self._h(c, "🔧  Add Your CNC Tools  (from Amazon)")
        self._p(c, "PathMaker builds your tool library from Amazon product links — no manual spec entry needed!")

        self._p(c, "\nHow to add a tool:")
        for stepNumber, instruction in enumerate([
            "Find any endmill or router bit on  Amazon  (one you own or plan to buy)",
            "Copy the  product URL  from your browser's address bar",
            "In Fusion 360:  Manufacturing workspace  →  PathMaker toolbar",
            "Click  Import Tool",
            "Paste the URL  and click  OK",
            "PathMaker reads the Amazon listing and saves the tool specs automatically ✅",
        ], 1):
            self._p(c, f"  {stepNumber}.  {instruction}")

        self._p(c, "\n💡  Do this for every bit you own.", YELLOW)
        self._p(c, "     The more tools you add, the smarter PathMaker gets at choosing the right one.", FG)

        c2 = self._card()
        self._h(c2, "📋  Manage Your Tools")
        self._p(c2, "Click  Manage Tools  in the toolbar to view, edit, or delete any saved tool.")

    def _step7(self):
        """Step 7: Explain how to add a material and generate toolpaths."""
        c = self._card()
        self._h(c, "⚡  Generate Your First Toolpath")
        self._p(c, "Once you have tools in your library, you're ready to let PathMaker do the CAM work.", YELLOW)

        self._p(c, "\nAdd a material (first time only):")
        for stepNumber, instruction in enumerate([
            "Click  Add Material  in the PathMaker toolbar",
            "Type the material name  (e.g. '1/4 inch Baltic Birch Plywood'  or  'Aluminum 6061')",
            "PathMaker uses AI to generate feeds & speeds and saves them — done!",
        ], 1):
            self._p(c, f"  {stepNumber}.  {instruction}")

        self._p(c, "\nGenerate toolpaths:")
        for stepNumber, instruction in enumerate([
            "Open your 3D model in Fusion 360's  Manufacturing  workspace",
            "Create a  CAM Setup  (set stock size and WCS zero point — normal Fusion step)",
            "Click  Generate Toolpaths  in the PathMaker toolbar",
            "Select your material from the dropdown",
            "Click  OK  — PathMaker analyzes the geometry and builds operations automatically",
            "Run the  Fusion simulation  to verify, then  post-process  as usual",
        ], 1):
            self._p(c, f"  {stepNumber}.  {instruction}")

        self._p(c, "\n💡  For 2-sided carving, use the  2-Sided Carve  button — it guides dowel pin placement.", FG)

    def _step8(self):
        """Step 8: Final summary screen with the full toolbar reference."""
        c = self._card()
        self._h(c, "🎉  You're Ready to Machine!")
        self._p(c, "PathMaker is installed, enabled, and set up. Here's a quick reference:", GREEN)

        toolbar_rows = [
            ("Generate Toolpaths", "Analyzes your model and creates all CAM operations"),
            ("Import Tool",        "Paste an Amazon URL → tool specs saved automatically"),
            ("Manage Tools",       "View, edit, or delete tools in your library"),
            ("Add Material",       "AI generates feeds & speeds for any material"),
            ("2-Sided Carve",      "Guided flip operation with dowel pin alignment"),
            ("Settings",           "API token, machine profile, default preferences"),
        ]
        for buttonName, description in toolbar_rows:
            self._p(c, f"  {'▸':>2}  {buttonName:<22}  {description}")

        self._p(c, "\n⚙  Your machine is pre-configured for:", FG)
        self._p(c, "     Onefinity Machinist  •  Makita RT0701C  •  9,600–30,000 RPM", YELLOW)
        self._p(c, "     Change this any time under  Settings  in the PathMaker toolbar.", FG)

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

    def _open_url(self, url):
        """Open a URL in the user's default web browser."""
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            messagebox.showinfo("Open Browser",
                                f"Please visit this URL in your browser:\n{url}")

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

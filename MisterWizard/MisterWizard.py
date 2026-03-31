"""
MisterWizard — Mist Coolant Solenoid Setup for Onefinity / Buildbotics
======================================================================
Standalone Python wizard (tkinter — no extra dependencies).

Run with:  python MisterWizard.py

Guides you through:
  Tab 1: Buildbotics web UI configuration (M7/M8 output pin setup)
  Tab 2: Solenoid wiring diagram & parts list
  Tab 3: Timing & G-code command settings
  Tab 4: Test G-code generator (upload .nc to Onefinity to verify)
  Tab 5: G-code injector (add M7/M9 to existing post-processed .nc files)

Hardware requirements:
  - Onefinity Machinist with Buildbotics controller
  - 5V TTL output from Buildbotics M7/M8 pin → relay/opto-isolator
  - 12V or 24V solenoid valve on your mist/coolant line
  - Flyback diode (1N4007) across the solenoid coil
  - DO NOT wire solenoid directly to GPIO — damage will result
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import json
import webbrowser

# Allow running from project root OR from FusionCam directory
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
if _THIS_DIR not in sys.path:
    sys.path.insert(0, _THIS_DIR)

import mister_control

# ── Window geometry ──────────────────────────────────────────────
WINDOW_TITLE = "MisterWizard — Onefinity Mist Coolant Setup"
WINDOW_SIZE = "820x620"
PAD = 12
INNER_PAD = 6

# ── Colors ───────────────────────────────────────────────────────
CLR_WARN = "#c0392b"
CLR_OK = "#27ae60"
CLR_INFO = "#2980b9"
CLR_BG_NOTE = "#fef9e7"


# ═══════════════════════════════════════════════════════════════════
#  HELPER — labeled frame
# ═══════════════════════════════════════════════════════════════════
def _lf(parent, text, **kwargs):
    """Return a ttk.LabelFrame with consistent padding."""
    f = ttk.LabelFrame(parent, text=text, padding=INNER_PAD)
    f.pack(fill=tk.BOTH, expand=kwargs.get('expand', False),
           padx=PAD, pady=(0, PAD))
    return f


def _note(parent, text, color=CLR_BG_NOTE):
    """A small highlighted note label."""
    lbl = tk.Label(parent, text=text, bg=color, relief=tk.FLAT,
                   justify=tk.LEFT, wraplength=720, anchor='w', padx=6, pady=4)
    lbl.pack(fill=tk.X, padx=PAD, pady=(0, INNER_PAD))
    return lbl


# ═══════════════════════════════════════════════════════════════════
#  TAB 1 — Buildbotics Web UI Setup
# ═══════════════════════════════════════════════════════════════════
class Tab1_ControllerSetup(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        ttk.Label(self, text="Step 1 — Configure Your Buildbotics Controller",
                  font=("", 12, "bold")).pack(anchor='w', padx=PAD, pady=(PAD, 4))

        _note(self,
              "The Buildbotics firmware that runs your Onefinity has built-in M7 (mist) "
              "and M8 (flood) coolant outputs. You need to:\n"
              "  a) Identify which physical pin on your controller board maps to M7\n"
              "  b) Wire your relay to that pin (see Tab 2)\n"
              "  c) Verify the controller accepts M7 commands via the MDI console",
              color="#eaf4fb")

        # — Controller URL —
        url_frame = _lf(self, "Onefinity / Buildbotics Web UI URL")
        row = ttk.Frame(url_frame)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Controller URL:").pack(side=tk.LEFT)
        self.url_var = tk.StringVar(value=self.app.config.get('controller_url', 'http://onefinity.local'))
        ttk.Entry(row, textvariable=self.url_var, width=34).pack(side=tk.LEFT, padx=6)
        ttk.Button(row, text="Open in Browser",
                   command=self._open_browser).pack(side=tk.LEFT, padx=4)
        ttk.Button(row, text="Save URL",
                   command=self._save_url).pack(side=tk.LEFT)
        ttk.Label(url_frame,
                  text="Common addresses: http://onefinity.local  |  http://bbctrl.local  |  http://192.168.1.x",
                  foreground="gray").pack(anchor='w', pady=(4, 0))

        # — Web UI navigation —
        nav_frame = _lf(self, "Buildbotics Web UI — Coolant Pin Configuration")
        steps = [
            "1. Open the Buildbotics web UI in your browser (use the button above).",
            "2. Click the ⚙ Settings icon (gear, top-right of the web UI).",
            "3. In the Settings panel, look for the 'Tool' or 'I/O' tab.",
            "4. Under 'Coolant', you will see output entries for 'Mist' (M7) and 'Flood' (M8).",
            "5. Assign the appropriate output pin number for your relay wiring.",
            "   • The Buildbotics board has labelled tool output headers — use the one you wired.",
            "6. Click Save / Apply in the web UI to persist the setting.",
            "7. Test with an MDI command (below) to confirm the output fires.",
        ]
        for s in steps:
            ttk.Label(nav_frame, text=s, justify=tk.LEFT,
                      wraplength=700).pack(anchor='w', pady=1)

        # — MDI test —
        mdi_frame = _lf(self, "Quick MDI Test (from Onefinity Web UI MDI Console)")
        ttk.Label(mdi_frame,
                  text="In the Onefinity web UI, navigate to the 'Control' tab → MDI input box, "
                       "then type these commands one at a time:",
                  wraplength=700, justify=tk.LEFT).pack(anchor='w')
        mdi_cmds = tk.Frame(mdi_frame, bg="#1e1e1e", padx=8, pady=6)
        mdi_cmds.pack(fill=tk.X, pady=(6, 0))
        for cmd, desc in [("M7", "→ Mist solenoid should fire (you'll hear the click)"),
                           ("G4 P3", "→ Wait 3 seconds"),
                           ("M9", "→ Mist solenoid should release"),
                           ("M8", "→ Flood output (if wired)"),
                           ("M9", "→ All coolant off")]:
            row = tk.Frame(mdi_cmds, bg="#1e1e1e")
            row.pack(fill=tk.X)
            tk.Label(row, text=cmd, bg="#1e1e1e", fg="#7ec8e3",
                     font=("Courier", 11, "bold"), width=8, anchor='w').pack(side=tk.LEFT)
            tk.Label(row, text=desc, bg="#1e1e1e", fg="#cccccc",
                     font=("Courier", 10)).pack(side=tk.LEFT)

        _note(self,
              "⚠️  If the solenoid does NOT click when you send M7: check your wiring (Tab 2) and "
              "confirm the output pin is correctly assigned in Buildbotics Settings.",
              color="#fdecea")

    def _open_browser(self):
        url = self.url_var.get().strip() or 'http://onefinity.local'
        webbrowser.open(url)

    def _save_url(self):
        self.app.config['controller_url'] = self.url_var.get().strip()
        self.app.save_config()
        messagebox.showinfo("Saved", "Controller URL saved.")


# ═══════════════════════════════════════════════════════════════════
#  TAB 2 — Wiring Guide
# ═══════════════════════════════════════════════════════════════════
class Tab2_WiringGuide(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        ttk.Label(self, text="Step 2 — Solenoid Wiring",
                  font=("", 12, "bold")).pack(anchor='w', padx=PAD, pady=(PAD, 4))

        _note(self,
              "⚠️  NEVER connect a solenoid valve directly to the Buildbotics GPIO pin. "
              "The 5V TTL output cannot drive inductive loads. "
              "You MUST use an opto-isolator + relay (or a relay module with built-in isolation).",
              color="#fdecea")

        opt_frame = _lf(self, "Solenoid Configuration")
        r1 = ttk.Frame(opt_frame)
        r1.pack(fill=tk.X, pady=2)
        ttk.Label(r1, text="Solenoid Voltage:").pack(side=tk.LEFT)
        self.volt_var = tk.StringVar(value=self.app.config.get('solenoid_voltage', '12V'))
        for v in ('12V', '24V'):
            ttk.Radiobutton(r1, text=v, value=v, variable=self.volt_var,
                            command=self._refresh_diagram).pack(side=tk.LEFT, padx=8)

        r2 = ttk.Frame(opt_frame)
        r2.pack(fill=tk.X, pady=2)
        ttk.Label(r2, text="Relay Type:").pack(side=tk.LEFT)
        self.relay_var = tk.StringVar(value=self.app.config.get('relay_type', 'normally_open'))
        for label, val in [("Normally Open (NO) — recommended", "normally_open"),
                            ("Normally Closed (NC)", "normally_closed")]:
            ttk.Radiobutton(r2, text=label, value=val, variable=self.relay_var,
                            command=self._refresh_diagram).pack(side=tk.LEFT, padx=8)

        save_btn = ttk.Button(opt_frame, text="Save & Refresh Diagram",
                              command=self._save_and_refresh)
        save_btn.pack(anchor='w', pady=(6, 0))

        diag_frame = _lf(self, "Wiring Diagram", expand=True)
        self.diag_text = scrolledtext.ScrolledText(
            diag_frame, font=("Courier", 9), wrap=tk.NONE,
            height=22, state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4")
        self.diag_text.pack(fill=tk.BOTH, expand=True)
        self._refresh_diagram()

    def _refresh_diagram(self):
        diagram = mister_control.get_wiring_diagram(
            self.volt_var.get(), self.relay_var.get())
        self.diag_text.config(state=tk.NORMAL)
        self.diag_text.delete("1.0", tk.END)
        self.diag_text.insert(tk.END, diagram)
        self.diag_text.config(state=tk.DISABLED)

    def _save_and_refresh(self):
        self.app.config['solenoid_voltage'] = self.volt_var.get()
        self.app.config['relay_type'] = self.relay_var.get()
        self.app.save_config()
        self._refresh_diagram()


# ═══════════════════════════════════════════════════════════════════
#  TAB 3 — Timing & G-Code Settings
# ═══════════════════════════════════════════════════════════════════
class Tab3_TimingSettings(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        ttk.Label(self, text="Step 3 — Timing & Command Settings",
                  font=("", 12, "bold")).pack(anchor='w', padx=PAD, pady=(PAD, 4))

        _note(self,
              "These settings control how M7/M9 commands are injected around your toolpaths. "
              "The pre-mist delay lets coolant flow before the cutter engages; "
              "the post-mist delay keeps cooling running while chips clear.",
              color="#eaf4fb")

        # — G-code mode —
        mode_frame = _lf(self, "G-Code Command Mode")
        self.mode_var = tk.StringVar(value=self.app.config.get('pin_mode', 'M7_mist'))
        for key, info in mister_control.BUILDBOTICS_PINS.items():
            rb = ttk.Radiobutton(mode_frame, text=info['label'],
                                 value=key, variable=self.mode_var,
                                 command=self._toggle_custom)
            rb.pack(anchor='w')
            ttk.Label(mode_frame, text=f"   {info['description']}",
                      foreground="gray").pack(anchor='w')

        cust_frame = ttk.Frame(mode_frame)
        cust_frame.pack(fill=tk.X, pady=(4, 0))
        ttk.Label(cust_frame, text="Custom ON command:").grid(row=0, column=0, sticky='w', pady=2)
        self.custom_on = tk.StringVar(value=self.app.config.get('custom_gcode_on', ''))
        self._cust_on_entry = ttk.Entry(cust_frame, textvariable=self.custom_on, width=12)
        self._cust_on_entry.grid(row=0, column=1, padx=6)
        ttk.Label(cust_frame, text="Custom OFF command:").grid(row=1, column=0, sticky='w', pady=2)
        self.custom_off = tk.StringVar(value=self.app.config.get('custom_gcode_off', ''))
        self._cust_off_entry = ttk.Entry(cust_frame, textvariable=self.custom_off, width=12)
        self._cust_off_entry.grid(row=1, column=1, padx=6)
        self._toggle_custom()

        # — Delays —
        delay_frame = _lf(self, "Mist Timing Delays")
        grid = ttk.Frame(delay_frame)
        grid.pack(fill=tk.X)

        ttk.Label(grid, text="Pre-mist delay (seconds):").grid(
            row=0, column=0, sticky='w', pady=4)
        self.pre_delay = tk.DoubleVar(
            value=self.app.config.get('pre_mist_delay_seconds', 2.0))
        ttk.Spinbox(grid, from_=0, to=15, increment=0.5,
                    textvariable=self.pre_delay, width=8).grid(row=0, column=1, padx=8)
        ttk.Label(grid,
                  text="Mist starts this many seconds BEFORE the spindle starts cutting.",
                  foreground="gray").grid(row=0, column=2, sticky='w')

        ttk.Label(grid, text="Post-mist delay (seconds):").grid(
            row=1, column=0, sticky='w', pady=4)
        self.post_delay = tk.DoubleVar(
            value=self.app.config.get('post_mist_delay_seconds', 5.0))
        ttk.Spinbox(grid, from_=0, to=30, increment=0.5,
                    textvariable=self.post_delay, width=8).grid(row=1, column=1, padx=8)
        ttk.Label(grid,
                  text="Mist continues this many seconds AFTER the spindle stops.",
                  foreground="gray").grid(row=1, column=2, sticky='w')

        # — Materials —
        mat_frame = _lf(self, "Enable Mister For")
        self.all_metals = tk.BooleanVar(
            value=self.app.config.get('apply_to_all_metals', True))
        ttk.Checkbutton(mat_frame,
                        text="All metals (aluminum, steel, brass, copper)",
                        variable=self.all_metals).pack(anchor='w')
        self.enabled_var = tk.BooleanVar(
            value=self.app.config.get('enabled', False))
        ttk.Checkbutton(mat_frame,
                        text="Mister enabled (inject M7/M9 into G-code)",
                        variable=self.enabled_var).pack(anchor='w', pady=(4, 0))

        ttk.Button(self, text="💾  Save Settings",
                   command=self._save).pack(anchor='w', padx=PAD, pady=PAD)
        self._status = ttk.Label(self, text="", foreground=CLR_OK)
        self._status.pack(anchor='w', padx=PAD)

    def _toggle_custom(self):
        state = tk.NORMAL if self.mode_var.get() == 'custom_m' else tk.DISABLED
        self._cust_on_entry.config(state=state)
        self._cust_off_entry.config(state=state)

    def _save(self):
        self.app.config.update({
            'pin_mode': self.mode_var.get(),
            'custom_gcode_on': self.custom_on.get(),
            'custom_gcode_off': self.custom_off.get(),
            'pre_mist_delay_seconds': round(self.pre_delay.get(), 1),
            'post_mist_delay_seconds': round(self.post_delay.get(), 1),
            'apply_to_all_metals': self.all_metals.get(),
            'enabled': self.enabled_var.get(),
        })
        valid, errors, warnings = mister_control.validate_config(self.app.config)
        if errors:
            messagebox.showerror("Validation Error", "\n".join(errors))
            return
        self.app.save_config()
        msg = "Settings saved."
        if warnings:
            msg += "\n\nWarnings:\n" + "\n".join(f"⚠ {w}" for w in warnings)
            messagebox.showwarning("Saved with Warnings", msg)
        self._status.config(text="✓ Settings saved successfully.")


# ═══════════════════════════════════════════════════════════════════
#  TAB 4 — Test G-Code Generator
# ═══════════════════════════════════════════════════════════════════
class Tab4_TestGCode(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build()

    def _build(self):
        ttk.Label(self, text="Step 4 — Generate & Run a Solenoid Test",
                  font=("", 12, "bold")).pack(anchor='w', padx=PAD, pady=(PAD, 4))

        _note(self,
              "This generates a short .nc file that cycles M7 ON and OFF without starting the "
              "spindle. Upload it to your Onefinity web UI and run it to confirm your solenoid "
              "fires correctly before machining anything.",
              color="#eaf4fb")

        _note(self,
              "⚠️  Run this test WITHOUT a tool installed and WITHOUT material clamped. "
              "The spindle is NOT started, but keep clear of the machine during the test.",
              color="#fdecea")

        btn_row = ttk.Frame(self)
        btn_row.pack(fill=tk.X, padx=PAD, pady=(0, INNER_PAD))
        ttk.Button(btn_row, text="⚡  Generate Test G-Code File",
                   command=self._generate).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(btn_row, text="📂  Open Output Folder",
                   command=self._open_folder).pack(side=tk.LEFT)

        code_frame = _lf(self, "Generated G-Code Preview", expand=True)
        self.code_text = scrolledtext.ScrolledText(
            code_frame, font=("Courier", 9), wrap=tk.NONE,
            height=18, state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4")
        self.code_text.pack(fill=tk.BOTH, expand=True)

        self._path_label = ttk.Label(self, text="", foreground=CLR_OK)
        self._path_label.pack(anchor='w', padx=PAD, pady=(4, 0))

        instr_frame = _lf(self, "How to run on Onefinity")
        steps = [
            "1. Click 'Generate Test G-Code File' above.",
            "2. Open the Onefinity web UI in your browser.",
            "3. In the 'Files' or 'Upload' section, upload the mister_test.nc file.",
            "4. Click 'Run' (make sure 'Confirm start' is enabled).",
            "5. Watch/listen for the solenoid to click ON and OFF during the test.",
            "6. If the solenoid doesn't fire — re-check wiring (Tab 2) and Buildbotics pin settings (Tab 1).",
        ]
        for s in steps:
            ttk.Label(instr_frame, text=s, justify=tk.LEFT,
                      wraplength=700).pack(anchor='w', pady=1)

    def _generate(self):
        gcode, path = mister_control.generate_test_gcode(self.app.config)
        self.code_text.config(state=tk.NORMAL)
        self.code_text.delete("1.0", tk.END)
        self.code_text.insert(tk.END, gcode)
        self.code_text.config(state=tk.DISABLED)
        self._path_label.config(text=f"✓ Saved: {path}")

    def _open_folder(self):
        folder = os.path.join(os.path.expanduser('~'), 'Documents', 'FusionCam', 'GCode')
        os.makedirs(folder, exist_ok=True)
        os.startfile(folder)


# ═══════════════════════════════════════════════════════════════════
#  TAB 5 — G-Code Injector
# ═══════════════════════════════════════════════════════════════════
class Tab5_GCodeInjector(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._nc_path = None
        self._build()

    def _build(self):
        ttk.Label(self, text="Step 5 — Inject Coolant Commands into Existing G-Code",
                  font=("", 12, "bold")).pack(anchor='w', padx=PAD, pady=(PAD, 4))

        _note(self,
              "After you post-process a job from Fusion 360, use this tool to inject M7/M9 "
              "commands around every spindle start (M3) and stop (M5) in the .nc file. "
              "The original file is backed up before any changes are made.",
              color="#eaf4fb")

        file_frame = _lf(self, "Select G-Code File")
        row = ttk.Frame(file_frame)
        row.pack(fill=tk.X)
        self._file_label = ttk.Label(row, text="No file selected", foreground="gray")
        self._file_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(row, text="Browse…",
                   command=self._browse).pack(side=tk.RIGHT)

        action_row = ttk.Frame(self)
        action_row.pack(fill=tk.X, padx=PAD, pady=INNER_PAD)
        ttk.Button(action_row, text="👁  Preview Injections",
                   command=self._preview).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(action_row, text="💉  Inject & Save",
                   command=self._inject).pack(side=tk.LEFT)

        preview_frame = _lf(self, "Preview / Result", expand=True)
        self.preview_text = scrolledtext.ScrolledText(
            preview_frame, font=("Courier", 9), wrap=tk.NONE,
            height=20, state=tk.DISABLED, bg="#1e1e1e", fg="#d4d4d4")
        self.preview_text.pack(fill=tk.BOTH, expand=True)

        self._status = ttk.Label(self, text="", foreground=CLR_OK)
        self._status.pack(anchor='w', padx=PAD, pady=(4, 0))

    def _browse(self):
        path = filedialog.askopenfilename(
            title="Select G-Code File",
            filetypes=[("G-Code files", "*.nc *.gcode *.tap"), ("All files", "*.*")])
        if path:
            self._nc_path = path
            self._file_label.config(text=os.path.basename(path), foreground="black")
            self._status.config(text="")

    def _preview(self):
        if not self._nc_path:
            messagebox.showwarning("No File", "Please select a G-code file first.")
            return
        if not self.app.config.get('enabled', False):
            messagebox.showwarning("Mister Disabled",
                                   "Mister is disabled in Settings (Tab 3). Enable it to preview injections.")
            return
        on_cmd, off_cmd = mister_control.get_gcode_commands(self.app.config)
        pre = self.app.config.get('pre_mist_delay_seconds', 2.0)
        post = self.app.config.get('post_mist_delay_seconds', 5.0)

        try:
            with open(self._nc_path, 'r', encoding='utf-8') as f:
                original = f.read()
        except Exception as e:
            messagebox.showerror("Read Error", str(e))
            return

        preview_lines = []
        for line in original.splitlines():
            s = line.strip().upper()
            import re
            if re.match(r'^M0*[34]\b', s):
                preview_lines.append(f">>> {on_cmd}    ; ← MIST ON (injected)")
                if pre > 0:
                    preview_lines.append(f">>> G4 P{pre:.1f}  ; ← pre-mist dwell")
            preview_lines.append(line)
            if re.match(r'^M0*5\b', s):
                if post > 0:
                    preview_lines.append(f">>> G4 P{post:.1f}  ; ← post-mist dwell")
                preview_lines.append(f">>> {off_cmd}   ; ← MIST OFF (injected)")

        self._set_preview('\n'.join(preview_lines))
        self._status.config(text="Preview generated — lines marked >>> will be injected.", foreground=CLR_INFO)

    def _inject(self):
        if not self._nc_path:
            messagebox.showwarning("No File", "Please select a G-code file first.")
            return
        if not self.app.config.get('enabled', False):
            messagebox.showwarning("Mister Disabled",
                                   "Mister is disabled in Settings (Tab 3). Enable it first.")
            return

        # Backup original
        backup_path = self._nc_path + '.backup'
        try:
            import shutil
            shutil.copy2(self._nc_path, backup_path)
        except Exception as e:
            messagebox.showerror("Backup Failed", f"Could not create backup: {e}")
            return

        try:
            out_path, summary = mister_control.inject_into_gcode(
                self._nc_path, self.app.config, output_path=self._nc_path)
        except Exception as e:
            messagebox.showerror("Injection Failed", str(e))
            return

        self._set_preview(summary + f"\n\nOriginal backed up to:\n{backup_path}")
        self._status.config(
            text=f"✓ Injected successfully. Backup: {os.path.basename(backup_path)}",
            foreground=CLR_OK)

    def _set_preview(self, text):
        self.preview_text.config(state=tk.NORMAL)
        self.preview_text.delete("1.0", tk.END)
        self.preview_text.insert(tk.END, text)
        self.preview_text.config(state=tk.DISABLED)


# ═══════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ═══════════════════════════════════════════════════════════════════
class MisterWizardApp:
    def __init__(self, root):
        self.root = root
        root.title(WINDOW_TITLE)
        root.geometry(WINDOW_SIZE)
        root.resizable(True, True)

        # Load config (mister section of user_settings.json)
        raw = mister_control.load_mister_config()
        self.config = dict(mister_control.DEFAULT_CONFIG)
        self.config.update(raw)

        self._build_header()
        self._build_notebook()
        self._build_footer()

    def _build_header(self):
        header = tk.Frame(self.root, bg="#2c3e50", padx=12, pady=8)
        header.pack(fill=tk.X)
        tk.Label(header, text="💧 MisterWizard",
                 bg="#2c3e50", fg="white",
                 font=("", 14, "bold")).pack(side=tk.LEFT)
        tk.Label(header, text="Mist Coolant Solenoid Setup for Onefinity / Buildbotics",
                 bg="#2c3e50", fg="#bdc3c7",
                 font=("", 10)).pack(side=tk.LEFT, padx=12)

    def _build_notebook(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        tabs = [
            ("1 · Controller Setup", Tab1_ControllerSetup),
            ("2 · Wiring Guide", Tab2_WiringGuide),
            ("3 · Timing & Settings", Tab3_TimingSettings),
            ("4 · Test G-Code", Tab4_TestGCode),
            ("5 · Inject G-Code", Tab5_GCodeInjector),
        ]
        for label, cls in tabs:
            frame = cls(self.notebook, self)
            self.notebook.add(frame, text=label)

    def _build_footer(self):
        footer = tk.Frame(self.root, bg="#ecf0f1", padx=8, pady=4)
        footer.pack(fill=tk.X, side=tk.BOTTOM)
        enabled_text = ("✅ Mister ENABLED" if self.config.get('enabled')
                        else "⬜ Mister disabled — enable in Tab 3")
        self._footer_label = tk.Label(
            footer, text=enabled_text, bg="#ecf0f1",
            font=("", 9), anchor='w')
        self._footer_label.pack(side=tk.LEFT)
        tk.Label(footer,
                 text="Config: data/user_settings.json  |  Onefinity/Buildbotics controller",
                 bg="#ecf0f1", fg="gray", font=("", 8)).pack(side=tk.RIGHT)

    def save_config(self):
        mister_control.save_mister_config(self.config)
        enabled_text = ("✅ Mister ENABLED" if self.config.get('enabled')
                        else "⬜ Mister disabled — enable in Tab 3")
        self._footer_label.config(text=enabled_text)


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default='')  # suppress default icon error on some systems
    except Exception:
        pass

    app = MisterWizardApp(root)
    root.mainloop()


if __name__ == '__main__':
    main()



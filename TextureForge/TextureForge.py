"""
TextureForge — Procedural Surface Texture Stamp for Fusion 360.

A standalone Fusion 360 add-in (Design workspace) that applies procedural
surface textures (carbon fiber, diamond knurl, wood grain, brushed metal,
leather) to model faces using Fusion's Emboss feature.

Works for:
  ✓ 3D Printing  — any scale; real geometry in the STL
  ✓ CNC Milling  — scale ≥ 2× tool diameter; use V-bit or ball-nose

Install:
  Copy this folder to Fusion's add-ins directory:
    Windows: %appdata%\\Autodesk\\Autodesk Fusion 360\\API\\AddIns\\TextureForge
  Then: Fusion 360 → Tools → Add-Ins → Run Add-In → TextureForge

Companion tool for AutoPath (Manufacturing workspace CAM).
"""

import adsk.core
import adsk.fusion
import traceback
import sys
import os

# Make submodules importable when Fusion loads this add-in directly
ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
if ADDIN_DIR not in sys.path:
    sys.path.insert(0, ADDIN_DIR)

_app      = None
_ui       = None
_handlers = []

PANEL_ID          = 'TextureForgePanel'
CMD_STAMP         = 'TextureForgeStampTexture'
CMD_IMAGE_TEXTURE = 'TextureForgeImageTexture'


# ─── Command created handler ──────────────────────────────────────────────────

class StampTextureCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Routes the command-created event into the ui/handlers module."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ui.handlers import on_texture_stamp_created
            on_texture_stamp_created(args)
        except Exception:
            _ui.messageBox(
                f'TextureForge — Stamp Texture Error:\n{traceback.format_exc()}',
                'TextureForge')


class ImageTextureCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Routes the image-texture command into the ui/handlers module."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ui.handlers import on_image_texture_created
            on_image_texture_created(args)
        except Exception:
            _ui.messageBox(
                f'TextureForge — Image Texture Error:\n{traceback.format_exc()}',
                'TextureForge')


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _res(name):
    """Return absolute path to a resources/<name> subfolder for icon PNGs."""
    return os.path.join(ADDIN_DIR, 'resources', name)


def _create_button(cmd_def_id, label, tooltip, handler_class, resource_folder=''):
    cmd_defs = _ui.commandDefinitions
    existing = cmd_defs.itemById(cmd_def_id)
    if existing:
        existing.deleteMe()
    cmd_def = cmd_defs.addButtonDefinition(cmd_def_id, label, tooltip, resource_folder)
    handler = handler_class()
    cmd_def.commandCreated.add(handler)
    _handlers.append(handler)
    return cmd_def


# ─── Add-in entry points ──────────────────────────────────────────────────────

def _log(msg):
    """Write a startup log line to ADDIN_DIR/textureforge.log for debugging."""
    try:
        log_path = os.path.join(ADDIN_DIR, 'textureforge.log')
        with open(log_path, 'a', encoding='utf-8') as f:
            import datetime
            f.write(f'[{datetime.datetime.now().isoformat()}] {msg}\n')
    except Exception:
        pass  # Never let logging break the add-in


def run(context):
    global _app, _ui
    _log('run() called')
    try:
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface
        _log('Fusion app & UI obtained')

        # Try several workspace IDs — the exact string varies by Fusion version.
        # We add the panel to ALL design-related workspaces we can find so the
        # user sees it regardless of which sub-mode they're in.
        DESIGN_WS_IDS = [
            'FusionSolidEnvironment',   # Design – Solid (most common)
            'FusionSurfaceEnvironment', # Design – Surface
        ]

        added_to = []
        for ws_id in DESIGN_WS_IDS:
            ws = _ui.workspaces.itemById(ws_id)
            if not ws:
                continue

            panels = ws.toolbarPanels
            existing = panels.itemById(PANEL_ID)
            if existing:
                existing.deleteMe()

            panel = panels.add(PANEL_ID, 'TextureForge', '', False)

            stamp_cmd = _create_button(
                CMD_STAMP,
                'Stamp Texture',
                'Apply a procedural surface texture (carbon fiber, knurl, wood grain, '
                'brushed metal, leather) to any model face.\n\n'
                'Works for 3D printing (any scale) and CNC milling (scale ≥ 2× tool dia).',
                StampTextureCommandCreatedHandler,
                _res('StampTexture')
            )
            panel.controls.addCommand(stamp_cmd)

            img_cmd = _create_button(
                CMD_IMAGE_TEXTURE,
                'Texture From Image',
                'Import an SVG, PNG, or BMP file and stamp it as an emboss texture onto any face.\n\n'
                'SVG: clean vector paths traced directly.\n'
                'PNG / BMP: pixel-stamp effect — each dark pixel becomes a small raised square.',
                ImageTextureCommandCreatedHandler,
                _res('ImageTexture')
            )
            panel.controls.addCommand(img_cmd)
            added_to.append(ws_id)
            _log(f'Panel added to workspace: {ws_id}')

        if not added_to:
            ws_list = ', '.join(w.id for w in _ui.workspaces) if _ui else 'unknown'
            _log(f'ERROR: No design workspace found. Available: {ws_list}')
            _ui.messageBox(
                'TextureForge: could not find the Design workspace.\n\n'
                'Available workspaces:\n' + ws_list + '\n\n'
                'Please open an issue at github.com/mikejsmith1985/MakerTools '
                'and paste the workspace IDs above.',
                'TextureForge — Setup')
        else:
            _log(f'run() completed successfully. Added to: {added_to}')

    except Exception:
        tb = traceback.format_exc()
        _log(f'EXCEPTION in run():\n{tb}')
        if _ui:
            _ui.messageBox(
                f'TextureForge failed to start:\n{tb}',
                'TextureForge')


def stop(context):
    global _ui
    try:
        if _ui:
            for ws_id in ('FusionSolidEnvironment', 'FusionSurfaceEnvironment'):
                ws = _ui.workspaces.itemById(ws_id)
                if ws:
                    panel = ws.toolbarPanels.itemById(PANEL_ID)
                    if panel:
                        panel.deleteMe()

            for cmd_id in (CMD_STAMP, CMD_IMAGE_TEXTURE):
                cmd_def = _ui.commandDefinitions.itemById(cmd_id)
                if cmd_def:
                    cmd_def.deleteMe()

        _handlers.clear()

    except Exception:
        if _ui:
            _ui.messageBox(
                f'TextureForge failed to stop cleanly:\n{traceback.format_exc()}',
                'TextureForge')



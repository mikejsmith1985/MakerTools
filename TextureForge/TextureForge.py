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
_dir = os.path.dirname(__file__)
if _dir not in sys.path:
    sys.path.insert(0, _dir)

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

def _create_button(cmd_def_id, label, tooltip, handler_class):
    cmd_defs = _ui.commandDefinitions
    existing = cmd_defs.itemById(cmd_def_id)
    if existing:
        existing.deleteMe()
    cmd_def = cmd_defs.addButtonDefinition(cmd_def_id, label, tooltip)
    handler = handler_class()
    cmd_def.commandCreated.add(handler)
    _handlers.append(handler)
    return cmd_def


# ─── Add-in entry points ──────────────────────────────────────────────────────

def run(context):
    global _app, _ui
    try:
        _app = adsk.core.Application.get()
        _ui  = _app.userInterface

        # TextureForge lives in the Design workspace where Emboss features live
        design_ws = _ui.workspaces.itemById('FusionSolidEnvironment')
        if not design_ws:
            _ui.messageBox(
                'TextureForge requires the Design workspace.\n'
                'Please switch to Design (Solid environment).',
                'TextureForge')
            return

        panels = design_ws.toolbarPanels
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
            StampTextureCommandCreatedHandler
        )
        panel.controls.addCommand(stamp_cmd)

        img_cmd = _create_button(
            CMD_IMAGE_TEXTURE,
            'Texture From Image',
            'Import an SVG, PNG, or BMP file and stamp it as an emboss texture onto any face.\n\n'
            'SVG: clean vector paths traced directly.\n'
            'PNG / BMP: pixel-stamp effect — each dark pixel becomes a small raised square.',
            ImageTextureCommandCreatedHandler
        )
        panel.controls.addCommand(img_cmd)

    except Exception:
        if _ui:
            _ui.messageBox(
                f'TextureForge failed to start:\n{traceback.format_exc()}',
                'TextureForge')


def stop(context):
    global _ui
    try:
        if _ui:
            design_ws = _ui.workspaces.itemById('FusionSolidEnvironment')
            if design_ws:
                rf_panel = design_ws.toolbarPanels.itemById(PANEL_ID)
                if rf_panel:
                    rf_panel.deleteMe()

            cmd_def = _ui.commandDefinitions.itemById(CMD_STAMP)
            if cmd_def:
                cmd_def.deleteMe()

            cmd_def = _ui.commandDefinitions.itemById(CMD_IMAGE_TEXTURE)
            if cmd_def:
                cmd_def.deleteMe()

        _handlers.clear()

    except Exception:
        if _ui:
            _ui.messageBox(
                f'TextureForge failed to stop cleanly:\n{traceback.format_exc()}',
                'TextureForge')



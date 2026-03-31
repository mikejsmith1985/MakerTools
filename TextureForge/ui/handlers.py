"""
UI Handlers for TextureForge.
Provides the Stamp Texture command dialog with CNC and 3D-print mode awareness.
"""

import adsk.core
import adsk.fusion
import traceback

_handlers = []

# ── Recommended minimum scale per texture per mode ───────────────────────────
# (scale_mm must exceed these for reliable results)
MIN_SCALE_PRINT_MM = {
    'carbon_fiber':  1.0,
    'knurl_diamond': 1.0,
    'wood_grain':    2.0,
    'brushed_metal': 0.5,
    'leather':       2.0,
    'honeycomb':     3.0,
}

# Approximate minimum recommended tool diameter for CNC per texture
CNC_TOOL_HINTS = {
    'carbon_fiber':  ('V-bit or 1/16" flat end mill', 1.6),
    'knurl_diamond': ('V-bit (gives the most authentic look)', 1.6),
    'wood_grain':    ('1/8" ball-nose end mill', 3.2),
    'brushed_metal': ('1/32" ball-nose or V-bit', 0.8),
    'leather':       ('1/8" ball-nose end mill', 3.2),
    'honeycomb':     ('V-bit or 1/8" flat end mill', 3.2),
}


class TextureInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Update scale/depth defaults when texture type or output mode changes."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from core.texture_stamp import TEXTURES

            changed = args.input
            inputs  = args.inputs

            type_input  = inputs.itemById('textureType')
            scale_input = inputs.itemById('textureScale')
            depth_input = inputs.itemById('textureDepth')
            hint_box    = inputs.itemById('patternHint')

            if not (type_input and scale_input and depth_input):
                return

            tex_idx = type_input.selectedItem.index
            tex_key = list(TEXTURES.keys())[tex_idx]
            info    = TEXTURES[tex_key]

            if changed.id == 'textureType':
                scale_input.value = info['default_scale_mm'] / 10.0
                depth_input.value = info['default_depth_mm'] / 10.0
                if hint_box:
                    tool_hint, min_tool_mm = CNC_TOOL_HINTS.get(tex_key, ('small end mill', 3.0))
                    hint_box.text = (
                        f'<b>{info["name"]}</b><br>'
                        f'Default scale: {info["default_scale_mm"]}mm | '
                        f'Default depth: {info["default_depth_mm"]}mm<br>'
                        f'CNC: {tool_hint}'
                    )
        except Exception:
            pass  # non-critical UI update


class TextureExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from core import texture_stamp
            from core.texture_stamp import TEXTURES

            app = adsk.core.Application.get()
            ui  = app.userInterface

            design = adsk.fusion.Design.cast(app.activeProduct)
            if not design:
                ui.messageBox(
                    'TextureForge requires an active Design.\n'
                    'Please switch to the Design workspace.',
                    'TextureForge')
                return

            cmd    = args.command
            inputs = cmd.commandInputs

            sel_input   = inputs.itemById('textureFace')
            type_input  = inputs.itemById('textureType')
            scale_input = inputs.itemById('textureScale')
            depth_input = inputs.itemById('textureDepth')
            cut_input   = inputs.itemById('textureCut')

            if not sel_input or sel_input.selectionCount == 0:
                ui.messageBox('Please select a face.', 'TextureForge')
                return

            face        = sel_input.selection(0).entity
            tex_idx     = type_input.selectedItem.index if type_input else 0
            texture_key = list(TEXTURES.keys())[tex_idx]
            scale_mm    = (scale_input.value * 10.0) if scale_input else 2.5
            depth_mm    = (depth_input.value * 10.0) if depth_input else 0.3
            is_cut      = cut_input.value if cut_input else False

            # ── Validate ──────────────────────────────────────────────────
            min_print = MIN_SCALE_PRINT_MM.get(texture_key, 1.0)
            if scale_mm < min_print:
                ui.messageBox(
                    f'Pattern Scale {scale_mm:.2f}mm is below the minimum '
                    f'({min_print}mm) for {TEXTURES[texture_key]["name"]}.\n'
                    'Features may be too fine to emboss reliably.',
                    'TextureForge — Scale Warning')
                return

            if depth_mm < 0.05:
                ui.messageBox(
                    f'Emboss Depth {depth_mm:.3f}mm is extremely shallow.\n'
                    'Minimum recommended: 0.1mm for printing, 0.3mm for CNC.',
                    'TextureForge — Depth Warning')
                return

            # ── Apply ──────────────────────────────────────────────────────
            feature, n_profiles, sketch = texture_stamp.apply_texture_to_face(
                face, texture_key, scale_mm, depth_mm, is_cut)

            texture_name = TEXTURES[texture_key]['name']
            direction    = 'deboss (cut in)' if is_cut else 'boss (raised)'
            tool_hint, _ = CNC_TOOL_HINTS.get(texture_key, ('small end mill', 3.0))

            ui.messageBox(
                f'✓ TextureForge — texture applied!\n\n'
                f'  Texture:  {texture_name}\n'
                f'  Scale:    {scale_mm:.2f} mm per repeat\n'
                f'  Depth:    {depth_mm:.3f} mm ({direction})\n'
                f'  Elements: {n_profiles} profiles\n\n'
                f'CNC tip: {tool_hint}\n'
                f'3D print tip: depth should be ≥ 2× your layer height.\n\n'
                f'The sketch "{sketch.name}" is the pattern source.',
                'TextureForge')

        except RuntimeError as e:
            adsk.core.Application.get().userInterface.messageBox(
                str(e), 'TextureForge — Error')
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                f'TextureForge failed:\n{traceback.format_exc()}',
                'TextureForge — Error')


def on_texture_stamp_created(args):
    """Build the TextureForge Stamp Texture dialog."""
    from core.texture_stamp import TEXTURES

    cmd    = args.command
    inputs = cmd.commandInputs

    inputs.addTextBoxCommandInput(
        'intro', '',
        '<b>TextureForge — Surface Texture Stamp</b><br>'
        'Select a face, choose a texture pattern, and click OK.<br>'
        'The pattern is modeled as real geometry — works for 3D printing <i>and</i> CNC.',
        4, True
    )

    # Face selection
    sel = inputs.addSelectionInput(
        'textureFace', 'Target Face', 'Select a face to texture')
    sel.addSelectionFilter('Faces')
    sel.setSelectionLimits(1, 1)

    # Texture type dropdown
    first_key = list(TEXTURES.keys())[0]
    drop = inputs.addDropDownCommandInput(
        'textureType', 'Texture Pattern',
        adsk.core.DropDownStyles.TextListDropDownStyle
    )
    for i, (key, info) in enumerate(TEXTURES.items()):
        drop.listItems.add(info['name'], i == 0)

    # Scale and depth (defaults for first texture, print mode)
    scale_cm = TEXTURES[first_key]['default_scale_mm'] / 10.0
    depth_cm = TEXTURES[first_key]['default_depth_mm'] / 10.0
    inputs.addValueInput('textureScale', 'Pattern Scale', 'mm',
                         adsk.core.ValueInput.createByReal(scale_cm))
    inputs.addValueInput('textureDepth', 'Emboss Depth',  'mm',
                         adsk.core.ValueInput.createByReal(depth_cm))

    # Boss / Cut toggle
    inputs.addBoolValueInput('textureCut', 'Deboss (cut into surface)', True, '', False)

    # Dynamic hint box (updated by inputChanged handler)
    first_info = TEXTURES[first_key]
    first_tool, _ = CNC_TOOL_HINTS.get(first_key, ('small end mill', 3.0))
    inputs.addTextBoxCommandInput(
        'patternHint', '',
        f'<b>{first_info["name"]}</b><br>'
        f'Default scale: {first_info["default_scale_mm"]}mm | '
        f'Default depth: {first_info["default_depth_mm"]}mm<br>'
        f'CNC: {first_tool}',
        3, True
    )

    # Register handlers
    exec_h = TextureExecuteHandler()
    cmd.execute.add(exec_h)
    _handlers.append(exec_h)

    ic_h = TextureInputChangedHandler()
    cmd.inputChanged.add(ic_h)
    _handlers.append(ic_h)


# ─── Image Texture: "Create Texture From Image" ───────────────────────────────

# Module-level storage so the file dialog result survives into execute
_pending_image_path = None


class ImageTextureInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Show/hide threshold control depending on whether the file is raster."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            inputs    = args.inputs
            path_inp  = inputs.itemById('imgFilePath')
            thresh_g  = inputs.itemById('thresholdGroup')
            hint_box  = inputs.itemById('imgHint')
            width_inp = inputs.itemById('patternWidth')

            if not path_inp:
                return

            path = path_inp.value.strip()
            ext  = path.rsplit('.', 1)[-1].lower() if '.' in path else ''
            is_raster = ext in ('png', 'bmp', 'dib')
            is_svg    = ext == 'svg'

            if thresh_g:
                thresh_g.isVisible = is_raster

            if hint_box:
                if is_svg:
                    hint_box.formattedText = (
                        '<b>SVG mode</b> — Vector paths are traced and embossed as clean geometry.<br>'
                        'Best results: simple filled shapes (no raster-embedded SVGs).<br>'
                        'Open strokes: convert to "Stroke to Path" in Inkscape first.'
                    )
                elif is_raster:
                    hint_box.formattedText = (
                        '<b>Raster mode</b> — Dark pixels become small raised/cut squares '
                        '(pixel-stamp effect).<br>'
                        'Adjust <b>Threshold</b> — lower = only very dark pixels stamp, '
                        'higher = more pixels included.<br>'
                        'Max grid: 64×64 cells (image is auto-downsampled).'
                    )
                elif path:
                    hint_box.formattedText = (
                        '<b>⚠ Unsupported format.</b> '
                        'Please choose a .svg, .png, or .bmp file.'
                    )

        except Exception:
            pass


class ImageTextureExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        import os
        try:
            from core.image_to_texture import apply_image_texture_to_face

            app = adsk.core.Application.get()
            ui  = app.userInterface

            design = adsk.fusion.Design.cast(app.activeProduct)
            if not design:
                ui.messageBox('TextureForge requires an active Design.', 'TextureForge')
                return

            cmd    = args.command
            inputs = cmd.commandInputs

            path_inp    = inputs.itemById('imgFilePath')
            sel_inp     = inputs.itemById('imgFace')
            depth_inp   = inputs.itemById('imgDepth')
            cut_inp     = inputs.itemById('imgCut')
            width_inp   = inputs.itemById('patternWidth')
            use_w_inp   = inputs.itemById('usePatternWidth')
            thresh_inp  = inputs.itemById('threshold')

            filepath = (path_inp.value.strip() if path_inp else '').strip('"\'')

            if not filepath:
                ui.messageBox('No file selected.\n\nEnter or paste the full path to an SVG, PNG, or BMP file.',
                              'TextureForge')
                return

            if not os.path.isfile(filepath):
                ui.messageBox(f'File not found:\n{filepath}', 'TextureForge')
                return

            ext = os.path.splitext(filepath)[1].lower()
            if ext not in ('.svg', '.png', '.bmp', '.dib'):
                ui.messageBox(
                    f'Unsupported format "{ext}".\nTextureForge accepts .svg, .png, or .bmp files.',
                    'TextureForge')
                return

            if not sel_inp or sel_inp.selectionCount == 0:
                ui.messageBox('Please select a face.', 'TextureForge')
                return

            face       = sel_inp.selection(0).entity
            depth_mm   = (depth_inp.value * 10.0) if depth_inp else 0.5
            is_cut     = cut_inp.value if cut_inp else False
            threshold  = int(thresh_inp.value) if thresh_inp else 128
            use_width  = use_w_inp.value if use_w_inp else False
            width_mm   = (width_inp.value * 10.0) if (use_width and width_inp) else None

            if depth_mm < 0.05:
                ui.messageBox('Emboss depth must be at least 0.05 mm.', 'TextureForge')
                return

            feature, n_profiles, sketch = apply_image_texture_to_face(
                face, filepath, depth_mm, is_cut,
                pattern_width_mm=width_mm,
                threshold=threshold,
            )

            fname     = os.path.basename(filepath)
            direction = 'deboss (cut in)' if is_cut else 'boss (raised)'
            ui.messageBox(
                f'✓ TextureForge — image texture applied!\n\n'
                f'  File:     {fname}\n'
                f'  Profiles: {n_profiles}\n'
                f'  Depth:    {depth_mm:.2f} mm ({direction})\n\n'
                f'The sketch "{sketch.name}" is the pattern source.\n'
                f'Suppress the Emboss in the timeline to remove the texture.',
                'TextureForge'
            )

        except RuntimeError as e:
            adsk.core.Application.get().userInterface.messageBox(str(e), 'TextureForge — Error')
        except Exception:
            adsk.core.Application.get().userInterface.messageBox(
                f'TextureForge failed:\n{traceback.format_exc()}', 'TextureForge — Error')


def on_image_texture_created(args):
    """
    Build the 'Create Texture From Image' command dialog.

    Immediately shows a system file-picker so the user can browse to their
    SVG / PNG / BMP.  If they cancel, the path field is left empty and they
    can still type/paste a path manually.
    """
    import os

    app = adsk.core.Application.get()
    ui  = app.userInterface
    cmd    = args.command
    inputs = cmd.commandInputs

    # ── Try to open a file dialog right away ──────────────────────────────────
    picked_path = ''
    try:
        dlg = ui.createFileDialog()
        dlg.title              = 'TextureForge — Select Image File'
        dlg.filter             = ('SVG Vector (*.svg)|*.svg|'
                                  'PNG Image (*.png)|*.png|'
                                  'BMP Image (*.bmp)|*.bmp|'
                                  'All Supported (*.svg;*.png;*.bmp)|*.svg;*.png;*.bmp')
        dlg.filterIndex        = 3
        dlg.isMultiSelectEnabled = False
        if dlg.showOpen() == adsk.core.DialogResults.DialogOK:
            picked_path = dlg.filename
    except Exception:
        pass  # File dialog unavailable — user will type path manually

    # ── Build dialog inputs ────────────────────────────────────────────────────
    inputs.addTextBoxCommandInput(
        'intro', '',
        '<b>TextureForge — Create Texture From Image</b><br>'
        'Paste or type the full file path below (or the file browser already filled it in).<br>'
        'Supported: <b>.svg</b> (vector paths), <b>.png</b> / <b>.bmp</b> (pixel stamp).',
        4, True
    )

    path_inp = inputs.addStringValueInput('imgFilePath', 'Image File', picked_path)
    path_inp.tooltip = ('Full path to your .svg, .png, or .bmp file.\n'
                        'Tip: drag the file onto a Windows Explorer address bar to copy its path.')

    # Face selector
    sel = inputs.addSelectionInput('imgFace', 'Target Face', 'Select a face to texture')
    sel.addSelectionFilter('Faces')
    sel.setSelectionLimits(1, 1)

    # Optional: explicit pattern width
    use_w = inputs.addBoolValueInput('usePatternWidth', 'Set Pattern Width', True, '', False)
    use_w.tooltip = 'Override the default "fit to face" scaling with a specific width.'
    width_inp = inputs.addValueInput(
        'patternWidth', 'Pattern Width', 'mm',
        adsk.core.ValueInput.createByReal(5.0)  # 5 cm default
    )
    width_inp.isVisible = False
    width_inp.tooltip   = 'Desired width of the imported image on the face (mm).'

    # Depth
    inputs.addValueInput('imgDepth', 'Emboss Depth', 'mm',
                         adsk.core.ValueInput.createByReal(0.05))  # 0.5 mm

    # Deboss toggle
    inputs.addBoolValueInput('imgCut', 'Deboss (cut into surface)', True, '', False)

    # Threshold (raster only — hidden for SVG)
    thresh_g = inputs.addGroupCommandInput('thresholdGroup', 'Raster Options')
    thresh_g.isExpanded = True
    thresh_g.isVisible  = False
    thresh_g.children.addValueInput(
        'threshold', 'Threshold (0=lightest, 255=all dark)', '',
        adsk.core.ValueInput.createByReal(128)
    )

    # Dynamic hint box
    inputs.addTextBoxCommandInput(
        'imgHint', '',
        '<b>SVG mode</b> — Vector paths are traced and embossed as clean geometry.<br>'
        'Best results: simple filled shapes. Convert text to paths in Inkscape first.'
        if picked_path.lower().endswith('.svg') else
        '<b>Enter a file path above</b> to see format-specific tips.',
        4, True
    )

    # Wire up handlers
    exec_h = ImageTextureExecuteHandler()
    cmd.execute.add(exec_h)
    _handlers.append(exec_h)

    ic_h = ImageTextureInputChangedHandler()
    cmd.inputChanged.add(ic_h)
    _handlers.append(ic_h)

    # Show/hide width input when checkbox changes
    class _WidthToggleHandler(adsk.core.InputChangedEventHandler):
        def __init__(self): super().__init__()
        def notify(self, args):
            if args.input.id == 'usePatternWidth':
                inp = args.inputs.itemById('patternWidth')
                if inp: inp.isVisible = args.input.value
            # Also update threshold group visibility
            pi  = args.inputs.itemById('imgFilePath')
            tg  = args.inputs.itemById('thresholdGroup')
            if pi and tg:
                ext = pi.value.strip().rsplit('.', 1)[-1].lower() if '.' in pi.value else ''
                tg.isVisible = ext in ('png', 'bmp', 'dib')

    wt_h = _WidthToggleHandler()
    cmd.inputChanged.add(wt_h)
    _handlers.append(wt_h)



"""
UI Event Handlers for FusionCam.
Each handler manages a command dialog's lifecycle:
create -> input changed -> validate -> execute.
"""

import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import json
import os

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ADDIN_DIR, 'config')
DATA_DIR = os.path.join(ADDIN_DIR, 'data')

_handlers = []


def _load_settings():
    path = os.path.join(DATA_DIR, 'user_settings.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_settings(settings):
    path = os.path.join(DATA_DIR, 'user_settings.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)


def _load_materials():
    path = os.path.join(CONFIG_DIR, 'materials.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


# ========== SETTINGS COMMAND ==========

class SettingsExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ..core import ai_client

            cmd = args.command
            inputs = cmd.commandInputs

            token_input = inputs.itemById('aiToken')
            token = token_input.value.strip() if token_input else ''

            if token:
                # Test the token first
                success, message = ai_client.test_token(token)

                app = adsk.core.Application.get()
                ui = app.userInterface

                if success:
                    ai_client.save_token(token)
                    settings = _load_settings()
                    settings['ai_token_validated'] = True
                    settings['first_run_complete'] = True
                    _save_settings(settings)
                    ui.messageBox(
                        'AI token validated and saved successfully!\n\n'
                        'You can now use AI-powered features:\n'
                        '- Import Tool from URL\n'
                        '- Add Material with AI\n'
                        '- Smart feeds/speeds suggestions',
                        'FusionCam Settings'
                    )
                else:
                    ui.messageBox(
                        f'Token validation failed:\n{message}\n\n'
                        'Get a token from: https://github.com/settings/tokens\n'
                        'Ensure it has "models:read" permission.',
                        'FusionCam Settings'
                    )
        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(f'Settings error:\n{traceback.format_exc()}')


def on_settings_created(args):
    """Build the Settings dialog UI."""
    cmd = args.command
    inputs = cmd.commandInputs

    settings = _load_settings()

    # AI Token group
    ai_group = inputs.addGroupCommandInput('aiGroup', 'AI Configuration (GitHub Models API)')

    token_input = ai_group.children.addStringValueInput(
        'aiToken', 'GitHub Token',
        settings.get('ai_token', '')
    )

    status_text = 'Validated' if settings.get('ai_token_validated') else 'Not configured'
    ai_group.children.addTextBoxCommandInput(
        'aiStatus', 'Status', f'<b>{status_text}</b>', 1, True
    )

    ai_group.children.addTextBoxCommandInput(
        'aiHelp', 'Help',
        'Get a free token at github.com/settings/tokens<br>'
        'Required permission: <b>models:read</b><br>'
        'Uses GPT-4o-mini via GitHub Models (free tier)',
        3, True
    )

    # Machine group
    machine_group = inputs.addGroupCommandInput('machineGroup', 'Machine Configuration')
    machine_group.children.addTextBoxCommandInput(
        'machineName', 'Machine', '<b>Onefinity Machinist</b>', 1, True
    )
    machine_group.children.addTextBoxCommandInput(
        'machineSpindle', 'Spindle', 'Makita RT0701C (dial 1-6: ~9.6k-30k RPM)', 1, True
    )
    machine_group.children.addTextBoxCommandInput(
        'machineWork', 'Work Area', '406 x 406 x 114 mm (16" x 16" x 4.5")', 1, True
    )

    # Defaults group
    defaults_group = inputs.addGroupCommandInput('defaultsGroup', 'Default Preferences')

    materials = _load_materials()
    material_dropdown = defaults_group.children.addDropDownCommandInput(
        'defaultMaterial', 'Default Material',
        adsk.core.DropDownStyles.TextListDropDownStyle
    )
    current_default = settings.get('default_material', 'aluminum_6061_t6')
    for key, mat in materials.get('materials', {}).items():
        is_selected = (key == current_default)
        material_dropdown.listItems.add(mat['name'], is_selected)

    quality_dropdown = defaults_group.children.addDropDownCommandInput(
        'defaultQuality', 'Default Quality',
        adsk.core.DropDownStyles.TextListDropDownStyle
    )
    current_quality = settings.get('default_quality', 'standard')
    for q in ['draft', 'standard', 'fine']:
        quality_dropdown.listItems.add(q.title(), q == current_quality)

    # Register execute handler
    handler = SettingsExecuteHandler()
    cmd.execute.add(handler)
    _handlers.append(handler)


# ========== IMPORT TOOL COMMAND ==========

class ImportToolExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ..core import tool_parser
            from ..core import tool_library
            from ..core import ai_client

            app = adsk.core.Application.get()
            ui = app.userInterface

            cmd = args.command
            inputs = cmd.commandInputs

            url_input = inputs.itemById('toolUrl')
            text_input = inputs.itemById('toolText')

            url = url_input.value.strip() if url_input else ''
            text = text_input.value.strip() if text_input else ''

            if not ai_client.has_valid_token():
                ui.messageBox(
                    'AI token not configured. Go to FusionCam Settings first.',
                    'FusionCam'
                )
                return

            tool_data = None
            raw_text = ''

            if url:
                ui.messageBox('Fetching product page... This may take a few seconds.', 'FusionCam')
                try:
                    tool_data, raw_text = tool_parser.parse_tool_from_url(url)
                except Exception as e:
                    ui.messageBox(f'URL fetch failed: {str(e)}\n\nTry pasting the product text instead.', 'FusionCam')
                    return
            elif text:
                tool_data = tool_parser.parse_tool_from_text(text)
            else:
                ui.messageBox('Please provide either an Amazon URL or paste the product description.', 'FusionCam')
                return

            if not tool_data:
                ui.messageBox('Could not extract tool specifications. Try manual entry.', 'FusionCam')
                return

            # Show extracted specs for review
            display = tool_library.format_tool_for_display(tool_data)
            result = ui.messageBox(
                f'Extracted tool specifications:\n\n{display}\n\n'
                'Add this tool to your library?',
                'FusionCam - Review Tool',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType,
                adsk.core.MessageBoxIconTypes.QuestionIconType
            )

            if result == adsk.core.DialogResults.DialogYes:
                tool_id = tool_parser.add_tool(tool_data)
                ui.messageBox(
                    f'Tool added to library as {tool_id}!\n\n'
                    f'{tool_data.get("display_name", "Tool")}',
                    'FusionCam'
                )

        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(f'Import error:\n{traceback.format_exc()}')


def on_import_tool_created(args):
    """Build the Import Tool dialog UI."""
    cmd = args.command
    inputs = cmd.commandInputs

    inputs.addTextBoxCommandInput(
        'importHelp', '',
        '<b>Import Tool from Amazon</b><br>'
        'Paste an Amazon product URL or copy the product description.<br>'
        'AI will extract the tool specifications automatically.',
        3, True
    )

    inputs.addStringValueInput('toolUrl', 'Amazon URL', '')

    inputs.addTextBoxCommandInput(
        'orLabel', '', '<i>-- OR paste product text below --</i>', 1, True
    )

    text_input = inputs.addTextBoxCommandInput(
        'toolText', 'Product Text',
        '',
        8, False
    )

    handler = ImportToolExecuteHandler()
    cmd.execute.add(handler)
    _handlers.append(handler)


# ========== MANAGE TOOLS COMMAND ==========

def on_manage_tools_created(args):
    """Show the current tool library."""
    from ..core import tool_library

    cmd = args.command
    inputs = cmd.commandInputs

    tools = tool_library.get_tool_library_summary()

    if not tools:
        inputs.addTextBoxCommandInput(
            'noTools', '',
            '<b>No tools in library</b><br><br>'
            'Use "Import Tool" to add endmills from Amazon URLs.',
            4, True
        )
        return

    inputs.addTextBoxCommandInput(
        'toolCount', '',
        f'<b>Tool Library ({len(tools)} tools)</b>',
        1, True
    )

    for tool in tools:
        group = inputs.addGroupCommandInput(tool['id'], tool['name'])
        group.children.addTextBoxCommandInput(
            f"{tool['id']}_info", 'Info',
            f"Type: {tool['type']}<br>"
            f"Diameter: {tool['diameter']}<br>"
            f"Flutes: {tool['flutes']}<br>"
            f"Material: {tool['material']}<br>"
            f"Coating: {tool['coating']}<br>"
            f"Brand: {tool['brand']}",
            6, True
        )
        group.isExpanded = False


# ========== ADD MATERIAL COMMAND ==========

class AddMaterialExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ..core import ai_client

            app = adsk.core.Application.get()
            ui = app.userInterface

            cmd = args.command
            inputs = cmd.commandInputs

            name_input = inputs.itemById('materialName')
            material_name = name_input.value.strip() if name_input else ''

            if not material_name:
                ui.messageBox('Please enter a material name.', 'FusionCam')
                return

            if not ai_client.has_valid_token():
                ui.messageBox('AI token not configured. Go to Settings first.', 'FusionCam')
                return

            # Generate material profile via AI
            profile = ai_client.generate_material_profile(material_name)

            if not profile:
                ui.messageBox('AI could not generate a material profile. Try a more specific name.', 'FusionCam')
                return

            # Show for review
            summary = (
                f"Material: {profile.get('name', material_name)}\n"
                f"Category: {profile.get('category', '?')}\n"
                f"Hardness: {profile.get('hardness', '?')}\n"
                f"SFM Range: {profile.get('sfm_range', {}).get('min', '?')}-{profile.get('sfm_range', {}).get('max', '?')}\n"
                f"Preferred Flutes: {profile.get('preferred_flute_count', '?')}\n"
                f"Coolant: {profile.get('coolant', '?')}\n"
                f"\nNotes: {profile.get('notes', 'None')}"
            )

            result = ui.messageBox(
                f'AI-generated material profile:\n\n{summary}\n\nAdd to material database?',
                'FusionCam - Review Material',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType
            )

            if result == adsk.core.DialogResults.DialogYes:
                # Save to materials.json
                materials_path = os.path.join(CONFIG_DIR, 'materials.json')
                with open(materials_path, 'r', encoding='utf-8') as f:
                    materials = json.load(f)

                key = material_name.lower().replace(' ', '_').replace('/', '_')
                materials['materials'][key] = profile

                with open(materials_path, 'w', encoding='utf-8') as f:
                    json.dump(materials, f, indent=2)

                ui.messageBox(f'Material "{profile.get("name", material_name)}" added!', 'FusionCam')

        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(f'Add material error:\n{traceback.format_exc()}')


def on_add_material_created(args):
    """Build the Add Material dialog."""
    cmd = args.command
    inputs = cmd.commandInputs

    inputs.addTextBoxCommandInput(
        'matHelp', '',
        '<b>Add Material with AI</b><br>'
        'Enter a material name and AI will generate a complete cutting profile<br>'
        'with recommended feeds, speeds, and tips for your Onefinity.',
        3, True
    )

    inputs.addStringValueInput('materialName', 'Material Name', '')

    inputs.addTextBoxCommandInput(
        'matExamples', 'Examples',
        'Polycarbonate / Lexan<br>'
        'HDPE<br>'
        'Acetal / Delrin<br>'
        'MDF<br>'
        'Brass<br>'
        'Carbon Fiber Sheet',
        6, True
    )

    handler = AddMaterialExecuteHandler()
    cmd.execute.add(handler)
    _handlers.append(handler)


# ========== GENERATE CAM COMMAND ==========

class GenerateCamExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ..core import geometry_analyzer
            from ..core import cam_generator
            from ..core import tool_parser
            from ..core import feeds_speeds

            app = adsk.core.Application.get()
            ui = app.userInterface
            design = adsk.fusion.Design.cast(app.activeProduct)

            if not design:
                ui.messageBox('No active design. Open a part first.', 'FusionCam')
                return

            cmd = args.command
            inputs = cmd.commandInputs

            # Get user selections
            material_dropdown = inputs.itemById('material')
            quality_dropdown = inputs.itemById('quality')
            stock_offset_input = inputs.itemById('stockOffset')

            material_idx = material_dropdown.selectedItem.index if material_dropdown else 0
            quality_idx = quality_dropdown.selectedItem.index if quality_dropdown else 1
            stock_offset = stock_offset_input.value * 10.0 if stock_offset_input else 2.0  # cm to mm

            # Map indices to keys
            materials = _load_materials()
            material_keys = list(materials.get('materials', {}).keys())
            material_key = material_keys[material_idx] if material_idx < len(material_keys) else 'aluminum_6061_t6'
            material_name = materials['materials'][material_key]['name']

            quality_keys = ['draft', 'standard', 'fine']
            quality = quality_keys[quality_idx] if quality_idx < len(quality_keys) else 'standard'

            # Analyze geometry
            root = design.rootComponent
            bodies = root.bRepBodies
            if bodies.count == 0:
                ui.messageBox('No solid bodies found.', 'FusionCam')
                return

            body = bodies.item(0)  # Analyze first body
            features = geometry_analyzer.analyze_body(body)

            if not features:
                ui.messageBox('No machinable features detected.', 'FusionCam')
                return

            # Show analysis summary
            summary = geometry_analyzer.get_analysis_summary(features)

            # Get available tools
            available_tools = tool_parser.get_all_tools()
            if not available_tools:
                ui.messageBox(
                    'No tools in library!\n\n'
                    'Use "Import Tool" to add your endmills first.',
                    'FusionCam'
                )
                return

            # Auto-assign tools
            tool_assignments = cam_generator.auto_assign_tools(features, available_tools)

            # Build operation plan preview
            plan = cam_generator.build_operation_plan(features, tool_assignments, material_key, quality)

            # Format plan for display
            plan_text = f"Material: {material_name}\nQuality: {quality.title()}\n"
            plan_text += f"Tool Changes: {plan['tool_changes']}\n"
            plan_text += f"Total Operations: {plan['total_operations']}\n\n"

            for op in plan.get('operations', []):
                status_icon = '  ' if op.get('status') == 'ready' else '  '
                plan_text += f"{status_icon} {op.get('operation', '?')}\n"
                plan_text += f"      Tool: {op.get('tool', '?')} | RPM: {op.get('rpm', '?')} | Feed: {op.get('feed', '?')}\n"

            if plan.get('warnings'):
                plan_text += "\nWarnings:\n"
                for w in plan['warnings']:
                    plan_text += f"  {w.get('feature', '?')}: {w.get('warning', '?')}\n"

            # Confirm with user
            result = ui.messageBox(
                f'FusionCam Operation Plan:\n\n{plan_text}\n\nGenerate these CAM operations?',
                'FusionCam - Review Plan',
                adsk.core.MessageBoxButtonTypes.YesNoButtonType
            )

            if result == adsk.core.DialogResults.DialogYes:
                stock_config = {
                    'mode': 'relative_offset',
                    'offset_mm': stock_offset,
                    'material_name': material_name
                }

                result = cam_generator.generate_cam(
                    features, tool_assignments, material_key, stock_config, quality
                )

                ui.messageBox(
                    f'CAM generation complete!\n\n'
                    f'Setup: {result["setup_name"]}\n'
                    f'Operations created: {result["operations_created"]}/{result["operations_planned"]}\n\n'
                    'Review the operations in the CAM browser,\n'
                    'then generate toolpaths and post-process.',
                    'FusionCam'
                )

        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(f'Generate CAM error:\n{traceback.format_exc()}')


def on_generate_cam_created(args):
    """Build the Generate CAM dialog."""
    cmd = args.command
    inputs = cmd.commandInputs

    settings = _load_settings()
    materials = _load_materials()

    inputs.addTextBoxCommandInput(
        'genHelp', '',
        '<b>1-Click CAM Generation</b><br>'
        'Select material and quality, then FusionCam will analyze<br>'
        'your part geometry and generate CAM operations automatically.',
        3, True
    )

    # Material dropdown
    material_dropdown = inputs.addDropDownCommandInput(
        'material', 'Material',
        adsk.core.DropDownStyles.TextListDropDownStyle
    )
    default_material = settings.get('default_material', 'aluminum_6061_t6')
    for key, mat in materials.get('materials', {}).items():
        material_dropdown.listItems.add(mat['name'], key == default_material)

    # Quality dropdown
    quality_dropdown = inputs.addDropDownCommandInput(
        'quality', 'Quality',
        adsk.core.DropDownStyles.TextListDropDownStyle
    )
    default_quality = settings.get('default_quality', 'standard')
    for q_key, q_name in [('draft', 'Draft (Fast)'), ('standard', 'Standard'), ('fine', 'Fine (Slow, Smooth)')]:
        quality_dropdown.listItems.add(q_name, q_key == default_quality)

    # Stock offset
    inputs.addValueInput(
        'stockOffset', 'Stock Offset',
        'mm',
        adsk.core.ValueInput.createByReal(0.2)  # 2mm in cm
    )

    handler = GenerateCamExecuteHandler()
    cmd.execute.add(handler)
    _handlers.append(handler)


# ========== 2-SIDED CARVE COMMAND ==========

class TwoSidedExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ..core import geometry_analyzer
            from ..core import two_sided
            from ..core import cam_generator
            from ..core import tool_parser

            app = adsk.core.Application.get()
            ui = app.userInterface
            design = adsk.fusion.Design.cast(app.activeProduct)

            if not design:
                ui.messageBox('No active design found.', 'FusionCam')
                return

            cmd = args.command
            inputs = cmd.commandInputs

            method_dropdown = inputs.itemById('alignMethod')
            method_idx = method_dropdown.selectedItem.index if method_dropdown else 0
            alignment_method = 'dowel_pins' if method_idx == 0 else 'corner_registration'

            stock_x_input = inputs.itemById('stockX')
            stock_y_input = inputs.itemById('stockY')
            stock_x = stock_x_input.value * 10.0 if stock_x_input else 200.0  # cm to mm
            stock_y = stock_y_input.value * 10.0 if stock_y_input else 150.0

            # Analyze geometry
            root = design.rootComponent
            body = root.bRepBodies.item(0)
            features = geometry_analyzer.analyze_body(body)

            # Create 2-sided workflow
            workflow = two_sided.TwoSidedWorkflow(body, features, alignment_method)

            if alignment_method == 'dowel_pins':
                workflow.calculate_dowel_positions(stock_x, stock_y)
                dowel_features = workflow.get_dowel_drill_features()
                # Prepend dowel holes to feature list
                features = dowel_features + features

            summary = workflow.get_summary()
            instructions = workflow.get_flip_instructions()

            # Show summary and instructions
            summary_text = (
                f"2-Sided Analysis:\n"
                f"  Part thickness: {summary['part_thickness_mm']:.1f}mm\n"
                f"  Side A features: {summary['side_a_feature_count']}\n"
                f"  Side B features: {summary['side_b_feature_count']}\n"
                f"  Shared features: {summary['shared_feature_count']}\n"
                f"  Alignment: {alignment_method.replace('_', ' ').title()}\n"
            )

            if summary.get('dowel_positions'):
                summary_text += f"\n  Dowel Pin 1: ({summary['dowel_positions'][0][0]:.1f}, {summary['dowel_positions'][0][1]:.1f})mm\n"
                summary_text += f"  Dowel Pin 2: ({summary['dowel_positions'][1][0]:.1f}, {summary['dowel_positions'][1][1]:.1f})mm\n"

            instructions_text = '\n'.join(instructions)

            ui.messageBox(
                f'{summary_text}\n\n'
                f'FLIP INSTRUCTIONS (save these):\n\n{instructions_text}',
                'FusionCam - 2-Sided Carving'
            )

        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(f'2-Sided error:\n{traceback.format_exc()}')


def on_two_sided_created(args):
    """Build the 2-Sided Carving dialog."""
    cmd = args.command
    inputs = cmd.commandInputs

    inputs.addTextBoxCommandInput(
        'twoHelp', '',
        '<b>2-Sided Carving Setup</b><br>'
        'Set up machining for both sides of your part with<br>'
        'precise alignment using dowel pins or corner registration.',
        3, True
    )

    # Alignment method
    method_dropdown = inputs.addDropDownCommandInput(
        'alignMethod', 'Alignment Method',
        adsk.core.DropDownStyles.TextListDropDownStyle
    )
    method_dropdown.listItems.add('Dowel Pin Alignment (Recommended)', True)
    method_dropdown.listItems.add('Corner Registration', False)

    # Stock dimensions
    inputs.addValueInput(
        'stockX', 'Stock Width (X)',
        'mm',
        adsk.core.ValueInput.createByReal(20.0)  # 200mm in cm
    )
    inputs.addValueInput(
        'stockY', 'Stock Height (Y)',
        'mm',
        adsk.core.ValueInput.createByReal(15.0)  # 150mm in cm
    )

    # Flip axis
    flip_dropdown = inputs.addDropDownCommandInput(
        'flipAxis', 'Flip Axis',
        adsk.core.DropDownStyles.TextListDropDownStyle
    )
    flip_dropdown.listItems.add('X Axis (left-to-right flip)', True)
    flip_dropdown.listItems.add('Y Axis (front-to-back flip)', False)

    handler = TwoSidedExecuteHandler()
    cmd.execute.add(handler)
    _handlers.append(handler)


# ═══════════════════════════════════════════════════════════════════
# TEXTURE STAMP COMMAND
# ═══════════════════════════════════════════════════════════════════

class TextureStampInputChangedHandler(adsk.core.InputChangedEventHandler):
    """Update scale/depth defaults when the user picks a different texture type."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ..core.texture_stamp import TEXTURES

            changed = args.input
            if changed.id != 'textureType':
                return

            inputs = args.inputs
            selected_key = list(TEXTURES.keys())[changed.selectedItem.index]
            info = TEXTURES[selected_key]

            scale_input = inputs.itemById('textureScale')
            depth_input = inputs.itemById('textureDepth')
            if scale_input:
                scale_input.value = info['default_scale_mm'] / 10.0   # mm → cm
            if depth_input:
                depth_input.value = info['default_depth_mm'] / 10.0
        except Exception:
            pass  # non-critical UI update


class TextureStampExecuteHandler(adsk.core.CommandEventHandler):
    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from ..core import texture_stamp
            from ..core.texture_stamp import TEXTURES

            app = adsk.core.Application.get()
            ui  = app.userInterface

            design = adsk.fusion.Design.cast(app.activeProduct)
            if not design:
                ui.messageBox(
                    'Texture Stamp requires an active Design.\n'
                    'Please switch to the Design workspace and open a model.',
                    'FusionCam — Texture Stamp')
                return

            cmd    = args.command
            inputs = cmd.commandInputs

            # ── Read inputs ──────────────────────────────────────────────
            sel_input  = inputs.itemById('textureFace')
            type_input = inputs.itemById('textureType')
            scale_input = inputs.itemById('textureScale')
            depth_input = inputs.itemById('textureDepth')
            cut_input   = inputs.itemById('textureCut')

            if not sel_input or sel_input.selectionCount == 0:
                ui.messageBox('Please select a face to texture.', 'FusionCam — Texture Stamp')
                return

            face        = sel_input.selection(0).entity
            texture_idx = type_input.selectedItem.index if type_input else 0
            texture_key = list(TEXTURES.keys())[texture_idx]
            scale_mm    = (scale_input.value * 10.0) if scale_input else 2.5   # cm → mm
            depth_mm    = (depth_input.value * 10.0) if depth_input else 0.3
            is_cut      = cut_input.value if cut_input else False

            texture_name = TEXTURES[texture_key]['name']

            # ── Validate ─────────────────────────────────────────────────
            if scale_mm < 0.3:
                ui.messageBox(
                    f'Pattern Scale {scale_mm:.2f}mm is very small — '
                    'features may be too fine to print or emboss reliably.\n'
                    'Minimum recommended: 0.5mm.',
                    'FusionCam — Texture Stamp Warning')
                return
            if depth_mm < 0.05:
                ui.messageBox(
                    f'Emboss Depth {depth_mm:.3f}mm is very shallow — '
                    'features may not be visible on a print.\n'
                    'Minimum recommended: 0.1mm.',
                    'FusionCam — Texture Stamp Warning')
                return

            # ── Apply ─────────────────────────────────────────────────────
            feature, n_profiles, sketch = texture_stamp.apply_texture_to_face(
                face, texture_key, scale_mm, depth_mm, is_cut)

            direction = 'deboss (cut)' if is_cut else 'boss (raise)'
            ui.messageBox(
                f'✓ Texture Stamp applied!\n\n'
                f'  Texture:   {texture_name}\n'
                f'  Scale:     {scale_mm:.2f} mm\n'
                f'  Depth:     {depth_mm:.3f} mm ({direction})\n'
                f'  Profiles:  {n_profiles} pattern elements\n\n'
                f'The sketch "{sketch.name}" was created as the pattern source.\n'
                f'You can suppress the Emboss feature in the timeline to remove the texture.',
                'FusionCam — Texture Stamp')

        except RuntimeError as e:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(str(e), 'FusionCam — Texture Stamp Error')
        except Exception:
            app = adsk.core.Application.get()
            app.userInterface.messageBox(
                f'Texture Stamp failed:\n{traceback.format_exc()}',
                'FusionCam — Texture Stamp Error')


def on_texture_stamp_created(args):
    """Build the Texture Stamp dialog."""
    from ..core.texture_stamp import TEXTURES

    cmd    = args.command
    inputs = cmd.commandInputs

    inputs.addTextBoxCommandInput(
        'textureHelp', '',
        '<b>Texture Stamp</b><br>'
        'Select a face, choose a texture pattern, and click OK to emboss it.<br>'
        'The pattern is physically modeled into the geometry — it will appear on your 3D print.',
        4, True
    )

    # Face selection
    sel = inputs.addSelectionInput('textureFace', 'Target Face', 'Select a face to texture')
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

    # Scale — default for first texture
    default_scale_cm = TEXTURES[first_key]['default_scale_mm'] / 10.0
    inputs.addValueInput(
        'textureScale', 'Pattern Scale', 'mm',
        adsk.core.ValueInput.createByReal(default_scale_cm)
    )

    # Depth
    default_depth_cm = TEXTURES[first_key]['default_depth_mm'] / 10.0
    inputs.addValueInput(
        'textureDepth', 'Emboss Depth', 'mm',
        adsk.core.ValueInput.createByReal(default_depth_cm)
    )

    # Boss vs Cut
    inputs.addBoolValueInput('textureCut', 'Deboss (cut into surface)', True, '', False)

    # Tips
    inputs.addTextBoxCommandInput(
        'textureTips', '',
        '<i>Tips: Scale = one pattern repeat size. Depth = how high/deep the texture is.<br>'
        'Recommended depth for FDM printing: 0.15–0.5mm (≥ 2× layer height).<br>'
        'The feature appears in the timeline — suppress it to remove the texture.</i>',
        4, True
    )

    # Register handlers
    execute_handler = TextureStampExecuteHandler()
    cmd.execute.add(execute_handler)
    _handlers.append(execute_handler)

    input_changed_handler = TextureStampInputChangedHandler()
    cmd.inputChanged.add(input_changed_handler)
    _handlers.append(input_changed_handler)

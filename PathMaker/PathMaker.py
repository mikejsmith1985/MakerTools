"""
PathMaker — AI-Powered 1-Click CAM for Fusion 360
Entry point for the Fusion 360 add-in.
"""

import adsk.core
import adsk.fusion
import adsk.cam
import traceback
import os
import json

# Global references to keep objects alive
_app = None
_ui = None
_handlers = []

# Add-in root directory
ADDIN_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(ADDIN_DIR, 'config')
DATA_DIR = os.path.join(ADDIN_DIR, 'data')

# Command IDs (keep internal IDs stable so saved workspaces don't break)
CMD_GENERATE_CAM = 'autoPathGenerate'
CMD_IMPORT_TOOL  = 'autoPathImportTool'
CMD_MANAGE_TOOLS = 'autoPathManageTools'
CMD_ADD_MATERIAL = 'autoPathAddMaterial'
CMD_TWO_SIDED    = 'autoPathTwoSided'
CMD_SETTINGS     = 'autoPathSettings'

# Panel and toolbar IDs
PANEL_ID = 'autoPathPanel'
TAB_ID   = 'autoPathTab'


def _load_json(filepath):
    """Load a JSON file from the config or data directory."""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)


def _ensure_data_dir():
    """Ensure the data directory exists with default files."""
    os.makedirs(DATA_DIR, exist_ok=True)

    settings_path = os.path.join(DATA_DIR, 'user_settings.json')
    if not os.path.exists(settings_path):
        with open(settings_path, 'w', encoding='utf-8') as f:
            json.dump({
                'ai_token': '',
                'ai_token_validated': False,
                'default_material': 'aluminum_6061_t6',
                'default_quality': 'standard',
                'two_sided_method': 'dowel_pins',
                'show_review_dialog': True,
                'first_run_complete': False
            }, f, indent=2)

    tools_path = os.path.join(DATA_DIR, 'tool_library.json')
    if not os.path.exists(tools_path):
        with open(tools_path, 'w', encoding='utf-8') as f:
            json.dump({'tools': [], 'version': 1}, f, indent=2)

    cache_path = os.path.join(DATA_DIR, 'feeds_speeds_cache.json')
    if not os.path.exists(cache_path):
        with open(cache_path, 'w', encoding='utf-8') as f:
            json.dump({'cache': {}, 'version': 1}, f, indent=2)


class GenerateCamCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for the 1-click CAM generate command."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from .ui.handlers import on_generate_cam_created
            on_generate_cam_created(args)
        except Exception:
            _ui.messageBox(f'Generate CAM Error:\n{traceback.format_exc()}')


class ImportToolCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for the Import Tool from URL command."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from .ui.handlers import on_import_tool_created
            on_import_tool_created(args)
        except Exception:
            _ui.messageBox(f'Import Tool Error:\n{traceback.format_exc()}')


class ManageToolsCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for the Manage Tools command."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from .ui.handlers import on_manage_tools_created
            on_manage_tools_created(args)
        except Exception:
            _ui.messageBox(f'Manage Tools Error:\n{traceback.format_exc()}')


class AddMaterialCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for the Add Material command."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from .ui.handlers import on_add_material_created
            on_add_material_created(args)
        except Exception:
            _ui.messageBox(f'Add Material Error:\n{traceback.format_exc()}')


class TwoSidedCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for the 2-Sided Carving command."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from .ui.handlers import on_two_sided_created
            on_two_sided_created(args)
        except Exception:
            _ui.messageBox(f'2-Sided Carve Error:\n{traceback.format_exc()}')


class SettingsCommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    """Handler for the Settings command."""

    def __init__(self):
        super().__init__()

    def notify(self, args):
        try:
            from .ui.handlers import on_settings_created
            on_settings_created(args)
        except Exception:
            _ui.messageBox(f'Settings Error:\n{traceback.format_exc()}')


def _res(name):
    """Return absolute path to a resources/<name> subfolder for icon PNGs."""
    return os.path.join(ADDIN_DIR, 'resources', name)


def _create_button(cmd_def_id, label, tooltip, handler_class, resource_folder=''):
    """Create a command definition and attach a handler."""
    cmd_defs = _ui.commandDefinitions
    existing = cmd_defs.itemById(cmd_def_id)
    if existing:
        existing.deleteMe()

    cmd_def = cmd_defs.addButtonDefinition(
        cmd_def_id,
        label,
        tooltip,
        resource_folder if resource_folder else ''
    )

    handler = handler_class()
    cmd_def.commandCreated.add(handler)
    _handlers.append(handler)

    return cmd_def


def run(context):
    """Called when the add-in is started."""
    global _app, _ui

    try:
        _app = adsk.core.Application.get()
        _ui = _app.userInterface

        _ensure_data_dir()

        # Get or create the AutoPath panel in the Manufacturing workspace
        mfg_workspace = _ui.workspaces.itemById('CAMEnvironment')
        if not mfg_workspace:
            _ui.messageBox('PathMaker requires the Manufacturing workspace.\n'
                           'Please ensure you have access to the CAM features.')
            return

        toolbar_panels = mfg_workspace.toolbarPanels

        # Remove existing panel if present (for clean reload during development)
        existing_panel = toolbar_panels.itemById(PANEL_ID)
        if existing_panel:
            existing_panel.deleteMe()

        panel = toolbar_panels.add(PANEL_ID, 'PathMaker', '', False)

        # Create command buttons
        gen_cmd = _create_button(
            CMD_GENERATE_CAM,
            'Generate Toolpaths',
            'Analyze geometry and generate CAM operations with AI-selected tools and feeds/speeds.',
            GenerateCamCommandCreatedHandler,
            _res('GenerateCAM')
        )
        panel.controls.addCommand(gen_cmd)

        import_cmd = _create_button(
            CMD_IMPORT_TOOL,
            'Import Tool',
            'Import an endmill/bit from an Amazon URL. AI extracts the specifications automatically.',
            ImportToolCommandCreatedHandler,
            _res('ImportTool')
        )
        panel.controls.addCommand(import_cmd)

        manage_cmd = _create_button(
            CMD_MANAGE_TOOLS,
            'Manage Tools',
            'View and edit your AutoPath tool library.',
            ManageToolsCommandCreatedHandler,
            _res('ManageTools')
        )
        panel.controls.addCommand(manage_cmd)

        panel.controls.addSeparator()

        material_cmd = _create_button(
            CMD_ADD_MATERIAL,
            'Add Material',
            'Add a new material profile using AI-generated feeds and speeds.',
            AddMaterialCommandCreatedHandler,
            _res('AddMaterial')
        )
        panel.controls.addCommand(material_cmd)

        two_sided_cmd = _create_button(
            CMD_TWO_SIDED,
            '2-Sided Carve',
            'Set up a 2-sided machining operation with dowel pin alignment.',
            TwoSidedCommandCreatedHandler,
            _res('TwoSided')
        )
        panel.controls.addCommand(two_sided_cmd)

        panel.controls.addSeparator()

        settings_cmd = _create_button(
            CMD_SETTINGS,
            'Settings',
            'Configure AutoPath: AI token, machine profile, default preferences.',
            SettingsCommandCreatedHandler,
            _res('Settings')
        )
        panel.controls.addCommand(settings_cmd)

        # Check for first run
        settings = _load_json(os.path.join(DATA_DIR, 'user_settings.json'))
        if not settings.get('first_run_complete', False):
            _ui.messageBox(
                'Welcome to PathMaker! 🎉\n\n'
                'To get started:\n'
                '1. Click "Settings" to configure your AI token (GitHub Models API)\n'
                '2. Click "Import Tool" to add your endmills from Amazon\n'
                '3. Click "Generate Toolpaths" to create CAM operations!\n\n'
                'Tip: For surface textures (carbon fiber, knurl, wood grain),\n'
                'install the companion add-in TextureForge from C:\\MakerTools\\TextureForge\n\n'
                'Find AutoPath in the Manufacturing workspace toolbar.',
                'PathMaker Setup'
            )

    except Exception:
        if _ui:
            _ui.messageBox(f'PathMaker failed to start:\n{traceback.format_exc()}')


def stop(context):
    """Called when the add-in is stopped."""
    try:
        if _ui:
            # Clean up panel
            mfg_workspace = _ui.workspaces.itemById('CAMEnvironment')
            if mfg_workspace:
                panel = mfg_workspace.toolbarPanels.itemById(PANEL_ID)
                if panel:
                    for control in panel.controls:
                        if control.isValid:
                            control.deleteMe()
                    panel.deleteMe()

            # Clean up command definitions
            for cmd_id in [CMD_GENERATE_CAM, CMD_IMPORT_TOOL, CMD_MANAGE_TOOLS,
                           CMD_ADD_MATERIAL, CMD_TWO_SIDED, CMD_SETTINGS]:
                cmd_def = _ui.commandDefinitions.itemById(cmd_id)
                if cmd_def:
                    cmd_def.deleteMe()

        _handlers.clear()

    except Exception:
        if _ui:
            _ui.messageBox(f'PathMaker failed to stop cleanly:\n{traceback.format_exc()}')


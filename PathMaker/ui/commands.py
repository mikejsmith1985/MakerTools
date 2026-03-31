"""
UI Command definitions for FusionCam.
Registers toolbar buttons and command handlers in Fusion 360's Manufacturing workspace.
"""

# Command metadata
COMMANDS = {
    'fusionCamGenerate': {
        'label': 'Generate CAM',
        'tooltip': 'Analyze geometry and auto-generate CAM operations',
        'icon': 'generate'
    },
    'fusionCamImportTool': {
        'label': 'Import Tool',
        'tooltip': 'Import endmill from Amazon URL using AI',
        'icon': 'import_tool'
    },
    'fusionCamManageTools': {
        'label': 'Manage Tools',
        'tooltip': 'View and edit your FusionCam tool library',
        'icon': 'tools'
    },
    'fusionCamAddMaterial': {
        'label': 'Add Material',
        'tooltip': 'Add new material with AI-generated cutting parameters',
        'icon': 'material'
    },
    'fusionCamTwoSided': {
        'label': '2-Sided Carve',
        'tooltip': 'Set up 2-sided machining with alignment',
        'icon': 'two_sided'
    },
    'fusionCamSettings': {
        'label': 'Settings',
        'tooltip': 'Configure AI token, machine, preferences',
        'icon': 'settings'
    },
    'fusionCamTextureStamp': {
        'label': 'Stamp Texture',
        'tooltip': 'Apply procedural surface texture (carbon fiber, knurl, wood grain…) to a face',
        'icon': 'texture'
    }
}

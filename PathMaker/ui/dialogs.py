"""
Dialogs for FusionCam setup and configuration.
"""

import adsk.core
import os
import json

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ADDIN_DIR, 'data')


def show_first_run_wizard(ui):
    """
    Display the first-run setup wizard.
    Guides users through: token setup -> first tool import -> test CAM.
    """
    result = ui.messageBox(
        'Welcome to FusionCam!\n\n'
        'This add-in helps you go from Fusion 360 design to G-code\n'
        'with minimal CAM knowledge. Here is what it does:\n\n'
        '1. IMPORT TOOLS: Paste Amazon URLs to build your tool library\n'
        '2. GENERATE CAM: Select material + click Generate\n'
        '3. 2-SIDED CARVE: Guided flip workflow with dowel pins\n\n'
        'To get started, you will need a GitHub token for AI features.\n'
        'Get one free at: github.com/settings/tokens\n\n'
        'Click OK to open Settings and configure your token.',
        'Welcome to FusionCam',
        adsk.core.MessageBoxButtonTypes.OKCancelButtonType
    )

    return result == adsk.core.DialogResults.DialogOK


def show_no_token_warning(ui):
    """Show a warning when AI features are used without a token."""
    ui.messageBox(
        'AI features require a GitHub token.\n\n'
        'Go to FusionCam > Settings to configure your token.\n'
        'Get a free token at: github.com/settings/tokens\n'
        'Required scope: models:read',
        'FusionCam - Token Required'
    )


def show_no_tools_warning(ui):
    """Show a warning when CAM generation is attempted without tools."""
    ui.messageBox(
        'Your tool library is empty!\n\n'
        'Use FusionCam > Import Tool to add your endmills.\n'
        'Paste an Amazon product URL and AI will extract the specs.',
        'FusionCam - No Tools'
    )

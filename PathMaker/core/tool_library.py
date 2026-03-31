"""
Tool Library Manager for FusionCam.
Bridges the persistent JSON tool library with Fusion 360's built-in tool library system.
"""

import adsk.core
import adsk.cam
import json
import os
import math

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ADDIN_DIR, 'data')


def _get_cam():
    """Get the CAM product from the active document."""
    app = adsk.core.Application.get()
    doc = app.activeDocument
    products = doc.products
    cam = products.itemByProductType('CAMProductType')
    if not cam:
        raise RuntimeError(
            'No CAM product found. Switch to the Manufacturing workspace first.'
        )
    return adsk.cam.CAM.cast(cam)


def _tool_type_to_fusion(tool_type_str):
    """Map our tool type string to Fusion 360's ToolType enum."""
    mapping = {
        'flat_endmill': adsk.cam.ToolType.FlatEndMillTool,
        'ball_endmill': adsk.cam.ToolType.BallEndMillTool,
        'bull_nose_endmill': adsk.cam.ToolType.BullNoseEndMillTool,
        'v_bit': adsk.cam.ToolType.ChamferMillTool,
        'chamfer_mill': adsk.cam.ToolType.ChamferMillTool,
        'drill_bit': adsk.cam.ToolType.DrillTool,
        'spot_drill': adsk.cam.ToolType.SpotDrillTool,
    }
    return mapping.get(tool_type_str, adsk.cam.ToolType.FlatEndMillTool)


def create_fusion_tool(tool_data):
    """
    Create a tool in the Fusion 360 document tool library from our tool data.

    Args:
        tool_data: Dict with tool specifications from tool_parser

    Returns:
        The created Fusion 360 Tool object
    """
    cam = _get_cam()

    tool_type = _tool_type_to_fusion(tool_data.get('tool_type', 'flat_endmill'))

    # Create a new tool using the Tool constructor
    tool = adsk.cam.Tool.createFromLibrary(False)

    # Build tool parameters
    tool_params = tool.parameters

    # Set common parameters (all in cm, Fusion's internal unit)
    diameter_cm = tool_data.get('diameter_mm', 6.35) / 10.0
    shank_diameter_cm = tool_data.get('shank_diameter_mm', 6.35) / 10.0
    flute_length_cm = tool_data.get('flute_length_mm', 19.05) / 10.0
    overall_length_cm = tool_data.get('overall_length_mm', 50.8) / 10.0

    # Use the tool preset approach instead
    tool_preset = {
        'tool_type': tool_data.get('tool_type', 'flat_endmill'),
        'diameter': diameter_cm,
        'shaft-diameter': shank_diameter_cm,
        'flute-length': flute_length_cm,
        'overall-length': overall_length_cm,
        'number-of-flutes': tool_data.get('flute_count', 2),
        'description': tool_data.get('display_name', ''),
        'comment': tool_data.get('notes', ''),
        'product-id': tool_data.get('product_url', ''),
    }

    if tool_data.get('corner_radius_inches'):
        tool_preset['corner-radius'] = tool_data['corner_radius_inches'] * 25.4 / 10.0

    if tool_data.get('v_angle_degrees') and tool_type == adsk.cam.ToolType.ChamferMillTool:
        tool_preset['taper-angle'] = tool_data['v_angle_degrees'] / 2.0

    return tool_preset


def sync_library_to_fusion():
    """
    Sync all tools from the persistent JSON library to the Fusion 360 document library.
    Returns count of tools synced.
    """
    from . import tool_parser

    tools = tool_parser.get_all_tools()
    synced = 0

    for tool_data in tools:
        try:
            create_fusion_tool(tool_data)
            synced += 1
        except Exception:
            continue

    return synced


def get_tool_library_summary():
    """
    Get a summary of the current tool library for display.
    Returns list of dicts with key display info.
    """
    from . import tool_parser

    tools = tool_parser.get_all_tools()
    summary = []

    for tool in tools:
        summary.append({
            'id': tool.get('id', '?'),
            'name': tool.get('display_name', 'Unknown Tool'),
            'type': tool.get('tool_type', '?').replace('_', ' ').title(),
            'diameter': f"{tool.get('diameter_inches', 0)}\" ({tool.get('diameter_mm', 0)}mm)",
            'flutes': tool.get('flute_count', '?'),
            'material': tool.get('material', '?'),
            'coating': tool.get('coating', '?'),
            'brand': tool.get('brand', '?'),
            'url': tool.get('product_url', '')
        })

    return summary


def format_tool_for_display(tool_data):
    """Format a tool dict into a human-readable multi-line string."""
    lines = [
        f"🔧 {tool_data.get('display_name', 'Tool')}",
        f"   Type: {tool_data.get('tool_type', '?').replace('_', ' ').title()}",
        f"   Diameter: {tool_data.get('diameter_inches', 0)}\" ({tool_data.get('diameter_mm', 0)}mm)",
        f"   Shank: {tool_data.get('shank_diameter_inches', 0)}\" ({tool_data.get('shank_diameter_mm', 0)}mm)",
        f"   Flutes: {tool_data.get('flute_count', '?')}",
        f"   Flute Length: {tool_data.get('flute_length_inches', 0)}\" ({tool_data.get('flute_length_mm', 0)}mm)",
        f"   Overall Length: {tool_data.get('overall_length_inches', 0)}\" ({tool_data.get('overall_length_mm', 0)}mm)",
        f"   Material: {tool_data.get('material', '?')}",
        f"   Coating: {tool_data.get('coating', '?')}",
        f"   Brand: {tool_data.get('brand', '?')}",
    ]

    if tool_data.get('corner_radius_inches'):
        lines.append(f"   Corner Radius: {tool_data['corner_radius_inches']}\"")
    if tool_data.get('v_angle_degrees'):
        lines.append(f"   V-Angle: {tool_data['v_angle_degrees']}°")
    if tool_data.get('suitable_materials'):
        lines.append(f"   Suitable For: {', '.join(tool_data['suitable_materials'])}")
    if tool_data.get('product_url'):
        lines.append(f"   URL: {tool_data['product_url']}")
    if tool_data.get('confidence'):
        confidence_emoji = {'high': '✅', 'medium': '⚠️', 'low': '❓', 'manual': '✏️'}
        lines.append(f"   Confidence: {confidence_emoji.get(tool_data['confidence'], '?')} {tool_data['confidence']}")

    return '\n'.join(lines)

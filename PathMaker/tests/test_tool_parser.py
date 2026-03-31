"""
Tests for the tool parser module.
Tests HTML stripping, Amazon page extraction, and manual tool creation.
Can run outside Fusion 360 (no adsk dependency).
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import tool_parser


def test_strip_html():
    """Test HTML tag stripping."""
    html = '<div><h1>SpeTool 1/4 Inch End Mill</h1><p>2 Flute <b>Carbide</b></p></div>'
    text = tool_parser._strip_html(html)
    assert 'SpeTool' in text
    assert '1/4 Inch End Mill' in text
    assert '2 Flute' in text
    assert 'Carbide' in text
    assert '<div>' not in text
    print("PASS: HTML stripping works correctly")


def test_manual_tool_creation():
    """Test creating a tool from manual input."""
    tool = tool_parser.create_manual_tool(
        tool_type='flat_endmill',
        diameter_inches=0.25,
        flute_count=2,
        material='carbide',
        coating='uncoated',
        notes='Test tool'
    )

    assert tool['tool_type'] == 'flat_endmill'
    assert tool['diameter_inches'] == 0.25
    assert tool['diameter_mm'] == 6.35
    assert tool['flute_count'] == 2
    assert tool['shank_diameter_inches'] == 0.25  # Default: shank = diameter
    assert tool['flute_length_inches'] == 0.75    # Default: 3x diameter
    assert tool['material'] == 'carbide'
    assert tool['confidence'] == 'manual'

    print(f"PASS: Manual tool creation")
    print(f"  {tool['diameter_inches']}\" {tool['flute_count']}F {tool['tool_type']}")
    print(f"  Flute length: {tool['flute_length_inches']}\" (auto-calculated)")
    print(f"  OAL: {tool['overall_length_inches']}\" (auto-calculated)")
    print()


def test_tool_library_persistence():
    """Test adding and retrieving tools from the library."""
    import tempfile
    import json

    # Use a temp directory for test
    original_data_dir = tool_parser.DATA_DIR
    temp_dir = tempfile.mkdtemp()
    tool_parser.DATA_DIR = temp_dir

    # Initialize library
    lib_path = os.path.join(temp_dir, 'tool_library.json')
    with open(lib_path, 'w') as f:
        json.dump({'tools': [], 'version': 1}, f)

    try:
        tool = tool_parser.create_manual_tool('flat_endmill', 0.25, 2)
        tool_id = tool_parser.add_tool(tool)

        assert tool_id is not None

        all_tools = tool_parser.get_all_tools()
        assert len(all_tools) == 1
        assert all_tools[0]['diameter_inches'] == 0.25

        retrieved = tool_parser.get_tool(tool_id)
        assert retrieved is not None
        assert retrieved['flute_count'] == 2

        # Add another tool
        tool2 = tool_parser.create_manual_tool('ball_endmill', 0.125, 2)
        tool_parser.add_tool(tool2)
        assert len(tool_parser.get_all_tools()) == 2

        # Remove first tool
        tool_parser.remove_tool(tool_id)
        assert len(tool_parser.get_all_tools()) == 1

        print("PASS: Tool library add/get/remove works")
        print()
    finally:
        tool_parser.DATA_DIR = original_data_dir
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_find_tools_for_feature():
    """Test tool-to-feature matching."""
    tools = [
        {'id': 't1', 'tool_type': 'flat_endmill', 'diameter_mm': 6.35, 'flute_length_mm': 19.05},
        {'id': 't2', 'tool_type': 'flat_endmill', 'diameter_mm': 3.175, 'flute_length_mm': 12.0},
        {'id': 't3', 'tool_type': 'drill_bit', 'diameter_mm': 6.35, 'flute_length_mm': 25.0},
        {'id': 't4', 'tool_type': 'v_bit', 'diameter_mm': 12.7, 'flute_length_mm': 10.0},
    ]

    # Pocket with 4mm corner radius - both endmills should fit
    pocket_feature = {'type': 'pocket', 'min_radius_mm': 4.0, 'depth_mm': 10.0}
    suitable = tool_parser.find_tools_for_feature(pocket_feature, tools)
    assert len(suitable) == 2, f"Expected 2 endmills, got {len(suitable)}"
    assert suitable[0]['id'] == 't1'  # Larger tool first

    # Small pocket - only small endmill fits
    small_pocket = {'type': 'pocket', 'min_radius_mm': 2.0, 'depth_mm': 5.0}
    suitable = tool_parser.find_tools_for_feature(small_pocket, tools)
    assert len(suitable) == 1
    assert suitable[0]['id'] == 't2'

    # Hole - drill bit and endmills match
    hole_feature = {'type': 'through_hole', 'min_radius_mm': 4.0, 'depth_mm': 10.0}
    suitable = tool_parser.find_tools_for_feature(hole_feature, tools)
    assert any(t['tool_type'] == 'drill_bit' for t in suitable)

    # Chamfer - only v-bit matches
    chamfer_feature = {'type': 'chamfer', 'min_radius_mm': 50.0, 'depth_mm': 2.0}
    suitable = tool_parser.find_tools_for_feature(chamfer_feature, tools)
    assert len(suitable) == 1
    assert suitable[0]['tool_type'] == 'v_bit'

    print("PASS: Tool-to-feature matching works correctly")
    print(f"  Pocket (4mm radius): {len(tool_parser.find_tools_for_feature(pocket_feature, tools))} tools")
    print(f"  Small pocket (2mm radius): {len(tool_parser.find_tools_for_feature(small_pocket, tools))} tools")
    print()


if __name__ == '__main__':
    print("=" * 60)
    print("FusionCam Tool Parser Tests")
    print("=" * 60)
    print()

    test_strip_html()
    test_manual_tool_creation()
    test_tool_library_persistence()
    test_find_tools_for_feature()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)

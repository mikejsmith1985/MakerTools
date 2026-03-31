"""
Tests for mister_control.py — runs outside Fusion 360.
"""

import sys
import os
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import mister_control


def test_gcode_commands():
    """Test that G-code commands are returned correctly for each mode."""
    config = {'pin_mode': 'M7_mist'}
    on, off = mister_control.get_gcode_commands(config)
    assert on == 'M7', f"Expected M7, got {on}"
    assert off == 'M9', f"Expected M9, got {off}"

    config = {'pin_mode': 'M8_flood'}
    on, off = mister_control.get_gcode_commands(config)
    assert on == 'M8'
    assert off == 'M9'

    config = {'pin_mode': 'custom_m', 'custom_gcode_on': 'M42', 'custom_gcode_off': 'M43'}
    on, off = mister_control.get_gcode_commands(config)
    assert on == 'M42'
    assert off == 'M43'

    print("PASS: G-code command resolution works for all modes")
    print()


def test_gcode_injection():
    """Test injection of M7/M9 into a sample G-code file."""
    sample_gcode = """; Sample G-code
G21
G90
M3 S18000
G0 X10 Y10
G1 X50 F600
M5
G0 X0 Y0
M2
"""
    tmp_dir = tempfile.mkdtemp()
    try:
        nc_path = os.path.join(tmp_dir, 'test.nc')
        with open(nc_path, 'w') as f:
            f.write(sample_gcode)

        config = {
            'enabled': True,
            'pin_mode': 'M7_mist',
            'pre_mist_delay_seconds': 2.0,
            'post_mist_delay_seconds': 3.0,
        }

        out_path, summary = mister_control.inject_into_gcode(nc_path, config)

        with open(out_path) as f:
            result = f.read()

        assert 'M7' in result, "M7 not found in output"
        assert 'M9' in result, "M9 not found in output"
        assert 'G4 P2.0' in result, "Pre-delay G4 not found"
        assert 'G4 P3.0' in result, "Post-delay G4 not found"

        # Verify M7 comes BEFORE M3
        m7_pos = result.index('M7')
        m3_pos = result.index('M3')
        assert m7_pos < m3_pos, "M7 should appear before M3"

        # Verify M9 comes AFTER M5
        m5_pos = result.index('M5')
        m9_pos = result.index('M9')
        assert m9_pos > m5_pos, "M9 should appear after M5"

        print("PASS: G-code injection is correct")
        print(f"  M7 at char {m7_pos}, M3 at char {m3_pos} (M7 first ✓)")
        print(f"  M5 at char {m5_pos}, M9 at char {m9_pos} (M9 after ✓)")
        print()

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_injection_disabled():
    """Test that injection is skipped when mister is disabled."""
    tmp_dir = tempfile.mkdtemp()
    try:
        nc_path = os.path.join(tmp_dir, 'test.nc')
        with open(nc_path, 'w') as f:
            f.write("M3 S18000\nG1 X10\nM5\nM2\n")

        config = {'enabled': False, 'pin_mode': 'M7_mist'}
        out_path, summary = mister_control.inject_into_gcode(nc_path, config)

        with open(out_path) as f:
            result = f.read()

        assert 'M7' not in result, "M7 should NOT be injected when disabled"
        assert 'M9' not in result, "M9 should NOT be injected when disabled"
        assert 'no changes made' in summary.lower()

        print("PASS: Injection correctly skipped when mister is disabled")
        print()
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test_generate_test_gcode():
    """Test that test G-code generation produces a valid file."""
    tmp_dir = tempfile.mkdtemp()
    original_dir = mister_control.os.path.join(os.path.expanduser('~'), 'Documents', 'FusionCam', 'GCode')

    config = {
        'enabled': True,
        'pin_mode': 'M7_mist',
        'pre_mist_delay_seconds': 2.0,
        'post_mist_delay_seconds': 4.0,
    }

    try:
        gcode, path = mister_control.generate_test_gcode(config)

        assert os.path.exists(path), f"Test file not created at {path}"
        assert 'M7' in gcode
        assert 'M9' in gcode
        assert 'G4 P3.0' in gcode  # 3-second hold
        assert 'M2' in gcode       # End program
        # M3 must appear only as a comment ("; M3 ..."), never as an uncommented command
        assert '; M3 S18000' in gcode, "M3 should appear commented-out in test G-code"
        for line in gcode.splitlines():
            stripped = line.strip()
            if stripped.startswith(';'):
                continue
            assert not stripped.upper().startswith('M3'), \
                f"Uncommented M3 found in test G-code line: {line!r}"

        print("PASS: Test G-code generated correctly")
        print(f"  File: {path}")
        print(f"  Length: {len(gcode)} chars")
        print()
    finally:
        pass  # Don't remove — useful to inspect


def test_config_validation():
    """Test configuration validation logic."""
    # Valid config
    good_config = {
        'pin_mode': 'M7_mist',
        'pre_mist_delay_seconds': 2.0,
        'post_mist_delay_seconds': 4.0,
        'wiring_confirmed': True,
    }
    valid, errors, warnings = mister_control.validate_config(good_config)
    assert valid, f"Expected valid, got errors: {errors}"
    assert len(errors) == 0

    # Custom mode without commands
    bad_config = {
        'pin_mode': 'custom_m',
        'custom_gcode_on': '',
        'custom_gcode_off': '',
    }
    valid, errors, warnings = mister_control.validate_config(bad_config)
    assert not valid
    assert len(errors) == 2  # Missing both on and off commands

    # Short delays should produce warnings
    warn_config = {
        'pin_mode': 'M7_mist',
        'pre_mist_delay_seconds': 0.5,
        'post_mist_delay_seconds': 1.0,
        'wiring_confirmed': False,
    }
    valid, errors, warnings = mister_control.validate_config(warn_config)
    assert valid  # No errors, just warnings
    assert len(warnings) > 0

    print("PASS: Config validation works correctly")
    print(f"  Good config: valid={valid}, warnings={len(warnings)}")
    print()


def test_wiring_diagram():
    """Test wiring diagram generation."""
    diagram = mister_control.get_wiring_diagram('12V', 'normally_open')
    assert '12V' in diagram
    assert 'M7' in diagram
    assert '1N4007' in diagram
    assert 'RELAY' in diagram.upper()
    assert 'OPTO' in diagram.upper()

    diagram_24v = mister_control.get_wiring_diagram('24V', 'normally_open')
    assert '24V' in diagram_24v

    print("PASS: Wiring diagram generated for 12V and 24V")
    print()


def test_should_use_mister():
    """Test material-based mister activation logic."""
    config = {
        'enabled': True,
        'apply_to_all_metals': True,
        'apply_to_materials': []
    }

    # Aluminum should activate mister
    result = mister_control.should_use_mister('aluminum_6061_t6', config)
    assert result, "Mister should activate for aluminum"

    # Disabled mister should never activate
    config_off = dict(config, enabled=False)
    result = mister_control.should_use_mister('aluminum_6061_t6', config_off)
    assert not result, "Mister should not activate when disabled"

    print("PASS: Material-based mister activation works")
    print()


if __name__ == '__main__':
    print("=" * 60)
    print("MisterWizard / Mister Control Tests")
    print("=" * 60)
    print()

    test_gcode_commands()
    test_gcode_injection()
    test_injection_disabled()
    test_generate_test_gcode()
    test_config_validation()
    test_wiring_diagram()
    test_should_use_mister()

    print("=" * 60)
    print("All tests passed!")
    print("=" * 60)

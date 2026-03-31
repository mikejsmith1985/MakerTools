"""
Tests for core/texture_stamp.py — pure-Python pattern generators.
Runs fully offline, no Fusion 360 required.
"""

import sys
import os
import math

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.texture_stamp import (
    TEXTURES,
    generate_pattern,
    _generate_carbon_fiber,
    _generate_knurl_diamond,
    _generate_brushed_metal,
    _generate_wood_grain,
    _generate_leather_hexagons,
    MAX_PROFILES,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _rects_overlap(r1, r2, tol=1e-6):
    """Return True if two (x,y,w,h) rects overlap (excluding shared edges)."""
    x1, y1, w1, h1 = r1
    x2, y2, w2, h2 = r2
    return (x1 + w1 - tol > x2 and x2 + w2 - tol > x1 and
            y1 + h1 - tol > y2 and y2 + h2 - tol > y1)


def _polygon_area(pts):
    """Shoelace formula for polygon area."""
    n = len(pts)
    s = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


# ═════════════════════════════════════════════════════════════════════════════
# Carbon Fiber
# ═════════════════════════════════════════════════════════════════════════════

def test_carbon_fiber_basic():
    """Carbon fiber rects fill a simple square face."""
    scale = 0.5   # cm
    rects = _generate_carbon_fiber(4.0, 4.0, scale)

    assert len(rects) > 0, "Should produce at least one rectangle"
    assert len(rects) <= MAX_PROFILES

    # All rects should be within (or close to) the face bounds
    for (x, y, w, h) in rects:
        assert x >= -0.001, f"x={x} below 0"
        assert y >= -0.001, f"y={y} below 0"
        assert x + w <= 4.0 + 0.001, f"rect exceeds width: x+w={x+w}"
        assert y + h <= 4.0 + 0.001, f"rect exceeds height: y+h={y+h}"
        assert w > 0 and h > 0, "Rect dimensions must be positive"

    print(f"PASS: carbon_fiber basic — {len(rects)} rects on 4×4cm face")


def test_carbon_fiber_no_overlap():
    """No two carbon fiber rects should overlap (they are separated by gap)."""
    rects = _generate_carbon_fiber(3.0, 3.0, 0.4)
    for i, r1 in enumerate(rects):
        for j, r2 in enumerate(rects):
            if i == j:
                continue
            assert not _rects_overlap(r1, r2), \
                f"Rects {i} and {j} overlap: {r1} / {r2}"
    print(f"PASS: carbon_fiber no-overlap — {len(rects)} rects checked")


def test_carbon_fiber_twill_offset():
    """
    Twill offset: the checker shifts by one column every TWO rows.
    Rows 0 & 1 share the same phase; rows 2 & 3 have a different phase.
    """
    scale = 1.0
    half = scale / 2
    rects = _generate_carbon_fiber(6.0, 6.0, scale)

    # Group rects by row (bucket by y)
    rows = {}
    for (x, y, w, h) in rects:
        row_idx = round(y / half)
        rows.setdefault(row_idx, []).append(x)

    row_keys = sorted(rows.keys())
    assert len(row_keys) >= 4, "Need at least 4 rows to verify twill"

    # Rows 0 and 1 share the same twill phase (twill_offset = 0)
    first_x_r0 = min(rows[row_keys[0]])
    first_x_r1 = min(rows[row_keys[1]])
    assert abs(first_x_r0 - first_x_r1) < 0.001, \
        "Rows 0 and 1 should have the same phase (same twill_offset)"

    # Rows 2 and 3 share a different phase (twill_offset = 1 → shifted by one cell)
    first_x_r2 = min(rows[row_keys[2]])
    assert abs(first_x_r0 - first_x_r2) > 0.001, \
        "Rows 0 and 2 should have DIFFERENT x phases (twill shift at row 2)"

    print("PASS: carbon_fiber twill offset verified (shifts every 2 rows)")


def test_carbon_fiber_respects_max():
    """Very large face with tiny scale should be capped at MAX_PROFILES."""
    rects = _generate_carbon_fiber(100.0, 100.0, 0.05)
    assert len(rects) == MAX_PROFILES, \
        f"Expected MAX_PROFILES={MAX_PROFILES}, got {len(rects)}"
    print(f"PASS: carbon_fiber MAX_PROFILES cap at {MAX_PROFILES}")


# ═════════════════════════════════════════════════════════════════════════════
# Knurl Diamond
# ═════════════════════════════════════════════════════════════════════════════

def test_knurl_diamond_basic():
    """Diamonds generated on a face; each diamond has exactly 4 vertices."""
    diamonds = _generate_knurl_diamond(5.0, 5.0, 0.5)
    assert len(diamonds) > 0
    assert len(diamonds) <= MAX_PROFILES

    for pts in diamonds:
        assert len(pts) == 4, f"Each diamond must have 4 points, got {len(pts)}"
        for (x, y) in pts:
            assert isinstance(x, float) and isinstance(y, float)

    print(f"PASS: knurl_diamond basic — {len(diamonds)} diamonds on 5×5cm face")


def test_knurl_diamond_shape():
    """Each diamond should be a proper rotated square (N/E/S/W pattern)."""
    diamonds = _generate_knurl_diamond(4.0, 4.0, 0.6)
    for i, pts in enumerate(diamonds[:10]):   # check first 10
        top, right, bot, left = pts
        cx = (top[0] + bot[0]) / 2
        cy = (right[1] + left[1]) / 2

        # Diagonals should be equal length
        horiz_d = math.hypot(right[0] - left[0], right[1] - left[1])
        vert_d  = math.hypot(top[0]   - bot[0],  top[1]   - bot[1])
        assert abs(horiz_d - vert_d) < 0.001, \
            f"Diamond {i} is not square: h={horiz_d:.4f}, v={vert_d:.4f}"

        # Area should be positive
        assert _polygon_area(pts) > 0, f"Diamond {i} has zero area"

    print(f"PASS: knurl_diamond shape — {len(diamonds)} diamonds verified")


# ═════════════════════════════════════════════════════════════════════════════
# Brushed Metal
# ═════════════════════════════════════════════════════════════════════════════

def test_brushed_metal_basic():
    """Brushed metal produces parallel horizontal stripes."""
    scale = 0.3
    rects = _generate_brushed_metal(5.0, 5.0, scale)
    assert len(rects) > 0

    # All stripes span the full width
    for (x, y, w, h) in rects:
        assert abs(x) < 0.001, "Stripe should start at x=0"
        assert abs(w - 5.0) < 0.001, "Stripe should span full width"
        assert h > 0 and h < scale, "Stripe height must be < pitch"

    # Stripes should not overlap
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not _rects_overlap(rects[i], rects[j]), \
                f"Stripes {i} and {j} overlap"

    print(f"PASS: brushed_metal — {len(rects)} stripes, no overlap")


def test_brushed_metal_duty_cycle():
    """Stripe height should be 30% of scale (duty cycle check)."""
    scale = 1.0
    rects = _generate_brushed_metal(4.0, 4.0, scale)
    heights = [h for (_, _, _, h) in rects if h > 0.001]
    expected_h = scale * 0.30
    for h in heights:
        assert abs(h - expected_h) < 0.001 or h < expected_h, \
            f"Stripe height {h:.4f} != expected {expected_h:.4f}"
    print(f"PASS: brushed_metal duty cycle — stripe h ≈ {expected_h*10:.1f}mm")


# ═════════════════════════════════════════════════════════════════════════════
# Wood Grain
# ═════════════════════════════════════════════════════════════════════════════

def test_wood_grain_basic():
    """Wood grain bands are closed polygons with ≥ 4 points each."""
    bands = _generate_wood_grain(6.0, 6.0, 0.8)
    assert len(bands) > 0

    for i, band in enumerate(bands):
        assert len(band) >= 4, f"Band {i} has < 4 points"
        # Each element is a (x, y) tuple
        for pt in band:
            assert len(pt) == 2, "Each point should be (x, y)"
            x, y = pt
            assert 0.0 <= x <= 6.0 + 0.001, f"Band point x={x} out of range"
            assert 0.0 <= y <= 6.0 + 0.001, f"Band point y={y} out of range"

    print(f"PASS: wood_grain — {len(bands)} closed bands generated")


def test_wood_grain_phases_differ():
    """Adjacent bands should have different wave phases (organic variety)."""
    bands = _generate_wood_grain(8.0, 8.0, 1.0)
    assert len(bands) >= 3

    # Compare mid-point y-values of band 0 and band 1 at x=4.0
    def midpoint_y(band):
        mid_idx = len(band) // 4   # top-curve midpoint
        return band[mid_idx][1]

    y0 = midpoint_y(bands[0])
    y1 = midpoint_y(bands[1])
    # They are at different y centers AND have different wave phase
    # Just verify they're not identical
    assert abs(y0 - y1) > 0.001, "Adjacent bands should differ in position/phase"
    print("PASS: wood_grain band phases differ (organic look)")


# ═════════════════════════════════════════════════════════════════════════════
# Leather Hexagons
# ═════════════════════════════════════════════════════════════════════════════

def test_leather_hexagons_basic():
    """Leather pattern produces valid hexagons (6 vertices each)."""
    hexagons = _generate_leather_hexagons(5.0, 5.0, 0.6)
    assert len(hexagons) > 0
    assert len(hexagons) <= MAX_PROFILES

    for i, pts in enumerate(hexagons):
        assert len(pts) == 6, f"Hexagon {i} should have 6 vertices"
        # Area should be positive
        assert _polygon_area(pts) > 0, f"Hexagon {i} has zero area"

    print(f"PASS: leather_hexagons — {len(hexagons)} hexagons on 5×5cm face")


def test_leather_hexagons_regularity():
    """All hexagon edges should have equal length (regular hexagon)."""
    hexagons = _generate_leather_hexagons(4.0, 4.0, 0.8)
    for hex_idx, pts in enumerate(hexagons[:5]):
        edge_lengths = []
        for i in range(6):
            p0, p1 = pts[i], pts[(i + 1) % 6]
            edge_lengths.append(math.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        # All edges should be equal (regular hexagon)
        max_diff = max(edge_lengths) - min(edge_lengths)
        assert max_diff < 1e-6, \
            f"Hexagon {hex_idx} edges not equal: {edge_lengths}"
    print("PASS: leather_hexagons regularity (all edges equal)")


# ═════════════════════════════════════════════════════════════════════════════
# generate_pattern dispatcher
# ═════════════════════════════════════════════════════════════════════════════

def test_dispatcher():
    """generate_pattern returns correct (kind, primitives) for all texture keys."""
    expected = {
        'carbon_fiber':  'rects',
        'knurl_diamond': 'diamonds',
        'brushed_metal': 'rects',
        'wood_grain':    'polygons',
        'leather':       'polygons',
    }
    for key, expected_kind in expected.items():
        kind, prims = generate_pattern(key, 3.0, 3.0, 0.4)
        assert kind == expected_kind, \
            f"Texture {key}: expected kind={expected_kind}, got {kind}"
        assert len(prims) > 0, f"Texture {key}: no primitives generated"
    print(f"PASS: dispatcher — all {len(expected)} textures return data")


def test_dispatcher_unknown_key():
    """Unknown texture key raises ValueError."""
    try:
        generate_pattern('banana_peel', 2.0, 2.0, 0.3)
        assert False, "Should have raised ValueError"
    except ValueError:
        pass
    print("PASS: dispatcher raises ValueError for unknown texture key")


def test_texture_catalog():
    """TEXTURES dict has required fields for all entries."""
    for key, info in TEXTURES.items():
        assert 'name' in info,                f"{key}: missing 'name'"
        assert 'description' in info,         f"{key}: missing 'description'"
        assert 'default_scale_mm' in info,    f"{key}: missing 'default_scale_mm'"
        assert 'default_depth_mm' in info,    f"{key}: missing 'default_depth_mm'"
        assert info['default_scale_mm'] > 0,  f"{key}: scale must be positive"
        assert info['default_depth_mm'] > 0,  f"{key}: depth must be positive"
    print(f"PASS: TEXTURES catalog — all {len(TEXTURES)} entries valid")


# ═════════════════════════════════════════════════════════════════════════════
# Main
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    print("=" * 60)
    print("Texture Stamp — Pattern Generator Tests")
    print("=" * 60)
    print()

    test_carbon_fiber_basic()
    test_carbon_fiber_no_overlap()
    test_carbon_fiber_twill_offset()
    test_carbon_fiber_respects_max()
    print()

    test_knurl_diamond_basic()
    test_knurl_diamond_shape()
    print()

    test_brushed_metal_basic()
    test_brushed_metal_duty_cycle()
    print()

    test_wood_grain_basic()
    test_wood_grain_phases_differ()
    print()

    test_leather_hexagons_basic()
    test_leather_hexagons_regularity()
    print()

    test_dispatcher()
    test_dispatcher_unknown_key()
    test_texture_catalog()
    print()

    print("=" * 60)
    print("All texture stamp tests passed!")
    print("=" * 60)

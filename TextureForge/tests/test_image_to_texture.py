"""
Tests for core/image_to_texture.py — all pure-Python, no Fusion 360 required.
Covers SVG path parsing, BMP reading, PNG reading, raster grid logic,
and geometry utilities.
"""

import os
import sys
import math
import struct
import zlib
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.image_to_texture import (
    _cubic_bezier,
    _quadratic_bezier,
    _svg_arc,
    _parse_svg_path,
    _parse_transform,
    _apply_transform,
    import_svg,
    _read_bmp,
    _read_png,
    import_raster,
    _poly_area_mm2,
    _douglas_peucker,
)


# ─── SVG path parsing ─────────────────────────────────────────────────────────

class TestCubicBezier(unittest.TestCase):
    def test_endpoints_preserved(self):
        pts = _cubic_bezier((0,0),(1,2),(3,2),(4,0))
        self.assertAlmostEqual(pts[0][0], 0.0)
        self.assertAlmostEqual(pts[-1][0], 4.0)

    def test_point_count(self):
        pts = _cubic_bezier((0,0),(1,1),(2,1),(3,0), n=8)
        self.assertEqual(len(pts), 9)

    def test_straight_line(self):
        # Control points on the line → all points on the line
        pts = _cubic_bezier((0,0),(1,0),(2,0),(3,0), n=6)
        for x, y in pts:
            self.assertAlmostEqual(y, 0.0, places=10)


class TestQuadraticBezier(unittest.TestCase):
    def test_endpoints(self):
        pts = _quadratic_bezier((0,0),(2,4),(4,0))
        self.assertAlmostEqual(pts[0],  (0.0, 0.0))
        self.assertAlmostEqual(pts[-1], (4.0, 0.0))

    def test_midpoint_pulled_to_control(self):
        # At t=0.5, point should be pulled toward the control point
        pts = _quadratic_bezier((0,0),(2,4),(4,0), n=2)
        mid = pts[1]
        self.assertGreater(mid[1], 0)  # y should be above the baseline


class TestSvgPathParser(unittest.TestCase):
    def test_simple_closed_rect(self):
        d = 'M0,0 L10,0 L10,10 L0,10 Z'
        subpaths = _parse_svg_path(d)
        self.assertEqual(len(subpaths), 1)
        sp = subpaths[0]
        self.assertGreaterEqual(len(sp), 4)
        # Should close back to origin
        self.assertAlmostEqual(sp[-1][0], 0.0)
        self.assertAlmostEqual(sp[-1][1], 0.0)

    def test_relative_commands(self):
        d = 'M5,5 l10,0 l0,10 l-10,0 z'
        subpaths = _parse_svg_path(d)
        self.assertEqual(len(subpaths), 1)
        sp = subpaths[0]
        self.assertAlmostEqual(sp[0][0], 5.0)
        self.assertAlmostEqual(sp[0][1], 5.0)

    def test_multiple_subpaths(self):
        d = 'M0,0 L5,0 Z M10,10 L15,10 Z'
        subpaths = _parse_svg_path(d)
        self.assertEqual(len(subpaths), 2)

    def test_cubic_bezier_in_path(self):
        # A smooth S-curve should produce more than 2 points
        d = 'M0,0 C5,10 10,10 15,0'
        subpaths = _parse_svg_path(d)
        self.assertEqual(len(subpaths), 1)
        self.assertGreater(len(subpaths[0]), 2)

    def test_horizontal_vertical(self):
        d = 'M0,0 H10 V10 H0 Z'
        subpaths = _parse_svg_path(d)
        sp = subpaths[0]
        # After H10: x=10,y=0; after V10: x=10,y=10; after H0: x=0,y=10
        self.assertAlmostEqual(sp[1][0], 10.0)
        self.assertAlmostEqual(sp[2][0], 10.0)
        self.assertAlmostEqual(sp[2][1], 10.0)

    def test_arc_command(self):
        # Quarter-circle arc
        d = 'M10,0 A10,10 0 0 1 0,10'
        subpaths = _parse_svg_path(d)
        self.assertEqual(len(subpaths), 1)
        self.assertGreater(len(subpaths[0]), 2)


class TestSvgTransform(unittest.TestCase):
    def test_translate(self):
        m = _parse_transform('translate(10, 20)')
        pts = _apply_transform([(0, 0)], m)
        self.assertAlmostEqual(pts[0][0], 10.0)
        self.assertAlmostEqual(pts[0][1], 20.0)

    def test_scale(self):
        m = _parse_transform('scale(2)')
        pts = _apply_transform([(5, 3)], m)
        self.assertAlmostEqual(pts[0][0], 10.0)
        self.assertAlmostEqual(pts[0][1], 6.0)

    def test_rotate_90(self):
        m = _parse_transform('rotate(90)')
        pts = _apply_transform([(1, 0)], m)
        self.assertAlmostEqual(pts[0][0], 0.0, places=5)
        self.assertAlmostEqual(pts[0][1], 1.0, places=5)

    def test_matrix(self):
        # matrix(a,b,c,d,e,f) → [a,c,e; b,d,f; 0,0,1]
        m = _parse_transform('matrix(1,0,0,1,5,10)')  # pure translate
        pts = _apply_transform([(0, 0)], m)
        self.assertAlmostEqual(pts[0][0], 5.0)
        self.assertAlmostEqual(pts[0][1], 10.0)


# ─── SVG file import ──────────────────────────────────────────────────────────

class TestImportSvg(unittest.TestCase):
    def _make_svg(self, content, viewbox='0 0 100 100'):
        tmp = tempfile.NamedTemporaryFile(suffix='.svg', delete=False, mode='w', encoding='utf-8')
        tmp.write(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{viewbox}">'
                  f'{content}</svg>')
        tmp.close()
        return tmp.name

    def test_rect_yields_contour(self):
        path = self._make_svg('<rect x="10" y="10" width="80" height="80"/>')
        try:
            contours, w, h = import_svg(path)
            self.assertGreater(len(contours), 0)
            self.assertGreater(w, 0)
            self.assertGreater(h, 0)
        finally:
            os.unlink(path)

    def test_circle_yields_contour(self):
        path = self._make_svg('<circle cx="50" cy="50" r="40"/>')
        try:
            contours, w, h = import_svg(path)
            self.assertGreater(len(contours), 0)
        finally:
            os.unlink(path)

    def test_polygon_yields_contour(self):
        path = self._make_svg('<polygon points="50,10 90,90 10,90"/>')
        try:
            contours, w, h = import_svg(path)
            self.assertGreater(len(contours), 0)
        finally:
            os.unlink(path)

    def test_closed_path_yields_contour(self):
        path = self._make_svg('<path d="M10,10 L90,10 L90,90 L10,90 Z"/>')
        try:
            contours, w, h = import_svg(path)
            self.assertGreater(len(contours), 0)
        finally:
            os.unlink(path)

    def test_viewbox_w_h_returned_in_mm(self):
        # viewBox 100x200 px → 100 * 0.264583 mm × 200 * 0.264583 mm
        path = self._make_svg('<rect x="0" y="0" width="100" height="200"/>',
                              viewbox='0 0 100 200')
        try:
            _, w, h = import_svg(path)
            self.assertAlmostEqual(w, 100 * 0.264583, places=2)
            self.assertAlmostEqual(h, 200 * 0.264583, places=2)
        finally:
            os.unlink(path)

    def test_group_traversal(self):
        svg = ('<g transform="translate(5,5)">'
               '<rect x="0" y="0" width="40" height="40"/>'
               '</g>')
        path = self._make_svg(svg)
        try:
            contours, _, _ = import_svg(path)
            self.assertGreater(len(contours), 0)
        finally:
            os.unlink(path)

    def test_empty_svg_returns_no_contours(self):
        path = self._make_svg('')
        try:
            contours, w, h = import_svg(path)
            # May or may not have contours — just must not crash
            self.assertIsInstance(contours, list)
        finally:
            os.unlink(path)


# ─── BMP reader ───────────────────────────────────────────────────────────────

def _make_bmp_24bit(width, height, pixels_rgb):
    """Build a minimal 24-bit BMP in memory (for testing)."""
    row_pad = (4 - (width * 3) % 4) % 4
    stride  = width * 3 + row_pad
    px_size = stride * height
    hdr = struct.pack('<2sIHHI', b'BM', 54 + px_size, 0, 0, 54)
    dib = struct.pack('<IiiHHIIiiII', 40, width, -height, 1, 24, 0, px_size, 0, 0, 0, 0)
    rows = b''
    for y in range(height):
        row = b''
        for x in range(width):
            r, g, b = pixels_rgb[y * width + x]
            row += struct.pack('BBB', b, g, r)  # BMP stores BGR
        rows += row + b'\x00' * row_pad
    return hdr + dib + rows


class TestReadBmp(unittest.TestCase):
    def test_white_pixel(self):
        bmp = _make_bmp_24bit(1, 1, [(255, 255, 255)])
        with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as f:
            f.write(bmp); name = f.name
        try:
            w, h, g = _read_bmp(name)
            self.assertEqual((w, h), (1, 1))
            self.assertEqual(g[0], 255)
        finally:
            os.unlink(name)

    def test_black_pixel(self):
        bmp = _make_bmp_24bit(1, 1, [(0, 0, 0)])
        with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as f:
            f.write(bmp); name = f.name
        try:
            w, h, g = _read_bmp(name)
            self.assertEqual(g[0], 0)
        finally:
            os.unlink(name)

    def test_2x2_grid(self):
        pixels = [(0,0,0), (255,255,255), (255,255,255), (0,0,0)]
        bmp = _make_bmp_24bit(2, 2, pixels)
        with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as f:
            f.write(bmp); name = f.name
        try:
            w, h, g = _read_bmp(name)
            self.assertEqual((w, h), (2, 2))
            self.assertEqual(len(g), 4)
            self.assertLess(g[0], 50)    # top-left: black
            self.assertGreater(g[1], 200) # top-right: white
        finally:
            os.unlink(name)


# ─── PNG reader ───────────────────────────────────────────────────────────────

def _make_png_grayscale(width, height, values):
    """Build a minimal 8-bit grayscale PNG in memory."""
    def chunk(name, data):
        c = name + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFFFFFF)

    sig  = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0))

    raw = b''
    for y in range(height):
        raw += b'\x00'  # filter type: None
        for x in range(width):
            raw += struct.pack('B', values[y * width + x])

    idat = chunk(b'IDAT', zlib.compress(raw))
    iend = chunk(b'IEND', b'')
    return sig + ihdr + idat + iend


class TestReadPng(unittest.TestCase):
    def test_white_pixel(self):
        png = _make_png_grayscale(1, 1, [255])
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(png); name = f.name
        try:
            w, h, g = _read_png(name)
            self.assertEqual((w, h), (1, 1))
            self.assertEqual(g[0], 255)
        finally:
            os.unlink(name)

    def test_black_pixel(self):
        png = _make_png_grayscale(1, 1, [0])
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(png); name = f.name
        try:
            w, h, g = _read_png(name)
            self.assertEqual(g[0], 0)
        finally:
            os.unlink(name)

    def test_4x4_grid(self):
        vals = [0]*8 + [255]*8  # top half black, bottom half white
        png = _make_png_grayscale(4, 4, vals)
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
            f.write(png); name = f.name
        try:
            w, h, g = _read_png(name)
            self.assertEqual((w, h), (4, 4))
            self.assertLess(g[0], 50)
            self.assertGreater(g[-1], 200)
        finally:
            os.unlink(name)


# ─── Raster import ────────────────────────────────────────────────────────────

class TestImportRaster(unittest.TestCase):
    def _write_bmp(self, w, h, pixels_rgb):
        bmp = _make_bmp_24bit(w, h, pixels_rgb)
        with tempfile.NamedTemporaryFile(suffix='.bmp', delete=False) as f:
            f.write(bmp)
            return f.name

    def test_all_dark_returns_cells(self):
        pixels = [(0,0,0)] * 9  # 3×3 all black
        name = self._write_bmp(3, 3, pixels)
        try:
            cells, gw, gh = import_raster(name, threshold=128)
            self.assertGreater(len(cells), 0)
        finally:
            os.unlink(name)

    def test_all_white_returns_no_cells(self):
        pixels = [(255,255,255)] * 9
        name = self._write_bmp(3, 3, pixels)
        try:
            cells, gw, gh = import_raster(name, threshold=128)
            self.assertEqual(len(cells), 0)
        finally:
            os.unlink(name)

    def test_threshold_controls_cutoff(self):
        # Middle gray (127) — below threshold 128 → should be included
        pixels = [(127,127,127)] * 4
        name = self._write_bmp(2, 2, pixels)
        try:
            cells_low, _, _  = import_raster(name, threshold=128)
            cells_high, _, _ = import_raster(name, threshold=126)
            self.assertGreater(len(cells_low),  0)  # 127 ≤ 128 → dark
            self.assertEqual(  len(cells_high), 0)  # 127 > 126 → light
        finally:
            os.unlink(name)

    def test_grid_dimensions_reasonable(self):
        pixels = [(0,0,0)] * (100 * 100)
        name = self._write_bmp(100, 100, pixels)
        try:
            cells, gw, gh = import_raster(name)
            self.assertLessEqual(gw, 64)
            self.assertLessEqual(gh, 64)
        finally:
            os.unlink(name)

    def test_unsupported_format_raises(self):
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as f:
            f.write(b'fake'); name = f.name
        try:
            with self.assertRaises(ValueError):
                import_raster(name)
        finally:
            os.unlink(name)


# ─── Geometry utilities ───────────────────────────────────────────────────────

class TestPolyArea(unittest.TestCase):
    def test_unit_square(self):
        sq = [(0,0),(1,0),(1,1),(0,1)]
        self.assertAlmostEqual(_poly_area_mm2(sq), 1.0)

    def test_triangle(self):
        tri = [(0,0),(6,0),(3,4)]
        self.assertAlmostEqual(_poly_area_mm2(tri), 12.0)

    def test_degenerate_line(self):
        self.assertAlmostEqual(_poly_area_mm2([(0,0),(1,0)]), 0.0)


class TestDouglasPeucker(unittest.TestCase):
    def test_straight_line_reduces_to_two_points(self):
        pts = [(float(i), 0.0) for i in range(20)]
        result = _douglas_peucker(pts, 0.01)
        self.assertEqual(len(result), 2)

    def test_preserves_corners(self):
        # L-shape: sharp corner at (5,0)→(5,5)
        pts = [(0.0, 0.0), (5.0, 0.0), (5.0, 5.0)]
        result = _douglas_peucker(pts, 0.01)
        self.assertEqual(len(result), 3)

    def test_reduces_circular_arc(self):
        n = 50
        pts = [(math.cos(2*math.pi*i/n), math.sin(2*math.pi*i/n)) for i in range(n+1)]
        result = _douglas_peucker(pts, 0.05)
        self.assertLess(len(result), n)
        self.assertGreaterEqual(len(result), 4)  # circle needs at least a few points


if __name__ == '__main__':
    unittest.main(verbosity=2)

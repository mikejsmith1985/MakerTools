#!/usr/bin/env python3
"""
MakerTools Icon Generator
Creates 16x16 and 32x32 PNG icons for PathMaker and TextureForge.
Run from MakerTools directory: python generate_icons.py
"""

import os
import math
import struct
import zlib


# ---------------------------------------------------------------------------
# Colours
# ---------------------------------------------------------------------------
PM_BG  = (29,  78, 216, 255)   # PathMaker   — blue
PM_HL  = (147, 197, 253, 255)  # PathMaker   — light blue accent
TF_BG  = (103,  65, 217, 255)  # TextureForge — purple
TF_HL  = (196, 181, 253, 255)  # TextureForge — light purple accent
WHITE  = (255, 255, 255, 255)
LGRAY  = (210, 210, 215, 255)
GOLD   = (251, 191,  36, 255)
TRANS  = (  0,   0,   0,   0)

WS = 64  # working canvas size; will be downscaled to 32 and 16


# ---------------------------------------------------------------------------
# PNG encoder
# ---------------------------------------------------------------------------
def _clamp(v):
    return max(0, min(255, int(round(v))))


def make_png(w, h, pixels):
    """Return raw PNG bytes from a list of (r,g,b,a) tuples, row-major."""
    def chunk(tag, data):
        c = tag + data
        return struct.pack('>I', len(data)) + c + struct.pack('>I', zlib.crc32(c) & 0xFFFF_FFFF)

    raw = b''.join(
        b'\x00' + b''.join(
            struct.pack('BBBB', _clamp(p[0]), _clamp(p[1]), _clamp(p[2]), _clamp(p[3]))
            for p in pixels[y * w:(y + 1) * w]
        )
        for y in range(h)
    )
    return (
        b'\x89PNG\r\n\x1a\n'
        + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
        + chunk(b'IDAT', zlib.compress(raw, 9))
        + chunk(b'IEND', b'')
    )


# ---------------------------------------------------------------------------
# Drawing canvas
# ---------------------------------------------------------------------------
class Canvas:
    def __init__(self, w, h):
        self.w, self.h = w, h
        self.px = [[0, 0, 0, 0] for _ in range(w * h)]

    def _i(self, x, y):
        return y * self.w + x

    def _over(self, i, r, g, b, a):
        """Alpha-composite (r,g,b,a) over existing pixel."""
        if not (0 <= i < len(self.px)) or a == 0:
            return
        bg = self.px[i]
        if a == 255:
            self.px[i] = [r, g, b, 255]
            return
        fa = a / 255
        ba = bg[3] / 255
        oa = fa + ba * (1 - fa)
        if oa < 1e-6:
            return
        self.px[i] = [
            _clamp((r * fa + bg[0] * ba * (1 - fa)) / oa),
            _clamp((g * fa + bg[1] * ba * (1 - fa)) / oa),
            _clamp((b * fa + bg[2] * ba * (1 - fa)) / oa),
            _clamp(oa * 255),
        ]

    # -- Primitives ----------------------------------------------------------

    def fill(self, c):
        r, g, b, a = c
        for i in range(len(self.px)):
            self.px[i] = [r, g, b, a]

    def set_pixel(self, x, y, c, alpha=255):
        if 0 <= x < self.w and 0 <= y < self.h:
            r, g, b, a = c
            self._over(self._i(x, y), r, g, b, min(a, alpha))

    def rect(self, x, y, w, h, c, rx=0):
        r, g, b, a = c
        x, y, w, h = int(x), int(y), int(w), int(h)
        for py in range(max(0, y), min(self.h, y + h)):
            for px in range(max(0, x), min(self.w, x + w)):
                if rx:
                    lx, ly = px - x, py - y
                    if lx < rx and ly < rx and math.hypot(lx - rx + 0.5, ly - rx + 0.5) > rx:
                        continue
                    if lx >= w - rx and ly < rx and math.hypot(lx - (w - rx) + 0.5, ly - rx + 0.5) > rx:
                        continue
                    if lx < rx and ly >= h - rx and math.hypot(lx - rx + 0.5, ly - (h - rx) + 0.5) > rx:
                        continue
                    if lx >= w - rx and ly >= h - rx and math.hypot(lx - (w - rx) + 0.5, ly - (h - rx) + 0.5) > rx:
                        continue
                self._over(self._i(px, py), r, g, b, a)

    def circle(self, cx, cy, r, c, hollow=False, thick=2.0):
        cr, cg, cb, ca = c
        for py in range(max(0, int(cy - r) - 1), min(self.h, int(cy + r) + 2)):
            for px in range(max(0, int(cx - r) - 1), min(self.w, int(cx + r) + 2)):
                d = math.hypot(px + 0.5 - cx, py + 0.5 - cy)
                if hollow:
                    dt = abs(d - r)
                    if dt < thick:
                        aa = _clamp((thick - dt + 0.5) * 255)
                        self._over(self._i(px, py), cr, cg, cb, min(ca, aa))
                else:
                    if d < r:
                        aa = _clamp((r - d + 0.5) * 255)
                        self._over(self._i(px, py), cr, cg, cb, min(ca, aa))

    def line(self, x0, y0, x1, y1, thick, c):
        cr, cg, cb, ca = c
        dx, dy = x1 - x0, y1 - y0
        L = math.hypot(dx, dy)
        if L < 1e-6:
            return
        bx0 = max(0, int(min(x0, x1) - thick) - 1)
        bx1 = min(self.w, int(max(x0, x1) + thick) + 2)
        by0 = max(0, int(min(y0, y1) - thick) - 1)
        by1 = min(self.h, int(max(y0, y1) + thick) + 2)
        for py in range(by0, by1):
            for px in range(bx0, bx1):
                t = max(0.0, min(1.0, ((px + 0.5 - x0) * dx + (py + 0.5 - y0) * dy) / (L * L)))
                d = math.hypot(px + 0.5 - (x0 + t * dx), py + 0.5 - (y0 + t * dy))
                if d < thick:
                    aa = _clamp((thick - d + 0.5) * 255)
                    self._over(self._i(px, py), cr, cg, cb, min(ca, aa))

    def poly(self, pts, c):
        cr, cg, cb, ca = c
        if len(pts) < 3:
            return
        miny = max(0, int(min(p[1] for p in pts)))
        maxy = min(self.h, int(max(p[1] for p in pts)) + 2)
        n = len(pts)
        for py in range(miny, maxy):
            xs = []
            for i in range(n):
                ax, ay = pts[i]
                bx, by = pts[(i + 1) % n]
                if (ay <= py < by) or (by <= py < ay):
                    if ay != by:
                        xs.append(ax + (py - ay) * (bx - ax) / (by - ay))
            xs.sort()
            for k in range(0, len(xs) - 1, 2):
                for px in range(max(0, int(xs[k])), min(self.w, int(xs[k + 1]) + 1)):
                    self._over(self._i(px, py), cr, cg, cb, ca)

    def arrow_right(self, cx, cy, length, head, thick, c):
        """Horizontal right-pointing arrow centred at (cx, cy)."""
        x0, x1 = cx - length // 2, cx + length // 2 - head
        self.line(x0, cy, x1, cy, thick, c)
        self.poly([(x1, cy - head), (x1, cy + head), (cx + length // 2, cy)], c)

    def arrow_left(self, cx, cy, length, head, thick, c):
        x0, x1 = cx + length // 2, cx - length // 2 + head
        self.line(x0, cy, x1, cy, thick, c)
        self.poly([(x1, cy - head), (x1, cy + head), (cx - length // 2, cy)], c)

    # -- Output --------------------------------------------------------------

    def to_png(self):
        return make_png(self.w, self.h, [tuple(p) for p in self.px])

    def scaled(self, nw, nh):
        sx, sy = self.w / nw, self.h / nh
        out = Canvas(nw, nh)
        for ny in range(nh):
            for nx in range(nw):
                x0 = int(nx * sx);  x1 = max(x0 + 1, int((nx + 1) * sx))
                y0 = int(ny * sy);  y1 = max(y0 + 1, int((ny + 1) * sy))
                rs = gs = bs = as_ = cnt = 0
                for ssy in range(y0, min(y1, self.h)):
                    for ssx in range(x0, min(x1, self.w)):
                        p = self.px[ssy * self.w + ssx]
                        rs += p[0]; gs += p[1]; bs += p[2]; as_ += p[3]; cnt += 1
                if cnt:
                    out.px[ny * nw + nx] = [rs // cnt, gs // cnt, bs // cnt, as_ // cnt]
        return out


# ---------------------------------------------------------------------------
# Icon drawing helpers
# ---------------------------------------------------------------------------
S = 64

def s(v):
    """Scale a design value (designed for 64px) to the actual canvas."""
    return v  # canvas IS 64px; helper kept for readability


def gear(c, cx, cy, outer_r, inner_r, teeth, tooth_h, tooth_w, color):
    """Draw a gear polygon."""
    pts = []
    for i in range(teeth * 2):
        angle = math.pi / teeth * i - math.pi / 2
        r = outer_r + tooth_h if i % 2 == 0 else outer_r
        pts.append((cx + math.cos(angle) * r, cy + math.sin(angle) * r))
    c.poly(pts, color)
    c.circle(cx, cy, inner_r, TF_BG if color == WHITE else PM_BG)


# ---------------------------------------------------------------------------
# Individual icon draw functions — all return a 64×64 Canvas
# ---------------------------------------------------------------------------

def draw_stamp_texture():
    """Purple BG + 3×3 grid of white rounded squares = knurl/texture stamp."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, TF_BG, rx=8)

    sq, gap = 14, 4
    total = 3 * sq + 2 * gap   # 50
    start = (S - total) // 2    # 7
    for row in range(3):
        for col in range(3):
            x = start + col * (sq + gap)
            y = start + row * (sq + gap)
            c.rect(x, y, sq, sq, WHITE, rx=3)

    # Small downward stamp arrow at the bottom-right corner
    c.poly([(47, 55), (53, 55), (50, 60)], TF_HL)
    return c


def draw_image_texture():
    """Purple BG + photo frame + image scene + texture grid overlay."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, TF_BG, rx=8)

    # Photo frame (white border, then carve out the inside)
    c.rect(7, 7, 34, 28, WHITE, rx=3)   # outer
    c.rect(10, 10, 28, 22, TF_BG)        # inner clear

    # Simple landscape inside: mountains + sun
    c.poly([(10, 32), (21, 16), (31, 32)], TF_HL)      # mountain left
    c.poly([(21, 32), (32, 18), (38, 32)], WHITE)       # mountain right
    c.circle(31, 14, 4, GOLD)                            # sun

    # Arrow: image → texture
    c.arrow_right(49, 22, 14, 5, 2.5, WHITE)

    # Tiny texture grid bottom-right
    gx, gy, gs, gg = 35, 38, 6, 2
    for row in range(3):
        for col in range(3):
            c.rect(gx + col * (gs + gg), gy + row * (gs + gg), gs, gs, TF_HL, rx=1)

    return c


def draw_generate_cam():
    """Blue BG + part outline + raster toolpath lines."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, PM_BG, rx=8)

    # Part silhouette (simplified L-shape, white outline)
    part_pts = [(10, 14), (40, 14), (40, 30), (28, 30), (28, 50), (10, 50)]
    c.poly(part_pts, PM_HL)
    # Bright outline
    n = len(part_pts)
    for i in range(n):
        x0, y0 = part_pts[i]
        x1, y1 = part_pts[(i + 1) % n]
        c.line(x0, y0, x1, y1, 1.5, WHITE)

    # Raster toolpath lines (white, inside the L-shape roughly)
    for yi, y in enumerate(range(18, 49, 7)):
        if y <= 30:
            if yi % 2 == 0:
                c.line(12, y, 38, y, 1.5, GOLD)
            else:
                c.line(38, y, 12, y, 1.5, GOLD)
        else:
            if yi % 2 == 0:
                c.line(12, y, 26, y, 1.5, GOLD)
            else:
                c.line(26, y, 12, y, 1.5, GOLD)

    # Small CNC bit icon top-right
    c.rect(47, 8, 7, 18, LGRAY, rx=2)  # shank
    c.poly([(47, 26), (54, 26), (50, 34)], LGRAY)  # tip

    return c


def draw_import_tool():
    """Blue BG + endmill + chain-link/URL import arrow."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, PM_BG, rx=8)

    # Endmill (centred left-ish)
    ex, ey = 14, 8
    c.rect(ex + 4, ey, 10, 8, LGRAY, rx=2)     # shank (narrow)
    c.rect(ex, ey + 8, 18, 22, WHITE, rx=2)     # cutter body
    # Flute lines
    c.line(ex + 4, ey + 10, ex + 14, ey + 28, 1.5, PM_HL)
    c.line(ex + 9, ey + 10, ex + 16, ey + 26, 1.0, PM_HL)
    # V-tip
    c.poly([(ex, ey + 30), (ex + 18, ey + 30), (ex + 9, ey + 40)], WHITE)

    # Download arrow (right side, pointing down = "import")
    ax = 44
    c.line(ax, 12, ax, 44, 3.0, GOLD)
    c.poly([(ax - 8, 38), (ax + 8, 38), (ax, 50)], GOLD)

    # Small link icon (chain) above the arrow
    c.circle(ax - 4, 8, 5, PM_HL, hollow=True, thick=2)
    c.circle(ax + 4, 8, 5, WHITE, hollow=True, thick=2)

    return c


def draw_manage_tools():
    """Blue BG + tool list (3 rows with endmill mini-icons)."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, PM_BG, rx=8)

    rows = [14, 28, 42]
    for y in rows:
        # Mini endmill
        c.rect(7, y - 7, 5, 4, LGRAY, rx=1)   # shank
        c.rect(5, y - 3, 9, 8, WHITE, rx=1)    # body
        c.poly([(5, y + 5), (14, y + 5), (9, y + 9)], WHITE)  # tip

        # Separator line
        c.line(18, y, 56, y, 2.0, WHITE)
        c.line(18, y + 4, 48, y + 4, 1.5, PM_HL)   # detail line

    return c


def draw_add_material():
    """Blue BG + isometric material block + plus sign."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, PM_BG, rx=8)

    # Isometric slab (top face + front face + right face)
    cx, cy = 28, 30
    dx, dy = 12, 7   # half-axes for isometric

    top   = [(cx, cy - dy), (cx + dx, cy), (cx, cy + dy), (cx - dx, cy)]
    front = [(cx - dx, cy), (cx, cy + dy), (cx, cy + dy + 14), (cx - dx, cy + 14)]
    right = [(cx, cy + dy), (cx + dx, cy), (cx + dx, cy + 14), (cx, cy + dy + 14)]

    c.poly(top,   WHITE)
    c.poly(front, PM_HL)
    c.poly(right, LGRAY)

    # Plus sign (top right)
    px_, py_ = 48, 12
    c.line(px_ - 7, py_, px_ + 7, py_, 3.5, GOLD)
    c.line(px_, py_ - 7, px_, py_ + 7, 3.5, GOLD)

    return c


def draw_two_sided():
    """Blue BG + part rectangle + bidirectional flip arrows."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, PM_BG, rx=8)

    # Part rectangle
    c.rect(14, 22, 36, 20, WHITE, rx=3)
    # Hatch lines to show it's a solid part
    for x in range(17, 48, 5):
        c.line(x, 22, x - 4, 42, 1.0, PM_HL)

    # Top arrow pointing left  (Side A → flip)
    c.arrow_left(32, 12, 28, 5, 2.5, GOLD)
    # Bottom arrow pointing right (Side B after flip)
    c.arrow_right(32, 52, 28, 5, 2.5, GOLD)

    # Flip symbol (small ↕ line)
    c.line(32, 14, 32, 50, 1.0, (255, 255, 255, 80))

    return c


def draw_settings():
    """Blue BG + white gear."""
    c = Canvas(S, S)
    c.rect(0, 0, S, S, PM_BG, rx=8)

    cx, cy = 32, 32
    gear(c, cx, cy, outer_r=18, inner_r=10, teeth=8, tooth_h=5, tooth_w=6, color=WHITE)
    # Centre hole
    c.circle(cx, cy, 6, PM_BG)
    # Small dot in centre
    c.circle(cx, cy, 2, PM_HL)

    return c


# ---------------------------------------------------------------------------
# Build resource folder layout and save PNGs
# ---------------------------------------------------------------------------
ICONS = [
    # (subfolder_relative_to_addon, draw_function)
    ('TextureForge/resources/StampTexture',  draw_stamp_texture),
    ('TextureForge/resources/ImageTexture',  draw_image_texture),
    ('PathMaker/resources/GenerateCAM',      draw_generate_cam),
    ('PathMaker/resources/ImportTool',       draw_import_tool),
    ('PathMaker/resources/ManageTools',      draw_manage_tools),
    ('PathMaker/resources/AddMaterial',      draw_add_material),
    ('PathMaker/resources/TwoSided',         draw_two_sided),
    ('PathMaker/resources/Settings',         draw_settings),
]


def main():
    base = os.path.dirname(os.path.abspath(__file__))

    for rel_dir, draw_fn in ICONS:
        out_dir = os.path.join(base, rel_dir)
        os.makedirs(out_dir, exist_ok=True)

        canvas64 = draw_fn()

        for size, name in [(32, '32x32.png'), (16, '16x16.png')]:
            scaled = canvas64.scaled(size, size)
            path = os.path.join(out_dir, name)
            with open(path, 'wb') as f:
                f.write(scaled.to_png())
            print(f'  wrote {path}')

    print('\nAll icons generated.')


if __name__ == '__main__':
    main()

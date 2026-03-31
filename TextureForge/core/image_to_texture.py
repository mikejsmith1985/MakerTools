"""
ReliefForge — Image-to-Texture: Import SVG, PNG, or BMP as an emboss texture.

SVG files:  Parsed as proper vector paths (all SVG path commands supported,
            plus <rect>, <circle>, <ellipse>, <polygon>, <polyline>, <line>).
            Curves are approximated with polylines.

PNG / BMP:  Decoded with Python's stdlib (no Pillow required).
            Each dark pixel in the downsampled grid becomes a small raised or
            cut square — a "pixel stamp" effect that looks great on both printed
            and milled parts.

Workflow overview:
  1. import_svg()  / import_raster()   → geometry in source coordinates
  2. apply_image_texture_to_face()     → scales to face, creates sketch, embosses

All coordinates are in MILLIMETRES inside this module.
Fusion 360 API calls convert to centimetres (÷10) at the point of use.
"""

import math
import os
import re
import struct
import zlib
import xml.etree.ElementTree as ET

# ─── SVG: Bézier and arc helpers ─────────────────────────────────────────────

def _cubic_bezier(p0, p1, p2, p3, n=12):
    """Approximate a cubic Bézier curve with n+1 sample points."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = u**3*p0[0] + 3*u**2*t*p1[0] + 3*u*t**2*p2[0] + t**3*p3[0]
        y = u**3*p0[1] + 3*u**2*t*p1[1] + 3*u*t**2*p2[1] + t**3*p3[1]
        pts.append((x, y))
    return pts


def _quadratic_bezier(p0, p1, p2, n=8):
    """Approximate a quadratic Bézier curve with n+1 sample points."""
    pts = []
    for i in range(n + 1):
        t = i / n
        u = 1.0 - t
        x = u**2*p0[0] + 2*u*t*p1[0] + t**2*p2[0]
        y = u**2*p0[1] + 2*u*t*p1[1] + t**2*p2[1]
        pts.append((x, y))
    return pts


def _svg_arc(x0, y0, rx, ry, phi_deg, large_arc, sweep, x1, y1, n=16):
    """Convert an SVG elliptical arc segment to a polyline (SVG spec §F.6.5)."""
    if rx == 0 or ry == 0 or (x0 == x1 and y0 == y1):
        return [(x0, y0), (x1, y1)]

    phi = math.radians(phi_deg)
    cp, sp = math.cos(phi), math.sin(phi)
    rx, ry = abs(rx), abs(ry)

    dx2, dy2 = (x0 - x1) / 2, (y0 - y1) / 2
    x1p =  cp * dx2 + sp * dy2
    y1p = -sp * dx2 + cp * dy2

    x1ps, y1ps, rxs, rys = x1p**2, y1p**2, rx**2, ry**2
    lam = x1ps / rxs + y1ps / rys
    if lam > 1:
        sq = math.sqrt(lam)
        rx, ry = rx * sq, ry * sq
        rxs, rys = rx**2, ry**2

    num = max(0.0, rxs * rys - rxs * y1ps - rys * x1ps)
    den = rxs * y1ps + rys * x1ps
    sq  = math.sqrt(num / den) if den else 0.0
    sign = -1 if large_arc == sweep else 1
    cxp =  sign * sq * rx * y1p / ry
    cyp = -sign * sq * ry * x1p / rx

    cx = cp * cxp - sp * cyp + (x0 + x1) / 2
    cy = sp * cxp + cp * cyp + (y0 + y1) / 2

    def _angle(ux, uy, vx, vy):
        d = math.sqrt(ux**2 + uy**2) * math.sqrt(vx**2 + vy**2)
        if d == 0:
            return 0.0
        a = math.acos(max(-1.0, min(1.0, (ux*vx + uy*vy) / d)))
        return -a if (ux * vy - uy * vx) < 0 else a

    theta1 = _angle(1, 0, (x1p - cxp) / rx, (y1p - cyp) / ry)
    dtheta = _angle((x1p - cxp) / rx, (y1p - cyp) / ry,
                    (-x1p - cxp) / rx, (-y1p - cyp) / ry)

    if not sweep and dtheta > 0:
        dtheta -= 2 * math.pi
    if sweep and dtheta < 0:
        dtheta += 2 * math.pi

    pts = []
    for i in range(n + 1):
        theta = theta1 + (i / n) * dtheta
        xp = rx * math.cos(theta)
        yp = ry * math.sin(theta)
        pts.append((cp * xp - sp * yp + cx, sp * xp + cp * yp + cy))
    return pts


# ─── SVG: Path `d` parser ────────────────────────────────────────────────────

_PATH_TOK = re.compile(
    r'[MmLlHhVvCcSsQqTtAaZz]'
    r'|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?'
)


def _parse_svg_path(d):
    """
    Parse SVG `d` attribute → list of subpaths.
    Each subpath is a list of (x, y) tuples in SVG user units.
    Curves are flattened to polylines.
    """
    tokens = _PATH_TOK.findall(d)
    subpaths, current = [], []
    x = y = sx = sy = 0.0
    lc2x = lc2y = None  # reflected control point for S/T
    i, cmd = 0, 'M'

    def _f(n):
        nonlocal i
        v = [float(tokens[i + k]) for k in range(n)]
        i += n
        return v

    while i < len(tokens):
        tok = tokens[i]
        if tok.isalpha():
            if tok.upper() == 'Z':
                # Z has no arguments — process immediately
                if current:
                    current.append((sx, sy))
                    subpaths.append(current)
                    current = []
                x, y = sx, sy
                i += 1
                lc2x = lc2y = None
                continue
            cmd = tok
            i += 1
            if cmd.upper() not in ('S', 's', 'T', 't'):
                lc2x = lc2y = None
            continue

        rel = cmd.islower()
        c   = cmd.upper()

        if c == 'M':
            nx, ny = _f(2)
            if rel: nx += x; ny += y
            if current: subpaths.append(current)
            current = [(nx, ny)]
            x, y = nx, ny; sx, sy = x, y
            cmd = 'l' if rel else 'L'

        elif c == 'L':
            nx, ny = _f(2)
            if rel: nx += x; ny += y
            current.append((nx, ny)); x, y = nx, ny

        elif c == 'H':
            nx = float(tokens[i]); i += 1
            if rel: nx += x
            current.append((nx, y)); x = nx

        elif c == 'V':
            ny = float(tokens[i]); i += 1
            if rel: ny += y
            current.append((x, ny)); y = ny

        elif c == 'C':
            ax, ay, bx, by, nx, ny = _f(6)
            if rel: ax+=x; ay+=y; bx+=x; by+=y; nx+=x; ny+=y
            current.extend(_cubic_bezier((x,y),(ax,ay),(bx,by),(nx,ny))[1:])
            lc2x, lc2y = bx, by; x, y = nx, ny

        elif c == 'S':
            bx, by, nx, ny = _f(4)
            if rel: bx+=x; by+=y; nx+=x; ny+=y
            ax = 2*x - (lc2x if lc2x is not None else x)
            ay = 2*y - (lc2y if lc2y is not None else y)
            current.extend(_cubic_bezier((x,y),(ax,ay),(bx,by),(nx,ny))[1:])
            lc2x, lc2y = bx, by; x, y = nx, ny

        elif c == 'Q':
            ax, ay, nx, ny = _f(4)
            if rel: ax+=x; ay+=y; nx+=x; ny+=y
            current.extend(_quadratic_bezier((x,y),(ax,ay),(nx,ny))[1:])
            lc2x, lc2y = ax, ay; x, y = nx, ny

        elif c == 'T':
            nx, ny = _f(2)
            if rel: nx += x; ny += y
            ax = 2*x - (lc2x if lc2x is not None else x)
            ay = 2*y - (lc2y if lc2y is not None else y)
            current.extend(_quadratic_bezier((x,y),(ax,ay),(nx,ny))[1:])
            lc2x, lc2y = ax, ay; x, y = nx, ny

        elif c == 'A':
            rx_, ry_, xr, la, sw, nx, ny = _f(7)
            if rel: nx += x; ny += y
            current.extend(_svg_arc(x, y, rx_, ry_, xr, int(la), int(sw), nx, ny)[1:])
            x, y = nx, ny

        if c not in ('C','S','Q','T'):
            lc2x = lc2y = None

    if current:
        subpaths.append(current)
    return subpaths


# ─── SVG: Transform matrix ────────────────────────────────────────────────────

def _identity():
    return [1,0,0, 0,1,0, 0,0,1]


def _mat_mul(A, B):
    C = [0.0] * 9
    for r in range(3):
        for c in range(3):
            for k in range(3):
                C[r*3+c] += A[r*3+k] * B[k*3+c]
    return C


def _parse_transform(s):
    """Parse an SVG `transform` attribute → 3×3 row-major matrix list."""
    if not s:
        return _identity()
    m = _identity()
    for match in re.finditer(r'(\w+)\s*\(([^)]*)\)', s):
        fn   = match.group(1)
        args = [float(v) for v in re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?',
                                              match.group(2))]
        if fn == 'translate':
            tx = args[0]; ty = args[1] if len(args) > 1 else 0.0
            t = [1,0,tx,  0,1,ty,  0,0,1]
        elif fn == 'scale':
            sx = args[0]; sy = args[1] if len(args) > 1 else args[0]
            t = [sx,0,0,  0,sy,0,  0,0,1]
        elif fn == 'rotate':
            a = math.radians(args[0]); ca, sa = math.cos(a), math.sin(a)
            if len(args) >= 3:
                cx, cy = args[1], args[2]
                t = _mat_mul([1,0,cx, 0,1,cy, 0,0,1],
                    _mat_mul([ca,-sa,0, sa,ca,0, 0,0,1],
                             [1,0,-cx, 0,1,-cy, 0,0,1]))
            else:
                t = [ca,-sa,0, sa,ca,0, 0,0,1]
        elif fn == 'skewX':
            t = [1, math.tan(math.radians(args[0])), 0, 0,1,0, 0,0,1]
        elif fn == 'skewY':
            t = [1,0,0, math.tan(math.radians(args[0])),1,0, 0,0,1]
        elif fn == 'matrix' and len(args) >= 6:
            a, b, c, d, e, f = args[:6]
            t = [a, c, e,  b, d, f,  0,0,1]
        else:
            continue
        m = _mat_mul(m, t)
    return m


def _apply_transform(pts, m):
    return [(m[0]*x + m[1]*y + m[2], m[3]*x + m[4]*y + m[5]) for x, y in pts]


# ─── SVG: Element traversal ───────────────────────────────────────────────────

def _tag(el):
    return el.tag.split('}')[-1] if '}' in el.tag else el.tag


def _get_viewbox(root):
    vb = root.get('viewBox') or root.get('viewbox')
    if vb:
        vals = [float(v) for v in re.split(r'[\s,]+', vb.strip()) if v]
        if len(vals) == 4:
            return vals
    w = float(re.sub(r'[^0-9.]', '', root.get('width',  '100')) or 100)
    h = float(re.sub(r'[^0-9.]', '', root.get('height', '100')) or 100)
    return [0.0, 0.0, w, h]


def _el_paths(el, parent_m):
    """
    Recursively extract closed/open path polygons from an SVG element.
    Returns list of [(x, y), …] in transformed SVG user-unit space.
    """
    m   = _mat_mul(parent_m, _parse_transform(el.get('transform', '')))
    tag = _tag(el)
    out = []

    if tag == 'path':
        for sp in _parse_svg_path(el.get('d', '')):
            if len(sp) >= 2:
                out.append(_apply_transform(sp, m))

    elif tag == 'rect':
        x  = float(el.get('x', 0)); y  = float(el.get('y', 0))
        w  = float(el.get('width',  0))
        h  = float(el.get('height', 0))
        if w > 0 and h > 0:
            pts = [(x,y),(x+w,y),(x+w,y+h),(x,y+h),(x,y)]
            out.append(_apply_transform(pts, m))

    elif tag == 'circle':
        cx = float(el.get('cx', 0)); cy = float(el.get('cy', 0))
        r  = float(el.get('r',  0))
        if r > 0:
            n  = max(24, int(2 * math.pi * r / 2))
            pts = [(cx + r*math.cos(2*math.pi*i/n),
                    cy + r*math.sin(2*math.pi*i/n)) for i in range(n+1)]
            out.append(_apply_transform(pts, m))

    elif tag == 'ellipse':
        cx = float(el.get('cx', 0)); cy = float(el.get('cy', 0))
        rx = float(el.get('rx', 0)); ry = float(el.get('ry', 0))
        if rx > 0 and ry > 0:
            n  = max(24, int(math.pi * (rx + ry) / 2))
            pts = [(cx + rx*math.cos(2*math.pi*i/n),
                    cy + ry*math.sin(2*math.pi*i/n)) for i in range(n+1)]
            out.append(_apply_transform(pts, m))

    elif tag == 'polygon':
        coords = [float(v) for v in re.split(r'[\s,]+', el.get('points','').strip()) if v]
        if len(coords) >= 4:
            pts = list(zip(coords[0::2], coords[1::2]))
            pts.append(pts[0])
            out.append(_apply_transform(pts, m))

    elif tag == 'polyline':
        coords = [float(v) for v in re.split(r'[\s,]+', el.get('points','').strip()) if v]
        if len(coords) >= 4:
            pts = list(zip(coords[0::2], coords[1::2]))
            out.append(_apply_transform(pts, m))

    elif tag == 'line':
        pts = [(float(el.get('x1',0)), float(el.get('y1',0))),
               (float(el.get('x2',0)), float(el.get('y2',0)))]
        out.append(_apply_transform(pts, m))

    if tag in ('g', 'svg', 'symbol', 'a', 'clipPath'):
        for child in el:
            out.extend(_el_paths(child, m))

    return out


# ─── SVG: Public importer ─────────────────────────────────────────────────────

def import_svg(filepath):
    """
    Parse an SVG file → list of path polygons in mm.

    SVG user units are treated as pixels (1 px = 0.264583 mm at 96 dpi).
    Returns (contours_mm, viewbox_w_mm, viewbox_h_mm).
    """
    PX_TO_MM = 0.264583  # 96 dpi

    tree = ET.parse(filepath)
    root = tree.getroot()
    vb   = _get_viewbox(root)
    vb_x, vb_y, vb_w, vb_h = vb

    # Shift origin, flip Y (SVG Y↓, Fusion Y↑)
    origin_m = [1,0,-vb_x,  0,1,-vb_y,  0,0,1]
    flip_m   = [1,0,0,       0,-1,vb_h,  0,0,1]
    base_m   = _mat_mul(flip_m, origin_m)

    contours_px = _el_paths(root, base_m)

    # Convert px → mm and filter degenerate paths
    contours_mm = []
    for c in contours_px:
        c_mm = [(x * PX_TO_MM, y * PX_TO_MM) for x, y in c]
        if len(c_mm) >= 2:
            contours_mm.append(c_mm)

    return contours_mm, vb_w * PX_TO_MM, vb_h * PX_TO_MM


# ─── PNG reader (pure stdlib) ─────────────────────────────────────────────────

def _read_png(filepath):
    """
    Minimal PNG → (width, height, flat_grayscale_list[0..255]).
    Handles 8/16-bit grayscale, RGB, RGBA, grayscale+alpha, indexed color.
    No external dependencies — uses stdlib zlib only.
    """
    with open(filepath, 'rb') as f:
        if f.read(8) != b'\x89PNG\r\n\x1a\n':
            raise ValueError('Not a valid PNG file.')

        width = height = bit_depth = color_type = interlace = 0
        palette = []  # for indexed color (type 3)
        idat = b''

        while True:
            hdr = f.read(8)
            if len(hdr) < 8:
                break
            length = struct.unpack('>I', hdr[:4])[0]
            ctype  = hdr[4:]
            data   = f.read(length)
            f.read(4)  # CRC

            if ctype == b'IHDR':
                width, height = struct.unpack('>II', data[:8])
                bit_depth, color_type, _, _, interlace = data[8], data[9], data[10], data[11], data[12]
            elif ctype == b'PLTE':
                palette = [(data[i], data[i+1], data[i+2]) for i in range(0, len(data), 3)]
            elif ctype == b'IDAT':
                idat += data
            elif ctype == b'IEND':
                break

    raw = zlib.decompress(idat)

    channels = {0:1, 2:3, 3:1, 4:2, 6:4}.get(color_type, 1)
    bytes_per_sample = (bit_depth + 7) // 8
    bpp    = channels * bytes_per_sample
    stride = width * bpp

    def paeth(a, b, c):
        p = a + b - c
        pa, pb, pc = abs(p-a), abs(p-b), abs(p-c)
        return a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)

    flat = bytearray()
    prev = bytearray(stride)

    for row in range(height):
        base = row * (stride + 1)
        ftype = raw[base]
        scan  = bytearray(raw[base+1: base+1+stride])

        if ftype == 1:   # Sub
            for i in range(bpp, stride):
                scan[i] = (scan[i] + scan[i - bpp]) & 0xFF
        elif ftype == 2:  # Up
            for i in range(stride):
                scan[i] = (scan[i] + prev[i]) & 0xFF
        elif ftype == 3:  # Average
            for i in range(stride):
                a = scan[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + (a + prev[i]) // 2) & 0xFF
        elif ftype == 4:  # Paeth
            for i in range(stride):
                a = scan[i - bpp] if i >= bpp else 0
                b = prev[i]
                c = prev[i - bpp] if i >= bpp else 0
                scan[i] = (scan[i] + paeth(a, b, c)) & 0xFF

        prev = scan
        flat.extend(scan)

    gray = []
    for i in range(width * height):
        base = i * bpp
        if color_type == 0:   # Grayscale
            v = struct.unpack('>H', flat[base:base+2])[0] if bit_depth == 16 else flat[base]
            gray.append(v * 255 // 65535 if bit_depth == 16 else v)
        elif color_type == 2:  # RGB
            gray.append((flat[base] + flat[base+1] + flat[base+2]) // 3)
        elif color_type == 3:  # Indexed
            idx = flat[base]
            r, g, b = palette[idx] if idx < len(palette) else (0,0,0)
            gray.append((r + g + b) // 3)
        elif color_type == 4:  # Grayscale+Alpha
            gray.append(flat[base])
        elif color_type == 6:  # RGBA
            gray.append((flat[base] + flat[base+1] + flat[base+2]) // 3)

    return width, height, gray


# ─── BMP reader (pure stdlib) ─────────────────────────────────────────────────

def _read_bmp(filepath):
    """
    Minimal BMP → (width, height, flat_grayscale_list[0..255]).
    Supports 1/4/8/24/32-bit uncompressed BMPs.
    """
    with open(filepath, 'rb') as f:
        data = f.read()

    if data[:2] != b'BM':
        raise ValueError('Not a valid BMP file.')

    px_offset = struct.unpack_from('<I', data, 10)[0]
    width     = struct.unpack_from('<i', data, 18)[0]
    height    = struct.unpack_from('<i', data, 22)[0]
    bit_count = struct.unpack_from('<H', data, 28)[0]

    flip   = height > 0  # positive height = bottom-up
    height = abs(height)
    px     = data[px_offset:]
    stride = ((bit_count * width + 31) // 32) * 4  # rows padded to 4 bytes

    gray = []
    for row in range(height):
        r = px[row * stride: row * stride + stride]
        for col in range(width):
            if bit_count == 24:
                gray.append((r[col*3] + r[col*3+1] + r[col*3+2]) // 3)
            elif bit_count == 32:
                gray.append((r[col*4] + r[col*4+1] + r[col*4+2]) // 3)
            elif bit_count == 8:
                gray.append(r[col])
            elif bit_count == 4:
                byte = r[col // 2]
                gray.append(((byte >> 4) if col % 2 == 0 else (byte & 0x0F)) * 17)
            elif bit_count == 1:
                gray.append(((r[col // 8] >> (7 - col % 8)) & 1) * 255)

    if flip:
        rows = [gray[r * width:(r+1) * width] for r in range(height)]
        gray = [v for row in reversed(rows) for v in row]

    return width, height, gray


# ─── Raster: downsample → dark-pixel cells ────────────────────────────────────

MAX_RASTER_DIM  = 64    # grid resolution cap (per axis)
MAX_RASTER_CELLS = 2000  # hard cap on total cells for Fusion performance


def import_raster(filepath, threshold=128):
    """
    Read a PNG or BMP image → list of (col, row) grid positions for dark pixels.

    Returns: (cells, grid_w, grid_h)
    The caller maps each cell → a small square in the Fusion sketch.
    """
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.png':
        w, h, gray = _read_png(filepath)
    elif ext in ('.bmp', '.dib'):
        w, h, gray = _read_bmp(filepath)
    else:
        raise ValueError(f'Unsupported raster format "{ext}". Use .png or .bmp')

    # Ceiling division so gw/gh always fit within MAX_RASTER_DIM
    scale = max(1, math.ceil(max(w, h) / MAX_RASTER_DIM))
    gw = max(1, w // scale)
    gh = max(1, h // scale)

    cells = []
    for gy in range(gh):
        for gx in range(gw):
            total = count = 0
            for dy in range(scale):
                for dx in range(scale):
                    px, py = gx * scale + dx, gy * scale + dy
                    if px < w and py < h:
                        total += gray[py * w + px]
                        count += 1
            if count and (total // count) <= threshold:
                cells.append((gx, gy))

    # Even-step trim if still too many
    if len(cells) > MAX_RASTER_CELLS:
        step  = len(cells) // MAX_RASTER_CELLS + 1
        cells = cells[::step][:MAX_RASTER_CELLS]

    return cells, gw, gh


# ─── Geometry utilities ───────────────────────────────────────────────────────

def _poly_area_mm2(pts):
    """Shoelace formula — area in the same units² as the coordinates."""
    n = len(pts)
    if n < 3:
        return 0.0
    a = 0.0
    for i in range(n):
        j = (i + 1) % n
        a += pts[i][0] * pts[j][1] - pts[j][0] * pts[i][1]
    return abs(a) / 2.0


def _douglas_peucker(pts, tol):
    """Ramer–Douglas–Peucker polyline simplification."""
    if len(pts) <= 2:
        return list(pts)

    def _pdist(pt, a, b):
        dx, dy = b[0]-a[0], b[1]-a[1]
        if dx == 0 and dy == 0:
            return math.hypot(pt[0]-a[0], pt[1]-a[1])
        t = max(0.0, min(1.0, ((pt[0]-a[0])*dx + (pt[1]-a[1])*dy) / (dx*dx+dy*dy)))
        return math.hypot(pt[0]-a[0]-t*dx, pt[1]-a[1]-t*dy)

    dmax, idx = 0.0, 0
    for i in range(1, len(pts)-1):
        d = _pdist(pts[i], pts[0], pts[-1])
        if d > dmax:
            dmax, idx = d, i

    if dmax > tol:
        l = _douglas_peucker(pts[:idx+1], tol)
        r = _douglas_peucker(pts[idx:],   tol)
        return l[:-1] + r
    return [pts[0], pts[-1]]


# ─── Fusion 360 integration ───────────────────────────────────────────────────

MAX_SVG_PATHS    = 150   # contour limit for performance
MAX_SVG_PTS      = 250   # points-per-path limit


def apply_image_texture_to_face(face, filepath, depth_mm, is_cut,
                                  pattern_width_mm=None,
                                  fit_mode='fit',
                                  threshold=128,
                                  min_feature_mm=0.5):
    """
    Apply an SVG, PNG, or BMP image as an Emboss texture on a Fusion 360 face.

    Parameters
    ----------
    face            : adsk.fusion.BRepFace  — target face
    filepath        : str — path to .svg / .png / .bmp
    depth_mm        : float — emboss/deboss depth in mm
    is_cut          : bool — True = deboss (cut), False = boss (raise)
    pattern_width_mm: float or None — desired pattern width on face;
                      None = scale to fill face (fit_mode='fit')
    fit_mode        : 'fit' | 'tile' — ignored if pattern_width_mm is given
    threshold       : int 0-255 — pixel darkness cutoff for raster images
    min_feature_mm  : float — drop SVG paths smaller than this (mm)

    Returns
    -------
    (emboss_feature, n_profiles, sketch)
    """
    import adsk.core
    import adsk.fusion

    app    = adsk.core.Application.get()
    design = adsk.fusion.Design.cast(app.activeProduct)
    rc     = design.rootComponent

    ext = os.path.splitext(filepath)[1].lower()

    # ── 1. Load source geometry ────────────────────────────────────────────────
    if ext == '.svg':
        contours_mm, src_w_mm, src_h_mm = import_svg(filepath)
        is_svg = True
    elif ext in ('.png', '.bmp', '.dib'):
        cells, grid_w, grid_h = import_raster(filepath, threshold)
        src_w_mm, src_h_mm = float(grid_w), float(grid_h)  # in cell units
        is_svg = False
    else:
        raise ValueError(f'Unsupported format "{ext}". Use .svg, .png, or .bmp')

    if is_svg and not contours_mm:
        raise RuntimeError(
            'No usable paths found in the SVG file.\n\n'
            'Make sure the SVG contains filled or stroked vector shapes '
            '(paths, rects, circles, polygons).\n'
            'Raster-embedded SVGs are not supported — export as plain SVG.'
        )

    # ── 2. Get face bounds in sketch space (cm) ────────────────────────────────
    sketch = rc.sketches.add(face)
    sketch.name = f'RF_img_{os.path.splitext(os.path.basename(filepath))[0]}'

    xf = sketch.transform.copy()
    xf.invert()

    xs, ys = [], []
    for v in face.vertices:
        lp = v.geometry.copy()
        lp.transformBy(xf)
        xs.append(lp.x); ys.append(lp.y)

    if not xs:
        sketch.deleteMe()
        raise RuntimeError('Could not read face vertex bounds.')

    fx_min, fx_max = min(xs), max(xs)
    fy_min, fy_max = min(ys), max(ys)
    face_w_cm = fx_max - fx_min   # Fusion internal units = cm
    face_h_cm = fy_max - fy_min

    depth_cm = depth_mm / 10.0

    # ── 3. Compute scale and offset ───────────────────────────────────────────
    if pattern_width_mm is not None:
        # User chose explicit width
        s_mm_per_mm = pattern_width_mm / src_w_mm  # uniform scale (mm→mm)
        img_w_cm = pattern_width_mm / 10.0
        img_h_cm = (src_h_mm * s_mm_per_mm) / 10.0
    elif fit_mode == 'fit' or True:
        # Scale uniformly to fill face (preserve aspect ratio)
        sx = (face_w_cm * 10.0) / src_w_mm   # mm per src-unit
        sy = (face_h_cm * 10.0) / src_h_mm
        s_mm_per_mm = min(sx, sy)
        img_w_cm = src_w_mm * s_mm_per_mm / 10.0
        img_h_cm = src_h_mm * s_mm_per_mm / 10.0

    # Center image on face
    off_x_cm = fx_min + (face_w_cm - img_w_cm) / 2.0
    off_y_cm = fy_min + (face_h_cm - img_h_cm) / 2.0

    def to_sketch_cm(src_x_mm, src_y_mm):
        """Map source mm coords → Fusion sketch cm coords."""
        return (off_x_cm + src_x_mm * s_mm_per_mm / 10.0,
                off_y_cm + src_y_mm * s_mm_per_mm / 10.0)

    # ── 4. Draw geometry into the sketch ──────────────────────────────────────
    lines_api = sketch.sketchCurves.sketchLines
    n_drawn   = 0

    if is_svg:
        # Filter tiny paths
        min_area = min_feature_mm ** 2 * 0.1
        kept = []
        for c in contours_mm[:MAX_SVG_PATHS]:
            if len(c) < 3:
                continue
            if _poly_area_mm2(c) < min_area:
                continue
            simp = _douglas_peucker(c, min_feature_mm * 0.3)
            if len(simp) >= 3:
                kept.append(simp[:MAX_SVG_PTS])

        for contour in kept:
            pts_cm = [to_sketch_cm(x, y) for x, y in contour]
            # Skip paths fully outside face bounds
            in_x = [fx_min <= p[0] <= fx_max for p in pts_cm]
            in_y = [fy_min <= p[1] <= fy_max for p in pts_cm]
            if not any(in_x) or not any(in_y):
                continue
            try:
                fp = [adsk.core.Point3D.create(p[0], p[1], 0) for p in pts_cm]
                prev = fp[-1]
                for pt in fp:
                    if math.hypot(pt.x - prev.x, pt.y - prev.y) > 1e-5:
                        lines_api.addByTwoPoints(prev, pt)
                        prev = pt
                n_drawn += 1
            except Exception:
                continue

    else:
        # Raster: each dark cell → a small square in sketch space
        # cell_cm: size of one grid cell in cm
        if pattern_width_mm is not None:
            cell_cm = (pattern_width_mm / grid_w) / 10.0
        else:
            cell_cm = min(face_w_cm / grid_w, face_h_cm / grid_h)

        gap_cm  = cell_cm * 0.12
        rect_cm = cell_cm - gap_cm

        for col, row in cells:
            x0 = off_x_cm + col * cell_cm + gap_cm / 2
            y0 = off_y_cm + row * cell_cm + gap_cm / 2
            x1 = x0 + rect_cm
            y1 = y0 + rect_cm
            if x1 > fx_max + 1e-4 or y1 > fy_max + 1e-4:
                continue
            if x0 < fx_min - 1e-4 or y0 < fy_min - 1e-4:
                continue
            try:
                p00 = adsk.core.Point3D.create(x0, y0, 0)
                p10 = adsk.core.Point3D.create(x1, y0, 0)
                p11 = adsk.core.Point3D.create(x1, y1, 0)
                p01 = adsk.core.Point3D.create(x0, y1, 0)
                lines_api.addByTwoPoints(p00, p10)
                lines_api.addByTwoPoints(p10, p11)
                lines_api.addByTwoPoints(p11, p01)
                lines_api.addByTwoPoints(p01, p00)
                n_drawn += 1
            except Exception:
                continue

    if n_drawn == 0:
        sketch.deleteMe()
        src_type = 'SVG' if is_svg else 'raster'
        raise RuntimeError(
            f'No embossable elements were drawn from the {src_type} file.\n\n'
            + ('• SVG: ensure the file has closed/filled shapes\n'
               '• Try increasing "Min Feature Size" or zooming in on the face\n'
               '• If using a text SVG, convert text to paths first'
               if is_svg else
               '• Try lowering the Threshold (more pixels become dark)\n'
               '• Check the image isn\'t all-white or all-black\n'
               '• Try a higher-contrast image')
        )

    # ── 5. Collect closed profiles ─────────────────────────────────────────────
    profiles = [prof for prof in sketch.profiles]

    if len(profiles) == 0:
        sketch.deleteMe()
        raise RuntimeError(
            f'Sketch drawn ({n_drawn} elements) but Fusion found no closed profiles.\n\n'
            'SVG tips:\n'
            '  • Paths must form closed loops (end with Z or rejoin start)\n'
            '  • Open strokes cannot be embossed — convert stroke to outline\n'
            '  • Open paths: try "Stroke to Path" in Inkscape first\n\n'
            'Raster tips:\n'
            '  • The pixel squares should always close — check for errors above'
        )

    # ── 6. Emboss ──────────────────────────────────────────────────────────────
    faces_col = [face]

    emboss_features = rc.features.embossFeatures
    emboss_input    = emboss_features.createInput(
        profiles, faces_col,
        adsk.core.ValueInput.createByReal(depth_cm)
    )
    emboss_input.embossFeatureType = (
        adsk.fusion.EmbossFeatureTypes.CutEmbossFeatureType
        if is_cut else
        adsk.fusion.EmbossFeatureTypes.BossEmbossFeatureType
    )

    feature = emboss_features.add(emboss_input)
    return feature, len(profiles), sketch

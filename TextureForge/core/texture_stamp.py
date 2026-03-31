"""
ReliefForge — Procedural Texture Stamp for Fusion 360.

Generates surface texture patterns and applies them to Fusion 360 model faces
using the Emboss feature. Works on both planar and curved faces.

Works for:
  ✓ 3D Printing  — any scale; recommended depth ≥ 2× layer height
  ✓ CNC Milling  — pattern scale must be ≥ 2× tool diameter;
                    use a V-bit for knurl/carbon fiber, ball-nose for wood grain/leather

Pattern generators (_generate_*) are pure Python — testable without Fusion 360.
Fusion 360 integration lives in apply_texture_to_face().

Supported textures:
  carbon_fiber  — 2×2 twill checkerboard of raised rectangles
  knurl_diamond — rotated-square (diamond) knurl grid
  wood_grain    — organic wavy horizontal bands
  brushed_metal — fine parallel horizontal grooves
  leather       — hexagonal bump array
  honeycomb     — thin-walled hexagonal cell grid (wall segments raised)

All internal geometry is in CENTIMETRES (Fusion 360's native unit).
"""

import math

# ── Texture catalog ──────────────────────────────────────────────────────────
TEXTURES = {
    'carbon_fiber': {
        'name': 'Carbon Fiber (2×2 Twill)',
        'description': 'Woven carbon fiber weave pattern — great for composite aesthetics',
        'default_scale_mm': 2.5,
        'default_depth_mm': 0.25,
    },
    'knurl_diamond': {
        'name': 'Diamond Knurl',
        'description': 'Classic diamond knurl grid — ideal for grip surfaces',
        'default_scale_mm': 2.0,
        'default_depth_mm': 0.40,
    },
    'wood_grain': {
        'name': 'Wood Grain',
        'description': 'Organic wavy grain lines — natural wood look',
        'default_scale_mm': 5.0,
        'default_depth_mm': 0.35,
    },
    'brushed_metal': {
        'name': 'Brushed Metal',
        'description': 'Fine parallel grooves simulating brushed aluminum finish',
        'default_scale_mm': 1.0,
        'default_depth_mm': 0.15,
    },
    'leather': {
        'name': 'Leather (Hex Bumps)',
        'description': 'Hexagonal bump grid simulating leather grain texture',
        'default_scale_mm': 3.5,
        'default_depth_mm': 0.30,
    },
    'honeycomb': {
        'name': 'Honeycomb',
        'description': 'Thin-walled hexagonal cell grid — raised walls with open cell voids',
        'default_scale_mm': 5.0,
        'default_depth_mm': 0.40,
    },
}

# Safety cap: limits number of sketch profiles to avoid Fusion 360 slowdown
MAX_PROFILES = 300


# ═══════════════════════════════════════════════════════════════════════════════
#  PURE-PYTHON PATTERN GENERATORS
#  All inputs/outputs in cm.  Each returns a list of primitives:
#    rects     → list of (x, y, w, h)                  lower-left + size
#    diamonds  → list of [(x,y), (x,y), (x,y), (x,y)]  4 corners N/E/S/W
#    polygons  → list of [(x,y), ...]                   N vertices
# ═══════════════════════════════════════════════════════════════════════════════

def _generate_carbon_fiber(width_cm, height_cm, scale_cm):
    """
    2×2 twill: alternating raised rectangles in a checker grid,
    shifted by one column every two rows (the 'twill' diagonal).
    """
    half = scale_cm / 2.0
    gap = scale_cm * 0.08          # 8% gap keeps rectangles visually separate
    inner = half - gap

    rects = []
    row = 0
    y = 0.0
    while y < height_cm:
        twill_offset = (row // 2) % 2   # shifts the checker by 1 col every 2 rows
        col = 0
        x = 0.0
        while x < width_cm:
            if (col + twill_offset) % 2 == 0:
                xd = x + gap / 2
                yd = y + gap / 2
                wd = min(inner, width_cm - xd)
                hd = min(inner, height_cm - yd)
                if wd > gap and hd > gap:
                    rects.append((xd, yd, wd, hd))
                    if len(rects) >= MAX_PROFILES:
                        return rects
            col += 1
            x += half
        row += 1
        y += half
    return rects


def _generate_knurl_diamond(width_cm, height_cm, scale_cm):
    """
    Diamond (45°-rotated square) grid.  Odd rows are offset by half a pitch
    for a true diamond-knurl look.
    """
    pitch = scale_cm
    d = scale_cm * 0.40    # half-diagonal; keep < pitch/2 so diamonds don't touch

    diamonds = []
    row = 0
    cy = pitch / 2
    while cy < height_cm + pitch:
        cx = (pitch / 2 if row % 2 == 0 else pitch)
        while cx < width_cm + pitch:
            pts = [
                (cx,     cy + d),   # top
                (cx + d, cy),       # right
                (cx,     cy - d),   # bottom
                (cx - d, cy),       # left
            ]
            if (cx - d) < width_cm and (cy - d) < height_cm:
                diamonds.append(pts)
                if len(diamonds) >= MAX_PROFILES:
                    return diamonds
            cx += pitch
        cy += pitch
        row += 1
    return diamonds


def _generate_brushed_metal(width_cm, height_cm, scale_cm):
    """Parallel horizontal raised stripes (30% of pitch height, 70% gap)."""
    stripe_h = scale_cm * 0.30
    pitch = scale_cm

    rects = []
    y = 0.0
    while y < height_cm:
        hd = min(stripe_h, height_cm - y)
        if hd > 0.001:
            rects.append((0.0, y, width_cm, hd))
            if len(rects) >= MAX_PROFILES:
                return rects
        y += pitch
    return rects


def _generate_wood_grain(width_cm, height_cm, scale_cm, n_pts=28):
    """
    Wavy horizontal bands.  Each band is a closed polygon with n_pts points
    on the top curve and n_pts on the bottom curve connected at the ends.
    Phase is offset per band to create an organic, natural look.
    """
    band_h = scale_cm * 0.55
    pitch = scale_cm
    amplitude = scale_cm * 0.30
    wavelength = max(width_cm / 2.0, scale_cm * 1.5)

    bands = []
    band_idx = 0
    y_center = pitch / 2
    while y_center < height_cm + pitch:
        phase = band_idx * 1.618   # golden-ratio offset for organic variety

        top_pts = []
        bot_pts = []
        for i in range(n_pts):
            t = i / (n_pts - 1)
            x = t * width_cm
            wave = amplitude * math.sin(2 * math.pi * x / wavelength + phase)
            top_y = min(height_cm - 0.001, max(0.001, y_center + wave + band_h / 2))
            bot_y = min(height_cm - 0.001, max(0.001, y_center + wave - band_h / 2))
            top_pts.append((x, top_y))
            bot_pts.append((x, bot_y))

        # Closed polygon: top L→R, right cap, bottom R→L, left cap
        polygon = top_pts + list(reversed(bot_pts))
        if len(polygon) >= 4:
            bands.append(polygon)
            if len(bands) >= MAX_PROFILES:
                return bands

        y_center += pitch
        band_idx += 1
    return bands


def _generate_leather_hexagons(width_cm, height_cm, scale_cm):
    """
    Flat-top regular hexagons packed in a hex grid.
    Circumradius = 40% of scale; 10% gap between hexagons.
    """
    r = scale_cm * 0.40
    gap = scale_cm * 0.10
    col_pitch = (r + gap) * math.sqrt(3)
    row_pitch = (r + gap) * 1.5

    hexagons = []
    row = 0
    cy = r
    while cy < height_cm + r:
        row_offset = (row % 2) * col_pitch / 2
        cx = row_offset + r
        while cx < width_cm + r:
            pts = []
            for i in range(6):
                angle = math.pi / 6 + i * math.pi / 3   # flat-top orientation
                pts.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
            if (cx - r) < width_cm and (cy - r) < height_cm:
                hexagons.append(pts)
                if len(hexagons) >= MAX_PROFILES:
                    return hexagons
            cx += col_pitch
        cy += row_pitch
        row += 1
    return hexagons
def _generate_honeycomb(width_cm, height_cm, scale_cm):
    """
    Honeycomb: each hexagonal cell wall is represented as a thin rotated-rectangle
    polygon (4 corners).  Only unique walls are emitted — shared edges between
    adjacent cells are drawn once to avoid duplicate-line confusion in Fusion's
    sketch solver.

    Wall thickness = 10% of scale.  Circumradius = 50% of scale so cells are
    edge-to-edge with no gap (walls are the only solid material).
    """
    r = scale_cm * 0.50           # circumradius
    wall_t = scale_cm * 0.10      # wall thickness

    # Pointy-top hex grid
    col_pitch = r * math.sqrt(3)
    row_pitch = r * 1.5

    walls = []
    seen = set()

    row = 0
    cy = r
    while cy - r < height_cm + row_pitch:
        row_offset = (col_pitch / 2) if (row % 2) else 0.0
        cx = row_offset + col_pitch / 2
        while cx - r < width_cm + col_pitch:
            # 6 vertices — pointy-top orientation
            verts = [
                (cx + r * math.cos(math.pi / 6 + i * math.pi / 3),
                 cy + r * math.sin(math.pi / 6 + i * math.pi / 3))
                for i in range(6)
            ]

            for i in range(6):
                v0 = verts[i]
                v1 = verts[(i + 1) % 6]

                # Deduplicate shared edges using sorted rounded endpoints
                key = tuple(sorted([
                    (round(v0[0], 4), round(v0[1], 4)),
                    (round(v1[0], 4), round(v1[1], 4)),
                ]))
                if key in seen:
                    continue
                seen.add(key)

                # Skip walls entirely outside the face bounds
                mx = max(v0[0], v1[0])
                my = max(v0[1], v1[1])
                lx = min(v0[0], v1[0])
                ly = min(v0[1], v1[1])
                if mx < 0 or lx > width_cm or my < 0 or ly > height_cm:
                    continue

                # Build a thin rectangle centred on the wall edge
                dx, dy = v1[0] - v0[0], v1[1] - v0[1]
                length = math.hypot(dx, dy)
                if length < 1e-9:
                    continue
                px = -dy / length * wall_t / 2   # perpendicular offset
                py =  dx / length * wall_t / 2

                walls.append([
                    (v0[0] - px, v0[1] - py),
                    (v0[0] + px, v0[1] + py),
                    (v1[0] + px, v1[1] + py),
                    (v1[0] - px, v1[1] - py),
                ])
                if len(walls) >= MAX_PROFILES:
                    return walls

            cx += col_pitch
        cy += row_pitch
        row += 1
    return walls




def generate_pattern(texture_key, width_cm, height_cm, scale_cm):
    """
    Generate the pattern primitives for a given texture key.

    Returns:
        (kind, primitives) where kind is 'rects' | 'diamonds' | 'polygons'
    """
    if texture_key == 'carbon_fiber':
        return 'rects', _generate_carbon_fiber(width_cm, height_cm, scale_cm)
    elif texture_key == 'knurl_diamond':
        return 'diamonds', _generate_knurl_diamond(width_cm, height_cm, scale_cm)
    elif texture_key == 'brushed_metal':
        return 'rects', _generate_brushed_metal(width_cm, height_cm, scale_cm)
    elif texture_key == 'wood_grain':
        return 'polygons', _generate_wood_grain(width_cm, height_cm, scale_cm)
    elif texture_key == 'leather':
        return 'polygons', _generate_leather_hexagons(width_cm, height_cm, scale_cm)
    elif texture_key == 'honeycomb':
        return 'polygons', _generate_honeycomb(width_cm, height_cm, scale_cm)
    else:
        raise ValueError(f'Unknown texture key: {texture_key!r}')


# ═══════════════════════════════════════════════════════════════════════════════
#  FUSION 360 SKETCH INTEGRATION
# ═══════════════════════════════════════════════════════════════════════════════

def _pt(x, y):
    import adsk.core
    return adsk.core.Point3D.create(x, y, 0.0)


def _draw_rect_in_sketch(lines, x, y, w, h):
    """Draw a closed rectangle using four sketch lines."""
    lines.addByTwoPoints(_pt(x,     y),     _pt(x + w, y))
    lines.addByTwoPoints(_pt(x + w, y),     _pt(x + w, y + h))
    lines.addByTwoPoints(_pt(x + w, y + h), _pt(x,     y + h))
    lines.addByTwoPoints(_pt(x,     y + h), _pt(x,     y))


def _draw_polygon_in_sketch(lines, pts):
    """Draw a closed polygon using sketch lines (pts is a list of (x, y) tuples)."""
    n = len(pts)
    for i in range(n):
        p0, p1 = pts[i], pts[(i + 1) % n]
        lines.addByTwoPoints(_pt(p0[0], p0[1]), _pt(p1[0], p1[1]))


def _get_face_bounds_in_sketch(face, sketch):
    """
    Return (min_x, min_y, width_cm, height_cm) — the face extent in sketch space.
    Transforms all edge vertices through the sketch's inverse transform.
    """
    import adsk.core

    world_to_sketch = sketch.transform.copy()
    world_to_sketch.invert()

    xs, ys = [], []
    for loop in face.loops:
        for coedge in loop.coEdges:
            for vtx in (coedge.edge.startVertex, coedge.edge.endVertex):
                p = vtx.geometry.copy()
                p.transformBy(world_to_sketch)
                xs.append(p.x)
                ys.append(p.y)

    if not xs:
        # Fallback to bounding-box corners
        bb = face.boundingBox
        for dx in (0, 1):
            for dy in (0, 1):
                for dz in (0, 1):
                    p = adsk.core.Point3D.create(
                        bb.minPoint.x + dx * (bb.maxPoint.x - bb.minPoint.x),
                        bb.minPoint.y + dy * (bb.maxPoint.y - bb.minPoint.y),
                        bb.minPoint.z + dz * (bb.maxPoint.z - bb.minPoint.z))
                    p.transformBy(world_to_sketch)
                    xs.append(p.x)
                    ys.append(p.y)

    min_x, min_y = min(xs), min(ys)
    width  = max(max(xs) - min_x, 0.05)   # never zero
    height = max(max(ys) - min_y, 0.05)
    return min_x, min_y, width, height


def apply_texture_to_face(face, texture_key, scale_mm, depth_mm, is_cut=False):
    """
    Apply a procedural texture to a BRep face via Fusion 360's Emboss feature.

    Args:
        face:         adsk.fusion.BRepFace  — target face
        texture_key:  str                   — key from TEXTURES dict
        scale_mm:     float                 — pattern repeat size in mm
        depth_mm:     float                 — emboss height/depth in mm
        is_cut:       bool                  — True → deboss (cut in), False → boss (raise)

    Returns:
        (feature, n_profiles, sketch)  on success
    Raises:
        RuntimeError with user-friendly message on failure.
    """
    import adsk.core
    import adsk.fusion

    if scale_mm <= 0 or depth_mm <= 0:
        raise ValueError('Scale and depth must be positive values.')

    component = face.body.parentComponent
    scale_cm  = scale_mm / 10.0
    depth_cm  = depth_mm / 10.0

    # ── Step 1: create sketch on the face ───────────────────────────────────
    sketch = component.sketches.add(face)
    sketch.isComputeDeferred = True   # batch all line-adds for performance

    min_x, min_y, width_cm, height_cm = _get_face_bounds_in_sketch(face, sketch)

    # ── Step 2: generate primitives and draw them into the sketch ───────────
    kind, primitives = generate_pattern(texture_key, width_cm, height_cm, scale_cm)

    if not primitives:
        sketch.deleteMe()
        raise RuntimeError(
            f'No pattern elements generated for {texture_key!r}.\n'
            'Try a smaller Pattern Scale so the pattern fits the face.')

    lines = sketch.sketchCurves.sketchLines

    if kind == 'rects':
        for (x, y, w, h) in primitives:
            _draw_rect_in_sketch(lines, min_x + x, min_y + y, w, h)
    else:  # 'diamonds' or 'polygons'
        for pts in primitives:
            adjusted = [(min_x + p[0], min_y + p[1]) for p in pts]
            _draw_polygon_in_sketch(lines, adjusted)

    sketch.isComputeDeferred = False

    # ── Step 3: collect closed profiles ─────────────────────────────────────
    profiles_oc = adsk.core.ObjectCollection.create()
    n_profiles = 0
    for i in range(sketch.profiles.count):
        profiles_oc.add(sketch.profiles.item(i))
        n_profiles += 1

    if n_profiles == 0:
        sketch.deleteMe()
        raise RuntimeError(
            'No closed profiles found in the generated sketch.\n'
            'The pattern lines may not form enclosed shapes on this face. '
            'Try a larger Pattern Scale.')

    # ── Step 4: apply Extrude feature ────────────────────────────────────────
    operation = (
        adsk.fusion.FeatureOperations.CutFeatureOperation if is_cut
        else adsk.fusion.FeatureOperations.JoinFeatureOperation
    )
    extrudes  = component.features.extrudeFeatures
    ext_input = extrudes.createInput(profiles_oc, operation)

    depth_vi = adsk.core.ValueInput.createByReal(depth_cm)
    dist_def = adsk.fusion.DistanceExtentDefinition.create(depth_vi)
    # Boss  → PositiveExtentDirection = outward from face (raises material)
    # Deboss → NegativeExtentDirection = inward into body  (cuts into material)
    direction = (adsk.fusion.ExtentDirections.NegativeExtentDirection if is_cut
                 else adsk.fusion.ExtentDirections.PositiveExtentDirection)
    ext_input.setOneSideExtent(dist_def, direction)
    ext_input.participantBodies = [face.body]

    feature = extrudes.add(ext_input)
    return feature, n_profiles, sketch

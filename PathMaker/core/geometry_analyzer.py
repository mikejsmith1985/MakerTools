"""
Geometry Analyzer for FusionCam.
Analyzes Fusion 360 BRep geometry to identify machinable features:
holes, pockets, profiles, bosses, chamfers, and 3D surfaces.
"""

import adsk.core
import adsk.fusion
import math
import json


def analyze_body(body, setup_direction=None):
    """
    Analyze a BRep body to identify machinable features.

    Args:
        body: adsk.fusion.BRepBody - the solid body to analyze
        setup_direction: adsk.core.Vector3D - the tool axis direction (default: Z+)

    Returns:
        List of feature dicts, each describing a detected feature
    """
    if setup_direction is None:
        setup_direction = adsk.core.Vector3D.create(0, 0, 1)

    features = []
    bounding = body.boundingBox

    stock_top_z = bounding.maxPoint.z
    stock_bottom_z = bounding.minPoint.z
    part_height = stock_top_z - stock_bottom_z

    # Analyze faces
    cylindrical_faces = []
    planar_faces = []
    other_faces = []

    for face in body.faces:
        geom = face.geometry
        if isinstance(geom, adsk.core.Cylinder):
            cylindrical_faces.append(face)
        elif isinstance(geom, adsk.core.Plane):
            planar_faces.append(face)
        else:
            other_faces.append(face)

    # Detect Holes
    holes = _detect_holes(cylindrical_faces, stock_top_z, stock_bottom_z, setup_direction)
    features.extend(holes)

    # Detect Pockets
    pockets = _detect_pockets(planar_faces, stock_top_z, stock_bottom_z, body, setup_direction)
    features.extend(pockets)

    # Detect Outer Profile
    profile = _detect_outer_profile(body, stock_top_z, stock_bottom_z)
    if profile:
        features.append(profile)

    # Detect Chamfers
    chamfers = _detect_chamfers(body)
    features.extend(chamfers)

    # Detect 3D Surfaces
    if other_faces:
        surfaces = _detect_3d_surfaces(other_faces, body)
        features.extend(surfaces)

    # Detect Face Operation Need
    face_op = _detect_face_need(body, stock_top_z)
    if face_op:
        features.insert(0, face_op)

    # Assign IDs
    for i, feature in enumerate(features):
        feature['id'] = f"feature_{i:03d}"

    return features


def _detect_holes(cylindrical_faces, stock_top_z, stock_bottom_z, setup_direction):
    """Detect through and blind holes from cylindrical faces."""
    holes = []

    # Group cylindrical faces by axis and radius (same hole)
    hole_groups = {}

    for face in cylindrical_faces:
        cyl = face.geometry
        axis = cyl.axis
        origin = cyl.origin
        radius = cyl.radius

        # Only consider holes aligned with setup direction (within 15 degrees)
        dot = abs(axis.x * setup_direction.x +
                  axis.y * setup_direction.y +
                  axis.z * setup_direction.z)
        if dot < math.cos(math.radians(15)):
            continue

        # Check if this is an internal cylindrical face (hole) vs external (boss)
        # Internal faces have normals pointing inward
        eval_point = face.pointOnFace
        normal = face.evaluator.getNormalAtPoint(eval_point)[1]
        # For holes, the normal points toward the center axis
        to_axis = adsk.core.Vector3D.create(
            origin.x - eval_point.x,
            origin.y - eval_point.y,
            0
        )
        if to_axis.length > 0.001:
            to_axis.normalize()
            # Dot product > 0 means normal points toward axis = hole
            dot_check = (normal.x * to_axis.x + normal.y * to_axis.y + normal.z * to_axis.z)
            if dot_check < 0:
                continue  # External surface, not a hole

        # Group key: rounded center XY + rounded radius
        key = (round(origin.x, 3), round(origin.y, 3), round(radius, 4))

        if key not in hole_groups:
            hole_groups[key] = {
                'faces': [],
                'origin': origin,
                'radius': radius,
                'min_z': float('inf'),
                'max_z': float('-inf')
            }

        hole_groups[key]['faces'].append(face)

        # Track Z extent
        bb = face.boundingBox
        hole_groups[key]['min_z'] = min(hole_groups[key]['min_z'], bb.minPoint.z)
        hole_groups[key]['max_z'] = max(hole_groups[key]['max_z'], bb.maxPoint.z)

    for key, group in hole_groups.items():
        diameter_mm = group['radius'] * 20.0  # radius in cm to diameter in mm
        depth_mm = (group['max_z'] - group['min_z']) * 10.0

        # Determine if through hole or blind
        tolerance = 0.05  # 0.5mm tolerance
        is_through = (group['min_z'] <= stock_bottom_z + tolerance)

        center_x_mm = group['origin'].x * 10.0
        center_y_mm = group['origin'].y * 10.0

        holes.append({
            'type': 'through_hole' if is_through else 'blind_hole',
            'center_x_mm': round(center_x_mm, 3),
            'center_y_mm': round(center_y_mm, 3),
            'diameter_mm': round(diameter_mm, 3),
            'diameter_inches': round(diameter_mm / 25.4, 4),
            'depth_mm': round(depth_mm, 3),
            'is_through': is_through,
            'min_radius_mm': round(diameter_mm / 2, 3),
            'description': f"{'Through' if is_through else 'Blind'} hole D{diameter_mm:.1f}mm at ({center_x_mm:.1f}, {center_y_mm:.1f})"
        })

    return holes


def _detect_pockets(planar_faces, stock_top_z, stock_bottom_z, body, setup_direction):
    """Detect pockets - planar faces below the top surface bounded by walls."""
    pockets = []

    # Find the top face (highest Z planar face that's roughly horizontal)
    top_faces = []
    for face in planar_faces:
        plane = face.geometry
        normal = plane.normal
        # Face normal pointing up (same as setup direction)
        dot = (normal.x * setup_direction.x +
               normal.y * setup_direction.y +
               normal.z * setup_direction.z)
        if dot > 0.95:  # Nearly horizontal, pointing up
            face_z = face.boundingBox.maxPoint.z
            top_faces.append((face, face_z))

    if not top_faces:
        return pockets

    # Sort by Z height
    top_faces.sort(key=lambda x: x[1], reverse=True)
    top_z = top_faces[0][1]

    # Pockets are horizontal faces below the top surface
    pocket_id = 0
    for face, face_z in top_faces:
        # Skip the top face itself
        if abs(face_z - top_z) < 0.01:  # 0.1mm tolerance
            continue

        # This face is below the top - it's a pocket floor
        depth_mm = (top_z - face_z) * 10.0  # cm to mm

        if depth_mm < 0.5:  # Skip very shallow features (< 0.5mm)
            continue

        bb = face.boundingBox
        width_mm = (bb.maxPoint.x - bb.minPoint.x) * 10.0
        height_mm = (bb.maxPoint.y - bb.minPoint.y) * 10.0
        area_mm2 = face.area * 100.0  # cm2 to mm2

        # Find minimum internal radius (constrains tool size)
        min_radius = _find_min_internal_radius(face)

        pocket_id += 1
        pockets.append({
            'type': 'pocket',
            'depth_mm': round(depth_mm, 3),
            'width_mm': round(width_mm, 3),
            'height_mm': round(height_mm, 3),
            'area_mm2': round(area_mm2, 2),
            'min_radius_mm': round(min_radius, 3) if min_radius else 50.0,
            'center_x_mm': round((bb.minPoint.x + bb.maxPoint.x) / 2 * 10.0, 3),
            'center_y_mm': round((bb.minPoint.y + bb.maxPoint.y) / 2 * 10.0, 3),
            'description': f"Pocket {pocket_id}: {width_mm:.1f}x{height_mm:.1f}mm, {depth_mm:.1f}mm deep"
        })

    return pockets


def _find_min_internal_radius(face):
    """Find the minimum internal corner radius on a face's edges."""
    min_radius = float('inf')

    for edge in face.edges:
        geom = edge.geometry
        if isinstance(geom, adsk.core.Arc3D):
            radius_mm = geom.radius * 10.0  # cm to mm
            if radius_mm < min_radius:
                min_radius = radius_mm

    return min_radius if min_radius < float('inf') else None


def _detect_outer_profile(body, stock_top_z, stock_bottom_z):
    """Detect the outer profile of the part that needs to be cut from stock."""
    bb = body.boundingBox
    width_mm = (bb.maxPoint.x - bb.minPoint.x) * 10.0
    height_mm = (bb.maxPoint.y - bb.minPoint.y) * 10.0
    depth_mm = (bb.maxPoint.z - bb.minPoint.z) * 10.0

    # Find minimum external fillet radius
    min_radius = _find_min_external_radius(body)

    return {
        'type': 'outer_profile',
        'width_mm': round(width_mm, 3),
        'height_mm': round(height_mm, 3),
        'depth_mm': round(depth_mm, 3),
        'min_radius_mm': round(min_radius, 3) if min_radius else 50.0,
        'description': f"Outer profile: {width_mm:.1f}x{height_mm:.1f}mm, {depth_mm:.1f}mm thick"
    }


def _find_min_external_radius(body):
    """Find the minimum external fillet radius on the body."""
    min_radius = float('inf')

    for edge in body.edges:
        geom = edge.geometry
        if isinstance(geom, adsk.core.Arc3D):
            radius_mm = geom.radius * 10.0
            if radius_mm < min_radius:
                min_radius = radius_mm

    return min_radius if min_radius < float('inf') else None


def _detect_chamfers(body):
    """Detect chamfered edges that may need a V-bit or chamfer operation."""
    chamfers = []

    for face in body.faces:
        geom = face.geometry
        # Chamfers are typically planar faces at an angle to both the top and sides
        if isinstance(geom, adsk.core.Plane):
            normal = geom.normal
            # A chamfer face has a normal that is neither horizontal nor vertical
            z_component = abs(normal.z)
            if 0.2 < z_component < 0.9:  # Angled face (not horizontal, not vertical)
                bb = face.boundingBox
                area_mm2 = face.area * 100.0

                if area_mm2 < 1.0:  # Skip very tiny faces
                    continue

                angle = math.degrees(math.acos(z_component))
                chamfers.append({
                    'type': 'chamfer',
                    'angle_degrees': round(angle, 1),
                    'area_mm2': round(area_mm2, 2),
                    'min_radius_mm': 50.0,
                    'depth_mm': round((bb.maxPoint.z - bb.minPoint.z) * 10.0, 3),
                    'description': f"Chamfer at {angle:.0f} degrees, area {area_mm2:.1f}mm2"
                })

    return chamfers


def _detect_3d_surfaces(other_faces, body):
    """Detect non-planar, non-cylindrical faces that need 3D machining."""
    surfaces = []

    total_area = sum(f.area for f in other_faces) * 100.0  # mm2

    if total_area > 10.0:  # Only report if significant
        bb = body.boundingBox
        surfaces.append({
            'type': '3d_surface',
            'total_area_mm2': round(total_area, 2),
            'face_count': len(other_faces),
            'min_radius_mm': 1.0,  # 3D surfaces typically need smaller tools
            'depth_mm': round((bb.maxPoint.z - bb.minPoint.z) * 10.0, 3),
            'description': f"3D surface region: {len(other_faces)} faces, {total_area:.0f}mm2 total area"
        })

    return surfaces


def _detect_face_need(body, stock_top_z):
    """Determine if a facing operation is needed (stock taller than part)."""
    return {
        'type': 'face',
        'depth_mm': 0.5,  # Skim cut by default
        'min_radius_mm': 50.0,  # Any tool works for facing
        'description': "Face top of stock (skim cut for flat reference surface)"
    }


def classify_sides(features, body):
    """
    Classify features as Side A (top), Side B (bottom), or Both.
    Used for 2-sided carving setup.

    Args:
        features: List of feature dicts from analyze_body()
        body: The BRep body

    Returns:
        Dict with 'side_a', 'side_b', 'both' lists of feature IDs
    """
    bb = body.boundingBox
    mid_z = (bb.maxPoint.z + bb.minPoint.z) / 2
    thickness_mm = (bb.maxPoint.z - bb.minPoint.z) * 10.0

    classification = {
        'side_a': [],    # Accessible from top (Z+)
        'side_b': [],    # Accessible from bottom (Z-)
        'both': [],      # Through features
        'thickness_mm': round(thickness_mm, 3),
        'needs_two_sided': False
    }

    has_side_b_features = False

    for feature in features:
        ftype = feature.get('type', '')
        fid = feature.get('id', '')

        if ftype == 'through_hole':
            classification['both'].append(fid)
        elif ftype == 'face':
            classification['side_a'].append(fid)
        elif ftype in ('pocket', 'boss', 'chamfer', '3d_surface'):
            # Determine which side based on feature center Z relative to part midpoint
            # This is simplified; real implementation would check face normals
            classification['side_a'].append(fid)
        elif ftype == 'outer_profile':
            classification['side_a'].append(fid)

    # Check if any features require side B access
    # In the simplified version, we flag 2-sided if:
    # 1. There are through-holes that need clean exit on both sides
    # 2. User explicitly requests 2-sided (handled in UI)
    if classification['side_b'] or classification['both']:
        classification['needs_two_sided'] = True
        has_side_b_features = True

    return classification


def get_analysis_summary(features):
    """Generate a human-readable summary of the geometry analysis."""
    if not features:
        return "No machinable features detected."

    counts = {}
    for f in features:
        ftype = f.get('type', 'unknown')
        counts[ftype] = counts.get(ftype, 0) + 1

    lines = ["Geometry Analysis Summary:", "=" * 40]

    type_labels = {
        'face': 'Facing Operations',
        'through_hole': 'Through Holes',
        'blind_hole': 'Blind Holes',
        'pocket': 'Pockets',
        'outer_profile': 'Outer Profiles',
        'boss': 'Bosses',
        'chamfer': 'Chamfers',
        '3d_surface': '3D Surfaces'
    }

    for ftype, count in counts.items():
        label = type_labels.get(ftype, ftype.replace('_', ' ').title())
        lines.append(f"  {label}: {count}")

    lines.append("")
    lines.append("Feature Details:")
    lines.append("-" * 40)

    for f in features:
        lines.append(f"  [{f.get('id', '?')}] {f.get('description', 'No description')}")

    return "\n".join(lines)

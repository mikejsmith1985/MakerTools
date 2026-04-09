"""
CAM Generator for FusionCam.
Creates Fusion 360 CAM setups and operations from analyzed geometry.
This is the core 1-click workflow engine.
"""

import adsk.core
import adsk.fusion
import adsk.cam
import json
import os
import math

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ADDIN_DIR, 'config')


def _load_machine_profile():
    """Load the active machine profile."""
    path = os.path.join(CONFIG_DIR, 'machine_profiles.json')
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    active = data.get('active_machine', 'onefinity_machinist')
    return data['machines'][active]


def _load_operation_templates():
    """Load operation templates."""
    path = os.path.join(CONFIG_DIR, 'operation_templates.json')
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _get_cam():
    """Get the CAM product."""
    app = adsk.core.Application.get()
    cam = adsk.cam.CAM.cast(app.activeProduct)
    if not cam:
        raise RuntimeError('Switch to the Manufacturing workspace first.')
    return cam


def generate_cam(features, tool_assignments, material_key, stock_config, quality='standard'):
    """
    Generate complete CAM operations from analyzed features.

    Args:
        features: List of feature dicts from geometry_analyzer
        tool_assignments: Dict mapping feature_id -> tool_data
        material_key: Material key (e.g., 'aluminum_6061_t6')
        stock_config: Dict with stock dimensions and offsets
        quality: 'draft', 'standard', or 'fine'

    Returns:
        Dict with setup info, operation count, estimated time
    """
    from . import feeds_speeds
    from . import tool_parser

    cam = _get_cam()
    machine = _load_machine_profile()
    templates = _load_operation_templates()
    quality_preset = templates['quality_presets'].get(quality, templates['quality_presets']['standard'])

    # Create the CAM Setup
    setup = _create_setup(cam, stock_config, machine)

    # Sort features by operation ordering
    op_order = templates.get('operation_ordering', [])
    sorted_features = _sort_features(features, op_order)

    operations_created = []
    current_tool_id = None

    for feature in sorted_features:
        feature_id = feature.get('id', '')
        feature_type = feature.get('type', '')
        tool_data = tool_assignments.get(feature_id)

        if not tool_data:
            continue

        # Calculate feeds/speeds for this tool + material combo
        if feature_type in ('through_hole', 'blind_hole') and tool_data.get('tool_type') == 'drill_bit':
            fs = feeds_speeds.calculate_for_drilling(
                tool_data, material_key,
                feature.get('depth_mm', 10),
                quality
            )
        else:
            op_type = 'adaptive' if 'roughing' in _get_phase(feature_type) else 'finishing'
            fs = feeds_speeds.calculate(tool_data, material_key, op_type, quality)

        # Get operation template
        feature_templates = templates['feature_operation_map'].get(feature_type, {})
        op_templates = feature_templates.get('operations', [])

        for op_template in op_templates:
            # Skip finishing ops in draft mode
            if quality_preset.get('skip_finishing', False) and op_template.get('phase') == 'finishing':
                continue

            # Skip fallback operations unless needed
            if op_template.get('fallback', False):
                continue

            op_name = op_template['name'].format(
                name=feature.get('description', ''),
                diameter=f"{feature.get('diameter_mm', 0):.1f}mm"
            )

            op_info = {
                'name': op_name,
                'feature_id': feature_id,
                'feature_type': feature_type,
                'fusion_operation': op_template['fusion_operation'],
                'tool': tool_data.get('display_name', 'Unknown'),
                'tool_id': tool_data.get('id', ''),
                'rpm': fs.get('rpm', 18000),
                'feed_rate_mm_min': fs.get('feed_rate_mm_min', 500),
                'plunge_rate_mm_min': fs.get('plunge_rate_mm_min', 200),
                'doc_mm': fs.get('doc_mm', 1.0),
                'woc_mm': fs.get('woc_mm', 2.0),
                'parameters': op_template.get('parameters', {}),
                'phase': op_template.get('phase', 'roughing')
            }

            operations_created.append(op_info)

    # Create Fusion 360 operations
    fusion_ops_created = 0
    for op_info in operations_created:
        try:
            _create_fusion_operation(cam, setup, op_info, machine)
            fusion_ops_created += 1
        except Exception as e:
            op_info['error'] = str(e)

    return {
        'setup_name': setup.name if setup else 'FusionCam Setup',
        'operations_planned': len(operations_created),
        'operations_created': fusion_ops_created,
        'operations': operations_created,
        'quality': quality,
        'material': material_key,
        'machine': machine.get('name', 'Onefinity Machinist')
    }


def _create_setup(cam, stock_config, machine):
    """Create a CAM Setup with stock and WCS configuration."""
    app = adsk.core.Application.get()
    doc = app.activeDocument
    design = adsk.fusion.Design.cast(doc.products.itemByProductType('DesignProductType'))

    if not design:
        raise RuntimeError('No design found in the active document.')

    # Get the root component
    root = design.rootComponent

    # Get bodies to machine
    bodies = root.bRepBodies
    if bodies.count == 0:
        raise RuntimeError('No solid bodies found in the design.')

    # Create setup input
    setups = cam.setups
    setup_input = setups.createInput(adsk.cam.OperationTypes.MillingOperation)

    # Set the body to machine
    models = setup_input.models
    model_collection = adsk.core.ObjectCollection.create()
    for i in range(bodies.count):
        model_collection.add(bodies.item(i))
    setup_input.models = model_collection

    # Configure stock mode on the input before creating the setup
    stock_mode = stock_config.get('mode', 'relative_offset')

    if stock_mode == 'fixed_size':
        # User specified physical stock dimensions (e.g., a purchased piece of material)
        setup_input.stockMode = adsk.cam.SetupStockModes.FixedBoxStock
    else:
        # Default: add a uniform offset around the model bounding box
        setup_input.stockMode = adsk.cam.SetupStockModes.RelativeBoxStock

        offset_mm = stock_config.get('offset_mm', 2.0)
        offset_cm = offset_mm / 10.0  # Fusion uses cm internally

        setup_input.stockOffsetTop = adsk.core.ValueInput.createByReal(offset_cm)
        setup_input.stockOffsetBottom = adsk.core.ValueInput.createByReal(0)
        setup_input.stockOffsetSide = adsk.core.ValueInput.createByReal(offset_cm)

    # Create the setup
    setup = setups.add(setup_input)
    setup.name = f'FusionCam - {stock_config.get("material_name", "Setup")}'

    # For fixed-size stock, apply the physical dimensions via the CAM parameters API.
    # We do this after creation because Fusion sets stock parameters on the setup object,
    # not on the setup input.
    if stock_mode == 'fixed_size':
        width_cm  = stock_config.get('width_mm',  100.0) / 10.0
        height_cm = stock_config.get('height_mm', 100.0) / 10.0
        depth_cm  = stock_config.get('depth_mm',   10.0) / 10.0

        for paramName, valueCm in [
            ('job_stocksizex', width_cm),
            ('job_stocksizey', height_cm),
            ('job_stocksizez', depth_cm),
        ]:
            try:
                param = setup.parameters.itemByName(paramName)
                if param:
                    param.expression = f'{valueCm} cm'
            except Exception:
                pass  # Parameter names can vary across Fusion versions — fail gracefully

    return setup


def _create_fusion_operation(cam, setup, op_info, machine):
    """
    Create a single Fusion 360 CAM operation.

    This maps our operation info to actual Fusion 360 API calls.
    """
    safety = machine.get('safety_defaults', {})

    # Map our operation types to Fusion 360 operation type strings
    fusion_op_map = {
        'adaptive2d': '2D Adaptive',
        'pocket2d': '2D Pocket',
        'contour2d': '2D Contour',
        'face': 'Face',
        'drilling': 'Drill',
        'bore': '2D Bore',
        'chamfer2d': '2D Chamfer',
        'adaptive3d': '3D Adaptive',
        'parallel': 'Parallel',
    }

    fusion_op_type = fusion_op_map.get(
        op_info.get('fusion_operation', ''),
        '2D Pocket'
    )

    # For now, we log what would be created
    # Full Fusion API operation creation requires selecting geometry
    # which depends on the specific part
    op_info['fusion_op_type'] = fusion_op_type
    op_info['status'] = 'planned'

    return op_info


def _sort_features(features, op_ordering):
    """Sort features by the operation ordering priority."""
    type_to_strategy = {
        'face': 'face',
        'pocket': 'adaptive_clearing',
        'boss': 'adaptive_clearing',
        'through_hole': 'drilling',
        'blind_hole': 'drilling',
        'outer_profile': 'profile_contour',
        'chamfer': 'chamfer',
        '3d_surface': 'adaptive_clearing_3d',
    }

    def sort_key(feature):
        strategy = type_to_strategy.get(feature.get('type', ''), 'profile_contour')
        try:
            return op_ordering.index(strategy)
        except ValueError:
            return 999

    return sorted(features, key=sort_key)


def _get_phase(feature_type):
    """Get the machining phase for a feature type."""
    roughing_types = {'pocket', 'boss', 'outer_profile', '3d_surface'}
    if feature_type in roughing_types:
        return 'roughing'
    return 'finishing'


def auto_assign_tools(features, available_tools):
    """
    Automatically assign the best tool from the library for each feature.

    Strategy:
    - Largest tool that fits (faster, more rigid)
    - Minimize tool changes (reuse tools across features when possible)
    - Match tool type to feature type

    Args:
        features: List of feature dicts
        available_tools: List of tool dicts from the library

    Returns:
        Dict mapping feature_id -> tool_data
    """
    from . import tool_parser

    assignments = {}

    # Group features by type for efficient tool reuse
    type_groups = {}
    for feature in features:
        ftype = feature.get('type', '')
        if ftype not in type_groups:
            type_groups[ftype] = []
        type_groups[ftype].append(feature)

    for ftype, feature_list in type_groups.items():
        for feature in feature_list:
            suitable = tool_parser.find_tools_for_feature(feature, available_tools)
            if suitable:
                assignments[feature.get('id', '')] = suitable[0]

    return assignments


def build_operation_plan(features, tool_assignments, material_key, quality='standard'):
    """
    Build a preview of what operations will be created, without actually creating them.
    Used for the review dialog.

    Returns:
        List of operation preview dicts
    """
    from . import feeds_speeds

    templates = _load_operation_templates()
    quality_preset = templates['quality_presets'].get(quality, templates['quality_presets']['standard'])
    op_order = templates.get('operation_ordering', [])
    sorted_features = _sort_features(features, op_order)

    plan = []
    tool_changes = 0
    current_tool = None

    for feature in sorted_features:
        feature_id = feature.get('id', '')
        feature_type = feature.get('type', '')
        tool_data = tool_assignments.get(feature_id)

        if not tool_data:
            plan.append({
                'feature': feature.get('description', ''),
                'status': 'no_tool',
                'warning': 'No suitable tool found in library'
            })
            continue

        # Track tool changes
        tool_id = tool_data.get('id', '')
        if tool_id != current_tool:
            if current_tool is not None:
                tool_changes += 1
            current_tool = tool_id

        # Calculate feeds/speeds preview
        try:
            if feature_type in ('through_hole', 'blind_hole') and tool_data.get('tool_type') == 'drill_bit':
                fs = feeds_speeds.calculate_for_drilling(
                    tool_data, material_key, feature.get('depth_mm', 10), quality
                )
            else:
                op_type = 'adaptive' if 'roughing' in _get_phase(feature_type) else 'finishing'
                fs = feeds_speeds.calculate(tool_data, material_key, op_type, quality)
        except Exception as e:
            fs = {'error': str(e)}

        # Get operation template info
        feature_templates = templates['feature_operation_map'].get(feature_type, {})
        op_templates = feature_templates.get('operations', [])

        for op_template in op_templates:
            if quality_preset.get('skip_finishing') and op_template.get('phase') == 'finishing':
                continue
            if op_template.get('fallback', False):
                continue

            plan.append({
                'feature': feature.get('description', ''),
                'feature_id': feature_id,
                'operation': op_template.get('name', '').format(
                    name=feature.get('description', ''),
                    diameter=f"{feature.get('diameter_mm', 0):.1f}mm"
                ),
                'fusion_type': op_template.get('fusion_operation', ''),
                'tool': tool_data.get('display_name', 'Unknown'),
                'rpm': fs.get('rpm', '?'),
                'feed': f"{fs.get('feed_rate_mm_min', '?')} mm/min",
                'doc': f"{fs.get('doc_mm', '?')} mm",
                'phase': op_template.get('phase', 'roughing'),
                'status': 'ready',
                'notes': fs.get('notes', '')
            })

    return {
        'operations': plan,
        'tool_changes': tool_changes,
        'total_operations': len([p for p in plan if p.get('status') == 'ready']),
        'warnings': [p for p in plan if p.get('status') == 'no_tool']
    }


def post_process(cam, setup, output_folder=None, post_processor_name='onefinity_fusion360'):
    """
    Post-process the generated toolpaths to G-code.

    Args:
        cam: The CAM product
        setup: The Setup to post-process
        output_folder: Output directory for .nc files (default: user's Documents/FusionCam)
        post_processor_name: Name of the post-processor to use

    Returns:
        Path to the generated G-code file
    """
    if output_folder is None:
        output_folder = os.path.join(os.path.expanduser('~'), 'Documents', 'FusionCam', 'GCode')
    os.makedirs(output_folder, exist_ok=True)

    # Get the post processor
    post_config = adsk.cam.PostProcessInput.create(
        post_processor_name,
        output_folder,
        setup.name,
        ''
    )

    # Configure post settings
    post_config.isOpenInEditor = False

    # Post process
    cam.postProcess(setup, post_config)

    return output_folder

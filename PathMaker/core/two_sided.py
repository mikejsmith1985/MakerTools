"""
Two-Sided Carving System for FusionCam.
Manages the workflow for machining parts that require flipping:
- Side A/B feature classification
- Dowel pin alignment hole generation
- Coordinate system transformation for flip
- Step-by-step guided workflow
"""

import adsk.core
import adsk.fusion
import adsk.cam
import math
import json
import os

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(ADDIN_DIR, 'config')


class TwoSidedWorkflow:
    """Manages a complete 2-sided machining workflow."""

    def __init__(self, body, features, alignment_method='dowel_pins'):
        """
        Args:
            body: The BRep body to machine
            features: Analyzed features from geometry_analyzer
            alignment_method: 'dowel_pins' or 'corner_registration'
        """
        self.body = body
        self.features = features
        self.alignment_method = alignment_method
        self.side_a_features = []
        self.side_b_features = []
        self.both_features = []
        self.dowel_positions = []
        self.flip_axis = 'X'  # Flip around X axis by default

        self._classify_features()

    def _classify_features(self):
        """Classify features into Side A, Side B, or Both."""
        bb = self.body.boundingBox
        mid_z_cm = (bb.maxPoint.z + bb.minPoint.z) / 2
        self.part_thickness_mm = (bb.maxPoint.z - bb.minPoint.z) * 10.0

        for feature in self.features:
            ftype = feature.get('type', '')
            fid = feature.get('id', '')

            if feature.get('is_through', False):
                self.both_features.append(feature)
            elif ftype == 'face':
                self.side_a_features.append(feature)
            else:
                # Default: accessible from top = Side A
                # In a more sophisticated version, we'd check face normals
                self.side_a_features.append(feature)

    @property
    def needs_two_sided(self):
        """Check if the part actually needs 2-sided machining."""
        return len(self.side_b_features) > 0 or len(self.both_features) > 0

    def calculate_dowel_positions(self, stock_width_mm, stock_height_mm, margin_mm=10.0):
        """
        Calculate optimal dowel pin positions outside the part boundary.

        Places 2 pins along the longest stock edge, outside the part but within stock.
        The pins should be:
        - At least margin_mm from the part boundary
        - At least margin_mm from the stock edge
        - Asymmetric (different distances from edges) to prevent 180deg rotation error

        Args:
            stock_width_mm: Stock width (X dimension)
            stock_height_mm: Stock height (Y dimension)
            margin_mm: Minimum margin from part and stock edges

        Returns:
            List of 2 (x, y) tuples for pin positions in mm
        """
        bb = self.body.boundingBox
        part_min_x = bb.minPoint.x * 10.0  # cm to mm
        part_max_x = bb.maxPoint.x * 10.0
        part_min_y = bb.minPoint.y * 10.0
        part_max_y = bb.maxPoint.y * 10.0

        # Place pins along the X axis (longer axis typically)
        # Pin 1: near left side, offset from center Y
        # Pin 2: near right side, offset from center Y (asymmetric)

        stock_center_y = stock_height_mm / 2.0

        # Try to place pins between part edge and stock edge
        # Check if there's room on the left/right sides
        left_space = part_min_x - 0  # Space between stock left edge and part
        right_space = stock_width_mm - part_max_x

        if left_space >= (margin_mm * 2 + 5):  # 5mm for pin diameter
            pin1_x = margin_mm + 2.5  # Center of pin
        else:
            pin1_x = part_min_x - margin_mm - 2.5

        if right_space >= (margin_mm * 2 + 5):
            pin2_x = stock_width_mm - margin_mm - 2.5
        else:
            pin2_x = part_max_x + margin_mm + 2.5

        # Asymmetric Y positions to prevent rotation error
        pin1_y = stock_center_y - stock_height_mm * 0.25
        pin2_y = stock_center_y + stock_height_mm * 0.15  # Intentionally asymmetric

        self.dowel_positions = [
            (round(pin1_x, 2), round(pin1_y, 2)),
            (round(pin2_x, 2), round(pin2_y, 2))
        ]

        return self.dowel_positions

    def get_dowel_drill_features(self, pin_diameter_mm=4.0, stock_thickness_mm=None):
        """
        Generate drilling features for alignment dowel pin holes.
        These are added to Side A operations.

        Args:
            pin_diameter_mm: Dowel pin diameter (default 4mm / ~5/32")
            stock_thickness_mm: Stock thickness for through-hole calculation

        Returns:
            List of hole feature dicts to add to Side A
        """
        if not self.dowel_positions:
            return []

        if stock_thickness_mm is None:
            stock_thickness_mm = self.part_thickness_mm + 2.0  # 2mm offset

        holes = []
        for i, (x, y) in enumerate(self.dowel_positions):
            holes.append({
                'id': f'dowel_pin_{i+1}',
                'type': 'through_hole',
                'center_x_mm': x,
                'center_y_mm': y,
                'diameter_mm': pin_diameter_mm,
                'diameter_inches': round(pin_diameter_mm / 25.4, 4),
                'depth_mm': stock_thickness_mm,
                'is_through': True,
                'is_alignment': True,
                'min_radius_mm': pin_diameter_mm / 2,
                'description': f'Alignment dowel pin hole {i+1} ({pin_diameter_mm}mm) at ({x:.1f}, {y:.1f})'
            })

        return holes

    def get_side_a_setup_config(self, stock_config):
        """Get the setup configuration for Side A machining."""
        config = dict(stock_config)
        config['name'] = 'FusionCam - Side A (Top)'
        config['wcs_origin'] = 'top_left'
        config['notes'] = (
            'Side A: Machine all top-accessible features.\n'
            'Alignment pin holes are drilled FIRST for registration.'
        )
        return config

    def get_side_b_setup_config(self, stock_config):
        """
        Get the setup configuration for Side B machining.
        The coordinate system is flipped to account for the stock flip.
        """
        config = dict(stock_config)
        config['name'] = 'FusionCam - Side B (Bottom)'

        if self.flip_axis == 'X':
            # Flip around X axis: Y is inverted, Z is inverted
            config['wcs_flip'] = 'around_x'
            config['notes'] = (
                'Side B: Stock has been flipped around the X axis.\n'
                'X coordinates are preserved, Y is mirrored.\n'
                'Re-zero Z to the new top surface only.'
            )
        else:
            # Flip around Y axis: X is inverted, Z is inverted
            config['wcs_flip'] = 'around_y'
            config['notes'] = (
                'Side B: Stock has been flipped around the Y axis.\n'
                'Y coordinates are preserved, X is mirrored.\n'
                'Re-zero Z to the new top surface only.'
            )

        return config

    def get_flip_instructions(self):
        """
        Generate step-by-step instructions for flipping the stock.
        Returns a list of instruction strings.
        """
        if self.alignment_method == 'dowel_pins':
            return self._dowel_pin_instructions()
        else:
            return self._corner_registration_instructions()

    def _dowel_pin_instructions(self):
        """Instructions for dowel pin flip workflow."""
        pin_positions = self.dowel_positions
        if not pin_positions:
            return ["Error: Dowel pin positions not calculated. Run calculate_dowel_positions() first."]

        instructions = [
            "=== 2-SIDED CARVING: FLIP PROCEDURE ===",
            "",
            "Side A machining is complete. Follow these steps to flip for Side B:",
            "",
            "Step 1: DO NOT MOVE THE MACHINE",
            "  - Leave the spindle where it is",
            "  - Do not re-home or jog the machine",
            "",
            "Step 2: INSERT DOWEL PINS",
            f"  - Insert a dowel pin into hole at ({pin_positions[0][0]:.1f}, {pin_positions[0][1]:.1f})mm",
            f"  - Insert a dowel pin into hole at ({pin_positions[1][0]:.1f}, {pin_positions[1][1]:.1f})mm",
            "  - Pins should fit snugly but not require force",
            "",
            f"Step 3: FLIP THE STOCK AROUND THE {self.flip_axis} AXIS",
            "  - Carefully lift the stock off the bed",
            f"  - Rotate 180 degrees around the {self.flip_axis} axis (left-to-right flip)" if self.flip_axis == 'X'
                else f"  - Rotate 180 degrees around the {self.flip_axis} axis (front-to-back flip)",
            "  - Lower the stock back onto the dowel pins",
            "  - The pins will locate the stock precisely",
            "",
            "Step 4: SECURE THE STOCK",
            "  - Clamp/tape the stock to the wasteboard",
            "  - Ensure the stock is flat against the bed",
            "  - The dowel pins maintain XY alignment",
            "",
            "Step 5: RE-ZERO Z AXIS ONLY",
            "  - Use a touch plate or paper method to zero Z on the NEW top surface",
            "  - DO NOT change X or Y zero — the pins maintain this",
            "",
            "Step 6: LOAD SIDE B G-CODE",
            "  - Load the Side B .nc file into the Onefinity controller",
            "  - Verify the first move is safe (not into clamps)",
            "  - Run Side B operations",
            "",
            "=== IMPORTANT NOTES ===",
            f"  - Part thickness: {self.part_thickness_mm:.1f}mm",
            "  - The two pin holes are intentionally asymmetric to prevent 180-degree rotation error",
            "  - If the pins don't line up, the stock is flipped the wrong way",
            "  - Keep the router/spindle OFF while inserting pins and flipping",
        ]
        return instructions

    def _corner_registration_instructions(self):
        """Instructions for corner registration flip workflow."""
        return [
            "=== 2-SIDED CARVING: CORNER REGISTRATION ===",
            "",
            "Side A machining is complete. Follow these steps to flip for Side B:",
            "",
            "Step 1: NOTE YOUR REGISTRATION CORNER",
            "  - The front-left corner of the stock is the reference point",
            "  - This corner stays in the same physical location after flip",
            "",
            "Step 2: REMOVE CLAMPS",
            "  - Carefully remove clamps/tape",
            "  - Do not bump the stock or move it yet",
            "",
            f"Step 3: FLIP THE STOCK AROUND THE {self.flip_axis} AXIS",
            "  - Carefully lift and flip the stock",
            "  - Place the registration corner back in the same position",
            "  - Use a fence, stop block, or vise jaw for precise placement",
            "",
            "Step 4: SECURE AND RE-ZERO",
            "  - Clamp the stock securely",
            "  - Re-zero Z to the new top surface",
            "  - Verify X/Y zero matches the registration corner",
            "",
            "Step 5: LOAD SIDE B G-CODE AND RUN",
            "",
            "NOTE: Corner registration is less precise than dowel pins.",
            "Expect +/- 0.5mm alignment accuracy depending on your setup.",
            "For critical features, consider upgrading to dowel pin alignment.",
        ]

    def get_summary(self):
        """Get a summary of the 2-sided workflow."""
        return {
            'needs_two_sided': self.needs_two_sided,
            'alignment_method': self.alignment_method,
            'side_a_feature_count': len(self.side_a_features),
            'side_b_feature_count': len(self.side_b_features),
            'shared_feature_count': len(self.both_features),
            'part_thickness_mm': round(self.part_thickness_mm, 2),
            'dowel_positions': self.dowel_positions,
            'flip_axis': self.flip_axis
        }

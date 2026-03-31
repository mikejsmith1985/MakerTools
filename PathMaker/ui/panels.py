"""
Custom panel layouts for FusionCam dialogs.
Provides reusable UI building blocks for complex dialogs.
"""

import adsk.core


def add_tool_review_table(inputs, tool_data):
    """Add a formatted tool review table to a command input group."""
    fields = [
        ('Type', tool_data.get('tool_type', '?').replace('_', ' ').title()),
        ('Diameter', f"{tool_data.get('diameter_inches', 0)}\" ({tool_data.get('diameter_mm', 0)}mm)"),
        ('Shank', f"{tool_data.get('shank_diameter_inches', 0)}\" ({tool_data.get('shank_diameter_mm', 0)}mm)"),
        ('Flutes', str(tool_data.get('flute_count', '?'))),
        ('Flute Length', f"{tool_data.get('flute_length_inches', 0)}\" ({tool_data.get('flute_length_mm', 0)}mm)"),
        ('Overall Length', f"{tool_data.get('overall_length_inches', 0)}\" ({tool_data.get('overall_length_mm', 0)}mm)"),
        ('Material', tool_data.get('material', '?')),
        ('Coating', tool_data.get('coating', '?')),
        ('Brand', tool_data.get('brand', '?')),
    ]

    html = '<table>'
    for label, value in fields:
        html += f'<tr><td><b>{label}:</b></td><td>{value}</td></tr>'
    html += '</table>'

    inputs.addTextBoxCommandInput('toolReview', 'Specifications', html, len(fields) + 1, True)


def add_feeds_speeds_display(inputs, fs_data, input_id_prefix='fs'):
    """Add a feeds & speeds display to a command input group."""
    html = (
        f"<b>RPM:</b> {fs_data.get('rpm', '?')} (Dial {fs_data.get('rpm_dial_setting', '?')})<br>"
        f"<b>Feed Rate:</b> {fs_data.get('feed_rate_mm_min', '?')} mm/min ({fs_data.get('feed_rate_ipm', '?')} ipm)<br>"
        f"<b>Plunge Rate:</b> {fs_data.get('plunge_rate_mm_min', '?')} mm/min<br>"
        f"<b>Depth of Cut:</b> {fs_data.get('doc_mm', '?')} mm ({fs_data.get('doc_inches', '?')}\")<br>"
        f"<b>Stepover:</b> {fs_data.get('woc_mm', '?')} mm ({fs_data.get('woc_inches', '?')}\")<br>"
        f"<b>Chipload:</b> {fs_data.get('chipload_inches', '?')}\" per tooth<br>"
    )

    notes = fs_data.get('notes', '')
    if notes:
        html += f"<br><i>{notes}</i>"

    inputs.addTextBoxCommandInput(
        f'{input_id_prefix}_display', 'Feeds & Speeds', html, 8, True
    )


def add_operation_plan_table(inputs, plan_data):
    """Add an operation plan table to a command input group."""
    ops = plan_data.get('operations', [])

    html = '<table style="width:100%">'
    html += '<tr><th>Operation</th><th>Tool</th><th>RPM</th><th>Feed</th></tr>'

    for op in ops:
        status = op.get('status', 'ready')
        color = '#333' if status == 'ready' else '#c00'
        html += (
            f'<tr style="color:{color}">'
            f'<td>{op.get("operation", "?")}</td>'
            f'<td>{op.get("tool", "?")}</td>'
            f'<td>{op.get("rpm", "?")}</td>'
            f'<td>{op.get("feed", "?")}</td>'
            f'</tr>'
        )

    html += '</table>'

    summary = (
        f"Total Operations: {plan_data.get('total_operations', 0)} | "
        f"Tool Changes: {plan_data.get('tool_changes', 0)}"
    )

    inputs.addTextBoxCommandInput('planTable', 'Operation Plan', html, min(len(ops) + 2, 15), True)
    inputs.addTextBoxCommandInput('planSummary', 'Summary', summary, 1, True)

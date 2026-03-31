"""
Tool Parser for FusionCam — Extracts CNC tool specs from Amazon product pages.
Uses urllib to fetch pages and AI to parse specifications.
"""

import json
import os
import re
import urllib.request
import urllib.error
import html.parser

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ADDIN_DIR, 'data')

# User-agent to avoid Amazon blocking
USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/120.0.0.0 Safari/537.36'
)


class _SimpleHTMLStripper(html.parser.HTMLParser):
    """Strip HTML tags and extract text content."""

    def __init__(self):
        super().__init__()
        self._pieces = []
        self._skip = False
        self._skip_tags = {'script', 'style', 'noscript'}

    def handle_starttag(self, tag, attrs):
        if tag in self._skip_tags:
            self._skip = True
        if tag in ('br', 'p', 'div', 'li', 'tr', 'h1', 'h2', 'h3', 'h4'):
            self._pieces.append('\n')

    def handle_endtag(self, tag):
        if tag in self._skip_tags:
            self._skip = False

    def handle_data(self, data):
        if not self._skip:
            self._pieces.append(data)

    def get_text(self):
        text = ''.join(self._pieces)
        # Collapse whitespace
        text = re.sub(r'[ \t]+', ' ', text)
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()


def _strip_html(html_content):
    """Convert HTML to plain text."""
    stripper = _SimpleHTMLStripper()
    stripper.feed(html_content)
    return stripper.get_text()


def _extract_product_section(html_content):
    """
    Extract the most relevant product information sections from Amazon HTML.
    Focuses on: title, feature bullets, product details table, description.
    """
    sections = []

    # Product title
    title_match = re.search(r'id="productTitle"[^>]*>(.*?)</span>', html_content, re.DOTALL)
    if title_match:
        sections.append(f"TITLE: {_strip_html(title_match.group(1)).strip()}")

    # Feature bullets
    bullets_match = re.search(r'id="feature-bullets"(.*?)</div>\s*</div>', html_content, re.DOTALL)
    if bullets_match:
        bullet_text = _strip_html(bullets_match.group(1))
        sections.append(f"FEATURES:\n{bullet_text.strip()}")

    # Technical details table
    tech_match = re.search(r'id="productDetails_techSpec_section_1"(.*?)</table>', html_content, re.DOTALL)
    if tech_match:
        tech_text = _strip_html(tech_match.group(1))
        sections.append(f"TECHNICAL DETAILS:\n{tech_text.strip()}")

    # Product details bullets
    detail_match = re.search(r'id="detailBullets_feature_div"(.*?)</div>', html_content, re.DOTALL)
    if detail_match:
        detail_text = _strip_html(detail_match.group(1))
        sections.append(f"PRODUCT DETAILS:\n{detail_text.strip()}")

    # Product description
    desc_match = re.search(r'id="productDescription"(.*?)</div>', html_content, re.DOTALL)
    if desc_match:
        desc_text = _strip_html(desc_match.group(1))
        sections.append(f"DESCRIPTION:\n{desc_text.strip()}")

    if sections:
        return '\n\n'.join(sections)

    # Fallback: strip the whole page
    return _strip_html(html_content)[:6000]


def fetch_product_page(url):
    """
    Fetch an Amazon product page and extract relevant text content.

    Args:
        url: Amazon product URL

    Returns:
        Tuple of (extracted_text, full_url) or raises an exception
    """
    # Normalize Amazon URL
    url = url.strip()
    if not url.startswith('http'):
        url = 'https://' + url

    req = urllib.request.Request(url, headers={
        'User-Agent': USER_AGENT,
        'Accept': 'text/html,application/xhtml+xml',
        'Accept-Language': 'en-US,en;q=0.9',
    })

    with urllib.request.urlopen(req, timeout=30) as response:
        html_content = response.read().decode('utf-8', errors='replace')

    product_text = _extract_product_section(html_content)

    if len(product_text) < 50:
        raise ValueError(
            'Could not extract product information from page. '
            'Amazon may be blocking automated requests. '
            'Try copying the product title and bullet points manually.'
        )

    return product_text, url


def parse_tool_from_url(url):
    """
    Full pipeline: fetch Amazon URL → extract text → AI parse → return tool specs.

    Args:
        url: Amazon product URL

    Returns:
        Tuple of (tool_dict, raw_text) or raises exception
    """
    from . import ai_client

    page_text, final_url = fetch_product_page(url)
    tool_data = ai_client.parse_tool_from_url(page_text, final_url)

    if not tool_data:
        raise ValueError(
            'AI could not extract tool specifications from the product page. '
            'The page content may not contain enough information. '
            'Try using the manual entry form instead.'
        )

    # Validate required fields
    required = ['tool_type', 'diameter_inches', 'flute_count']
    missing = [f for f in required if not tool_data.get(f)]
    if missing:
        raise ValueError(f'AI response missing required fields: {", ".join(missing)}')

    # Ensure both unit systems
    if 'diameter_mm' not in tool_data and 'diameter_inches' in tool_data:
        tool_data['diameter_mm'] = round(tool_data['diameter_inches'] * 25.4, 3)
    if 'shank_diameter_mm' not in tool_data and 'shank_diameter_inches' in tool_data:
        tool_data['shank_diameter_mm'] = round(tool_data['shank_diameter_inches'] * 25.4, 3)
    if 'flute_length_mm' not in tool_data and 'flute_length_inches' in tool_data:
        tool_data['flute_length_mm'] = round(tool_data['flute_length_inches'] * 25.4, 3)
    if 'overall_length_mm' not in tool_data and 'overall_length_inches' in tool_data:
        tool_data['overall_length_mm'] = round(tool_data['overall_length_inches'] * 25.4, 3)

    return tool_data, page_text


def parse_tool_from_text(text):
    """
    Parse tool specs from user-provided text (copied from product page).
    Useful as fallback when URL fetching fails.
    """
    from . import ai_client

    tool_data = ai_client.parse_tool_from_url(text)

    if not tool_data:
        return None

    # Same validation as URL path
    if 'diameter_mm' not in tool_data and 'diameter_inches' in tool_data:
        tool_data['diameter_mm'] = round(tool_data['diameter_inches'] * 25.4, 3)

    return tool_data


def create_manual_tool(tool_type, diameter_inches, flute_count, shank_diameter_inches=None,
                       flute_length_inches=None, overall_length_inches=None, material='carbide',
                       coating='uncoated', notes=''):
    """
    Create a tool entry from manual input.
    Fills in reasonable defaults for missing values.
    """
    if shank_diameter_inches is None:
        shank_diameter_inches = diameter_inches  # Most common: shank = diameter

    if flute_length_inches is None:
        # Typical flute length is 3-4x diameter
        flute_length_inches = diameter_inches * 3

    if overall_length_inches is None:
        # Typical OAL is flute length + 1.5x shank
        overall_length_inches = flute_length_inches + (shank_diameter_inches * 1.5)

    return {
        'tool_type': tool_type,
        'brand': 'Manual Entry',
        'model': None,
        'diameter_inches': diameter_inches,
        'diameter_mm': round(diameter_inches * 25.4, 3),
        'shank_diameter_inches': shank_diameter_inches,
        'shank_diameter_mm': round(shank_diameter_inches * 25.4, 3),
        'flute_count': flute_count,
        'flute_length_inches': flute_length_inches,
        'flute_length_mm': round(flute_length_inches * 25.4, 3),
        'overall_length_inches': overall_length_inches,
        'overall_length_mm': round(overall_length_inches * 25.4, 3),
        'helix_angle_degrees': 30 if tool_type != 'drill_bit' else 118,
        'corner_radius_inches': None,
        'v_angle_degrees': None,
        'material': material,
        'coating': coating,
        'suitable_materials': [],
        'product_url': '',
        'notes': notes,
        'confidence': 'manual'
    }


# --- Tool Library Persistence ---

def _load_tool_library():
    """Load the persistent tool library."""
    path = os.path.join(DATA_DIR, 'tool_library.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'tools': [], 'version': 1}


def _save_tool_library(library):
    """Save the persistent tool library."""
    path = os.path.join(DATA_DIR, 'tool_library.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(library, f, indent=2)


def add_tool(tool_data):
    """Add a tool to the persistent library. Returns the tool's ID."""
    library = _load_tool_library()

    # Generate an ID
    tool_id = f"tool_{len(library['tools']) + 1:03d}"
    tool_data['id'] = tool_id

    # Generate a display name
    if not tool_data.get('display_name'):
        diameter = tool_data.get('diameter_inches', 0)
        tool_type = tool_data.get('tool_type', 'endmill').replace('_', ' ').title()
        flutes = tool_data.get('flute_count', '?')
        brand = tool_data.get('brand', '')
        tool_data['display_name'] = f'{diameter}" {flutes}F {tool_type} ({brand})'.strip()

    library['tools'].append(tool_data)
    _save_tool_library(library)

    return tool_id


def get_all_tools():
    """Get all tools in the library."""
    library = _load_tool_library()
    return library.get('tools', [])


def get_tool(tool_id):
    """Get a tool by ID."""
    for tool in get_all_tools():
        if tool.get('id') == tool_id:
            return tool
    return None


def remove_tool(tool_id):
    """Remove a tool from the library."""
    library = _load_tool_library()
    library['tools'] = [t for t in library['tools'] if t.get('id') != tool_id]
    _save_tool_library(library)


def find_tools_for_feature(feature, tools=None):
    """
    Find suitable tools for a given feature from the library.

    Args:
        feature: Dict with 'type', 'min_radius_mm', 'depth_mm', etc.
        tools: Optional tool list (defaults to full library)

    Returns:
        List of suitable tools, sorted best-first
    """
    if tools is None:
        tools = get_all_tools()

    suitable = []
    feature_type = feature.get('type', '')
    min_radius_mm = feature.get('min_radius_mm', float('inf'))
    depth_mm = feature.get('depth_mm', 0)

    for tool in tools:
        tool_radius_mm = tool.get('diameter_mm', 0) / 2
        flute_length_mm = tool.get('flute_length_mm', 0)

        # Tool radius must fit in the feature
        if tool_radius_mm > min_radius_mm:
            continue

        # Flute length must reach the depth
        if flute_length_mm < depth_mm * 0.8:
            continue

        # Match tool type to feature type
        tool_type = tool.get('tool_type', '')

        if feature_type in ('through_hole', 'blind_hole'):
            if tool_type in ('drill_bit', 'flat_endmill'):
                suitable.append(tool)
        elif feature_type == 'chamfer':
            if tool_type in ('v_bit', 'chamfer_mill'):
                suitable.append(tool)
        elif feature_type == '3d_surface':
            if tool_type in ('ball_endmill', 'bull_nose_endmill', 'flat_endmill'):
                suitable.append(tool)
        else:
            # Pockets, profiles, bosses, face — endmills
            if tool_type in ('flat_endmill', 'bull_nose_endmill'):
                suitable.append(tool)

    # Sort: largest diameter first (faster, more rigid)
    suitable.sort(key=lambda t: t.get('diameter_mm', 0), reverse=True)

    return suitable

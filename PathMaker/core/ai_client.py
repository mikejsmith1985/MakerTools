"""
AI Client for FusionCam — GitHub Models API Integration.
Follows the CodeReader pattern: prompt templates, multi-level token resolution,
test-before-save, caching, and fallback to heuristics.
"""

import json
import os
import urllib.request
import urllib.error

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ADDIN_DIR, 'data')

API_ENDPOINT = 'https://models.inference.ai.azure.com/chat/completions'
MODEL = 'gpt-4o-mini'
MAX_TOKENS = 4096
TEMPERATURE = 0.3

# --- Token Management (CodeReader pattern: DB → env → prompt) ---

_token_cache = None


def _load_settings():
    """Load user settings from JSON file."""
    path = os.path.join(DATA_DIR, 'user_settings.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}


def _save_settings(settings):
    """Save user settings to JSON file."""
    path = os.path.join(DATA_DIR, 'user_settings.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(settings, f, indent=2)


def get_token():
    """
    Multi-level token resolution:
    1. Cached in-memory token (fastest)
    2. Saved token from user_settings.json
    3. Environment variable FUSIONCAM_GITHUB_TOKEN
    4. Environment variable GITHUB_MODELS_TOKEN
    Returns None if no token found.
    """
    global _token_cache

    if _token_cache:
        return _token_cache

    settings = _load_settings()
    token = settings.get('ai_token', '').strip()
    if token:
        _token_cache = token
        return token

    for env_var in ['FUSIONCAM_GITHUB_TOKEN', 'GITHUB_MODELS_TOKEN']:
        token = os.environ.get(env_var, '').strip()
        if token:
            _token_cache = token
            return token

    return None


def clear_token_cache():
    """Clear the in-memory token cache (call after token update)."""
    global _token_cache
    _token_cache = None


def save_token(token):
    """Save an AI token to user settings."""
    settings = _load_settings()
    settings['ai_token'] = token.strip()
    settings['ai_token_validated'] = False
    _save_settings(settings)
    clear_token_cache()


def test_token(token):
    """
    Validate a token by making a minimal API call.
    Returns (success: bool, message: str).
    """
    try:
        messages = [
            {'role': 'system', 'content': 'Respond with exactly: OK'},
            {'role': 'user', 'content': 'Test'}
        ]
        result = _call_api(messages, token=token, max_tokens=10)
        if result and 'OK' in result:
            settings = _load_settings()
            settings['ai_token_validated'] = True
            _save_settings(settings)
            return True, 'Token validated successfully!'
        return False, f'Unexpected response: {result}'
    except urllib.error.HTTPError as e:
        if e.code == 401:
            return False, 'Invalid token (401 Unauthorized). Check your GitHub personal access token.'
        elif e.code == 403:
            return False, 'Token lacks permissions (403 Forbidden). Ensure GitHub Models API access.'
        elif e.code == 429:
            return False, 'Rate limited (429). Token works but you\'re making too many requests.'
        return False, f'HTTP Error {e.code}: {e.reason}'
    except Exception as e:
        return False, f'Connection error: {str(e)}'


def has_valid_token():
    """Check if a validated token is available."""
    token = get_token()
    if not token:
        return False
    settings = _load_settings()
    return settings.get('ai_token_validated', False)


# --- API Communication ---

def _call_api(messages, token=None, max_tokens=None, temperature=None):
    """
    Make a request to the GitHub Models API.
    Returns the response text content, or None on failure.
    """
    if token is None:
        token = get_token()
    if not token:
        return None

    payload = json.dumps({
        'model': MODEL,
        'messages': messages,
        'max_tokens': max_tokens or MAX_TOKENS,
        'temperature': temperature if temperature is not None else TEMPERATURE
    }).encode('utf-8')

    req = urllib.request.Request(
        API_ENDPOINT,
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {token}'
        },
        method='POST'
    )

    with urllib.request.urlopen(req, timeout=60) as response:
        result = json.loads(response.read().decode('utf-8'))
        choices = result.get('choices', [])
        if choices:
            return choices[0].get('message', {}).get('content', '')
    return None


def _parse_json_response(text):
    """Extract and parse JSON from an AI response that may contain markdown fences."""
    if not text:
        return None

    text = text.strip()

    # Try to find JSON block in markdown code fences
    if '```json' in text:
        start = text.index('```json') + 7
        end = text.index('```', start)
        text = text[start:end].strip()
    elif '```' in text:
        start = text.index('```') + 3
        end = text.index('```', start)
        text = text[start:end].strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find JSON object or array
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start >= 0:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == start_char:
                    depth += 1
                elif text[i] == end_char:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break

    return None


# --- Caching ---

def _load_cache():
    """Load the feeds/speeds cache."""
    path = os.path.join(DATA_DIR, 'feeds_speeds_cache.json')
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {'cache': {}, 'version': 1}


def _save_cache(cache_data):
    """Save the feeds/speeds cache."""
    path = os.path.join(DATA_DIR, 'feeds_speeds_cache.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(cache_data, f, indent=2)


def get_cached(cache_key):
    """Get a cached AI response by key."""
    cache = _load_cache()
    return cache.get('cache', {}).get(cache_key)


def set_cached(cache_key, value):
    """Cache an AI response by key."""
    cache = _load_cache()
    cache['cache'][cache_key] = value
    _save_cache(cache)


# --- Prompt Templates (Configuration-driven, like CodeReader's depth prompts) ---

PROMPTS = {
    'tool_parse': {
        'system': (
            'You are an expert CNC machinist tool librarian. You extract precise cutting tool '
            'specifications from product listings. You MUST return valid JSON matching the exact '
            'schema provided. Be precise with measurements — convert everything to consistent units. '
            'If a specification is ambiguous or missing, use your expert knowledge to provide the '
            'most likely value and mark it with "estimated": true in that field.\n\n'
            'IMPORTANT: SpeTool is a common brand on Amazon. Their naming convention usually includes '
            'diameter, flute count, and material in the title. Bullet points contain detailed specs.'
        ),
        'user': (
            'Extract CNC cutting tool specifications from this product listing and return as JSON.\n\n'
            'PRODUCT PAGE CONTENT:\n{page_content}\n\n'
            'Return JSON with this exact schema:\n'
            '{{\n'
            '  "tool_type": "flat_endmill|ball_endmill|bull_nose_endmill|v_bit|drill_bit|spot_drill|chamfer_mill",\n'
            '  "brand": "string",\n'
            '  "model": "string or null",\n'
            '  "diameter_inches": number,\n'
            '  "diameter_mm": number,\n'
            '  "shank_diameter_inches": number,\n'
            '  "shank_diameter_mm": number,\n'
            '  "flute_count": integer,\n'
            '  "flute_length_inches": number,\n'
            '  "flute_length_mm": number,\n'
            '  "overall_length_inches": number,\n'
            '  "overall_length_mm": number,\n'
            '  "helix_angle_degrees": number or null,\n'
            '  "corner_radius_inches": number or null,\n'
            '  "v_angle_degrees": number or null,\n'
            '  "material": "carbide|hss|cobalt",\n'
            '  "coating": "TiAlN|TiN|ZrN|TiB2|AlTiN|DLC|uncoated|other",\n'
            '  "suitable_materials": ["aluminum", "wood", "plastic", ...],\n'
            '  "product_url": "string",\n'
            '  "notes": "string",\n'
            '  "confidence": "high|medium|low"\n'
            '}}\n\n'
            'RULES:\n'
            '- diameter_inches and diameter_mm must BOTH be provided (convert if needed)\n'
            '- If V-bit, include v_angle_degrees\n'
            '- If bull nose, include corner_radius_inches\n'
            '- flute_count is critical — count carefully from description\n'
            '- suitable_materials should list what the manufacturer recommends'
        )
    },
    'feeds_speeds': {
        'system': (
            'You are an expert CNC machinist specializing in feeds and speeds calculation '
            'for hobby CNC machines. You understand that hobby machines like the Onefinity are '
            'less rigid than industrial VMCs and require conservative parameters.\n\n'
            'CRITICAL SAFETY RULES:\n'
            '- Always err on the side of conservative (slower, shallower)\n'
            '- Account for the machine rigidity factor provided\n'
            '- RPM must be within the spindle range\n'
            '- Feed rate must be within machine max feed rate\n'
            '- For aluminum: ALWAYS recommend some form of lubrication\n'
            '- For wood: watch for burning at low feeds\n'
            '- Plunge rates should be 30-50% of XY feed rate'
        ),
        'user': (
            'Calculate feeds and speeds for this tool + material + machine combination.\n\n'
            'TOOL:\n{tool_json}\n\n'
            'MATERIAL:\n{material_json}\n\n'
            'MACHINE:\n{machine_json}\n\n'
            'OPERATION TYPE: {operation_type}\n\n'
            'Return JSON:\n'
            '{{\n'
            '  "rpm": integer,\n'
            '  "rpm_dial_setting": integer (1-6, nearest Makita RT0701C dial),\n'
            '  "feed_rate_mm_min": number,\n'
            '  "feed_rate_ipm": number,\n'
            '  "plunge_rate_mm_min": number,\n'
            '  "doc_mm": number (depth of cut per pass),\n'
            '  "woc_mm": number (width of cut / stepover),\n'
            '  "doc_inches": number,\n'
            '  "woc_inches": number,\n'
            '  "chipload_inches": number,\n'
            '  "sfm": number,\n'
            '  "notes": "string with any warnings or tips",\n'
            '  "confidence": "high|medium|low"\n'
            '}}'
        )
    },
    'material_add': {
        'system': (
            'You are an expert CNC machinist who creates material cutting profiles for hobby CNC '
            'machines. You will generate a complete material profile that includes recommended '
            'cutting parameters for various tool diameters.\n\n'
            'IMPORTANT:\n'
            '- The machine is a Onefinity Machinist (hobby CNC, belt-driven, rigidity_factor 0.6)\n'
            '- Spindle is a Makita RT0701C router (9,600-30,000 RPM, dial 1-6)\n'
            '- All chipload values must be conservative for hobby CNC\n'
            '- Include practical notes for the specific material'
        ),
        'user': (
            'Create a complete material cutting profile for: {material_name}\n\n'
            'The profile will be used on a Onefinity Machinist CNC with Makita RT0701C router.\n\n'
            'Return JSON matching this exact schema:\n'
            '{{\n'
            '  "name": "string (display name)",\n'
            '  "category": "metal|wood|plastic|composite|foam",\n'
            '  "hardness": "very_soft|soft|medium|hard|very_hard",\n'
            '  "machinability_rating": number (0.0-1.0),\n'
            '  "sfm_range": {{"min": number, "max": number}},\n'
            '  "chipload_table": {{\n'
            '    "1/8": {{"min": number, "max": number, "recommended": number}},\n'
            '    "1/4": {{"min": number, "max": number, "recommended": number}},\n'
            '    "3/8": {{"min": number, "max": number, "recommended": number}},\n'
            '    "1/2": {{"min": number, "max": number, "recommended": number}}\n'
            '  }},\n'
            '  "chipload_unit": "inches per tooth",\n'
            '  "doc_multiplier": number (fraction of tool diameter),\n'
            '  "woc_multiplier_roughing": number,\n'
            '  "woc_multiplier_finishing": number,\n'
            '  "preferred_flute_count": integer,\n'
            '  "preferred_tool_material": "carbide|hss",\n'
            '  "preferred_coating": ["string"],\n'
            '  "coolant": "required|recommended|optional|none",\n'
            '  "coolant_notes": "string",\n'
            '  "notes": "string with practical tips for cutting this material"\n'
            '}}\n\n'
            'All chipload values in inches per tooth. Be conservative for hobby CNC.'
        )
    },
    'geometry_advice': {
        'system': (
            'You are an expert CNC CAM programmer. Given a description of detected geometric '
            'features on a part, you recommend the optimal machining strategy, operation order, '
            'and tool selection approach.\n\n'
            'CONTEXT:\n'
            '- Machine: Onefinity Machinist (3-axis hobby CNC)\n'
            '- Controller: Buildbotics (GRBL-compatible)\n'
            '- No automatic tool changer — minimize tool changes\n'
            '- Prefer adaptive/HSM clearing for roughing (less tool load)\n'
            '- Always use ramp/helix entry (never plunge into material)'
        ),
        'user': (
            'Recommend machining strategy for this part.\n\n'
            'DETECTED FEATURES:\n{features_json}\n\n'
            'AVAILABLE TOOLS:\n{tools_json}\n\n'
            'MATERIAL: {material_name}\n\n'
            'Return JSON:\n'
            '{{\n'
            '  "strategy_summary": "string",\n'
            '  "operation_plan": [\n'
            '    {{\n'
            '      "order": integer,\n'
            '      "feature_id": "string",\n'
            '      "operation_type": "string",\n'
            '      "tool_id": "string or null",\n'
            '      "reasoning": "string"\n'
            '    }}\n'
            '  ],\n'
            '  "tool_change_count": integer,\n'
            '  "warnings": ["string"],\n'
            '  "tips": ["string"]\n'
            '}}'
        )
    }
}


# --- Public API Functions ---

def parse_tool_from_url(page_content, product_url=''):
    """
    Use AI to extract tool specifications from a product page.
    Returns parsed tool dict or None.
    """
    prompt = PROMPTS['tool_parse']
    messages = [
        {'role': 'system', 'content': prompt['system']},
        {'role': 'user', 'content': prompt['user'].format(page_content=page_content[:8000])}
    ]

    response = _call_api(messages)
    result = _parse_json_response(response)

    if result and product_url:
        result['product_url'] = product_url

    return result


def get_ai_feeds_speeds(tool_data, material_data, machine_data, operation_type='roughing'):
    """
    Use AI to calculate feeds and speeds for a tool + material + machine combo.
    Checks cache first. Falls back to heuristic calculation if AI unavailable.
    """
    cache_key = f"{tool_data.get('diameter_inches', 0)}_{material_data.get('name', '')}_{operation_type}"
    cached = get_cached(cache_key)
    if cached:
        return cached

    prompt = PROMPTS['feeds_speeds']
    messages = [
        {'role': 'system', 'content': prompt['system']},
        {'role': 'user', 'content': prompt['user'].format(
            tool_json=json.dumps(tool_data, indent=2),
            material_json=json.dumps(material_data, indent=2),
            machine_json=json.dumps(machine_data, indent=2),
            operation_type=operation_type
        )}
    ]

    response = _call_api(messages)
    result = _parse_json_response(response)

    if result:
        set_cached(cache_key, result)
        return result

    # Fallback to heuristic calculation
    return None


def generate_material_profile(material_name):
    """
    Use AI to generate a complete material cutting profile.
    Returns material profile dict or None.
    """
    prompt = PROMPTS['material_add']
    messages = [
        {'role': 'system', 'content': prompt['system']},
        {'role': 'user', 'content': prompt['user'].format(material_name=material_name)}
    ]

    response = _call_api(messages)
    return _parse_json_response(response)


def get_geometry_advice(features, tools, material_name):
    """
    Use AI to recommend machining strategy for detected features.
    Returns strategy dict or None.
    """
    prompt = PROMPTS['geometry_advice']
    messages = [
        {'role': 'system', 'content': prompt['system']},
        {'role': 'user', 'content': prompt['user'].format(
            features_json=json.dumps(features, indent=2),
            tools_json=json.dumps(tools, indent=2),
            material_name=material_name
        )}
    ]

    response = _call_api(messages)
    return _parse_json_response(response)

"""
Post-Processor helpers for FusionCam.
Handles downloading, installing, and configuring the Onefinity post-processor.
"""

import os
import urllib.request
import json

ADDIN_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESOURCES_DIR = os.path.join(ADDIN_DIR, 'resources')
POST_DIR = os.path.join(RESOURCES_DIR, 'post_processors')

ONEFINITY_POST_URL = (
    'https://raw.githubusercontent.com/blaghislain/onefinity-post-processors/'
    'main/Fusion/onefinity_fusion360.cps'
)

ONEFINITY_MACHINE_URL = (
    'https://raw.githubusercontent.com/blaghislain/onefinity-post-processors/'
    'main/Fusion/Onefinity.Machinist.machine'
)


def ensure_post_processor():
    """
    Ensure the Onefinity post-processor is downloaded and available.
    Returns the path to the .cps file.
    """
    os.makedirs(POST_DIR, exist_ok=True)
    cps_path = os.path.join(POST_DIR, 'onefinity_fusion360.cps')

    if not os.path.exists(cps_path):
        download_post_processor()

    return cps_path


def download_post_processor():
    """Download the latest Onefinity post-processor from GitHub."""
    os.makedirs(POST_DIR, exist_ok=True)

    cps_path = os.path.join(POST_DIR, 'onefinity_fusion360.cps')
    machine_path = os.path.join(POST_DIR, 'Onefinity.Machinist.machine')

    try:
        # Download post-processor
        req = urllib.request.Request(ONEFINITY_POST_URL, headers={
            'User-Agent': 'FusionCam/0.1'
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(cps_path, 'wb') as f:
                f.write(response.read())

        # Download machine config
        req = urllib.request.Request(ONEFINITY_MACHINE_URL, headers={
            'User-Agent': 'FusionCam/0.1'
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            with open(machine_path, 'wb') as f:
                f.write(response.read())

        return True

    except Exception as e:
        raise RuntimeError(
            f'Failed to download Onefinity post-processor: {str(e)}\n\n'
            'You can manually download it from:\n'
            'https://github.com/blaghislain/onefinity-post-processors/releases\n\n'
            f'Place the .cps file at:\n{cps_path}'
        )


def get_post_processor_path():
    """Get the path to the post-processor, or None if not installed."""
    cps_path = os.path.join(POST_DIR, 'onefinity_fusion360.cps')
    return cps_path if os.path.exists(cps_path) else None


def get_machine_config_path():
    """Get the path to the machine configuration file."""
    machine_path = os.path.join(POST_DIR, 'Onefinity.Machinist.machine')
    return machine_path if os.path.exists(machine_path) else None


def get_fusion_post_library_path():
    """
    Get the Fusion 360 personal post library path.
    This is where users install custom post-processors.
    """
    # Fusion 360 stores posts in the user's cloud or local cache
    # The exact path depends on the Fusion installation
    home = os.path.expanduser('~')

    possible_paths = [
        os.path.join(home, 'AppData', 'Local', 'Autodesk', 'Fusion 360 CAM', 'Posts'),
        os.path.join(home, 'Library', 'Application Support', 'Autodesk', 'Fusion 360 CAM', 'Posts'),
    ]

    for path in possible_paths:
        if os.path.exists(path):
            return path

    return None


def install_to_fusion():
    """
    Copy the post-processor to Fusion 360's post library directory.
    Returns True if successful.
    """
    import shutil

    source = get_post_processor_path()
    if not source:
        ensure_post_processor()
        source = get_post_processor_path()

    fusion_posts = get_fusion_post_library_path()
    if not fusion_posts:
        return False

    try:
        dest = os.path.join(fusion_posts, 'onefinity_fusion360.cps')
        shutil.copy2(source, dest)

        machine_source = get_machine_config_path()
        if machine_source:
            machine_dest = os.path.join(fusion_posts, 'Onefinity.Machinist.machine')
            shutil.copy2(machine_source, machine_dest)

        return True
    except Exception:
        return False

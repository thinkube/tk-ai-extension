# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Save large cell outputs to shared JuiceFS filesystem.

Outputs are written to a .outputs/ directory within the notebooks volume,
which is accessible from both Jupyter pods and code-server.
"""

import base64
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Output size thresholds
IMAGE_UPLOAD_THRESHOLD = 0  # Always save images (they're always large)
TEXT_UPLOAD_THRESHOLD = 10000  # Save text outputs > 10KB

# Base path for outputs on the shared JuiceFS notebooks volume
_OUTPUTS_DIR = Path.home() / 'thinkube' / 'notebooks' / '.outputs'


def _ensure_output_dir(subdir: str) -> Path:
    """Ensure the output directory exists and return the full path."""
    output_dir = _OUTPUTS_DIR / subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    return output_dir


def _generate_filename(ext: str) -> tuple[str, str]:
    """Generate a unique filename and its date subdirectory."""
    date = datetime.utcnow().strftime('%Y-%m-%d')
    uid = uuid.uuid4().hex[:12]
    return date, f"{uid}.{ext}"


def _save_output(content: bytes, date_dir: str, filename: str) -> str | None:
    """Save content to the shared filesystem.

    Args:
        content: Raw bytes to save
        date_dir: Date-based subdirectory
        filename: Output filename

    Returns:
        Relative path from .outputs/ (e.g., "2026-05-11/abc123.png")
    """
    try:
        output_dir = _ensure_output_dir(date_dir)
        filepath = output_dir / filename
        filepath.write_bytes(content)
        rel_path = f"{date_dir}/{filename}"
        logger.info(f"Saved {len(content)} bytes to {filepath}")
        return rel_path
    except Exception as e:
        logger.error(f"Failed to save output: {e}")
        return None


def process_outputs(outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process cell execution outputs, saving large items to shared filesystem.

    - Base64 images → save to .outputs/, replace with path
    - Long text outputs → save to .outputs/, truncate with path

    The original outputs in YDoc are unchanged (visible in JupyterLab).
    This only affects what's returned in the MCP response.
    """
    processed = []

    for output in outputs:
        output_type = output.get('output_type', '')

        # Handle image data in display_data and execute_result
        if output_type in ('display_data', 'execute_result'):
            data = output.get('data', {})

            if 'image/png' in data:
                png_b64 = data['image/png']
                try:
                    png_bytes = base64.b64decode(png_b64)
                    date_dir, filename = _generate_filename('png')
                    rel_path = _save_output(png_bytes, date_dir, filename)

                    if rel_path:
                        # Replace base64 with filesystem path
                        new_data = {k: v for k, v in data.items() if k != 'image/png'}
                        new_data['image/png'] = f"[Image saved: .outputs/{rel_path}]"
                        output = {**output, 'data': new_data}
                    # If save fails, keep original (will be large but functional)
                except Exception as e:
                    logger.warning(f"Failed to process image output: {e}")

        # Handle long stream outputs
        if output_type == 'stream':
            text = output.get('text', '')
            if len(text) > TEXT_UPLOAD_THRESHOLD:
                date_dir, filename = _generate_filename('txt')
                rel_path = _save_output(text.encode('utf-8'), date_dir, filename)

                if rel_path:
                    truncated = text[:TEXT_UPLOAD_THRESHOLD]
                    output = {
                        **output,
                        'text': f"{truncated}\n\n[Output truncated at {TEXT_UPLOAD_THRESHOLD} chars. Full output ({len(text)} chars): .outputs/{rel_path}]"
                    }

        processed.append(output)

    return processed

# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Upload large cell outputs to SeaweedFS S3.

Reads credentials from the service discovery env file at
/home/thinkube/.config/thinkube/service-env-jh.sh (or environment variables).
"""

import base64
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Output size thresholds
IMAGE_UPLOAD_THRESHOLD = 0  # Always upload images (they're always large)
TEXT_UPLOAD_THRESHOLD = 10000  # Upload text outputs > 10KB

_s3_client = None
_s3_endpoint = None


def _load_env_from_file(path: str) -> Dict[str, str]:
    """Parse a bash export file into a dict."""
    env = {}
    try:
        with open(path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if line.startswith('export '):
                    line = line[7:]
                if '=' in line:
                    key, value = line.split('=', 1)
                    value = value.strip('"').strip("'")
                    env[key] = value
    except Exception as e:
        logger.warning(f"Failed to read env file {path}: {e}")
    return env


def _get_s3_client():
    """Get or create a boto3 S3 client using SeaweedFS credentials."""
    global _s3_client, _s3_endpoint

    if _s3_client is not None:
        return _s3_client, _s3_endpoint

    try:
        import boto3
        from botocore.config import Config

        # Try environment first
        endpoint = os.environ.get('SEAWEEDFS_S3_ENDPOINT')
        access_key = os.environ.get('SEAWEEDFS_ACCESS_KEY')
        secret_key = os.environ.get('SEAWEEDFS_SECRET_KEY')

        # Fall back to service discovery env file
        if not endpoint or not access_key or not secret_key:
            env_file = Path.home() / '.config' / 'thinkube' / 'service-env-jh.sh'
            if env_file.exists():
                env = _load_env_from_file(str(env_file))
                endpoint = endpoint or env.get('SEAWEEDFS_S3_ENDPOINT')
                access_key = access_key or env.get('SEAWEEDFS_ACCESS_KEY')
                secret_key = secret_key or env.get('SEAWEEDFS_SECRET_KEY')

        if not endpoint or not access_key or not secret_key:
            logger.error("SeaweedFS S3 credentials not found")
            return None, None

        _s3_client = boto3.client(
            's3',
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version='s3v4'),
            verify=False
        )
        _s3_endpoint = endpoint
        logger.info(f"S3 client initialized: {endpoint}")
        return _s3_client, _s3_endpoint

    except ImportError:
        logger.error("boto3 not installed")
        return None, None
    except Exception as e:
        logger.error(f"Failed to create S3 client: {e}")
        return None, None


def _upload_to_s3(content: bytes, key: str, content_type: str) -> Optional[str]:
    """Upload content to S3 and return the URL."""
    client, endpoint = _get_s3_client()
    if client is None:
        return None

    bucket = 'notebook-outputs'
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=content,
            ContentType=content_type
        )
        url = f"{endpoint}/{bucket}/{key}"
        logger.info(f"Uploaded {len(content)} bytes to {url}")
        return url
    except Exception as e:
        logger.error(f"S3 upload failed: {e}")
        return None


def _generate_key(ext: str) -> str:
    """Generate a unique S3 key."""
    date = datetime.utcnow().strftime('%Y-%m-%d')
    uid = uuid.uuid4().hex[:12]
    return f"outputs/{date}/{uid}.{ext}"


def process_outputs(outputs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process cell execution outputs, uploading large items to S3.

    - Base64 images → upload to S3, replace with URL
    - Long text outputs → upload to S3, truncate with link

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
                    key = _generate_key('png')
                    url = _upload_to_s3(png_bytes, key, 'image/png')

                    if url:
                        # Replace base64 with URL
                        new_data = {k: v for k, v in data.items() if k != 'image/png'}
                        new_data['image/png'] = f"[Image uploaded to S3: {url}]"
                        output = {**output, 'data': new_data}
                    # If upload fails, keep original (will be large but functional)
                except Exception as e:
                    logger.warning(f"Failed to process image output: {e}")

        # Handle long stream outputs
        if output_type == 'stream':
            text = output.get('text', '')
            if len(text) > TEXT_UPLOAD_THRESHOLD:
                key = _generate_key('txt')
                url = _upload_to_s3(text.encode('utf-8'), key, 'text/plain')

                if url:
                    truncated = text[:TEXT_UPLOAD_THRESHOLD]
                    output = {
                        **output,
                        'text': f"{truncated}\n\n[Output truncated at {TEXT_UPLOAD_THRESHOLD} chars. Full output ({len(text)} chars): {url}]"
                    }

        processed.append(output)

    return processed

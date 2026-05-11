# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Shared utilities for MCP tools."""

import logging
from typing import Any, Optional

from .ydoc_helper import get_jupyter_ydoc, get_notebook_path
from .execution_helper import execute_code_with_timeout, format_outputs

logger = logging.getLogger(__name__)


async def resolve_kernel_id(session_manager: Any, notebook_path: str) -> Optional[str]:
    """Find the kernel_id for a notebook from active JupyterHub sessions."""
    if not session_manager:
        return None
    try:
        sessions = await session_manager.list_sessions()
        for s in sessions:
            if s.get('path') == notebook_path or s.get('name') == notebook_path:
                return s.get('kernel', {}).get('id')
    except Exception as e:
        logger.warning(f"Failed to resolve kernel_id: {e}")
    return None


__all__ = [
    'get_jupyter_ydoc',
    'get_notebook_path',
    'execute_code_with_timeout',
    'format_outputs',
    'resolve_kernel_id',
]

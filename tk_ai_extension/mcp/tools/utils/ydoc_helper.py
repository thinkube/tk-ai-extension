# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Helper to access YNotebook documents via jupyter_server_ydoc."""

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


def get_notebook_path(serverapp: Any, relative_path: str) -> str:
    """Convert relative notebook path to absolute path."""
    if Path(relative_path).is_absolute():
        return relative_path
    if serverapp:
        root_dir = serverapp.root_dir
        return str(Path(root_dir) / relative_path)
    return relative_path


async def get_jupyter_ydoc(serverapp: Any, notebook_path: str) -> Optional[Any]:
    """Get a YNotebook document for a notebook that is open in JupyterLab.

    Uses the jupyter_server_ydoc extension's get_document() API.

    Args:
        serverapp: Jupyter ServerApp instance
        notebook_path: Path to the notebook (relative or absolute)

    Returns:
        YNotebook document if available, None otherwise
    """
    try:
        abs_path = get_notebook_path(serverapp, notebook_path)

        file_id_manager = serverapp.web_app.settings.get("file_id_manager")
        if not file_id_manager:
            logger.error("file_id_manager not available")
            return None

        file_id = file_id_manager.get_id(abs_path)
        document_id = f"json:notebook:{file_id}"

        ydoc_extensions = serverapp.extension_manager.extension_apps.get("jupyter_server_ydoc", set())
        if not ydoc_extensions:
            logger.error("jupyter_server_ydoc extension not loaded")
            return None

        ydoc_extension = next(iter(ydoc_extensions))
        ydoc = await ydoc_extension.get_document(room_id=document_id, copy=False)

        if ydoc is None:
            logger.error(f"No YDoc document for {document_id} — notebook must be open in JupyterLab")
            return None

        logger.info(f"Got YDoc for {notebook_path}")
        return ydoc

    except Exception as e:
        logger.error(f"Failed to get YDoc: {e}", exc_info=True)
        return None

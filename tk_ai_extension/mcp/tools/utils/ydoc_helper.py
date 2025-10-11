# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Helper functions for YDoc operations with file fallback."""

import logging
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


async def get_jupyter_ydoc(serverapp: Any, file_id: str) -> Optional[Any]:
    """Get the YNotebook document if it's currently open in a collaborative session.

    Args:
        serverapp: Jupyter ServerApp instance
        file_id: File ID from file_id_manager

    Returns:
        YNotebook document if available, None otherwise
    """
    try:
        # Get ywebsocket_server from YDocExtension instance
        ydoc_extensions = serverapp.extension_manager.extension_apps.get("jupyter_server_ydoc", set())
        if not ydoc_extensions:
            logger.debug("jupyter_server_ydoc extension not loaded")
            return None

        ydoc_ext = next(iter(ydoc_extensions))
        ywebsocket_server = ydoc_ext.ywebsocket_server

        room_id = f"json:notebook:{file_id}"

        if ywebsocket_server.room_exists(room_id):
            yroom = await ywebsocket_server.get_room(room_id)
            notebook = yroom._document  # DocumentRoom stores YNotebook as _document attribute
            logger.debug(f"Got YDoc for {file_id}")
            return notebook
        else:
            logger.debug(f"No room for {room_id}")
    except Exception as e:
        logger.debug(f"Failed to get YDoc: {e}")

    return None


def get_notebook_path(serverapp: Any, relative_path: str) -> str:
    """Convert relative notebook path to absolute path.

    Args:
        serverapp: Jupyter ServerApp instance
        relative_path: Relative path to notebook

    Returns:
        Absolute path to notebook
    """
    if Path(relative_path).is_absolute():
        return relative_path

    if serverapp:
        root_dir = serverapp.root_dir
        return str(Path(root_dir) / relative_path)

    return relative_path

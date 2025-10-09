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
        yroom_manager = serverapp.web_app.settings.get("yroom_manager")
        if yroom_manager is None:
            logger.debug("yroom_manager not available")
            return None

        room_id = f"json:notebook:{file_id}"

        if yroom_manager.has_room(room_id):
            yroom = yroom_manager.get_room(room_id)
            notebook = await yroom.get_jupyter_ydoc()
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

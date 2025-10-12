# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Conversation persistence in notebook metadata."""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


async def save_conversation_to_notebook(notebook_path: str, messages: List[Dict[str, Any]], serverapp=None) -> bool:
    """Save conversation history to notebook metadata via YDoc (NO FILE OPERATIONS).

    Args:
        notebook_path: Path to the notebook file
        messages: List of conversation messages [{"role": "user"|"assistant", "content": "..."}]
        serverapp: Jupyter ServerApp instance (REQUIRED)

    Returns:
        True if successful, False otherwise
    """
    if not serverapp:
        logger.error("serverapp is REQUIRED - cannot save conversation without YDoc access")
        return False

    try:
        from .mcp.tools.utils import get_jupyter_ydoc, get_notebook_path

        logger.info(f"save_conversation called with notebook_path: {notebook_path}")

        # Get absolute path
        abs_path = get_notebook_path(serverapp, notebook_path)
        logger.info(f"Converted to abs_path: {abs_path}")

        # Get file_id for YDoc lookup
        file_id_manager = serverapp.web_app.settings.get("file_id_manager")
        if not file_id_manager:
            logger.error("file_id_manager not available")
            return False

        file_id = file_id_manager.get_id(abs_path)
        logger.info(f"Got file_id: {file_id}")

        # Get YDoc
        ydoc = await get_jupyter_ydoc(serverapp, file_id)

        if not ydoc:
            logger.error(f"YDoc not available for {notebook_path} - notebook must be open")
            return False

        # Access metadata via YDoc's _ymeta Map
        ymeta = ydoc._ymeta
        metadata = ymeta.get("metadata", {})

        # Convert to Python dict if it's a pycrdt Map
        if hasattr(metadata, 'to_py'):
            metadata = metadata.to_py()
        else:
            metadata = dict(metadata)

        # Ensure tk_ai structure exists
        if 'tk_ai' not in metadata:
            metadata['tk_ai'] = {}

        # Save conversation history (limit to last 100 messages)
        metadata['tk_ai']['conversation_history'] = messages[-100:]

        # Write back to YDoc metadata
        from pycrdt import Map
        ymeta["metadata"] = Map(metadata)

        logger.info(f"Saved {len(messages)} messages to {notebook_path} via YDoc")
        return True

    except Exception as e:
        logger.error(f"Error saving conversation via YDoc to {notebook_path}: {e}", exc_info=True)
        return False


def load_conversation_from_notebook(notebook_path: str) -> List[Dict[str, Any]]:
    """Load conversation history from notebook metadata.

    Args:
        notebook_path: Path to the notebook file

    Returns:
        List of conversation messages, or empty list if none found
    """
    try:
        # Convert to Path object
        nb_path = Path(notebook_path)

        # Handle relative paths
        if not nb_path.is_absolute():
            # Check if path already contains thinkube/notebooks prefix
            path_str = str(notebook_path)
            if path_str.startswith('thinkube/notebooks/'):
                # Path already includes the prefix, just prepend home
                nb_path = Path.home() / path_str
            else:
                # Path needs full prefix
                nb_path = Path.home() / 'thinkube' / 'notebooks' / notebook_path

        if not nb_path.exists():
            logger.warning(f"Notebook not found: {nb_path}")
            return []

        # Load notebook
        with open(nb_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)

        # Extract conversation history
        messages = (notebook.get('metadata', {})
                           .get('tk_ai', {})
                           .get('conversation_history', []))

        logger.info(f"Loaded {len(messages)} messages from {notebook_path}")
        return messages

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in notebook {notebook_path}: {e}")
        return []
    except Exception as e:
        logger.error(f"Error loading conversation from {notebook_path}: {e}")
        return []


async def clear_conversation(notebook_path: str, serverapp=None) -> bool:
    """Clear conversation history from notebook metadata via YDoc (NO FILE OPERATIONS).

    Args:
        notebook_path: Path to the notebook file
        serverapp: Jupyter ServerApp instance (REQUIRED)

    Returns:
        True if successful, False otherwise
    """
    if not serverapp:
        logger.error("serverapp is REQUIRED - cannot clear conversation without YDoc access")
        return False

    try:
        from .mcp.tools.utils import get_jupyter_ydoc, get_notebook_path

        logger.info(f"clear_conversation called with notebook_path: {notebook_path}")

        # Get absolute path
        abs_path = get_notebook_path(serverapp, notebook_path)
        logger.info(f"Converted to abs_path: {abs_path}")

        # Get file_id for YDoc lookup
        file_id_manager = serverapp.web_app.settings.get("file_id_manager")
        if not file_id_manager:
            logger.error("file_id_manager not available")
            return False

        file_id = file_id_manager.get_id(abs_path)
        logger.info(f"Got file_id: {file_id}")

        # Get YDoc
        ydoc = await get_jupyter_ydoc(serverapp, file_id)

        if not ydoc:
            logger.error(f"YDoc not available for {notebook_path} - notebook must be open")
            return False

        # Access metadata via YDoc's _ymeta Map
        ymeta = ydoc._ymeta
        metadata = ymeta.get("metadata", {})

        # Convert to Python dict if it's a pycrdt Map
        if hasattr(metadata, 'to_py'):
            metadata = metadata.to_py()
        else:
            metadata = dict(metadata)

        # Ensure tk_ai structure exists
        if 'tk_ai' not in metadata:
            metadata['tk_ai'] = {}

        # Clear conversation history
        metadata['tk_ai']['conversation_history'] = []

        # Write back to YDoc metadata
        from pycrdt import Map
        ymeta["metadata"] = Map(metadata)

        logger.info(f"Cleared conversation history from {notebook_path} via YDoc")
        return True

    except Exception as e:
        logger.error(f"Error clearing conversation via YDoc from {notebook_path}: {e}", exc_info=True)
        return False


def get_notebook_name(notebook_path: str) -> str:
    """Extract notebook name from path.

    Args:
        notebook_path: Path to the notebook file

    Returns:
        Notebook filename without extension
    """
    return Path(notebook_path).stem

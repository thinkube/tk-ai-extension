# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Conversation persistence in notebook metadata.

Save/clear use YDoc for real-time sync with JupyterLab.
Load reads from the file (works even before YDoc has synced).
"""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any

logger = logging.getLogger(__name__)


def _resolve_notebook_path(notebook_path: str) -> Path:
    """Resolve a notebook path to an absolute path."""
    nb_path = Path(notebook_path)
    if nb_path.is_absolute():
        return nb_path

    path_str = str(notebook_path)
    if path_str.startswith('thinkube/notebooks/'):
        return Path.home() / path_str
    else:
        return Path.home() / 'thinkube' / 'notebooks' / notebook_path


def load_conversation_from_notebook(notebook_path: str) -> List[Dict[str, Any]]:
    """Load conversation history from notebook metadata (file-based).

    Reads directly from the .ipynb file. Works even if the notebook
    is not currently open in JupyterLab.
    """
    try:
        nb_path = _resolve_notebook_path(notebook_path)

        if not nb_path.exists():
            logger.warning(f"Notebook not found: {nb_path}")
            return []

        with open(nb_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)

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


async def save_conversation_to_notebook(notebook_path: str, messages: List[Dict[str, Any]], serverapp=None) -> bool:
    """Save conversation history to notebook metadata via YDoc.

    Uses YDoc so the save syncs to JupyterLab in real time and is
    persisted when JupyterLab autosaves.
    """
    if not serverapp:
        logger.error("serverapp is required for YDoc access")
        return False

    try:
        from .mcp.tools.utils import get_jupyter_ydoc

        ydoc = await get_jupyter_ydoc(serverapp, notebook_path)
        if not ydoc:
            # YDoc unavailable — fall back to file save
            logger.warning(f"YDoc not available for {notebook_path}, saving to file")
            return _save_to_file(notebook_path, messages)

        # Access metadata via YDoc
        meta = ydoc._ymeta
        metadata = meta.get("metadata", {})

        if hasattr(metadata, 'to_py'):
            metadata = metadata.to_py()
        else:
            metadata = dict(metadata)

        if 'tk_ai' not in metadata:
            metadata['tk_ai'] = {}

        metadata['tk_ai']['conversation_history'] = messages[-100:]

        from pycrdt import Map
        meta["metadata"] = Map(metadata)

        logger.info(f"Saved {len(messages)} messages to {notebook_path} via YDoc")
        return True

    except Exception as e:
        logger.error(f"Error saving conversation to {notebook_path}: {e}", exc_info=True)
        return False


def _save_to_file(notebook_path: str, messages: List[Dict[str, Any]]) -> bool:
    """File-based save — used when YDoc is not available."""
    try:
        nb_path = _resolve_notebook_path(notebook_path)
        if not nb_path.exists():
            logger.error(f"Notebook not found: {nb_path}")
            return False

        with open(nb_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)

        if 'metadata' not in notebook:
            notebook['metadata'] = {}
        if 'tk_ai' not in notebook['metadata']:
            notebook['metadata']['tk_ai'] = {}

        notebook['metadata']['tk_ai']['conversation_history'] = messages[-100:]

        with open(nb_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)
            f.write('\n')

        logger.info(f"Saved {len(messages)} messages to {nb_path} (file)")
        return True
    except Exception as e:
        logger.error(f"Error saving conversation to file: {e}", exc_info=True)
        return False


async def clear_conversation(notebook_path: str, serverapp=None) -> bool:
    """Clear conversation history."""
    return await save_conversation_to_notebook(notebook_path, [], serverapp)


def get_notebook_name(notebook_path: str) -> str:
    """Extract notebook name from path."""
    return Path(notebook_path).stem

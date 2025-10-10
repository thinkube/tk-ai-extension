# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Conversation persistence in notebook metadata."""

import json
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


def save_conversation_to_notebook(notebook_path: str, messages: List[Dict[str, Any]]) -> bool:
    """Save conversation history to notebook metadata.

    Args:
        notebook_path: Path to the notebook file
        messages: List of conversation messages [{"role": "user"|"assistant", "content": "..."}]

    Returns:
        True if successful, False otherwise
    """
    try:
        # Convert to Path object
        nb_path = Path(notebook_path)

        # Handle relative paths (assume from /home/jovyan/thinkube/notebooks)
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
            logger.error(f"Notebook not found: {nb_path}")
            return False

        # Load notebook
        with open(nb_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)

        # Ensure metadata structure exists
        if 'metadata' not in notebook:
            notebook['metadata'] = {}

        if 'tk_ai' not in notebook['metadata']:
            notebook['metadata']['tk_ai'] = {}

        # Save conversation history (limit to last 100 messages to avoid bloat)
        notebook['metadata']['tk_ai']['conversation_history'] = messages[-100:]
        notebook['metadata']['tk_ai']['last_updated'] = str(Path(nb_path).stat().st_mtime)

        # Write back to disk
        with open(nb_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)

        logger.info(f"Saved {len(messages)} messages to {notebook_path}")
        return True

    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON in notebook {notebook_path}: {e}")
        return False
    except Exception as e:
        logger.error(f"Error saving conversation to {notebook_path}: {e}")
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


def clear_conversation(notebook_path: str) -> bool:
    """Clear conversation history from notebook metadata.

    Args:
        notebook_path: Path to the notebook file

    Returns:
        True if successful, False otherwise
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
            logger.error(f"Notebook not found: {nb_path}")
            return False

        # Load notebook
        with open(nb_path, 'r', encoding='utf-8') as f:
            notebook = json.load(f)

        # Clear conversation history
        if 'metadata' in notebook and 'tk_ai' in notebook['metadata']:
            notebook['metadata']['tk_ai']['conversation_history'] = []
            notebook['metadata']['tk_ai']['last_updated'] = str(Path(nb_path).stat().st_mtime)

        # Write back to disk
        with open(nb_path, 'w', encoding='utf-8') as f:
            json.dump(notebook, f, indent=1, ensure_ascii=False)

        logger.info(f"Cleared conversation history from {notebook_path}")
        return True

    except Exception as e:
        logger.error(f"Error clearing conversation from {notebook_path}: {e}")
        return False


def get_notebook_name(notebook_path: str) -> str:
    """Extract notebook name from path.

    Args:
        notebook_path: Path to the notebook file

    Returns:
        Notebook filename without extension
    """
    return Path(notebook_path).stem

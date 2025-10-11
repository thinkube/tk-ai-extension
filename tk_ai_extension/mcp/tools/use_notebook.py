# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Use notebook tool implementation."""

import logging
import asyncio
from typing import Any, Optional, Literal
from pathlib import Path
from ..tools.base import BaseTool

logger = logging.getLogger(__name__)


class UseNotebookTool(BaseTool):
    """Tool to use (connect to or create) a notebook file.

    This tool allows Thinky to explicitly connect to a notebook and its kernel,
    solving the "which notebook?" problem. Once connected, execution tools will
    use this notebook's kernel.
    """

    @property
    def name(self) -> str:
        return "use_notebook"

    @property
    def description(self) -> str:
        return """Use a notebook file (connect to existing, create new, or switch to already-connected notebook).

IMPORTANT: You must use this tool before executing code in notebooks. This establishes which notebook to operate on.

Args:
    notebook_name: Unique identifier for the notebook (e.g., "analysis", "main")
    notebook_path: Path to the notebook file, relative to ~/thinkube/notebooks (e.g. "work/analysis.ipynb").
                  Optional - if not provided, switches to an already-connected notebook with the given name.
    mode: "connect" to connect to existing notebook, "create" to create new notebook
    kernel_id: Specific kernel ID to use (optional, will create new kernel if not provided)

Returns:
    str: Success message with notebook information

Examples:
    - Connect to existing: use_notebook(notebook_name="main", notebook_path="analysis.ipynb", mode="connect")
    - Create new: use_notebook(notebook_name="work", notebook_path="new_work.ipynb", mode="create")
    - Switch to connected: use_notebook(notebook_name="main")"""

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_name": {
                    "type": "string",
                    "description": "Unique identifier for the notebook (e.g., 'analysis', 'main')"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook file, relative to ~/thinkube/notebooks (e.g. 'work/analysis.ipynb'). Optional - if not provided, switches to already-connected notebook."
                },
                "mode": {
                    "type": "string",
                    "enum": ["connect", "create"],
                    "description": "Whether to connect to existing notebook or create new one",
                    "default": "connect"
                },
                "kernel_id": {
                    "type": "string",
                    "description": "Specific kernel ID to use (optional, will create new kernel if not provided)"
                }
            },
            "required": ["notebook_name"]
        }

    async def _check_path_exists(
        self,
        contents_manager: Any,
        notebook_path: str,
        mode: str
    ) -> tuple[bool, Optional[str]]:
        """Check if path exists using contents_manager API.

        Args:
            contents_manager: Jupyter contents manager
            notebook_path: Path to check
            mode: "connect" or "create"

        Returns:
            (success, error_message) tuple
        """
        path = Path(notebook_path)
        try:
            parent_path = str(path.parent) if str(path.parent) != "." else ""

            # Get directory contents using local API
            model = await contents_manager.get(parent_path, content=True, type='directory')

            if mode == "connect":
                file_exists = any(item['name'] == path.name for item in model.get('content', []))
                if not file_exists:
                    return False, f"'{notebook_path}' not found. Please check the notebook exists."

            return True, None
        except Exception as e:
            parent_dir = str(path.parent) if str(path.parent) != "." else "root directory"
            return False, f"'{parent_dir}' not found: {e}"

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        notebook_manager: Optional[Any] = None,
        serverapp: Optional[Any] = None,
        # Tool-specific parameters
        notebook_name: str = None,
        notebook_path: Optional[str] = None,
        mode: Literal["connect", "create"] = "connect",
        kernel_id: Optional[str] = None,
        **kwargs
    ) -> str:
        """Execute the use_notebook tool.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager for creating kernel-notebook associations
            notebook_manager: NotebookManager instance for tracking active notebooks
            serverapp: Jupyter ServerApp instance (unused)
            notebook_name: Unique identifier for the notebook
            notebook_path: Path to the notebook file (optional, if not provided switches to existing)
            mode: "connect" or "create"
            kernel_id: Optional specific kernel ID
            **kwargs: Additional parameters

        Returns:
            Success message with notebook information
        """
        if not notebook_manager:
            return "Error: NotebookManager not available. Extension initialization may have failed."

        if not notebook_name:
            return "Error: notebook_name is required."

        # Case 1: No notebook_path provided - switch to already-connected notebook
        if notebook_path is None:
            if notebook_name not in notebook_manager:
                return f"Notebook '{notebook_name}' is not connected. Please provide a notebook_path to connect to it first."

            # Switch to the existing notebook
            notebook_manager.set_current_notebook(notebook_name)
            current_path = notebook_manager.get_current_notebook_path()
            return f"Successfully switched to notebook '{notebook_name}' at {current_path}."

        # Case 2: Notebook already connected with this name
        if notebook_name in notebook_manager:
            return f"Notebook '{notebook_name}' is already connected. Use a different name or call unuse_notebook first if you want to reconnect."

        # Case 3: Connect to or create new notebook
        # Check the path exists (or parent exists for create mode)
        path_ok, error_msg = await self._check_path_exists(contents_manager, notebook_path, mode)
        if not path_ok:
            return f"Error: {error_msg}"

        # Create notebook if needed
        if mode == "create":
            try:
                await contents_manager.new(model={'type': 'notebook'}, path=notebook_path)
                logger.info(f"Created new notebook at '{notebook_path}'")
            except Exception as e:
                return f"Failed to create notebook at '{notebook_path}': {e}"

        # Create or connect to kernel
        if kernel_id:
            # Connect to existing kernel - verify it exists
            if kernel_id not in kernel_manager:
                return f"Kernel '{kernel_id}' not found in kernel manager."
            kernel_info = {"id": kernel_id}
            logger.info(f"Connected to existing kernel '{kernel_id}'")
        else:
            # Find the existing session for this notebook
            existing_kernel_id = None
            if session_manager:
                try:
                    sessions = await session_manager.list_sessions()
                    for session in sessions:
                        if session.get('path') == notebook_path or session.get('name') == notebook_path:
                            existing_kernel_id = session.get('kernel', {}).get('id')
                            logger.info(f"Found existing session with kernel '{existing_kernel_id}' for notebook '{notebook_path}'")
                            break
                except Exception as e:
                    return f"Failed to list sessions: {e}"

            if not existing_kernel_id:
                return f"No existing kernel found for notebook '{notebook_path}'. The notebook must be opened in JupyterLab first."

            # Reuse the existing kernel
            kernel_id = existing_kernel_id
            kernel_info = {"id": kernel_id}
            logger.info(f"Reusing existing kernel '{kernel_id}' for notebook '{notebook_path}'")

        # Don't create a new session - use the existing one
        # The session already exists since we found the kernel from it

        # Add notebook to manager
        notebook_manager.add_notebook(
            notebook_name,
            kernel_info,
            notebook_path
        )

        # Set as current notebook
        notebook_manager.set_current_notebook(notebook_name)

        # Return success message
        return f"Successfully connected to notebook '{notebook_name}' at '{notebook_path}' with existing kernel {kernel_id}."

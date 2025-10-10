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
            # Start a new kernel
            try:
                kernel_id = await kernel_manager.start_kernel()
                logger.info(f"Started kernel '{kernel_id}', waiting for it to be ready...")

                # CRITICAL: Wait for the kernel to actually start and be ready
                # The start_kernel() call returns immediately, but kernel takes time to start
                max_wait_time = 30  # seconds
                wait_interval = 0.5  # seconds
                elapsed = 0
                kernel_ready = False

                while elapsed < max_wait_time:
                    try:
                        # Get kernel model to check its state
                        kernel_model = kernel_manager.get_kernel(kernel_id)
                        if kernel_model is not None:
                            # Kernel exists, check if it's ready by getting connection info
                            try:
                                kernel_manager.get_connection_info(kernel_id)
                                kernel_ready = True
                                logger.info(f"Kernel '{kernel_id}' is ready (took {elapsed:.1f}s)")
                                break
                            except:
                                # Connection info not available yet, kernel still starting
                                pass
                    except Exception as e:
                        logger.debug(f"Waiting for kernel to start: {e}")

                    await asyncio.sleep(wait_interval)
                    elapsed += wait_interval

                if not kernel_ready:
                    logger.warning(f"Kernel '{kernel_id}' may not be fully ready after {max_wait_time}s wait")

                kernel_info = {"id": kernel_id}
            except Exception as e:
                return f"Failed to start kernel: {e}"

        # Create a Jupyter session to associate the kernel with the notebook
        # This is CRITICAL for JupyterLab to recognize the kernel-notebook connection
        if session_manager is not None:
            try:
                # create_session is an async method
                session_dict = await session_manager.create_session(
                    path=notebook_path,
                    kernel_id=kernel_id,
                    type="notebook",
                    name=notebook_path
                )
                logger.info(f"Created Jupyter session '{session_dict.get('id')}' for notebook '{notebook_path}' with kernel '{kernel_id}'")
            except Exception as e:
                logger.warning(f"Failed to create Jupyter session: {e}. Notebook may not be properly connected in JupyterLab UI.")
        else:
            logger.warning("No session_manager available. Notebook may not be properly connected in JupyterLab UI.")

        # Add notebook to manager
        # Our NotebookManager has a simpler signature: add_notebook(name, kernel_info, path)
        notebook_manager.add_notebook(
            notebook_name,
            kernel_info,
            notebook_path
        )

        # Set as current notebook
        notebook_manager.set_current_notebook(notebook_name)

        # Return success message
        if mode == "create":
            return f"Successfully created and connected to notebook '{notebook_name}' at '{notebook_path}' with kernel {kernel_id}."
        else:
            return f"Successfully connected to notebook '{notebook_name}' at '{notebook_path}' with kernel {kernel_id}."

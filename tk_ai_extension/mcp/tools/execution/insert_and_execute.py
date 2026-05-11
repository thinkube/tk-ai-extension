# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for inserting and executing a cell in one operation."""

import logging
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path, execute_code_with_timeout

logger = logging.getLogger(__name__)


class InsertAndExecuteCellTool(BaseTool):
    """Insert a new code cell and execute it immediately."""

    @property
    def name(self) -> str:
        return "insert_and_execute_cell"

    @property
    def description(self) -> str:
        return (
            "Insert a new code cell into a notebook and execute it immediately. "
            "IMPORTANT: cell_index is 0-based position (NOT execution count). "
            "Use list_cells first to see current indices. "
            "NOTE: You must call use_notebook first to connect to a notebook and its kernel."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook"
                },
                "cell_index": {
                    "type": "integer",
                    "description": "0-based index where to insert (NOT execution count). Cell will be inserted BEFORE this index. Use list_cells to see current indices."
                },
                "code": {
                    "type": "string",
                    "description": "Code to insert and execute"
                },
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to use for execution"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum time to wait for execution (default: 300)",
                    "default": 300
                }
            },
            "required": ["notebook_path", "cell_index", "code", "kernel_id"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        notebook_manager: Optional[Any] = None,
        serverapp: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Insert and execute a cell using YDoc.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager for tracking
            serverapp: Jupyter ServerApp instance
            notebook_path: Path to notebook
            cell_index: Where to insert
            code: Code to insert
            kernel_id: Kernel ID to use
            timeout_seconds: Execution timeout

        Returns:
            Dict with execution results
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")
        code = kwargs.get("code") or kwargs.get("source")
        kernel_id = kwargs.get("kernel_id")
        timeout_seconds = kwargs.get("timeout_seconds", 300)

        # Auto-resolve kernel_id from sessions if not provided
        if not kernel_id and notebook_path and session_manager:
            from ..utils import resolve_kernel_id
            kernel_id = await resolve_kernel_id(session_manager, notebook_path)

        if not notebook_path or cell_index is None or not code:
            return {"error": "notebook_path, cell_index, and code are required", "success": False}

        if not kernel_id:
            return {
                "error": f"No kernel found for {notebook_path}. The notebook must be open in JupyterLab.",
                "success": False
            }

        try:
            if not serverapp:
                return {"error": "ServerApp not available", "success": False}

            abs_path = get_notebook_path(serverapp, notebook_path)

            # Check kernel state
            kernels = list(kernel_manager.list_kernels())
            kernel_info = None
            for k in kernels:
                if k['id'] == kernel_id:
                    kernel_info = k
                    break

            if not kernel_info:
                return {"error": f"Kernel '{kernel_id}' not found", "success": False}

            execution_state = kernel_info.get('execution_state', 'unknown')
            if execution_state == 'busy':
                return {
                    "error": "Kernel is busy. Wait for the current execution to complete.",
                    "success": False
                }

            ydoc = await get_jupyter_ydoc(serverapp, notebook_path)
            if not ydoc:
                return {
                    "error": f"YDoc not available for {notebook_path}. The notebook must be open in JupyterLab.",
                    "success": False
                }

            # Clamp cell index
            if cell_index < 0:
                cell_index = 0
            if cell_index > len(ydoc.ycells):
                cell_index = len(ydoc.ycells)

            # Create new cell dict with source content
            # create_ycell() will convert source to Text object automatically
            new_cell = {
                "cell_type": "code",
                "source": code,
                "execution_count": None,  # Required for code cells
            }

            # Create proper CRDT cell object
            ycell = ydoc.create_ycell(new_cell)
            ydoc.ycells.insert(cell_index, ycell)

            # Get the newly inserted cell to retrieve its ID
            inserted_cell_id = ycell.get("id")

            # Execute the cell
            outputs = await execute_code_with_timeout(
                kernel_manager,
                kernel_id,
                code,
                timeout_seconds,
                serverapp=serverapp
            )

            return {
                "success": True,
                "cell_index": cell_index,
                "outputs": outputs,
                "message": f"Cell inserted at index {cell_index} and executed"
            }

        except Exception as e:
            logger.error(f"Failed to insert and execute cell: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

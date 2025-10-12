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
        return "Insert a new code cell into a notebook and execute it immediately. NOTE: You must call use_notebook first to connect to a notebook and its kernel."

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
                    "description": "Index where to insert the cell (cell will be inserted before this index)"
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
        code = kwargs.get("code")
        kernel_id = kwargs.get("kernel_id")
        timeout_seconds = kwargs.get("timeout_seconds", 300)

        if not notebook_path or cell_index is None or not code or not kernel_id:
            return {
                "error": "notebook_path, cell_index, code, and kernel_id are required",
                "success": False
            }

        # Proactive check: suggest using use_notebook if no notebooks connected
        if notebook_manager and notebook_manager.is_empty():
            return {
                "error": "No notebook connected. Use the use_notebook tool first to connect to a notebook.",
                "success": False,
                "suggestion": "Call use_notebook with notebook_name and notebook_path parameters"
            }

        try:
            # Get absolute path
            if not serverapp:
                return {
                    "error": "ServerApp not available - cannot access YDoc",
                    "success": False
                }

            abs_path = get_notebook_path(serverapp, notebook_path)

            # Check if kernel exists
            kernels = list(kernel_manager.list_kernels())
            if not any(k['id'] == kernel_id for k in kernels):
                return {
                    "error": f"Kernel '{kernel_id}' not found",
                    "success": False
                }

            # Get file_id for YDoc lookup
            file_id_manager = serverapp.web_app.settings.get("file_id_manager")
            if not file_id_manager:
                return {
                    "error": "file_id_manager not available",
                    "success": False
                }

            file_id = file_id_manager.get_id(abs_path)
            ydoc = await get_jupyter_ydoc(serverapp, file_id)

            if not ydoc:
                return {
                    "error": f"YDoc not available for {notebook_path}. The notebook must be open in JupyterLab with collaborative mode enabled.",
                    "success": False
                }

            # Get document_id for RTC integration
            document_id = f"json:notebook:{file_id}"

            # Validate cell index
            if cell_index < 0 or cell_index > len(ydoc.ycells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(ydoc.ycells)} cells",
                    "success": False
                }

            # Insert new code cell with source included from the start
            new_cell = {
                "cell_type": "code",
                "source": code,  # Include source in initial cell dict
                "execution_count": None,  # Required for code cells
            }
            # Create proper CRDT cell object with source already set
            ycell = ydoc.create_ycell(new_cell)
            ydoc.ycells.insert(cell_index, ycell)

            # Get the newly inserted cell to retrieve its ID
            inserted_cell_id = ycell.get("id")

            # Execute the cell with RTC metadata
            outputs = await execute_code_with_timeout(
                kernel_manager,
                kernel_id,
                code,
                timeout_seconds,
                serverapp=serverapp,
                document_id=document_id,
                cell_id=inserted_cell_id
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

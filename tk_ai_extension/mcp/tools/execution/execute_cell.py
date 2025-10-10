# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for executing notebook cells."""

import nbformat
from pathlib import Path
from typing import Any, Optional, Dict, List
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path, execute_code_with_timeout


class ExecuteCellTool(BaseTool):
    """Execute a cell in a Jupyter notebook."""

    @property
    def name(self) -> str:
        return "execute_cell"

    @property
    def description(self) -> str:
        return "Execute a code cell in a Jupyter notebook and return its output. NOTE: You must call use_notebook first to connect to a notebook and its kernel."

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
                    "description": "Index of the cell to execute (0-based)"
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
            "required": ["notebook_path", "cell_index", "kernel_id"]
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
        """Execute a cell.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager for tracking
            serverapp: Jupyter ServerApp instance
            notebook_path: Path to notebook
            cell_index: Cell index to execute
            kernel_id: Kernel ID to use
            timeout_seconds: Execution timeout

        Returns:
            Dict with execution results
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")
        kernel_id = kwargs.get("kernel_id")
        timeout_seconds = kwargs.get("timeout_seconds", 300)

        if not notebook_path or cell_index is None or not kernel_id:
            return {
                "error": "notebook_path, cell_index, and kernel_id are required",
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
            serverapp = getattr(contents_manager, 'parent', None)
            abs_path = get_notebook_path(serverapp, notebook_path)

            # Check if kernel exists
            kernels = list(kernel_manager.list_kernels())
            if not any(k['id'] == kernel_id for k in kernels):
                return {
                    "error": f"Kernel '{kernel_id}' not found",
                    "success": False
                }

            # Get file_id for YDoc lookup
            if serverapp:
                file_id_manager = serverapp.web_app.settings.get("file_id_manager")
                if file_id_manager:
                    file_id = file_id_manager.get_id(abs_path)
                    ydoc = await get_jupyter_ydoc(serverapp, file_id)

                    if ydoc:
                        # Use YDoc for collaborative editing
                        if cell_index < 0 or cell_index >= len(ydoc.ycells):
                            return {
                                "error": f"Cell index {cell_index} out of range. Notebook has {len(ydoc.ycells)} cells",
                                "success": False
                            }

                        ycell = ydoc.ycells[cell_index]
                        if ycell.get("cell_type") != "code":
                            return {
                                "error": f"Cell {cell_index} is not a code cell",
                                "success": False
                            }

                        # Get cell source
                        source_raw = ycell.get("source", "")
                        if isinstance(source_raw, list):
                            cell_source = "".join(source_raw)
                        else:
                            cell_source = str(source_raw)

                        # Execute code
                        outputs = await execute_code_with_timeout(
                            kernel_manager, kernel_id, cell_source, timeout_seconds, serverapp=serverapp
                        )

                        return {
                            "success": True,
                            "cell_index": cell_index,
                            "outputs": outputs
                        }

            # Fallback to file operations
            with open(abs_path, 'r', encoding='utf-8') as f:
                notebook = nbformat.read(f, as_version=4)

            if cell_index < 0 or cell_index >= len(notebook.cells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(notebook.cells)} cells",
                    "success": False
                }

            cell = notebook.cells[cell_index]
            if cell.cell_type != 'code':
                return {
                    "error": f"Cell {cell_index} is not a code cell (type: {cell.cell_type})",
                    "success": False
                }

            # Execute code
            outputs = await execute_code_with_timeout(
                kernel_manager, kernel_id, cell.source, timeout_seconds, serverapp=serverapp
            )

            return {
                "success": True,
                "cell_index": cell_index,
                "outputs": outputs
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "cell_index": cell_index
            }

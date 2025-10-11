# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for inserting and executing a cell in one operation."""

import nbformat
from nbformat.v4 import new_code_cell
from pathlib import Path
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path, execute_code_with_timeout


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
        """Insert and execute a cell.

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
            serverapp = getattr(contents_manager, 'parent', None)
            abs_path = get_notebook_path(serverapp, notebook_path)

            # Check if kernel exists
            kernels = list(kernel_manager.list_kernels())
            if not any(k['id'] == kernel_id for k in kernels):
                return {
                    "error": f"Kernel '{kernel_id}' not found",
                    "success": False
                }

            # Connect via WebSocket as proper collaborative client
            if serverapp:
                file_id_manager = serverapp.web_app.settings.get("file_id_manager")
                if file_id_manager:
                    file_id = file_id_manager.get_id(abs_path)

                    # Get auth token from serverapp
                    token = getattr(serverapp, 'token', '')
                    if not token and hasattr(serverapp, 'identity_provider'):
                        token = getattr(serverapp.identity_provider, 'token', '')

                    # Construct authenticated WebSocket URL
                    base_url = f"http://127.0.0.1:{serverapp.port}"
                    ws_url = base_url.replace("http://", "ws://")
                    ws_url = f"{ws_url}/api/collaboration/room/json:notebook:{file_id}?token={token}"

                    # Use NbModelClient to connect as a proper collaborator
                    from jupyter_nbmodel_client import NbModelClient

                    async with NbModelClient(ws_url) as nb_client:
                        ydoc = nb_client._doc

                        # Use YDoc for collaborative editing
                        if cell_index < 0 or cell_index > len(ydoc.ycells):
                            return {
                                "error": f"Cell index {cell_index} out of range. Notebook has {len(ydoc.ycells)} cells",
                                "success": False
                            }

                        # Insert new code cell - use minimal dict and let create_ycell() add all metadata
                        new_cell = {
                            "cell_type": "code",
                            "source": "",
                        }
                        # Create proper CRDT cell object before inserting
                        ycell = ydoc.create_ycell(new_cell)
                        ydoc.ycells.insert(cell_index, ycell)

                        # Set source after insertion (matches jupyter-mcp-server pattern)
                        if code:
                            ycell["source"] = code

                        # Get the newly inserted cell to retrieve its ID
                        inserted_cell_id = ycell.get("id")

                        # Construct document_id for RTC integration
                        document_id = f"json:notebook:{file_id}"

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

            # Fallback to file operations
            with open(abs_path, 'r', encoding='utf-8') as f:
                notebook = nbformat.read(f, as_version=4)

            if cell_index < 0 or cell_index > len(notebook.cells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(notebook.cells)} cells",
                    "success": False
                }

            # Insert new cell
            new_cell = new_code_cell(code)
            notebook.cells.insert(cell_index, new_cell)

            # Save notebook
            with open(abs_path, 'w', encoding='utf-8') as f:
                nbformat.write(notebook, f)

            # Execute the cell
            outputs = await execute_code_with_timeout(
                kernel_manager, kernel_id, code, timeout_seconds, serverapp=serverapp
            )

            return {
                "success": True,
                "cell_index": cell_index,
                "outputs": outputs,
                "message": f"Cell inserted at index {cell_index} and executed"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

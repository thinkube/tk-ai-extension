# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for deleting cells from notebooks."""

import nbformat
from pathlib import Path
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path


class DeleteCellTool(BaseTool):
    """Delete a cell from a Jupyter notebook."""

    @property
    def name(self) -> str:
        return "delete_cell"

    @property
    def description(self) -> str:
        return "Delete a cell from a Jupyter notebook at a specific position"

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
                    "description": "Index of the cell to delete (0-based)"
                }
            },
            "required": ["notebook_path", "cell_index"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Delete a cell.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            notebook_path: Path to notebook
            cell_index: Cell index to delete

        Returns:
            Dict with deletion status
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")

        if not notebook_path or cell_index is None:
            return {
                "error": "notebook_path and cell_index are required",
                "success": False
            }

        try:
            # Get absolute path
            serverapp = getattr(contents_manager, 'parent', None)
            abs_path = get_notebook_path(serverapp, notebook_path)

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

                        # Delete cell
                        del ydoc.ycells[cell_index]

                        return {
                            "success": True,
                            "cell_index": cell_index,
                            "message": f"Cell at index {cell_index} deleted successfully"
                        }

            # Fallback to file operations
            with open(abs_path, 'r', encoding='utf-8') as f:
                notebook = nbformat.read(f, as_version=4)

            if cell_index < 0 or cell_index >= len(notebook.cells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(notebook.cells)} cells",
                    "success": False
                }

            # Delete cell
            del notebook.cells[cell_index]

            # Save notebook
            with open(abs_path, 'w', encoding='utf-8') as f:
                nbformat.write(notebook, f)

            return {
                "success": True,
                "cell_index": cell_index,
                "message": f"Cell at index {cell_index} deleted successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

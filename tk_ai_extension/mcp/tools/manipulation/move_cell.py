# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for moving cells within notebooks."""

import nbformat
from pathlib import Path
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path


class MoveCellTool(BaseTool):
    """Move a cell to a different position in a notebook."""

    @property
    def name(self) -> str:
        return "move_cell"

    @property
    def description(self) -> str:
        return "Move a cell from one position to another in a Jupyter notebook"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook"
                },
                "from_index": {
                    "type": "integer",
                    "description": "Current index of the cell (0-based)"
                },
                "to_index": {
                    "type": "integer",
                    "description": "Target index where the cell should be moved (0-based)"
                }
            },
            "required": ["notebook_path", "from_index", "to_index"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Move a cell.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            notebook_path: Path to notebook
            from_index: Current cell index
            to_index: Target cell index

        Returns:
            Dict with move status
        """
        notebook_path = kwargs.get("notebook_path")
        from_index = kwargs.get("from_index")
        to_index = kwargs.get("to_index")

        if not notebook_path or from_index is None or to_index is None:
            return {
                "error": "notebook_path, from_index, and to_index are required",
                "success": False
            }

        if from_index == to_index:
            return {
                "success": True,
                "message": "Cell is already at the target position",
                "from_index": from_index,
                "to_index": to_index
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
                        if from_index < 0 or from_index >= len(ydoc.ycells):
                            return {
                                "error": f"from_index {from_index} out of range. Notebook has {len(ydoc.ycells)} cells",
                                "success": False
                            }

                        if to_index < 0 or to_index >= len(ydoc.ycells):
                            return {
                                "error": f"to_index {to_index} out of range. Notebook has {len(ydoc.ycells)} cells",
                                "success": False
                            }

                        # Move cell using YDoc
                        cell = ydoc.ycells[from_index]
                        del ydoc.ycells[from_index]

                        # Adjust to_index if needed
                        if to_index > from_index:
                            to_index -= 1

                        ydoc.ycells.insert(to_index, cell)

                        return {
                            "success": True,
                            "from_index": from_index,
                            "to_index": to_index,
                            "message": f"Cell moved from index {from_index} to {to_index}"
                        }

            # Fallback to file operations
            with open(abs_path, 'r', encoding='utf-8') as f:
                notebook = nbformat.read(f, as_version=4)

            if from_index < 0 or from_index >= len(notebook.cells):
                return {
                    "error": f"from_index {from_index} out of range. Notebook has {len(notebook.cells)} cells",
                    "success": False
                }

            if to_index < 0 or to_index >= len(notebook.cells):
                return {
                    "error": f"to_index {to_index} out of range. Notebook has {len(notebook.cells)} cells",
                    "success": False
                }

            # Move cell
            cell = notebook.cells.pop(from_index)

            # Adjust to_index if needed
            if to_index > from_index:
                to_index -= 1

            notebook.cells.insert(to_index, cell)

            # Save notebook
            with open(abs_path, 'w', encoding='utf-8') as f:
                nbformat.write(notebook, f)

            return {
                "success": True,
                "from_index": from_index,
                "to_index": to_index,
                "message": f"Cell moved from index {from_index} to {to_index}"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

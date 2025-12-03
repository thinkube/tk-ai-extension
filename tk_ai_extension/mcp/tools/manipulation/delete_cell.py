# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for deleting cells from notebooks."""

import logging
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path

logger = logging.getLogger(__name__)


class DeleteCellTool(BaseTool):
    """Delete a cell from a Jupyter notebook."""

    @property
    def name(self) -> str:
        return "delete_cell"

    @property
    def description(self) -> str:
        return (
            "Delete a cell from a Jupyter notebook at a specific position. "
            "IMPORTANT: cell_index is 0-based position (NOT execution count). "
            "Use list_cells first to see current indices and identify which cell to delete."
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
                    "description": "0-based index of the cell to delete (NOT execution count). Use list_cells to see current indices."
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
        """Delete a cell using YDoc.

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
            if not serverapp:
                return {
                    "error": "ServerApp not available - cannot access YDoc",
                    "success": False
                }

            abs_path = get_notebook_path(serverapp, notebook_path)

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

            # Use YDoc for collaborative editing
            if cell_index < 0 or cell_index >= len(ydoc.ycells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(ydoc.ycells)} cells",
                    "success": False
                }

            # Get cell info before deletion using proper YNotebook API for undo support
            cell_dict = ydoc.get_cell(cell_index)
            cell_type = cell_dict.get("cell_type", "code")
            source_raw = cell_dict.get("source", "")
            if isinstance(source_raw, list):
                previous_content = "".join(source_raw)
            else:
                previous_content = str(source_raw)

            # Delete cell using pop for proper CRDT sync
            ydoc.ycells.pop(cell_index)

            return {
                "success": True,
                "cell_index": cell_index,
                "message": f"Cell at index {cell_index} deleted successfully",
                "previous_content": previous_content,  # For undo support
                "cell_type": cell_type  # For undo support
            }

        except Exception as e:
            logger.error(f"Failed to delete cell: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

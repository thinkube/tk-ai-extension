# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for inserting cells into notebooks."""

import logging
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path

logger = logging.getLogger(__name__)


class InsertCellTool(BaseTool):
    """Insert a new cell into a Jupyter notebook."""

    @property
    def name(self) -> str:
        return "insert_cell"

    @property
    def description(self) -> str:
        return "Insert a new cell (code or markdown) into a Jupyter notebook at a specific position"

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
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                    "description": "Type of cell to insert"
                },
                "source": {
                    "type": "string",
                    "description": "Content of the cell"
                }
            },
            "required": ["notebook_path", "cell_index", "cell_type", "source"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Insert a cell using YDoc.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            notebook_path: Path to notebook
            cell_index: Where to insert
            cell_type: Type of cell (code/markdown)
            source: Cell content

        Returns:
            Dict with insertion status
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")
        cell_type = kwargs.get("cell_type")
        source = kwargs.get("source")

        if not notebook_path or cell_index is None or not cell_type or source is None:
            return {
                "error": "notebook_path, cell_index, cell_type, and source are required",
                "success": False
            }

        if cell_type not in ["code", "markdown"]:
            return {
                "error": f"Invalid cell_type '{cell_type}'. Must be 'code' or 'markdown'",
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

            # Validate cell index
            if cell_index < 0 or cell_index > len(ydoc.ycells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(ydoc.ycells)} cells",
                    "success": False
                }

            # Insert new cell - use minimal dict and let create_ycell() add all metadata
            new_cell = {
                "cell_type": cell_type,
                "source": "",
            }

            # Code cells require execution_count (null for unexecuted)
            if cell_type == "code":
                new_cell["execution_count"] = None

            # Create proper CRDT cell object before inserting
            ycell = ydoc.create_ycell(new_cell)
            ydoc.ycells.insert(cell_index, ycell)

            # Set source after insertion (matches jupyter-mcp-server pattern)
            if source:
                ycell["source"] = source

            return {
                "success": True,
                "cell_index": cell_index,
                "cell_type": cell_type,
                "message": f"{cell_type.capitalize()} cell inserted at index {cell_index}"
            }

        except Exception as e:
            logger.error(f"Failed to insert cell: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for overwriting cell content."""

import difflib
import logging
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path

logger = logging.getLogger(__name__)


class OverwriteCellTool(BaseTool):
    """Overwrite the source of an existing cell."""

    @property
    def name(self) -> str:
        return "overwrite_cell_source"

    @property
    def description(self) -> str:
        return (
            "Overwrite the source of an existing cell. Shows a diff of the changes made. "
            "IMPORTANT: cell_index is 0-based position (NOT execution count). "
            "Use list_cells first to see current indices and identify which cell to modify."
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
                    "description": "0-based index of the cell to overwrite (NOT execution count). Use list_cells to see current indices."
                },
                "source": {
                    "type": "string",
                    "description": "New cell source - must match existing cell type"
                }
            },
            "required": ["notebook_path", "cell_index", "source"]
        }

    def _generate_diff(self, old_source: str, new_source: str) -> str:
        """Generate unified diff between old and new source."""
        old_lines = old_source.splitlines(keepends=False)
        new_lines = new_source.splitlines(keepends=False)

        diff_lines = list(difflib.unified_diff(
            old_lines,
            new_lines,
            lineterm='',
            n=3  # Number of context lines
        ))

        # Remove the first 3 lines (file headers) from unified_diff output
        if len(diff_lines) > 3:
            return '\n'.join(diff_lines[3:])
        return "no changes detected"

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Overwrite a cell's source using YDoc.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            notebook_path: Path to notebook
            cell_index: Cell index to overwrite
            source: New cell source

        Returns:
            Dict with overwrite status and diff
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")
        source = kwargs.get("source")

        if not notebook_path or cell_index is None or source is None:
            return {
                "error": "notebook_path, cell_index, and source are required",
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

            # Get original cell content and type
            cell = ydoc.ycells[cell_index]
            cell_type = cell.get("cell_type", "code")
            old_source_raw = cell.get("source", "")
            if isinstance(old_source_raw, list):
                old_source = "".join(old_source_raw)
            else:
                old_source = str(old_source_raw)

            # Set new cell source within a transaction for atomic update
            with ydoc.ycells[cell_index].doc.transaction():
                ydoc.ycells[cell_index]["source"] = source

            # Generate diff
            diff_content = self._generate_diff(old_source, source)

            if not diff_content.strip() or diff_content == "no changes detected":
                return {
                    "success": True,
                    "cell_index": cell_index,
                    "cell_type": cell_type,
                    "message": "Cell overwritten successfully - no changes detected",
                    "previous_content": old_source  # For undo support
                }

            return {
                "success": True,
                "cell_index": cell_index,
                "cell_type": cell_type,
                "message": f"Cell {cell_index} overwritten successfully!",
                "diff": diff_content,
                "previous_content": old_source  # For undo support
            }

        except Exception as e:
            logger.error(f"Failed to overwrite cell: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

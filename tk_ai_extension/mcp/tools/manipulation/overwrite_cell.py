# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for overwriting cell content."""

import difflib
import nbformat
from pathlib import Path
from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import get_jupyter_ydoc, get_notebook_path


class OverwriteCellTool(BaseTool):
    """Overwrite the source of an existing cell."""

    @property
    def name(self) -> str:
        return "overwrite_cell_source"

    @property
    def description(self) -> str:
        return "Overwrite the source of an existing cell. Shows a diff of the changes made."

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
                    "description": "Index of the cell to overwrite (0-based)"
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
        """Overwrite a cell's source.

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

                        # Get original cell content
                        old_source_raw = ydoc.ycells[cell_index].get("source", "")
                        if isinstance(old_source_raw, list):
                            old_source = "".join(old_source_raw)
                        else:
                            old_source = str(old_source_raw)

                        # Set new cell source
                        ydoc.ycells[cell_index]["source"] = source

                        # Generate diff
                        diff_content = self._generate_diff(old_source, source)

                        if not diff_content.strip() or diff_content == "no changes detected":
                            return {
                                "success": True,
                                "cell_index": cell_index,
                                "message": "Cell overwritten successfully - no changes detected"
                            }

                        return {
                            "success": True,
                            "cell_index": cell_index,
                            "message": f"Cell {cell_index} overwritten successfully!",
                            "diff": diff_content
                        }

            # Fallback to file operations
            with open(abs_path, 'r', encoding='utf-8') as f:
                notebook = nbformat.read(f, as_version=4)

            if cell_index < 0 or cell_index >= len(notebook.cells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(notebook.cells)} cells",
                    "success": False
                }

            # Get original cell content
            old_source = notebook.cells[cell_index].source

            # Set new cell source
            notebook.cells[cell_index].source = source

            # Save notebook
            with open(abs_path, 'w', encoding='utf-8') as f:
                nbformat.write(notebook, f)

            # Generate diff
            diff_content = self._generate_diff(old_source, source)

            if not diff_content.strip() or diff_content == "no changes detected":
                return {
                    "success": True,
                    "cell_index": cell_index,
                    "message": "Cell overwritten successfully - no changes detected"
                }

            return {
                "success": True,
                "cell_index": cell_index,
                "message": f"Cell {cell_index} overwritten successfully!",
                "diff": diff_content
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

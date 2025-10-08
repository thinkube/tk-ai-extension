# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""List cells tool (simplified for local-only use)."""

from typing import Any, Optional
from .base import BaseTool


class ListCellsTool(BaseTool):
    """Tool to list all cells in a notebook."""

    @property
    def name(self) -> str:
        return "list_cells"

    @property
    def description(self) -> str:
        return "List all cells in a notebook with their types and preview"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook": {
                    "type": "string",
                    "description": "Path to the notebook file (e.g., 'notebook.ipynb')"
                }
            },
            "required": ["notebook"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        notebook: str = None,
        **kwargs
    ) -> str:
        """Execute the list_cells tool.

        Args:
            notebook: Path to the notebook

        Returns:
            Formatted list of cells
        """
        if not notebook:
            return "Error: notebook parameter is required"

        try:
            # Get notebook content
            model = await contents_manager.get(notebook, content=True, type='notebook')
            cells = model.get('content', {}).get('cells', [])

            if not cells:
                return f"Notebook '{notebook}' has no cells"

            result = [f"Cells in '{notebook}':"]
            result.append("-" * 80)

            for i, cell in enumerate(cells):
                cell_type = cell.get('cell_type', 'unknown')
                source = cell.get('source', '')

                # Format source (handle both string and list formats)
                if isinstance(source, list):
                    source = ''.join(source)

                # Get preview (first 50 chars)
                preview = source[:50].replace('\n', ' ')
                if len(source) > 50:
                    preview += "..."

                # Add execution count for code cells
                exec_info = ""
                if cell_type == "code":
                    execution_count = cell.get('execution_count')
                    if execution_count is not None:
                        exec_info = f" [#{execution_count}]"

                result.append(f"{i:3d}. {cell_type:10s}{exec_info:10s} | {preview}")

            return "\n".join(result)

        except FileNotFoundError:
            return f"Error: Notebook '{notebook}' not found"
        except Exception as e:
            return f"Error listing cells: {str(e)}"

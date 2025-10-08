# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Execute cell tool (simplified for local-only use)."""

from typing import Any, Optional
from .base import BaseTool


class ExecuteCellTool(BaseTool):
    """Tool to execute a cell in a notebook."""

    @property
    def name(self) -> str:
        return "execute_cell"

    @property
    def description(self) -> str:
        return "Execute a specific cell in a notebook and return its output"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook": {
                    "type": "string",
                    "description": "Path to the notebook file (e.g., 'notebook.ipynb')"
                },
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to execute (0-based)"
                }
            },
            "required": ["notebook", "cell_index"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        notebook: str = None,
        cell_index: int = None,
        **kwargs
    ) -> str:
        """Execute the execute_cell tool.

        Args:
            notebook: Path to the notebook
            cell_index: Index of the cell to execute

        Returns:
            Execution result
        """
        if not notebook:
            return "Error: notebook parameter is required"
        if cell_index is None:
            return "Error: cell_index parameter is required"

        try:
            # Get notebook content
            model = await contents_manager.get(notebook, content=True, type='notebook')
            cells = model.get('content', {}).get('cells', [])

            if cell_index < 0 or cell_index >= len(cells):
                return f"Error: cell_index {cell_index} out of range (notebook has {len(cells)} cells)"

            cell = cells[cell_index]
            cell_type = cell.get('cell_type', 'unknown')

            if cell_type != 'code':
                return f"Error: Cell {cell_index} is not a code cell (type: {cell_type})"

            source = cell.get('source', '')
            if isinstance(source, list):
                source = ''.join(source)

            if not source.strip():
                return f"Cell {cell_index} is empty"

            # TODO: Implement actual kernel execution
            # This would require:
            # 1. Starting/connecting to a kernel
            # 2. Executing the code
            # 3. Collecting outputs
            # 4. Handling timeouts and errors

            return (
                f"Note: Cell execution not fully implemented yet.\n\n"
                f"Cell {cell_index} code:\n"
                f"```python\n{source}\n```\n\n"
                f"To execute this cell, please use JupyterLab UI for now."
            )

        except FileNotFoundError:
            return f"Error: Notebook '{notebook}' not found"
        except Exception as e:
            return f"Error executing cell: {str(e)}"

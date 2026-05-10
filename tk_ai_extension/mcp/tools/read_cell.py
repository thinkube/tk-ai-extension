# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Read cell tool (simplified for local-only use)."""

from typing import Any, Optional
from .base import BaseTool


class ReadCellTool(BaseTool):
    """Tool to read a specific cell from a notebook."""

    @property
    def name(self) -> str:
        return "read_cell"

    @property
    def description(self) -> str:
        return "Read the content of a specific cell from a notebook by index"

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
                    "description": "Index of the cell to read (0-based)"
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
        """Execute the read_cell tool.

        Args:
            notebook: Path to the notebook
            cell_index: Index of the cell to read

        Returns:
            Cell content formatted as text
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
            source = cell.get('source', '')

            # Format source (handle both string and list formats)
            if isinstance(source, list):
                source = ''.join(source)

            result = [
                f"Cell {cell_index} ({cell_type}):",
                "```" + ("python" if cell_type == "code" else ""),
                source,
                "```"
            ]

            # Add execution count for code cells
            if cell_type == "code":
                execution_count = cell.get('execution_count')
                if execution_count is not None:
                    result.insert(1, f"Execution count: {execution_count}")

            # Add outputs for code cells
            outputs = cell.get('outputs', [])
            if outputs:
                result.append("\nOutputs:")
                for i, output in enumerate(outputs):
                    output_type = output.get('output_type', 'unknown')
                    if output_type == 'stream':
                        text = output.get('text', '')
                        if isinstance(text, list):
                            text = ''.join(text)
                        result.append(f"  [{output_type}] {text}")
                    elif output_type == 'execute_result' or output_type == 'display_data':
                        data = output.get('data', {})
                        text = data.get('text/plain', str(data))
                        if isinstance(text, list):
                            text = ''.join(text)
                        result.append(f"  [{output_type}] {text}")
                    elif output_type == 'error':
                        ename = output.get('ename', 'Error')
                        evalue = output.get('evalue', '')
                        result.append(f"  [error] {ename}: {evalue}")

            return "\n".join(result)

        except FileNotFoundError:
            return f"Error: Notebook '{notebook}' not found"
        except Exception as e:
            return f"Error reading cell: {str(e)}"

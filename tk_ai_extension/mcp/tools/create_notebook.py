# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for creating new Jupyter notebooks."""

from typing import Any, Optional, List, Dict
import nbformat
from nbformat.v4 import new_notebook, new_markdown_cell, new_code_cell
from .base import BaseTool


class CreateNotebookTool(BaseTool):
    """Create a new Jupyter notebook with optional initial cells."""

    @property
    def name(self) -> str:
        return "create_notebook"

    @property
    def description(self) -> str:
        return "Create a new Jupyter notebook with optional markdown and code cells"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path where to create the notebook (relative to notebooks directory)"
                },
                "cells": {
                    "type": "array",
                    "description": "Optional initial cells to add to the notebook",
                    "items": {
                        "type": "object",
                        "properties": {
                            "cell_type": {
                                "type": "string",
                                "enum": ["markdown", "code"],
                                "description": "Type of cell"
                            },
                            "source": {
                                "type": "string",
                                "description": "Cell content"
                            }
                        },
                        "required": ["cell_type", "source"]
                    }
                }
            },
            "required": ["path"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Create a new notebook.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            path: Notebook path
            cells: Optional list of initial cells

        Returns:
            Dict with creation status and path
        """
        path = kwargs.get("path")
        initial_cells = kwargs.get("cells", [])

        if not path:
            return {
                "error": "path parameter is required",
                "success": False
            }

        # Ensure path ends with .ipynb
        if not path.endswith('.ipynb'):
            path = path + '.ipynb'

        try:
            # Create new notebook
            nb = new_notebook()

            # Add initial cells if provided
            for cell_spec in initial_cells:
                cell_type = cell_spec.get("cell_type", "code")
                source = cell_spec.get("source", "")

                if cell_type == "markdown":
                    cell = new_markdown_cell(source)
                else:
                    cell = new_code_cell(source)

                nb.cells.append(cell)

            # Save the notebook
            model = {
                "type": "notebook",
                "content": nb,
                "format": "json"
            }

            contents_manager.save(model, path)

            return {
                "success": True,
                "path": path,
                "message": f"Notebook created successfully at {path}",
                "cells_added": len(initial_cells)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "path": path
            }

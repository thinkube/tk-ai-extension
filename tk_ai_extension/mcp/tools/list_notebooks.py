# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""List notebooks tool (simplified for local-only use)."""

from typing import Any, Optional, List
from .base import BaseTool


class ListNotebooksTool(BaseTool):
    """Tool to list all notebooks in the Jupyter server."""

    @property
    def name(self) -> str:
        return "list_notebooks"

    @property
    def description(self) -> str:
        return "List all .ipynb files in the current directory and subdirectories"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def _list_notebooks_recursive(
        self,
        contents_manager: Any,
        path: str = "",
        notebooks: Optional[List[str]] = None
    ) -> List[str]:
        """Recursively list all notebooks."""
        if notebooks is None:
            notebooks = []

        try:
            model = await contents_manager.get(path, content=True, type='directory')
            for item in model.get('content', []):
                full_path = f"{path}/{item['name']}" if path else item['name']
                if item['type'] == "directory":
                    await self._list_notebooks_recursive(
                        contents_manager, full_path, notebooks
                    )
                elif item['type'] == "notebook" or item['name'].endswith('.ipynb'):
                    notebooks.append(full_path)
        except Exception:
            # Skip inaccessible directories
            pass

        return notebooks

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> str:
        """Execute the list_notebooks tool.

        Returns:
            Formatted list of notebook paths
        """
        all_notebooks = await self._list_notebooks_recursive(contents_manager)

        if not all_notebooks:
            return "No notebooks found in the current directory."

        return "Notebooks:\n" + "\n".join(f"  - {nb}" for nb in sorted(all_notebooks))

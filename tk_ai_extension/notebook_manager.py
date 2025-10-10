# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""
Notebook and Kernel Management Module

Centralized management for Jupyter notebooks and kernels in JUPYTER_SERVER mode.
Adapted from jupyter-mcp-server for tk-ai-extension use.
"""

from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class NotebookManager:
    """
    Centralized manager for notebooks and their corresponding kernels.

    This is simplified for JUPYTER_SERVER mode (local) where:
    - Notebooks are identified by path
    - Kernels are managed by JupyterLab's kernel_manager
    - We track which notebook is currently "active" for Thinky
    """

    def __init__(self):
        """Initialize the notebook manager."""
        self._notebooks: Dict[str, Dict[str, Any]] = {}
        self._current_notebook: Optional[str] = None
        logger.info("NotebookManager initialized")

    def __contains__(self, name: str) -> bool:
        """Check if a notebook is managed by this instance."""
        return name in self._notebooks

    def add_notebook(
        self,
        name: str,
        kernel_info: Dict[str, Any],
        path: str
    ) -> None:
        """
        Add a notebook to the manager.

        Args:
            name: Unique identifier for the notebook (user-friendly name)
            kernel_info: Kernel metadata dict with 'id' key
            path: Notebook file path
        """
        self._notebooks[name] = {
            "kernel": kernel_info,
            "path": path
        }

        # Set as current notebook if this is the first one
        if self._current_notebook is None:
            self._current_notebook = name

        logger.info(f"Added notebook '{name}' at path '{path}' with kernel {kernel_info.get('id')}")

    def remove_notebook(self, name: str) -> bool:
        """
        Remove a notebook from the manager.

        Args:
            name: Notebook identifier

        Returns:
            True if removed successfully, False if not found
        """
        if name in self._notebooks:
            del self._notebooks[name]

            # If we removed the current notebook, update the current pointer
            if self._current_notebook == name:
                # Set to another notebook if available
                if self._notebooks:
                    self._current_notebook = next(iter(self._notebooks.keys()))
                else:
                    self._current_notebook = None

            logger.info(f"Removed notebook '{name}'")
            return True
        return False

    def get_kernel_id(self, name: str) -> Optional[str]:
        """
        Get the kernel ID for a specific notebook.

        Args:
            name: Notebook identifier

        Returns:
            Kernel ID string or None if not found
        """
        if name in self._notebooks:
            kernel_info = self._notebooks[name]["kernel"]
            return kernel_info.get("id")
        return None

    def set_current_notebook(self, name: str) -> bool:
        """
        Set the currently active notebook.

        Args:
            name: Notebook identifier

        Returns:
            True if set successfully, False if notebook doesn't exist
        """
        if name in self._notebooks:
            self._current_notebook = name
            logger.info(f"Set current notebook to '{name}'")
            return True
        logger.warning(f"Cannot set current notebook to '{name}' - not found")
        return False

    def get_current_notebook(self) -> Optional[str]:
        """
        Get the name of the currently active notebook.

        Returns:
            Current notebook name or None if no active notebook
        """
        return self._current_notebook

    def get_current_notebook_path(self) -> Optional[str]:
        """
        Get the file path of the currently active notebook.

        Returns:
            Notebook file path or None if no active notebook
        """
        if self._current_notebook and self._current_notebook in self._notebooks:
            return self._notebooks[self._current_notebook]["path"]
        return None

    def get_current_kernel_id(self) -> Optional[str]:
        """
        Get the kernel ID of the currently active notebook.

        Returns:
            Kernel ID or None if no active notebook
        """
        if self._current_notebook:
            return self.get_kernel_id(self._current_notebook)
        return None

    def list_all_notebooks(self) -> Dict[str, Dict[str, Any]]:
        """
        Get information about all managed notebooks.

        Returns:
            Dictionary with notebook names as keys and their info as values
        """
        result = {}
        for name, notebook_data in self._notebooks.items():
            result[name] = {
                "path": notebook_data["path"],
                "kernel_id": notebook_data["kernel"].get("id"),
                "is_current": name == self._current_notebook
            }
        return result

    def is_empty(self) -> bool:
        """Check if the manager is empty (no notebooks)."""
        return len(self._notebooks) == 0

# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for quickly checking if a module is available."""

import logging
from typing import Any, Optional, Dict, List
from ..base import BaseTool

logger = logging.getLogger(__name__)


class CheckModuleTool(BaseTool):
    """Quick check if one or more Python modules are available."""

    @property
    def name(self) -> str:
        return "check_module"

    @property
    def description(self) -> str:
        return (
            "Quick boolean check if one or more Python modules are installed. "
            "Much faster than list_python_modules for checking specific packages. "
            "Returns availability status and version for each module."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "module_names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of module names to check (e.g., ['numpy', 'plotly', 'torch'])"
                },
                "module_name": {
                    "type": "string",
                    "description": "Single module name to check (alternative to module_names)"
                }
            }
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        notebook_manager: Optional[Any] = None,
        serverapp: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Check if modules are available.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager (unused)
            serverapp: Jupyter ServerApp instance (unused)
            module_names: List of module names to check
            module_name: Single module name (alternative)

        Returns:
            Dict with availability status for each module
        """
        # Handle both single and multiple module names
        module_names = kwargs.get("module_names")
        single_module = kwargs.get("module_name")

        if not module_names and not single_module:
            return {
                "success": False,
                "error": "Either module_name or module_names is required"
            }

        # Convert to list
        if single_module:
            module_names = [single_module]
        elif not isinstance(module_names, list):
            return {
                "success": False,
                "error": "module_names must be a list of strings"
            }

        try:
            # Import here to avoid issues if not available
            import importlib.metadata as metadata

            results = []

            for module_name in module_names:
                try:
                    dist = metadata.distribution(module_name)
                    results.append({
                        "module": module_name,
                        "available": True,
                        "version": dist.metadata['Version']
                    })
                except metadata.PackageNotFoundError:
                    results.append({
                        "module": module_name,
                        "available": False,
                        "version": None
                    })

            # If checking single module, return simplified response
            if single_module:
                return {
                    "success": True,
                    "module": results[0]["module"],
                    "available": results[0]["available"],
                    "version": results[0]["version"]
                }

            # For multiple modules, return full list
            available_count = sum(1 for r in results if r["available"])
            return {
                "success": True,
                "modules": results,
                "total_checked": len(results),
                "available_count": available_count,
                "unavailable_count": len(results) - available_count
            }

        except ImportError:
            return {
                "success": False,
                "error": "importlib.metadata not available (requires Python 3.8+)"
            }
        except Exception as e:
            logger.error(f"Failed to check modules: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

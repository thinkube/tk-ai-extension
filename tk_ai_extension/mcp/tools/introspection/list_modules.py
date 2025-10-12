# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for listing installed Python packages."""

import logging
import re
from typing import Any, Optional, Dict, List
from ..base import BaseTool

logger = logging.getLogger(__name__)


class ListModulesTool(BaseTool):
    """List all installed Python packages in the notebook environment."""

    @property
    def name(self) -> str:
        return "list_python_modules"

    @property
    def description(self) -> str:
        return (
            "List all installed Python packages in the notebook environment. "
            "Useful for discovering available libraries for visualization, data processing, ML, etc. "
            "Returns package names and versions."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "filter_pattern": {
                    "type": "string",
                    "description": "Optional regex pattern to filter packages (e.g., 'plot.*', 'scikit.*', 'torch.*')"
                },
                "show_versions": {
                    "type": "boolean",
                    "description": "Include version numbers (default: true)",
                    "default": True
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of packages to return (default: 100)",
                    "default": 100
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
        """List installed Python packages.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager (unused)
            serverapp: Jupyter ServerApp instance (unused)
            filter_pattern: Optional regex to filter packages
            show_versions: Include version numbers
            limit: Maximum packages to return

        Returns:
            Dict with list of packages
        """
        filter_pattern = kwargs.get("filter_pattern")
        show_versions = kwargs.get("show_versions", True)
        limit = kwargs.get("limit", 100)

        try:
            # Import here to avoid issues if not available
            import importlib.metadata as metadata

            packages: List[Dict[str, str]] = []

            # Compile regex pattern if provided
            pattern = None
            if filter_pattern:
                try:
                    pattern = re.compile(filter_pattern, re.IGNORECASE)
                except re.error as e:
                    return {
                        "success": False,
                        "error": f"Invalid regex pattern: {e}"
                    }

            # Iterate through all distributions
            for dist in metadata.distributions():
                name = dist.metadata['Name']

                # Apply filter if provided
                if pattern and not pattern.search(name):
                    continue

                package_info = {"name": name}
                if show_versions:
                    package_info["version"] = dist.metadata['Version']

                packages.append(package_info)

                # Respect limit
                if len(packages) >= limit:
                    break

            # Sort by name
            packages.sort(key=lambda x: x['name'].lower())

            result = {
                "success": True,
                "packages": packages,
                "total_count": len(packages)
            }

            if pattern:
                result["filter_applied"] = filter_pattern

            if len(packages) >= limit:
                result["truncated"] = True
                result["message"] = f"Results limited to {limit} packages. Use 'limit' parameter to see more."

            return result

        except ImportError:
            return {
                "success": False,
                "error": "importlib.metadata not available (requires Python 3.8+)"
            }
        except Exception as e:
            logger.error(f"Failed to list modules: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

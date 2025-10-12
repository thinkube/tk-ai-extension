# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for getting detailed information about a Python package."""

import logging
from typing import Any, Optional, Dict
from ..base import BaseTool

logger = logging.getLogger(__name__)


class GetModuleInfoTool(BaseTool):
    """Get detailed information about a specific Python package."""

    @property
    def name(self) -> str:
        return "get_module_info"

    @property
    def description(self) -> str:
        return (
            "Get detailed information about a specific Python package including version, "
            "summary, homepage, dependencies, and more. Useful for understanding what a "
            "package does and its requirements."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "package_name": {
                    "type": "string",
                    "description": "Name of the package (e.g., 'numpy', 'plotly', 'torch')"
                },
                "include_dependencies": {
                    "type": "boolean",
                    "description": "Include package dependencies (default: false)",
                    "default": False
                }
            },
            "required": ["package_name"]
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
        """Get detailed package information.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager (unused)
            serverapp: Jupyter ServerApp instance (unused)
            package_name: Name of the package
            include_dependencies: Include dependency information

        Returns:
            Dict with package details
        """
        package_name = kwargs.get("package_name")
        include_dependencies = kwargs.get("include_dependencies", False)

        if not package_name:
            return {
                "success": False,
                "error": "package_name is required"
            }

        try:
            # Import here to avoid issues if not available
            import importlib.metadata as metadata

            # Get distribution info
            try:
                dist = metadata.distribution(package_name)
            except metadata.PackageNotFoundError:
                return {
                    "success": False,
                    "error": f"Package '{package_name}' not found. Use list_python_modules to see available packages."
                }

            # Build response with available metadata
            info = {
                "success": True,
                "name": dist.metadata['Name'],
                "version": dist.metadata['Version']
            }

            # Add optional metadata fields if available
            optional_fields = [
                'Summary',
                'Home-page',
                'Author',
                'Author-email',
                'License',
                'Platform',
                'Classifier'
            ]

            for field in optional_fields:
                value = dist.metadata.get(field)
                if value:
                    # Convert field name to lowercase with underscores
                    key = field.lower().replace('-', '_')
                    info[key] = value

            # Add dependencies if requested
            if include_dependencies:
                requires = dist.metadata.get_all('Requires-Dist')
                if requires:
                    info['dependencies'] = requires
                else:
                    info['dependencies'] = []

            # Add installation location
            if dist.locate_file:
                try:
                    location = str(dist.locate_file(''))
                    info['location'] = location
                except Exception:
                    pass  # Location not always available

            return info

        except ImportError:
            return {
                "success": False,
                "error": "importlib.metadata not available (requires Python 3.8+)"
            }
        except Exception as e:
            logger.error(f"Failed to get module info for {package_name}: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for listing running Jupyter kernels."""

from typing import Any, Optional, Dict, List
from ..base import BaseTool


class ListRunningKernelsTool(BaseTool):
    """List all currently running Jupyter kernels."""

    @property
    def name(self) -> str:
        return "list_running_kernels"

    @property
    def description(self) -> str:
        return "List all currently running Jupyter kernels with their IDs and connection information"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {},
            "required": []
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """List running kernels.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)

        Returns:
            Dict with list of running kernels
        """
        try:
            kernels = []

            for kernel_info in kernel_manager.list_kernels():
                kernel_id = kernel_info['id']
                kernel_name = kernel_info.get('name', 'unknown')
                last_activity = kernel_info.get('last_activity', None)
                execution_state = kernel_info.get('execution_state', 'unknown')
                connections = kernel_info.get('connections', 0)

                kernels.append({
                    "id": kernel_id,
                    "name": kernel_name,
                    "last_activity": last_activity,
                    "execution_state": execution_state,
                    "connections": connections
                })

            return {
                "success": True,
                "kernels": kernels,
                "count": len(kernels)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "kernels": []
            }

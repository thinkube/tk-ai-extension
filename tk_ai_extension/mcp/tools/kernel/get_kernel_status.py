# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for getting Jupyter kernel status."""

from typing import Any, Optional, Dict
from ..base import BaseTool


class GetKernelStatusTool(BaseTool):
    """Get the status of a Jupyter kernel."""

    @property
    def name(self) -> str:
        return "get_kernel_status"

    @property
    def description(self) -> str:
        return "Get the current status of a Jupyter kernel (idle, busy, etc.)"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to check"
                }
            },
            "required": ["kernel_id"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Get kernel status.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            kernel_id: ID of the kernel to check

        Returns:
            Dict with kernel status information
        """
        kernel_id = kwargs.get("kernel_id")

        if not kernel_id:
            return {
                "error": "kernel_id parameter is required",
                "success": False
            }

        try:
            # Check if kernel exists
            kernels = list(kernel_manager.list_kernels())
            kernel_info = None

            for k in kernels:
                if k['id'] == kernel_id:
                    kernel_info = k
                    break

            if not kernel_info:
                return {
                    "error": f"Kernel '{kernel_id}' not found",
                    "success": False,
                    "available_kernels": [k['id'] for k in kernels]
                }

            return {
                "success": True,
                "kernel_id": kernel_id,
                "name": kernel_info.get('name', 'unknown'),
                "execution_state": kernel_info.get('execution_state', 'unknown'),
                "last_activity": kernel_info.get('last_activity'),
                "connections": kernel_info.get('connections', 0)
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "kernel_id": kernel_id
            }

# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for restarting Jupyter kernels."""

from typing import Any, Optional, Dict
from ..base import BaseTool


class RestartKernelTool(BaseTool):
    """Restart a Jupyter kernel."""

    @property
    def name(self) -> str:
        return "restart_kernel"

    @property
    def description(self) -> str:
        return "Restart a Jupyter kernel by its ID. This clears all variables and resets the kernel state."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to restart"
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
        """Restart a kernel.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            kernel_id: ID of the kernel to restart

        Returns:
            Dict with restart status
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
            kernel_exists = any(k['id'] == kernel_id for k in kernels)

            if not kernel_exists:
                return {
                    "error": f"Kernel '{kernel_id}' not found",
                    "success": False,
                    "available_kernels": [k['id'] for k in kernels]
                }

            # Restart the kernel
            await kernel_manager.restart_kernel(kernel_id)

            return {
                "success": True,
                "kernel_id": kernel_id,
                "message": f"Kernel {kernel_id} restarted successfully"
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "kernel_id": kernel_id
            }

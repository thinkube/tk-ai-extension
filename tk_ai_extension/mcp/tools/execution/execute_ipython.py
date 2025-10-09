# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for executing arbitrary IPython code."""

from typing import Any, Optional, Dict
from ..base import BaseTool
from ..utils import execute_code_with_timeout


class ExecuteIPythonTool(BaseTool):
    """Execute arbitrary IPython code in a kernel."""

    @property
    def name(self) -> str:
        return "execute_ipython"

    @property
    def description(self) -> str:
        return "Execute arbitrary IPython code in a kernel without modifying any notebook"

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to execute in"
                },
                "code": {
                    "type": "string",
                    "description": "Python/IPython code to execute"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum time to wait for execution (default: 300)",
                    "default": 300
                }
            },
            "required": ["kernel_id", "code"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute IPython code.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            kernel_id: Kernel ID to use
            code: Code to execute
            timeout_seconds: Execution timeout

        Returns:
            Dict with execution results
        """
        kernel_id = kwargs.get("kernel_id")
        code = kwargs.get("code")
        timeout_seconds = kwargs.get("timeout_seconds", 300)

        if not kernel_id or not code:
            return {
                "error": "kernel_id and code are required",
                "success": False
            }

        try:
            # Check if kernel exists
            kernels = list(kernel_manager.list_kernels())
            if not any(k['id'] == kernel_id for k in kernels):
                return {
                    "error": f"Kernel '{kernel_id}' not found",
                    "success": False,
                    "available_kernels": [k['id'] for k in kernels]
                }

            # Execute code
            outputs = await execute_code_with_timeout(
                kernel_manager, kernel_id, code, timeout_seconds
            )

            return {
                "success": True,
                "outputs": outputs
            }

        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }

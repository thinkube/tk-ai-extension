# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for checking async execution status."""

import logging
from typing import Any, Optional, Dict
from ..base import BaseTool

# Import the shared execution tracking dict
from .execute_cell_async import _async_executions

logger = logging.getLogger(__name__)


class CheckExecutionStatusTool(BaseTool):
    """Check the status of an async cell execution."""

    @property
    def name(self) -> str:
        return "check_execution_status"

    @property
    def description(self) -> str:
        return (
            "Check the status of an async cell execution started with execute_cell_async. "
            "Returns the current status (running, completed, error) and outputs if available. "
            "Use this tool to poll long-running executions without blocking."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "Execution ID returned by execute_cell_async"
                }
            },
            "required": ["execution_id"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Check execution status.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            execution_id: Execution ID to check

        Returns:
            Dict with execution status and results
        """
        execution_id = kwargs.get("execution_id")

        if not execution_id:
            return {
                "error": "execution_id parameter is required",
                "success": False
            }

        if execution_id not in _async_executions:
            return {
                "error": f"Execution ID '{execution_id}' not found",
                "success": False
            }

        execution_info = _async_executions[execution_id]

        result = {
            "success": True,
            "execution_id": execution_id,
            "status": execution_info["status"],
            "cell_index": execution_info["cell_index"],
            "notebook_path": execution_info["notebook_path"],
            "kernel_id": execution_info["kernel_id"]
        }

        # Add outputs if completed
        if execution_info["status"] == "completed":
            result["outputs"] = execution_info["outputs"]
            result["message"] = f"Execution completed successfully with {len(execution_info['outputs'])} outputs"

        # Add error if failed
        elif execution_info["status"] == "error":
            result["error"] = execution_info["error"]
            result["message"] = f"Execution failed: {execution_info['error']}"

        # Running status
        elif execution_info["status"] == "running":
            result["message"] = "Execution is still running. Check again later."

        return result

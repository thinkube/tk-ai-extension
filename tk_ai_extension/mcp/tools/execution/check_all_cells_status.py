# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for checking execute_all_cells status."""

import logging
from typing import Any, Optional, Dict
from ..base import BaseTool

# Import the shared execution tracking dict
from .execute_all_cells import _async_executions_all

logger = logging.getLogger(__name__)


class CheckAllCellsStatusTool(BaseTool):
    """Check the status of an execute_all_cells operation."""

    @property
    def name(self) -> str:
        return "check_all_cells_status"

    @property
    def description(self) -> str:
        return (
            "Check the status of an execute_all_cells operation. "
            "Returns progress (current cell, completed cells, total cells) and final results. "
            "Essential for self-healing workflows to verify successful re-execution."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "execution_id": {
                    "type": "string",
                    "description": "Execution ID returned by execute_all_cells"
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
        """Check execute_all status.

        Args:
            contents_manager: Jupyter contents manager (unused)
            kernel_manager: Jupyter kernel manager (unused)
            kernel_spec_manager: Kernel spec manager (unused)
            execution_id: Execution ID to check

        Returns:
            Dict with execution status and progress
        """
        execution_id = kwargs.get("execution_id")

        if not execution_id:
            return {
                "error": "execution_id parameter is required",
                "success": False
            }

        if execution_id not in _async_executions_all:
            return {
                "error": f"Execution ID '{execution_id}' not found",
                "success": False
            }

        execution_info = _async_executions_all[execution_id]

        result = {
            "success": True,
            "execution_id": execution_id,
            "status": execution_info["status"],
            "total_cells": execution_info["total_cells"],
            "completed_cells": execution_info["completed_cells"],
            "current_cell_index": execution_info["current_cell_index"],
            "notebook_path": execution_info["notebook_path"],
            "kernel_id": execution_info["kernel_id"]
        }

        # Running status
        if execution_info["status"] == "running":
            progress_pct = int((execution_info["completed_cells"] / execution_info["total_cells"]) * 100)
            result["progress_percent"] = progress_pct
            if execution_info["current_cell_index"] is not None:
                result["message"] = f"Executing cell {execution_info['current_cell_index']} ({execution_info['completed_cells']}/{execution_info['total_cells']} completed, {progress_pct}%)"
            else:
                result["message"] = "Preparing to execute cells..."

        # Completed status
        elif execution_info["status"] == "completed":
            result["results"] = execution_info["results"]
            result["progress_percent"] = 100
            result["message"] = f"All {execution_info['total_cells']} cells executed successfully!"

        # Error status
        elif execution_info["status"] == "error":
            result["failed_cell_index"] = execution_info["failed_cell_index"]
            result["error"] = execution_info["error"]
            result["results"] = execution_info["results"]
            progress_pct = int((execution_info["completed_cells"] / execution_info["total_cells"]) * 100)
            result["progress_percent"] = progress_pct
            result["message"] = f"Execution failed at cell {execution_info['failed_cell_index']} after completing {execution_info['completed_cells']}/{execution_info['total_cells']} cells"

        return result

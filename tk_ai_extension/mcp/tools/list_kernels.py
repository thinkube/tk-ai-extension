# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""List kernels tool (simplified for local-only use)."""

from typing import Any, Optional
from .base import BaseTool


class ListKernelsTool(BaseTool):
    """Tool to list all running kernels."""

    @property
    def name(self) -> str:
        return "list_kernels"

    @property
    def description(self) -> str:
        return "List all currently running Jupyter kernels"

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
    ) -> str:
        """Execute the list_kernels tool.

        Returns:
            Formatted list of running kernels
        """
        try:
            # List all running kernels
            kernels = kernel_manager.list_kernels()

            if not kernels:
                return "No kernels currently running"

            result = ["Running kernels:"]
            result.append("-" * 80)

            for kernel in kernels:
                kernel_id = kernel.get('id', 'unknown')
                kernel_name = kernel.get('name', 'unknown')
                execution_state = kernel.get('execution_state', 'unknown')
                connections = kernel.get('connections', 0)

                result.append(
                    f"ID: {kernel_id[:8]}... | "
                    f"Name: {kernel_name:15s} | "
                    f"State: {execution_state:10s} | "
                    f"Connections: {connections}"
                )

            # Also list available kernel specs
            if kernel_spec_manager:
                specs = kernel_spec_manager.get_all_specs()
                if specs:
                    result.append("\nAvailable kernel types:")
                    result.append("-" * 80)
                    for spec_name, spec_info in specs.items():
                        display_name = spec_info.get('spec', {}).get('display_name', spec_name)
                        result.append(f"  - {spec_name}: {display_name}")

            return "\n".join(result)

        except Exception as e:
            return f"Error listing kernels: {str(e)}"

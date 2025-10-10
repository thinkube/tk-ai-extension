# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Base class for MCP tools (simplified for local-only use)."""

from abc import ABC, abstractmethod
from typing import Any, Optional


class BaseTool(ABC):
    """Abstract base class for all MCP tools.

    Simplified version for local-only operation within JupyterLab.
    All tools have direct access to Jupyter managers (no HTTP client needed).
    """

    def __init__(self):
        """Initialize the tool."""
        pass

    @abstractmethod
    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        notebook_manager: Optional[Any] = None,
        serverapp: Optional[Any] = None,
        **kwargs
    ) -> Any:
        """Execute the tool logic with direct manager access.

        Args:
            contents_manager: Direct access to Jupyter contents manager
            kernel_manager: Direct access to Jupyter kernel manager
            kernel_spec_manager: Direct access to kernel spec manager (optional)
            session_manager: Direct access to session manager (optional)
            notebook_manager: NotebookManager instance for tracking active notebooks (optional)
            serverapp: Jupyter ServerApp instance for ExecutionStack access (optional)
            **kwargs: Tool-specific parameters

        Returns:
            Tool execution result (type varies by tool)
        """
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Return the tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Return the tool description."""
        pass

    @property
    @abstractmethod
    def input_schema(self) -> dict:
        """Return the tool input schema for Claude Agent SDK."""
        pass

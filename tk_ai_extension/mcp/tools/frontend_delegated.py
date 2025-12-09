# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Frontend-delegated MCP tool base class.

This module provides a base class for MCP tools that delegate execution
to the frontend (JupyterLab UI) via WebSocket. This ensures:
1. UI updates instantly when cells are added/modified/executed
2. Frontend always reads from live notebook model (not stale files)
3. tqdm progress bars and real-time output work via IOPub streaming
"""

import json
import logging
from typing import Any, Dict, Optional
from .base import BaseTool
from ...frontend_delegation import delegate_to_frontend, should_delegate_to_frontend

logger = logging.getLogger(__name__)


class FrontendDelegatedTool(BaseTool):
    """Base class for tools that delegate execution to the frontend.

    Subclasses should implement:
    - name: Tool name (used for frontend routing)
    - description: Tool description for Claude
    - input_schema: JSON schema for tool inputs
    - frontend_tool_name: Name of the tool as recognized by frontend (if different from name)
    """

    @property
    def frontend_tool_name(self) -> str:
        """Name of the tool as recognized by frontend. Override if different from self.name."""
        return self.name

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
        """Execute by delegating to frontend.

        The frontend handles the actual notebook manipulation using JupyterLab APIs,
        ensuring UI updates and real-time IOPub streaming.
        """
        tool_name = self.frontend_tool_name

        # Log the delegation
        logger.info(f"[Frontend Delegation] Delegating {tool_name} to frontend with args: {kwargs}")

        try:
            # Delegate to frontend and wait for result
            result = await delegate_to_frontend(tool_name, kwargs)

            # Log result
            success = result.get('success', False)
            if success:
                logger.info(f"[Frontend Delegation] {tool_name} succeeded: {result}")
            else:
                logger.warning(f"[Frontend Delegation] {tool_name} failed: {result.get('error', 'Unknown error')}")

            return result

        except Exception as e:
            logger.error(f"[Frontend Delegation] {tool_name} exception: {e}")
            return {
                "success": False,
                "error": f"Frontend delegation failed: {str(e)}"
            }


class ListCellsTool(FrontendDelegatedTool):
    """List all cells in a notebook (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "list_cells"

    @property
    def description(self) -> str:
        return "List all cells in the current notebook with their indices, types, and source code."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional, uses current notebook if not specified)"
                }
            },
            "required": []
        }


class ReadCellTool(FrontendDelegatedTool):
    """Read a specific cell's content (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "read_cell"

    @property
    def description(self) -> str:
        return "Read the content and outputs of a specific cell by index."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to read (0-based)"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": ["cell_index"]
        }


class ExecuteCellTool(FrontendDelegatedTool):
    """Execute a cell with real-time IOPub streaming (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "execute_cell"

    @property
    def description(self) -> str:
        return (
            "Execute a code cell and return its output. "
            "Supports real-time streaming output including tqdm progress bars."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to execute (0-based)"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": ["cell_index"]
        }


class InsertCellTool(FrontendDelegatedTool):
    """Insert a new cell (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "insert_cell"

    @property
    def description(self) -> str:
        return "Insert a new cell into the notebook."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Content/source code for the new cell"
                },
                "cell_type": {
                    "type": "string",
                    "enum": ["code", "markdown"],
                    "description": "Type of cell (default: code)"
                },
                "position": {
                    "type": "string",
                    "enum": ["above", "below", "end"],
                    "description": "Where to insert relative to active cell (default: end)"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": ["content"]
        }


class OverwriteCellTool(FrontendDelegatedTool):
    """Overwrite cell content (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "overwrite_cell"

    @property
    def frontend_tool_name(self) -> str:
        return "overwrite_cell"

    @property
    def description(self) -> str:
        return "Overwrite the source content of a cell."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to overwrite (0-based)"
                },
                "content": {
                    "type": "string",
                    "description": "New content for the cell"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": ["cell_index", "content"]
        }


class DeleteCellTool(FrontendDelegatedTool):
    """Delete a cell (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "delete_cell"

    @property
    def description(self) -> str:
        return "Delete a cell from the notebook."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to delete (0-based)"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": ["cell_index"]
        }


class MoveCellTool(FrontendDelegatedTool):
    """Move a cell (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "move_cell"

    @property
    def description(self) -> str:
        return "Move a cell from one position to another."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "from_index": {
                    "type": "integer",
                    "description": "Current index of the cell (0-based)"
                },
                "to_index": {
                    "type": "integer",
                    "description": "Target index for the cell (0-based)"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": ["from_index", "to_index"]
        }


class InsertAndExecuteCellTool(FrontendDelegatedTool):
    """Insert and execute a cell (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "insert_and_execute_cell"

    @property
    def description(self) -> str:
        return "Insert a new code cell and execute it immediately."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "Code to insert and execute"
                },
                "position": {
                    "type": "string",
                    "enum": ["above", "below", "end"],
                    "description": "Where to insert (default: below)"
                },
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": ["content"]
        }


class ExecuteAllCellsTool(FrontendDelegatedTool):
    """Execute all cells (frontend-delegated)."""

    @property
    def name(self) -> str:
        return "execute_all_cells"

    @property
    def description(self) -> str:
        return "Execute all code cells in the notebook sequentially."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook (optional)"
                }
            },
            "required": []
        }


# Export all frontend-delegated tools
FRONTEND_DELEGATED_TOOLS = [
    ListCellsTool,
    ReadCellTool,
    ExecuteCellTool,
    InsertCellTool,
    OverwriteCellTool,
    DeleteCellTool,
    MoveCellTool,
    InsertAndExecuteCellTool,
    ExecuteAllCellsTool,
]

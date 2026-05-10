# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Frontend-delegated MCP tool base class with backend fallback.

This module provides a base class for MCP tools that delegate execution
to the frontend (JupyterLab UI) via WebSocket when available. When no
WebSocket is connected (e.g., when called from Claude Code via the MCP
bridge), tools fall back to backend-only execution via YDoc or
contents_manager.

Execution priority:
1. Frontend delegation (WebSocket connected) — real-time UI updates
2. Backend fallback (no WebSocket) — YDoc/contents_manager
"""

import logging
from typing import Any, Dict, Optional
from .base import BaseTool
from ...frontend_delegation import delegate_to_frontend, _active_websocket

logger = logging.getLogger(__name__)


class FrontendDelegatedTool(BaseTool):
    """Base class for tools that delegate execution to the frontend.

    When a WebSocket is connected (Thinky chat open in JupyterLab), tools
    are delegated to the frontend for real-time UI updates. When no WebSocket
    is available (Claude Code via MCP bridge), tools fall back to their
    backend implementations.

    Subclasses should implement:
    - name: Tool name (used for frontend routing)
    - description: Tool description for Claude
    - input_schema: JSON schema for tool inputs
    - _create_backend_tool(): Factory method returning backend BaseTool instance
    - _map_args_to_backend(kwargs): Map frontend arg names to backend arg names
    """

    @property
    def frontend_tool_name(self) -> str:
        """Name of the tool as recognized by frontend. Override if different from self.name."""
        return self.name

    def _create_backend_tool(self) -> Optional[BaseTool]:
        """Create a backend tool instance for fallback execution.

        Override in subclasses that have backend implementations.
        Returns None if no backend fallback is available.
        """
        return None

    def _map_args_to_backend(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Map frontend argument names to backend argument names.

        Override in subclasses where argument names differ between
        frontend and backend tools. Default: pass through unchanged.
        """
        return kwargs

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
        """Execute via frontend delegation or backend fallback.

        Priority:
        1. If WebSocket is connected → delegate to frontend
        2. Otherwise → use backend tool implementation
        """
        tool_name = self.frontend_tool_name

        # Try frontend delegation if WebSocket is connected
        if _active_websocket is not None:
            logger.info(f"[Frontend Delegation] Delegating {tool_name} to frontend with args: {kwargs}")
            try:
                result = await delegate_to_frontend(tool_name, kwargs)
                success = result.get('success', False)
                if success:
                    logger.info(f"[Frontend Delegation] {tool_name} succeeded")
                else:
                    logger.warning(f"[Frontend Delegation] {tool_name} failed: {result.get('error', 'Unknown error')}")
                return result
            except Exception as e:
                logger.warning(f"[Frontend Delegation] {tool_name} failed, trying backend: {e}")

        # Backend fallback
        backend_tool = self._create_backend_tool()
        if backend_tool is None:
            return {
                "success": False,
                "error": f"No backend fallback available for {tool_name} and no frontend WebSocket connected"
            }

        backend_kwargs = self._map_args_to_backend(kwargs)
        logger.info(f"[Backend Fallback] Executing {tool_name} via backend with args: {backend_kwargs}")

        try:
            result = await backend_tool.execute(
                contents_manager=contents_manager,
                kernel_manager=kernel_manager,
                kernel_spec_manager=kernel_spec_manager,
                session_manager=session_manager,
                notebook_manager=notebook_manager,
                serverapp=serverapp,
                **backend_kwargs
            )
            return result
        except Exception as e:
            logger.error(f"[Backend Fallback] {tool_name} failed: {e}")
            return {
                "success": False,
                "error": f"Backend execution failed: {str(e)}"
            }


class ListCellsTool(FrontendDelegatedTool):
    """List all cells in a notebook (frontend-delegated with backend fallback)."""

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

    def _create_backend_tool(self):
        from .list_cells import ListCellsTool as BackendListCellsTool
        return BackendListCellsTool()

    def _map_args_to_backend(self, kwargs):
        # Backend uses 'notebook', frontend uses 'notebook_path'
        mapped = dict(kwargs)
        if 'notebook_path' in mapped:
            mapped['notebook'] = mapped.pop('notebook_path')
        return mapped


class ReadCellTool(FrontendDelegatedTool):
    """Read a specific cell's content (frontend-delegated with backend fallback)."""

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

    def _create_backend_tool(self):
        from .read_cell import ReadCellTool as BackendReadCellTool
        return BackendReadCellTool()

    def _map_args_to_backend(self, kwargs):
        mapped = dict(kwargs)
        if 'notebook_path' in mapped:
            mapped['notebook'] = mapped.pop('notebook_path')
        return mapped


class ExecuteCellTool(FrontendDelegatedTool):
    """Execute a cell (frontend-delegated with backend fallback)."""

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

    def _create_backend_tool(self):
        from .execution.execute_cell import ExecuteCellTool as BackendExecuteCellTool
        return BackendExecuteCellTool()

    def _map_args_to_backend(self, kwargs):
        # Backend execute_cell needs notebook_path + cell_index + kernel_id
        # kernel_id must be resolved from notebook_manager if not provided
        return dict(kwargs)


class InsertCellTool(FrontendDelegatedTool):
    """Insert a new cell (frontend-delegated with backend fallback)."""

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

    def _create_backend_tool(self):
        from .manipulation.insert_cell import InsertCellTool as BackendInsertCellTool
        return BackendInsertCellTool()

    def _map_args_to_backend(self, kwargs):
        # Map frontend args to backend: content→source, position→cell_index
        mapped = dict(kwargs)
        if 'content' in mapped:
            mapped['source'] = mapped.pop('content')
        if 'cell_type' not in mapped:
            mapped['cell_type'] = 'code'
        # If position is used instead of cell_index, we need to resolve it
        # For backend fallback, default to appending at end (cell_index = -1 handled by tool)
        if 'cell_index' not in mapped:
            # Will be resolved by the backend tool; use a large number to append at end
            mapped['cell_index'] = 99999  # Backend tool clamps to len(cells)
        return mapped


class OverwriteCellTool(FrontendDelegatedTool):
    """Overwrite cell content (frontend-delegated with backend fallback)."""

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

    def _create_backend_tool(self):
        from .manipulation.overwrite_cell import OverwriteCellTool as BackendOverwriteCellTool
        return BackendOverwriteCellTool()

    def _map_args_to_backend(self, kwargs):
        # Backend uses 'source', frontend uses 'content'
        mapped = dict(kwargs)
        if 'content' in mapped:
            mapped['source'] = mapped.pop('content')
        return mapped


class DeleteCellTool(FrontendDelegatedTool):
    """Delete a cell (frontend-delegated with backend fallback)."""

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

    def _create_backend_tool(self):
        from .manipulation.delete_cell import DeleteCellTool as BackendDeleteCellTool
        return BackendDeleteCellTool()


class MoveCellTool(FrontendDelegatedTool):
    """Move a cell (frontend-delegated with backend fallback)."""

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

    def _create_backend_tool(self):
        from .manipulation.move_cell import MoveCellTool as BackendMoveCellTool
        return BackendMoveCellTool()


class InsertAndExecuteCellTool(FrontendDelegatedTool):
    """Insert and execute a cell (frontend-delegated, no backend fallback yet)."""

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

    # No _create_backend_tool — composite operation, handled by frontend only for now


class ExecuteAllCellsTool(FrontendDelegatedTool):
    """Execute all cells (frontend-delegated, no backend fallback yet)."""

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

    # No _create_backend_tool — composite operation, handled by frontend only for now


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

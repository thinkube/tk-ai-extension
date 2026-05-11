# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Frontend-delegated MCP tools with backend YDoc execution.

Two execution paths for two callers:
1. Thinky chat (WebSocket connected) → delegate to JupyterLab frontend
2. Claude Code (no WebSocket) → execute via backend YDoc/kernel APIs

Both paths sync to the JupyterLab UI in real time via YDoc.
"""

import logging
from typing import Any, Dict, Optional
from .base import BaseTool
from ...frontend_delegation import delegate_to_frontend, _active_websocket

logger = logging.getLogger(__name__)


class FrontendDelegatedTool(BaseTool):
    """Base class for tools that execute via frontend or backend.

    When Thinky chat is open (WebSocket connected), tools delegate to the
    frontend for real-time IOPub streaming. When called from Claude Code
    (no WebSocket), tools execute via backend YDoc/kernel APIs.
    """

    @property
    def frontend_tool_name(self) -> str:
        return self.name

    def _get_backend_tool(self) -> Optional[BaseTool]:
        """Return the backend tool instance. Override in subclasses."""
        return None

    def _map_to_backend_args(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Map frontend arg names to backend arg names. Override if needed."""
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
        tool_name = self.frontend_tool_name

        # Path 1: Thinky chat — delegate to frontend
        if _active_websocket is not None:
            logger.info(f"[Frontend] {tool_name} with args: {kwargs}")
            try:
                result = await delegate_to_frontend(tool_name, kwargs)
                return result
            except Exception as e:
                logger.warning(f"[Frontend] {tool_name} failed: {e}")
                # Don't fall through — if WebSocket is connected, frontend is the path
                return {"success": False, "error": f"Frontend delegation failed: {str(e)}"}

        # Path 2: Claude Code — execute via backend
        backend = self._get_backend_tool()
        if backend is None:
            return {"success": False, "error": f"No backend implementation for {tool_name}"}

        backend_kwargs = self._map_to_backend_args(kwargs)
        logger.info(f"[Backend] {tool_name} with args: {backend_kwargs}")
        return await backend.execute(
            contents_manager=contents_manager,
            kernel_manager=kernel_manager,
            kernel_spec_manager=kernel_spec_manager,
            session_manager=session_manager,
            notebook_manager=notebook_manager,
            serverapp=serverapp,
            **backend_kwargs
        )


# ---------------------------------------------------------------------------
# Tool subclasses
# ---------------------------------------------------------------------------

class ListCellsTool(FrontendDelegatedTool):
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

    def _get_backend_tool(self):
        from .list_cells import ListCellsTool as Backend
        return Backend()

    def _map_to_backend_args(self, kwargs):
        m = dict(kwargs)
        if 'notebook_path' in m:
            m['notebook'] = m.pop('notebook_path')
        return m


class ReadCellTool(FrontendDelegatedTool):
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
                "cell_index": {"type": "integer", "description": "Index of the cell to read (0-based)"},
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": ["cell_index"]
        }

    def _get_backend_tool(self):
        from .read_cell import ReadCellTool as Backend
        return Backend()

    def _map_to_backend_args(self, kwargs):
        m = dict(kwargs)
        if 'notebook_path' in m:
            m['notebook'] = m.pop('notebook_path')
        return m


class ExecuteCellTool(FrontendDelegatedTool):
    @property
    def name(self) -> str:
        return "execute_cell"

    @property
    def description(self) -> str:
        return "Execute a code cell and return its output."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "cell_index": {"type": "integer", "description": "Index of the cell to execute (0-based)"},
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": ["cell_index"]
        }

    def _get_backend_tool(self):
        from .execution.execute_cell import ExecuteCellTool as Backend
        return Backend()


class InsertCellTool(FrontendDelegatedTool):
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
                "content": {"type": "string", "description": "Content/source code for the new cell"},
                "cell_type": {"type": "string", "enum": ["code", "markdown"], "description": "Type of cell (default: code)"},
                "position": {"type": "string", "enum": ["above", "below", "end"], "description": "Where to insert (default: end)"},
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": ["content"]
        }

    def _get_backend_tool(self):
        from .manipulation.insert_cell import InsertCellTool as Backend
        return Backend()

    def _map_to_backend_args(self, kwargs):
        m = dict(kwargs)
        if 'content' in m:
            m['source'] = m.pop('content')
        if 'cell_type' not in m:
            m['cell_type'] = 'code'
        if 'cell_index' not in m:
            m['cell_index'] = 99999  # append at end
        return m


class OverwriteCellTool(FrontendDelegatedTool):
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
                "cell_index": {"type": "integer", "description": "Index of the cell to overwrite (0-based)"},
                "content": {"type": "string", "description": "New content for the cell"},
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": ["cell_index", "content"]
        }

    def _get_backend_tool(self):
        from .manipulation.overwrite_cell import OverwriteCellTool as Backend
        return Backend()

    def _map_to_backend_args(self, kwargs):
        m = dict(kwargs)
        if 'content' in m:
            m['source'] = m.pop('content')
        return m


class DeleteCellTool(FrontendDelegatedTool):
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
                "cell_index": {"type": "integer", "description": "Index of the cell to delete (0-based)"},
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": ["cell_index"]
        }

    def _get_backend_tool(self):
        from .manipulation.delete_cell import DeleteCellTool as Backend
        return Backend()


class MoveCellTool(FrontendDelegatedTool):
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
                "from_index": {"type": "integer", "description": "Current index of the cell (0-based)"},
                "to_index": {"type": "integer", "description": "Target index for the cell (0-based)"},
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": ["from_index", "to_index"]
        }

    def _get_backend_tool(self):
        from .manipulation.move_cell import MoveCellTool as Backend
        return Backend()


class InsertAndExecuteCellTool(FrontendDelegatedTool):
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
                "content": {"type": "string", "description": "Code to insert and execute"},
                "position": {"type": "string", "enum": ["above", "below", "end"], "description": "Where to insert (default: below)"},
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": ["content"]
        }

    def _get_backend_tool(self):
        from .execution.insert_and_execute import InsertAndExecuteCellTool as Backend
        return Backend()

    def _map_to_backend_args(self, kwargs):
        m = dict(kwargs)
        if 'content' in m:
            m['source'] = m.pop('content')
        if 'cell_type' not in m:
            m['cell_type'] = 'code'
        if 'cell_index' not in m:
            m['cell_index'] = 99999
        return m


class ExecuteAllCellsTool(FrontendDelegatedTool):
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
                "notebook_path": {"type": "string", "description": "Path to the notebook (optional)"}
            },
            "required": []
        }

    def _get_backend_tool(self):
        from .execution.execute_all_cells import ExecuteAllCellsTool as Backend
        return Backend()


FRONTEND_DELEGATED_TOOLS = [
    ListCellsTool, ReadCellTool, ExecuteCellTool,
    InsertCellTool, OverwriteCellTool, DeleteCellTool,
    MoveCellTool, InsertAndExecuteCellTool, ExecuteAllCellsTool,
]

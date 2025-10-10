# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for executing notebook cells."""

import logging
from pathlib import Path
from typing import Any, Optional, Dict, List
from jupyter_nbmodel_client import NbModelClient
from ..base import BaseTool
from ..utils import get_notebook_path

logger = logging.getLogger(__name__)


class ExecuteCellTool(BaseTool):
    """Execute a cell in a Jupyter notebook."""

    @property
    def name(self) -> str:
        return "execute_cell"

    @property
    def description(self) -> str:
        return "Execute a code cell in a Jupyter notebook and return its output. NOTE: You must call use_notebook first to connect to a notebook and its kernel."

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook"
                },
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to execute (0-based)"
                },
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to use for execution"
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum time to wait for execution (default: 300)",
                    "default": 300
                }
            },
            "required": ["notebook_path", "cell_index", "kernel_id"]
        }

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
        """Execute a cell using NbModelClient as collaborative WebSocket client.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager for tracking
            serverapp: Jupyter ServerApp instance
            notebook_path: Path to notebook
            cell_index: Cell index to execute
            kernel_id: Kernel ID to use
            timeout_seconds: Execution timeout

        Returns:
            Dict with execution results
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")
        kernel_id = kwargs.get("kernel_id")
        timeout_seconds = kwargs.get("timeout_seconds", 300)

        if not serverapp:
            serverapp = getattr(contents_manager, 'parent', None)

        if serverapp:
            serverapp.log.info(f"ExecuteCellTool.execute called: notebook_path={notebook_path}, cell_index={cell_index}, kernel_id={kernel_id}")

        if not notebook_path or cell_index is None or not kernel_id:
            return {
                "error": "notebook_path, cell_index, and kernel_id are required",
                "success": False
            }

        try:
            # Get absolute path and file_id
            abs_path = get_notebook_path(serverapp, notebook_path)
            file_id_manager = serverapp.web_app.settings.get("file_id_manager")
            file_id = file_id_manager.get_id(abs_path)

            # Construct WebSocket URL for collaborative room with session ID
            # Generate a unique session ID for this connection (as a collaborative client)
            import uuid
            session_id = str(uuid.uuid4())

            # Get JupyterHub base URL (includes /user/username/)
            base_url = serverapp.base_url
            ws_url = f"ws://127.0.0.1:{serverapp.port}{base_url}api/collaboration/room/json:notebook:{file_id}?sessionId={session_id}"

            serverapp.log.info(f"Connecting to notebook via WebSocket as session {session_id}: {ws_url}")

            # Connect as collaborative client and execute
            async with NbModelClient(ws_url) as nb_client:
                serverapp.log.info("Connected to notebook as collaborative WebSocket client")

                # Execute the cell - this will automatically sync via RTC
                result = await nb_client.execute_cell(cell_index, kernel_id, timeout=timeout_seconds)

                serverapp.log.info(f"Cell executed via NbModelClient, outputs will sync via RTC")

                return {
                    "success": True,
                    "cell_index": cell_index,
                    "outputs": result.get("outputs", []) if isinstance(result, dict) else []
                }

        except Exception as e:
            if serverapp:
                serverapp.log.error(f"Error executing cell via NbModelClient: {e}")
            return {
                "success": False,
                "error": str(e),
                "cell_index": cell_index
            }

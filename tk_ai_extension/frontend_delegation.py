# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Frontend delegation for notebook operations.

This module enables MCP tools to delegate operations to the frontend (JupyterLab UI)
via WebSocket. This ensures:
1. UI updates instantly when cells are added/modified/executed
2. Frontend always reads from live notebook model (not stale files)
3. tqdm progress bars and real-time output work via IOPub streaming
"""

import asyncio
import json
import logging
import uuid
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# Global registry of pending tool requests awaiting frontend response
_pending_requests: Dict[str, asyncio.Future] = {}

# Global reference to the active WebSocket connection
_active_websocket = None


def set_active_websocket(ws):
    """Set the active WebSocket connection for frontend delegation."""
    global _active_websocket
    _active_websocket = ws
    logger.info("Frontend delegation WebSocket registered")


def clear_active_websocket():
    """Clear the active WebSocket connection."""
    global _active_websocket
    _active_websocket = None
    logger.info("Frontend delegation WebSocket cleared")


async def handle_tool_response(request_id: str, result: Dict[str, Any]):
    """Handle a tool response from the frontend.

    Called by the WebSocket handler when it receives a tool_response message.
    """
    if request_id in _pending_requests:
        future = _pending_requests.pop(request_id)
        if not future.done():
            future.set_result(result)
            logger.info(f"Tool response received for request {request_id}")
    else:
        logger.warning(f"Received response for unknown request {request_id}")


async def delegate_to_frontend(
    tool_name: str,
    args: Dict[str, Any],
    timeout: float = 30.0
) -> Dict[str, Any]:
    """Delegate a tool call to the frontend and wait for response.

    Args:
        tool_name: Name of the tool to execute (e.g., 'execute_cell', 'list_cells')
        args: Arguments to pass to the frontend tool
        timeout: Maximum time to wait for response (seconds)

    Returns:
        Result dictionary from frontend execution

    Raises:
        RuntimeError: If no WebSocket connection or timeout
    """
    global _active_websocket

    if _active_websocket is None:
        raise RuntimeError("No active WebSocket connection for frontend delegation")

    # Generate unique request ID
    request_id = str(uuid.uuid4())

    # Create future to wait for response
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    _pending_requests[request_id] = future

    try:
        # Send tool request to frontend
        await _active_websocket.write_message(json.dumps({
            "type": "tool_request",
            "id": request_id,
            "name": tool_name,
            "args": args
        }))
        logger.info(f"Sent tool_request to frontend: {tool_name} (id={request_id})")

        # Wait for response with timeout
        result = await asyncio.wait_for(future, timeout=timeout)
        return result

    except asyncio.TimeoutError:
        _pending_requests.pop(request_id, None)
        logger.error(f"Timeout waiting for frontend response: {tool_name}")
        return {
            "success": False,
            "error": f"Timeout waiting for frontend to execute {tool_name}"
        }
    except Exception as e:
        _pending_requests.pop(request_id, None)
        logger.error(f"Error delegating to frontend: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# Tools that should be delegated to frontend
FRONTEND_DELEGATED_TOOLS = {
    # Read operations - get fresh data from UI
    "list_cells",
    "read_cell",

    # Write operations - update UI immediately
    "execute_cell",
    "execute_cell_async",
    "execute_all_cells",
    "insert_cell",
    "insert_and_execute_cell",
    "delete_cell",
    "move_cell",
    "overwrite_cell",
    "overwrite_cell_source",
}


def should_delegate_to_frontend(tool_name: str) -> bool:
    """Check if a tool should be delegated to frontend."""
    return tool_name in FRONTEND_DELEGATED_TOOLS

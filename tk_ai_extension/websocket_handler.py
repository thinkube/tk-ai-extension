# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""WebSocket handler for streaming Claude responses with cancellation support."""

import asyncio
import json
import logging
import os
from pathlib import Path
from tornado import websocket
from jupyter_server.base.handlers import JupyterHandler

logger = logging.getLogger(__name__)


def load_secrets():
    """Load secrets from .secrets.env file into environment."""
    secrets_path = Path.home() / 'thinkube' / 'notebooks' / '.secrets.env'
    if secrets_path.exists():
        try:
            with open(secrets_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('export '):
                        line = line[7:]
                    if '=' in line:
                        key, value = line.split('=', 1)
                        value = value.strip('"').strip("'")
                        os.environ[key] = value
        except Exception as e:
            logger.warning(f"Failed to load secrets: {e}")


class MCPStreamingWebSocket(websocket.WebSocketHandler, JupyterHandler):
    """WebSocket handler for streaming Claude responses.

    Protocol:
    - Client sends: {"type": "chat", "message": "...", "notebook_path": "..."}
    - Client sends: {"type": "cancel"} to abort current request
    - Server sends: {"type": "token", "content": "..."} for each token
    - Server sends: {"type": "tool_call", "name": "...", "args": {...}}
    - Server sends: {"type": "tool_result", "name": "...", "result": {...}}
    - Server sends: {"type": "done", "full_response": "..."}
    - Server sends: {"type": "error", "message": "..."}
    - Server sends: {"type": "cancelled"}
    """

    def initialize(self):
        """Initialize the WebSocket handler."""
        self._current_task: asyncio.Task | None = None
        self._cancelled = False
        self._notebook_path: str | None = None

    def check_origin(self, origin):
        """Allow WebSocket connections from the same origin."""
        return True

    def open(self):
        """Handle WebSocket connection opened."""
        logger.info("WebSocket connection opened")
        self._cancelled = False

    def on_close(self):
        """Handle WebSocket connection closed."""
        logger.info("WebSocket connection closed")
        self._cancel_current_request()

    def _cancel_current_request(self):
        """Cancel any ongoing request."""
        self._cancelled = True
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            logger.info("Cancelled current request")

    async def on_message(self, message):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'cancel':
                self._cancel_current_request()
                await self.write_message(json.dumps({"type": "cancelled"}))
                return

            if msg_type == 'chat':
                user_message = data.get('message')
                notebook_path = data.get('notebook_path')

                if not user_message:
                    await self.write_message(json.dumps({
                        "type": "error",
                        "message": "message is required"
                    }))
                    return

                if not notebook_path:
                    await self.write_message(json.dumps({
                        "type": "error",
                        "message": "notebook_path is required"
                    }))
                    return

                self._notebook_path = notebook_path
                self._cancelled = False

                # Start streaming response in background task
                self._current_task = asyncio.create_task(
                    self._stream_response(user_message, notebook_path)
                )

        except json.JSONDecodeError:
            await self.write_message(json.dumps({
                "type": "error",
                "message": "Invalid JSON"
            }))
        except Exception as e:
            logger.error(f"Error handling message: {e}")
            await self.write_message(json.dumps({
                "type": "error",
                "message": str(e)
            }))

    async def _stream_response(self, user_message: str, notebook_path: str):
        """Stream Claude's response token by token."""
        try:
            # Load secrets
            load_secrets()

            # Check credentials
            if not os.environ.get('CLAUDE_CODE_OAUTH_TOKEN') and not os.environ.get('ANTHROPIC_API_KEY'):
                await self.write_message(json.dumps({
                    "type": "error",
                    "message": "Claude API credentials not found"
                }))
                return

            # Import SDK
            try:
                from claude_agent_sdk import (
                    ClaudeAgentOptions, AssistantMessage, TextBlock,
                    ToolUseBlock, ToolResultBlock
                )
            except ImportError:
                await self.write_message(json.dumps({
                    "type": "error",
                    "message": "claude-agent-sdk not installed"
                }))
                return

            # Get MCP server
            from .agent.tools_registry import create_jupyter_mcp_server, get_allowed_tool_names

            jupyter_mcp = create_jupyter_mcp_server()
            allowed_tools = get_allowed_tool_names()

            # Build system prompt
            user_notebooks = Path.home() / 'thinkube' / 'notebooks'
            system_prompt = self._build_system_prompt(user_notebooks, notebook_path)

            options = ClaudeAgentOptions(
                mcp_servers={"jupyter": jupyter_mcp},
                allowed_tools=allowed_tools,
                cwd=str(user_notebooks),
                system_prompt=system_prompt,
                setting_sources=["project"],
                env=os.environ.copy()
            )

            # Get client
            client_manager = self.settings.get('claude_client_manager')
            if not client_manager:
                await self.write_message(json.dumps({
                    "type": "error",
                    "message": "Server configuration error"
                }))
                return

            client = await client_manager.get_or_create_client(notebook_path, options)

            # Send query
            logger.info(f"[WS USER MESSAGE] {user_message}")
            await client.query(user_message)

            # Stream response
            full_response = ""

            async for message in client.receive_response():
                # Check for cancellation
                if self._cancelled:
                    logger.info("Request was cancelled")
                    return

                # Log message type for debugging
                msg_type_name = type(message).__name__
                logger.info(f"[WS MESSAGE TYPE] {msg_type_name}")

                # Handle ToolUseBlock as top-level message
                if isinstance(message, ToolUseBlock):
                    logger.info(f"[WS TOOL USE] {message.name}")
                    await self.write_message(json.dumps({
                        "type": "tool_call",
                        "name": message.name,
                        "args": message.input if hasattr(message, 'input') else {}
                    }))
                    continue

                # Handle ToolResultBlock as top-level message
                if isinstance(message, ToolResultBlock):
                    tool_name = getattr(message, 'tool_use_id', 'unknown')
                    is_error = getattr(message, 'is_error', False)
                    logger.info(f"[WS TOOL RESULT] {tool_name} error={is_error}")

                    # Try to parse result content
                    result_data = None
                    if hasattr(message, 'content'):
                        try:
                            if isinstance(message.content, str):
                                result_data = json.loads(message.content)
                            elif isinstance(message.content, list) and message.content:
                                first = message.content[0]
                                if hasattr(first, 'text'):
                                    result_data = json.loads(first.text)
                        except (json.JSONDecodeError, AttributeError):
                            pass

                    await self.write_message(json.dumps({
                        "type": "tool_result",
                        "name": tool_name,
                        "success": not is_error,
                        "result": result_data
                    }))

                    # Send cell_updated for markdown cells
                    if result_data and 'cell_type' in result_data:
                        cell_type = result_data.get('cell_type')
                        cell_index = result_data.get('cell_index')
                        if cell_type == 'markdown' and cell_index is not None:
                            await self.write_message(json.dumps({
                                "type": "cell_updated",
                                "cell_type": "markdown",
                                "cell_index": cell_index
                            }))
                    continue

                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if self._cancelled:
                            return

                        # Log block type for debugging
                        logger.debug(f"[WS BLOCK TYPE] {type(block).__name__}")

                        if isinstance(block, TextBlock):
                            # Stream text token
                            full_response += block.text
                            await self.write_message(json.dumps({
                                "type": "token",
                                "content": block.text
                            }))

                        elif isinstance(block, ToolUseBlock):
                            # Notify about tool call
                            await self.write_message(json.dumps({
                                "type": "tool_call",
                                "name": block.name,
                                "args": block.input if hasattr(block, 'input') else {}
                            }))

                        elif isinstance(block, ToolResultBlock):
                            # Notify about tool result with data for undo tracking
                            result_data = None
                            tool_name = getattr(block, 'name', 'unknown')
                            if hasattr(block, 'content'):
                                # Try to extract result data for cell operations
                                try:
                                    if isinstance(block.content, str):
                                        result_data = json.loads(block.content)
                                    elif isinstance(block.content, list) and block.content:
                                        first = block.content[0]
                                        if hasattr(first, 'text'):
                                            result_data = json.loads(first.text)
                                except (json.JSONDecodeError, AttributeError):
                                    pass

                            await self.write_message(json.dumps({
                                "type": "tool_result",
                                "name": tool_name,
                                "success": not getattr(block, 'is_error', False),
                                "result": result_data
                            }))

                            # Send cell_updated message for markdown cells to trigger re-render
                            if result_data and tool_name == 'overwrite_cell_source':
                                cell_type = result_data.get('cell_type')
                                cell_index = result_data.get('cell_index')
                                if cell_type == 'markdown' and cell_index is not None:
                                    await self.write_message(json.dumps({
                                        "type": "cell_updated",
                                        "cell_type": "markdown",
                                        "cell_index": cell_index
                                    }))

            # Send completion
            if not self._cancelled:
                logger.info(f"[WS RESPONSE COMPLETE] {len(full_response)} chars")
                await self.write_message(json.dumps({
                    "type": "done",
                    "full_response": full_response
                }))

                # Save conversation
                await self._save_conversation(notebook_path, user_message, full_response)

        except asyncio.CancelledError:
            logger.info("Request task was cancelled")
            try:
                await self.write_message(json.dumps({"type": "cancelled"}))
            except Exception:
                pass

        except Exception as e:
            logger.error(f"Error streaming response: {e}")
            try:
                await self.write_message(json.dumps({
                    "type": "error",
                    "message": str(e)
                }))
            except Exception:
                pass

    async def _save_conversation(self, notebook_path: str, user_message: str, response: str):
        """Save conversation to notebook metadata."""
        try:
            from .conversation_persistence import (
                save_conversation_to_notebook,
                load_conversation_from_notebook
            )

            existing = load_conversation_from_notebook(notebook_path)
            updated = existing + [
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": response}
            ]

            serverapp = self.settings.get('serverapp')
            await save_conversation_to_notebook(notebook_path, updated, serverapp)
            logger.info(f"Conversation saved to {notebook_path}")
        except Exception as e:
            logger.warning(f"Failed to save conversation: {e}")

    def _build_system_prompt(self, notebooks_dir: Path, notebook_path: str = None) -> str:
        """Build system prompt with notebook context."""
        prompt_parts = [
            "You are a helpful AI assistant with access to Jupyter notebooks and Thinkube services.",
            "",
            "IMPORTANT: Use concise formatting. Avoid excessive blank lines in your responses.",
            "",
            "## Current Context",
            f"Working directory: {notebooks_dir}",
        ]

        if notebook_path:
            prompt_parts.extend([
                f"Currently open notebook: {notebook_path}",
                ""
            ])
        else:
            prompt_parts.append("")

        prompt_parts.extend([
            "## Available Capabilities",
            "- List and read Jupyter notebooks in the current directory",
            "- List and read cells from notebooks",
            "- Execute code cells in running kernels",
            "- Modify cells using overwrite_cell (YDoc-based, instant updates)",
            "- Insert, delete, and move cells",
            "- Create new notebooks with create_notebook",
            "- Discover installed Python packages and their versions",
            "- Check module availability before using them",
            "- Get detailed package information (dependencies, homepage, etc.)",
            "- Access Thinkube services via ~/.thinkube_env environment variables",
            "",
            "## CRITICAL: Tool Selection for Notebooks",
            "For ALL Jupyter notebook operations, ALWAYS use the MCP tools (mcp__jupyter__*), NEVER use Claude Code's built-in file tools:",
            "",
            "**NEVER use these built-in tools for notebooks:**",
            "- Read tool → Use read_cell or list_cells instead",
            "- NotebookEdit tool → Use overwrite_cell instead",
            "- Write tool → Use create_notebook instead",
            "- Edit tool → Use overwrite_cell instead",
            "- Glob tool → Use list_notebooks instead",
            "",
            "## CRITICAL: Cell Numbering and Selection",
            "- JupyterLab shows execution count [N] in the UI",
            "- ALL cell operations use 0-based index (cell_index), NOT execution count",
            "- User messages automatically include [Context: ...] showing selected/active cell indices",
            "- When user says 'this cell' or 'the selected cell', use the index from [Context]",
            "",
            "- Always provide clear explanations of what you're doing",
        ])

        if notebook_path:
            prompt_parts.append(f"- When asked about 'this notebook' or 'current notebook', refer to {notebook_path}")

        return "\n".join(prompt_parts)

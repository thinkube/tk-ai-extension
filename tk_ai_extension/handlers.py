# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""HTTP handlers for MCP protocol."""

import json
import os
from pathlib import Path
from tornado import web
from jupyter_server.base.handlers import JupyterHandler


def load_secrets():
    """Load secrets from .secrets.env file into environment."""
    secrets_path = Path.home() / 'thinkube' / 'notebooks' / '.secrets.env'
    if secrets_path.exists():
        try:
            with open(secrets_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    # Skip comments and empty lines
                    if not line or line.startswith('#'):
                        continue
                    # Parse export statements
                    if line.startswith('export '):
                        line = line[7:]  # Remove 'export '
                    # Split on first = only
                    if '=' in line:
                        key, value = line.split('=', 1)
                        # Remove quotes if present
                        value = value.strip('"').strip("'")
                        os.environ[key] = value
        except Exception as e:
            print(f"Warning: Failed to load secrets from {secrets_path}: {e}")


class MCPHealthHandler(JupyterHandler):
    """Health check endpoint for MCP."""

    @web.authenticated
    async def get(self):
        """GET /api/tk-ai/mcp/health"""
        self.finish({
            "status": "ok",
            "service": "tk-ai-extension",
            "version": "0.1.0"
        })


class MCPToolsListHandler(JupyterHandler):
    """List available MCP tools."""

    @web.authenticated
    async def get(self):
        """GET /api/tk-ai/mcp/tools/list"""
        from .agent.tools_registry import get_registered_tools

        tools = get_registered_tools()
        tool_list = []

        for tool_name, tool_data in tools.items():
            tool_instance = tool_data['instance']
            tool_list.append({
                "name": tool_instance.name,
                "description": tool_instance.description,
                "inputSchema": tool_instance.input_schema
            })

        self.finish({
            "tools": tool_list
        })


class MCPToolCallHandler(JupyterHandler):
    """Execute an MCP tool."""

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/tools/call

        Body:
        {
            "tool": "tool_name",
            "arguments": {...}
        }
        """
        try:
            body = json.loads(self.request.body.decode('utf-8'))
            tool_name = body.get('tool')
            arguments = body.get('arguments', {})

            if not tool_name:
                self.set_status(400)
                self.finish({"error": "tool parameter is required"})
                return

            from .agent.tools_registry import get_registered_tools
            tools = get_registered_tools()

            if tool_name not in tools:
                self.set_status(404)
                self.finish({"error": f"Tool '{tool_name}' not found"})
                return

            # Execute the tool
            tool_executor = tools[tool_name]['executor']
            result = await tool_executor(arguments)

            self.finish(result)

        except json.JSONDecodeError:
            self.set_status(400)
            self.finish({"error": "Invalid JSON in request body"})
        except Exception as e:
            self.log.error(f"Error executing tool: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class MCPChatHandler(JupyterHandler):
    """Chat endpoint using Claude Agent SDK with MCP tools."""

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/chat

        Body:
        {
            "message": "User message",
            "history": [{"role": "user"|"assistant", "content": "..."}]  # optional
        }
        """
        try:
            # Load secrets before processing request
            load_secrets()

            # Check for API credentials
            if not os.environ.get('CLAUDE_CODE_OAUTH_TOKEN') and not os.environ.get('ANTHROPIC_API_KEY'):
                self.set_status(401)
                self.finish({
                    "error": "Claude API credentials not found",
                    "message": "Add CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY in thinkube-control Secrets page, then click 'Export to Notebooks'"
                })
                return

            body = json.loads(self.request.body.decode('utf-8'))
            user_message = body.get('message')

            if not user_message:
                self.set_status(400)
                self.finish({"error": "message parameter is required"})
                return

            # Import claude-agent-sdk
            try:
                from claude_agent_sdk import ClaudeSDKClient, ClaudeAgentOptions, AssistantMessage, TextBlock
            except ImportError:
                self.set_status(500)
                self.finish({
                    "error": "claude-agent-sdk not installed",
                    "message": "Install with: pip install claude-agent-sdk"
                })
                return

            # Get Jupyter MCP server with tools
            from .agent.tools_registry import create_jupyter_mcp_server, get_allowed_tool_names

            jupyter_mcp = create_jupyter_mcp_server()
            allowed_tools = get_allowed_tool_names()

            # Configure Claude options with MCP server
            options = ClaudeAgentOptions(
                mcp_servers={"jupyter": jupyter_mcp},
                allowed_tools=allowed_tools
            )

            # Execute query with Claude SDK client
            response_text = ""
            async with ClaudeSDKClient(options=options) as client:
                await client.query(user_message)

                # Collect response from all messages
                async for message in client.receive_response():
                    if isinstance(message, AssistantMessage):
                        for block in message.content:
                            if isinstance(block, TextBlock):
                                response_text += block.text

            self.finish({
                "response": response_text,
                "timestamp": body.get('timestamp', None)
            })

        except json.JSONDecodeError:
            self.set_status(400)
            self.finish({"error": "Invalid JSON in request body"})
        except Exception as e:
            self.log.error(f"Error in chat: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})

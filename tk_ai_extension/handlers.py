# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""HTTP handlers for MCP protocol."""

import json
from tornado import web
from jupyter_server.base.handlers import JupyterHandler


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

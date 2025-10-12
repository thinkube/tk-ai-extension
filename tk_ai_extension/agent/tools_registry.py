# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Tool registration system for Claude Agent SDK."""

from typing import Dict, Any, Callable, List
from claude_agent_sdk import tool, create_sdk_mcp_server

# Global registry of tool instances
_tool_instances = {}
_jupyter_managers = {}


def set_jupyter_managers(contents_manager, kernel_manager, kernel_spec_manager=None, session_manager=None, notebook_manager=None, serverapp=None):
    """Set Jupyter managers for tool execution.

    Must be called during extension initialization.
    """
    global _jupyter_managers
    _jupyter_managers['contents_manager'] = contents_manager
    _jupyter_managers['kernel_manager'] = kernel_manager
    _jupyter_managers['kernel_spec_manager'] = kernel_spec_manager
    _jupyter_managers['session_manager'] = session_manager
    _jupyter_managers['notebook_manager'] = notebook_manager
    _jupyter_managers['serverapp'] = serverapp


def register_tool(tool_instance):
    """Register a tool with Claude Agent SDK.

    This wraps our BaseTool implementation with the @tool decorator
    from claude-agent-sdk.

    Args:
        tool_instance: Instance of a BaseTool subclass
    """
    global _tool_instances

    # Create async wrapper function for this tool
    async def tool_executor(args: Dict[str, Any]) -> Dict[str, Any]:
        """Execute tool with Jupyter managers."""
        serverapp = _jupyter_managers.get('serverapp')
        if serverapp:
            serverapp.log.info(f"[TOOL CALL] {tool_instance.name} called with args: {args}")
        try:
            result = await tool_instance.execute(
                contents_manager=_jupyter_managers.get('contents_manager'),
                kernel_manager=_jupyter_managers.get('kernel_manager'),
                kernel_spec_manager=_jupyter_managers.get('kernel_spec_manager'),
                session_manager=_jupyter_managers.get('session_manager'),
                notebook_manager=_jupyter_managers.get('notebook_manager'),
                serverapp=_jupyter_managers.get('serverapp'),
                **args
            )

            if serverapp:
                # Log success without dumping potentially large result data
                success = result.get('success', True) if isinstance(result, dict) else True
                if success:
                    serverapp.log.info(f"[TOOL RESULT] {tool_instance.name} completed successfully")
                else:
                    error = result.get('error', 'Unknown error') if isinstance(result, dict) else 'Unknown error'
                    serverapp.log.info(f"[TOOL RESULT] {tool_instance.name} failed: {error}")

            return {
                "content": [
                    {
                        "type": "text",
                        "text": str(result)
                    }
                ]
            }
        except Exception as e:
            return {
                "content": [
                    {
                        "type": "text",
                        "text": f"Error executing tool: {str(e)}"
                    }
                ],
                "isError": True
            }

    # Register with Claude Agent SDK using @tool decorator
    decorated_tool = tool(
        tool_instance.name,
        tool_instance.description,
        tool_instance.input_schema
    )(tool_executor)

    _tool_instances[tool_instance.name] = {
        'instance': tool_instance,
        'executor': decorated_tool,  # For Claude Agent SDK
        'direct_executor': tool_executor  # For direct HTTP API calls
    }

    return decorated_tool


def get_registered_tools():
    """Get all registered tool instances."""
    return _tool_instances


def create_jupyter_mcp_server():
    """Create SDK MCP server with all registered Jupyter tools.

    Returns:
        MCP server configured with Jupyter tools
    """
    # Get all decorated tool functions
    tool_functions = [
        tool_data['executor']
        for tool_data in _tool_instances.values()
    ]

    # Create MCP server
    return create_sdk_mcp_server(
        name="jupyter",
        version="1.0.0",
        tools=tool_functions
    )


def get_allowed_tool_names() -> List[str]:
    """Get list of allowed tool names for ClaudeAgentOptions.

    Returns:
        List of tool names in format "mcp__jupyter__tool_name"
    """
    return [
        f"mcp__jupyter__{tool_name}"
        for tool_name in _tool_instances.keys()
    ]

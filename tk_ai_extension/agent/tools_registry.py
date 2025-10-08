# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Tool registration system for Claude Agent SDK."""

from typing import Dict, Any, Callable
from claude_agent_sdk import tool

# Global registry of tool instances
_tool_instances = {}
_jupyter_managers = {}


def set_jupyter_managers(contents_manager, kernel_manager, kernel_spec_manager=None):
    """Set Jupyter managers for tool execution.

    Must be called during extension initialization.
    """
    global _jupyter_managers
    _jupyter_managers['contents_manager'] = contents_manager
    _jupyter_managers['kernel_manager'] = kernel_manager
    _jupyter_managers['kernel_spec_manager'] = kernel_spec_manager


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
        try:
            result = await tool_instance.execute(
                contents_manager=_jupyter_managers.get('contents_manager'),
                kernel_manager=_jupyter_managers.get('kernel_manager'),
                kernel_spec_manager=_jupyter_managers.get('kernel_spec_manager'),
                **args
            )

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
        'executor': decorated_tool
    }

    return decorated_tool


def get_registered_tools():
    """Get all registered tool instances."""
    return _tool_instances

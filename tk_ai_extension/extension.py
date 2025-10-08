# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""JupyterLab server extension for tk-ai-extension."""

from jupyter_server.extension.application import ExtensionApp


class TKAIExtension(ExtensionApp):
    """tk-ai-extension server extension."""

    name = "tk_ai_extension"
    extension_url = "/tk-ai"

    def initialize_settings(self):
        """Initialize extension settings."""
        self.log.info("tk-ai-extension: Initializing")

        try:
            # Get Jupyter managers from serverapp
            contents_manager = self.serverapp.contents_manager
            kernel_manager = self.serverapp.kernel_manager
            kernel_spec_manager = self.serverapp.kernel_spec_manager

            # Set managers for tool execution
            from .agent.tools_registry import set_jupyter_managers
            set_jupyter_managers(
                contents_manager,
                kernel_manager,
                kernel_spec_manager
            )

            # Register MCP tools
            self._register_tools()

            self.log.info("tk-ai-extension: MCP tools registered successfully")

        except Exception as e:
            self.log.error(f"tk-ai-extension: Failed to initialize: {e}")
            raise

    def _register_tools(self):
        """Register all MCP tools with Claude Agent SDK."""
        from .agent.tools_registry import register_tool
        from .mcp.tools.list_notebooks import ListNotebooksTool
        from .mcp.tools.list_cells import ListCellsTool
        from .mcp.tools.read_cell import ReadCellTool
        from .mcp.tools.execute_cell import ExecuteCellTool
        from .mcp.tools.list_kernels import ListKernelsTool

        # Register all tools
        register_tool(ListNotebooksTool())
        register_tool(ListCellsTool())
        register_tool(ReadCellTool())
        register_tool(ExecuteCellTool())
        register_tool(ListKernelsTool())

    def initialize_handlers(self):
        """Initialize HTTP handlers."""
        from .handlers import MCPHealthHandler, MCPToolsListHandler, MCPToolCallHandler

        self.handlers.extend([
            (r"/api/tk-ai/mcp/health", MCPHealthHandler),
            (r"/api/tk-ai/mcp/tools/list", MCPToolsListHandler),
            (r"/api/tk-ai/mcp/tools/call", MCPToolCallHandler),
        ])


# Entry point for jupyter_server
def _jupyter_server_extension_points():
    return [{"module": "tk_ai_extension.extension", "app": TKAIExtension}]

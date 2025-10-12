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
            session_manager = self.serverapp.session_manager

            # Initialize notebook manager for tracking active notebooks
            from .notebook_manager import NotebookManager
            notebook_manager = NotebookManager()
            self.settings['notebook_manager'] = notebook_manager
            self.log.info("tk-ai-extension: Notebook manager initialized")

            # Set managers for tool execution
            from .agent.tools_registry import set_jupyter_managers
            set_jupyter_managers(
                contents_manager,
                kernel_manager,
                kernel_spec_manager,
                session_manager,
                notebook_manager,
                self.serverapp  # Pass serverapp for ExecutionStack access
            )

            # Register MCP tools
            self._register_tools()

            # Initialize persistent Claude client manager
            from .client_manager import ClaudeClientManager
            client_manager = ClaudeClientManager()
            self.settings['claude_client_manager'] = client_manager
            self.log.info("tk-ai-extension: Claude client manager initialized")

            self.log.info("tk-ai-extension: MCP tools registered successfully")

        except Exception as e:
            self.log.error(f"tk-ai-extension: Failed to initialize: {e}")
            raise

    def _register_tools(self):
        """Register all MCP tools with Claude Agent SDK."""
        from .agent.tools_registry import register_tool

        # Basic notebook operations
        from .mcp.tools.list_notebooks import ListNotebooksTool
        from .mcp.tools.list_cells import ListCellsTool
        from .mcp.tools.read_cell import ReadCellTool
        from .mcp.tools.list_kernels import ListKernelsTool

        # Kernel management
        from .mcp.tools.kernel import (
            RestartKernelTool,
            InterruptKernelTool,
            ListRunningKernelsTool,
            GetKernelStatusTool
        )

        # Cell execution
        from .mcp.tools.execution import (
            ExecuteCellTool,
            InsertAndExecuteCellTool
        )

        # Cell manipulation
        from .mcp.tools.manipulation import (
            InsertCellTool,
            DeleteCellTool,
            OverwriteCellTool,
            MoveCellTool
        )

        # Notebook connection
        from .mcp.tools.use_notebook import UseNotebookTool

        # Register basic tools
        register_tool(ListNotebooksTool())
        register_tool(ListCellsTool())
        register_tool(ReadCellTool())
        register_tool(ListKernelsTool())

        # Register kernel management tools
        register_tool(RestartKernelTool())
        register_tool(InterruptKernelTool())
        register_tool(ListRunningKernelsTool())
        register_tool(GetKernelStatusTool())

        # Register execution tools
        register_tool(ExecuteCellTool())
        register_tool(InsertAndExecuteCellTool())

        # Register manipulation tools
        register_tool(InsertCellTool())
        register_tool(DeleteCellTool())
        register_tool(OverwriteCellTool())
        register_tool(MoveCellTool())

        # Register notebook connection tools
        register_tool(UseNotebookTool())

    def initialize_handlers(self):
        """Initialize HTTP handlers."""
        from .handlers import (
            MCPHealthHandler,
            ModelHealthHandler,
            MCPToolsListHandler,
            MCPToolCallHandler,
            MCPChatHandler,
            SessionCloseHandler,
            NotebookConnectHandler,
            FileIdHandler
        )

        self.handlers.extend([
            (r"/api/tk-ai/mcp/health", MCPHealthHandler),
            (r"/api/tk-ai/mcp/model-health", ModelHealthHandler),
            (r"/api/tk-ai/mcp/tools/list", MCPToolsListHandler),
            (r"/api/tk-ai/mcp/tools/call", MCPToolCallHandler),
            (r"/api/tk-ai/mcp/chat", MCPChatHandler),
            (r"/api/tk-ai/mcp/session/close", SessionCloseHandler),
            (r"/api/tk-ai/mcp/notebook/connect", NotebookConnectHandler),
            (r"/api/tk-ai/fileid", FileIdHandler),
        ])


# Entry point for jupyter_server
def _jupyter_server_extension_points():
    return [{"module": "tk_ai_extension.extension", "app": TKAIExtension}]

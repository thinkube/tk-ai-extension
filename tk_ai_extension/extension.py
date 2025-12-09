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

        # Frontend-delegated tools (execute via JupyterLab UI for real-time updates)
        # These tools delegate to the frontend for:
        # - Real-time UI updates when cells are modified
        # - IOPub streaming for tqdm/progress bars
        # - Reading fresh data from live notebook model
        from .mcp.tools.frontend_delegated import (
            ListCellsTool as FrontendListCellsTool,
            ReadCellTool as FrontendReadCellTool,
            ExecuteCellTool as FrontendExecuteCellTool,
            InsertCellTool as FrontendInsertCellTool,
            OverwriteCellTool as FrontendOverwriteCellTool,
            DeleteCellTool as FrontendDeleteCellTool,
            MoveCellTool as FrontendMoveCellTool,
            InsertAndExecuteCellTool as FrontendInsertAndExecuteCellTool,
            ExecuteAllCellsTool as FrontendExecuteAllCellsTool,
        )

        # Backend-only tools (don't need frontend delegation)
        from .mcp.tools.list_notebooks import ListNotebooksTool
        from .mcp.tools.list_kernels import ListKernelsTool

        # Kernel management (backend only - kernel operations don't need UI)
        from .mcp.tools.kernel import (
            RestartKernelTool,
            InterruptKernelTool,
            ListRunningKernelsTool,
            GetKernelStatusTool
        )

        # Async execution tracking (backend only)
        from .mcp.tools.execution import (
            ExecuteCellAsyncTool,
            CheckExecutionStatusTool,
            CheckAllCellsStatusTool
        )

        # Notebook connection (backend only)
        from .mcp.tools.use_notebook import UseNotebookTool

        # Python environment introspection (backend only)
        from .mcp.tools.introspection import (
            ListModulesTool,
            GetModuleInfoTool,
            CheckModuleTool
        )

        # Register frontend-delegated tools (these delegate to JupyterLab UI)
        register_tool(FrontendListCellsTool())
        register_tool(FrontendReadCellTool())
        register_tool(FrontendExecuteCellTool())
        register_tool(FrontendInsertCellTool())
        register_tool(FrontendOverwriteCellTool())
        register_tool(FrontendDeleteCellTool())
        register_tool(FrontendMoveCellTool())
        register_tool(FrontendInsertAndExecuteCellTool())
        register_tool(FrontendExecuteAllCellsTool())

        # Register backend-only tools
        register_tool(ListNotebooksTool())
        register_tool(ListKernelsTool())

        # Register kernel management tools
        register_tool(RestartKernelTool())
        register_tool(InterruptKernelTool())
        register_tool(ListRunningKernelsTool())
        register_tool(GetKernelStatusTool())

        # Register async execution tools (backend tracking)
        register_tool(ExecuteCellAsyncTool())
        register_tool(CheckExecutionStatusTool())
        register_tool(CheckAllCellsStatusTool())

        # Register notebook connection tools
        register_tool(UseNotebookTool())

        # Register introspection tools
        register_tool(ListModulesTool())
        register_tool(GetModuleInfoTool())
        register_tool(CheckModuleTool())

    def initialize_handlers(self):
        """Initialize HTTP and WebSocket handlers."""
        from .handlers import (
            MCPHealthHandler,
            ModelHealthHandler,
            MCPToolsListHandler,
            MCPToolCallHandler,
            MCPChatHandler,
            SessionCloseHandler,
            NotebookConnectHandler,
            ClearConversationHandler
        )
        from .websocket_handler import MCPStreamingWebSocket

        self.handlers.extend([
            (r"/api/tk-ai/mcp/health", MCPHealthHandler),
            (r"/api/tk-ai/mcp/model-health", ModelHealthHandler),
            (r"/api/tk-ai/mcp/tools/list", MCPToolsListHandler),
            (r"/api/tk-ai/mcp/tools/call", MCPToolCallHandler),
            (r"/api/tk-ai/mcp/chat", MCPChatHandler),
            (r"/api/tk-ai/mcp/session/close", SessionCloseHandler),
            (r"/api/tk-ai/mcp/notebook/connect", NotebookConnectHandler),
            (r"/api/tk-ai/mcp/conversation/clear", ClearConversationHandler),
            # WebSocket endpoint for streaming responses
            (r"/api/tk-ai/mcp/stream", MCPStreamingWebSocket),
        ])


# Entry point for jupyter_server
def _jupyter_server_extension_points():
    return [{"module": "tk_ai_extension.extension", "app": TKAIExtension}]

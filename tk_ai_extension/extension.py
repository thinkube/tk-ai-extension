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

        # TODO: Initialize MCP server with Claude Agent SDK
        # TODO: Register MCP tools
        # TODO: Setup HTTP handlers

    def initialize_handlers(self):
        """Initialize HTTP handlers."""
        self.handlers.extend([
            # TODO: Add MCP endpoint handlers
        ])


# Entry point for jupyter_server
def _jupyter_server_extension_points():
    return [{"module": "tk_ai_extension.extension", "app": TKAIExtension}]

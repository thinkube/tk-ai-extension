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


class ModelHealthHandler(JupyterHandler):
    """Check AI model (Claude) connectivity."""

    @web.authenticated
    async def get(self):
        """GET /api/tk-ai/mcp/model-health"""
        try:
            # Load secrets to get API key
            load_secrets()

            # Check if API key is configured
            has_oauth = bool(os.environ.get('CLAUDE_CODE_OAUTH_TOKEN'))
            has_api_key = bool(os.environ.get('ANTHROPIC_API_KEY'))

            if not has_oauth and not has_api_key:
                self.finish({
                    "model_available": False,
                    "error": "No API credentials found. Please set CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY."
                })
                return

            # API key is present
            self.finish({
                "model_available": True
            })

        except Exception as e:
            self.log.error(f"Model health check failed: {e}")
            self.finish({
                "model_available": False,
                "error": str(e)
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

    def _build_system_prompt(self, notebooks_dir: Path, notebook_path: str = None) -> str:
        """Build enhanced system prompt with notebook context.

        Args:
            notebooks_dir: Path to user's notebooks directory
            notebook_path: Path to currently open notebook (if any)

        Returns:
            System prompt string with context
        """
        prompt_parts = [
            "You are a helpful AI assistant with access to Jupyter notebooks and Thinkube services.",
            "",
            "IMPORTANT: Use concise formatting. Avoid excessive blank lines in your responses.",
            "",
            "## Current Context",
            f"Working directory: {notebooks_dir}",
        ]

        # Add currently open notebook if available
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
            "- Access Thinkube services via ~/.thinkube_env environment variables",
            "",
            "## Thinkube Services",
            "All services are accessible via environment variables loaded from ~/.thinkube_env.",
            "Use `from dotenv import load_dotenv; load_dotenv('/home/jovyan/.thinkube_env')` in Python.",
            "",
            "Available services include:",
            "- Databases: PostgreSQL, Valkey (Redis-compatible), ClickHouse",
            "- Vector DBs: Qdrant, Chroma, Weaviate",
            "- Storage: SeaweedFS (S3-compatible)",
            "- ML Tools: MLflow, LiteLLM, Langfuse",
            "- Search: OpenSearch",
            "- Annotation: Argilla, CVAT",
            "",
            "## Guidelines",
            "- When asked about notebooks, use MCP tools to list and read them",
            "- When executing code, verify kernel is available first",
            "- Always provide clear explanations of what you're doing",
            "- If CLAUDE.md exists in the working directory, respect any user preferences defined there",
        ])

        if notebook_path:
            prompt_parts.append(f"- When asked about 'this notebook' or 'current notebook', refer to {notebook_path}")

        return "\n".join(prompt_parts)

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
            notebook_path = body.get('notebook_path')

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

            self.log.info("Creating Jupyter MCP server...")
            jupyter_mcp = create_jupyter_mcp_server()
            allowed_tools = get_allowed_tool_names()
            self.log.info(f"MCP server created with {len(allowed_tools)} tools")

            # Configure Claude options with MCP server
            # Set working directory to user's notebooks for Claude CLI context
            user_notebooks = Path.home() / 'thinkube' / 'notebooks'

            # Build enhanced system prompt with notebook context
            system_prompt_text = self._build_system_prompt(user_notebooks, notebook_path)

            options = ClaudeAgentOptions(
                mcp_servers={"jupyter": jupyter_mcp},
                allowed_tools=allowed_tools,
                cwd=str(user_notebooks),  # Set working directory to notebooks
                # SDK v0.1.0+ requires explicit system_prompt configuration
                system_prompt=system_prompt_text,
                # Enable loading CLAUDE.md and other settings from project directory
                setting_sources=["project"],  # Load .claude/settings.json and CLAUDE.md from cwd
                env=os.environ.copy()  # Pass all environment variables including auth token
            )

            # Require notebook_path for per-notebook sessions
            if not notebook_path:
                self.set_status(400)
                self.finish({"error": "notebook_path parameter is required"})
                return

            # Get or create persistent Claude client for this notebook
            client_manager = self.settings.get('claude_client_manager')
            if not client_manager:
                self.log.error("Claude client manager not initialized!")
                self.set_status(500)
                self.finish({"error": "Server configuration error"})
                return

            self.log.info(f"Getting Claude client for notebook: {notebook_path}...")
            client = await client_manager.get_or_create_client(notebook_path, options)

            # Execute query with persistent client (maintains conversation history)
            self.log.info(f"[USER MESSAGE] {user_message}")
            self.log.info("Sending query to existing Claude session...")
            response_text = ""
            await client.query(user_message)

            self.log.info("Receiving response...")
            # Collect response from all messages
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_text += block.text
            self.log.info(f"[CLAUDE RESPONSE] {response_text}")
            self.log.info(f"Response received: {len(response_text)} chars")

            # Save conversation to notebook metadata
            try:
                from .conversation_persistence import save_conversation_to_notebook, load_conversation_from_notebook

                # Load existing conversation
                existing_messages = load_conversation_from_notebook(notebook_path)

                # Append new exchange
                updated_messages = existing_messages + [
                    {"role": "user", "content": user_message},
                    {"role": "assistant", "content": response_text}
                ]

                # Save back to notebook
                save_conversation_to_notebook(notebook_path, updated_messages)
                self.log.info(f"Conversation saved to {notebook_path}")
            except Exception as e:
                self.log.warning(f"Failed to save conversation: {e}")
                # Don't fail the request if saving fails

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


class SessionCloseHandler(JupyterHandler):
    """Close Claude session for a notebook."""

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/session/close

        Body:
        {
            "notebook_path": "path/to/notebook.ipynb"
        }
        """
        try:
            body = json.loads(self.request.body.decode('utf-8'))
            notebook_path = body.get('notebook_path')

            if not notebook_path:
                self.set_status(400)
                self.finish({"error": "notebook_path parameter is required"})
                return

            # Get client manager
            client_manager = self.settings.get('claude_client_manager')
            if not client_manager:
                self.set_status(500)
                self.finish({"error": "Server configuration error"})
                return

            # Close the client for this notebook
            await client_manager.close_client(notebook_path)
            self.log.info(f"Closed session for notebook: {notebook_path}")

            self.finish({"success": True})

        except json.JSONDecodeError:
            self.set_status(400)
            self.finish({"error": "Invalid JSON in request body"})
        except Exception as e:
            self.log.error(f"Error closing session: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class FileIdHandler(JupyterHandler):
    """Get file_id UUID for a given notebook path."""

    @web.authenticated
    async def get(self):
        """GET /api/tk-ai/fileid?path=notebook/path.ipynb

        Returns:
        {
            "file_id": "uuid-string",
            "path": "notebook/path.ipynb"
        }
        """
        try:
            path = self.get_argument('path', None)

            if not path:
                self.set_status(400)
                self.finish({"error": "path parameter is required"})
                return

            # Get file_id_manager from serverapp
            serverapp = self.settings.get('serverapp')
            if not serverapp:
                self.set_status(500)
                self.finish({"error": "ServerApp not available"})
                return

            file_id_manager = serverapp.web_app.settings.get("file_id_manager")
            if not file_id_manager:
                self.set_status(500)
                self.finish({"error": "file_id_manager not available"})
                return

            # Convert relative path to absolute if needed
            from pathlib import Path
            if not Path(path).is_absolute():
                root_dir = serverapp.root_dir
                abs_path = str(Path(root_dir) / path)
            else:
                abs_path = path

            # Get file_id
            file_id = file_id_manager.get_id(abs_path)

            self.finish({
                "file_id": file_id,
                "path": path,
                "document_id": f"json:notebook:{file_id}"
            })

        except Exception as e:
            self.log.error(f"Error getting file_id: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})


class NotebookConnectHandler(JupyterHandler):
    """Connect to a notebook and load conversation history."""

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/notebook/connect

        Body:
        {
            "notebook_path": "path/to/notebook.ipynb"
        }

        Returns:
        {
            "success": true,
            "notebook_name": "notebook",
            "messages": [{"role": "user"|"assistant", "content": "..."}],
            "kernel_id": "..."
        }
        """
        try:
            body = json.loads(self.request.body.decode('utf-8'))
            notebook_path = body.get('notebook_path')

            if not notebook_path:
                self.set_status(400)
                self.finish({"error": "notebook_path parameter is required"})
                return

            # Get notebook manager
            notebook_manager = self.settings.get('notebook_manager')
            if not notebook_manager:
                self.set_status(500)
                self.finish({"error": "Server configuration error"})
                return

            # Extract notebook name from path
            from .conversation_persistence import get_notebook_name, load_conversation_from_notebook

            notebook_name = get_notebook_name(notebook_path)

            # Check if notebook is already connected
            if notebook_name in notebook_manager:
                kernel_id = notebook_manager.get_kernel_id(notebook_name)
                self.log.info(f"Notebook {notebook_name} already connected, kernel: {kernel_id}")
            else:
                # Use the use_notebook tool to connect
                from .agent.tools_registry import get_registered_tools, _jupyter_managers

                tools = get_registered_tools()
                if 'use_notebook' not in tools:
                    self.set_status(500)
                    self.finish({"error": "use_notebook tool not available"})
                    return

                # Get the tool instance and execute it directly
                use_notebook_tool = tools['use_notebook']['instance']
                result = await use_notebook_tool.execute(
                    contents_manager=_jupyter_managers.get('contents_manager'),
                    kernel_manager=_jupyter_managers.get('kernel_manager'),
                    kernel_spec_manager=_jupyter_managers.get('kernel_spec_manager'),
                    session_manager=_jupyter_managers.get('session_manager'),
                    notebook_manager=_jupyter_managers.get('notebook_manager'),
                    serverapp=_jupyter_managers.get('serverapp'),
                    notebook_name=notebook_name,
                    notebook_path=notebook_path,
                    mode="connect"
                )

                # Check if connection was successful
                if "error" in str(result).lower() or "not found" in str(result).lower():
                    self.set_status(400)
                    self.finish({
                        "error": f"Failed to connect to notebook: {result}",
                        "success": False
                    })
                    return

                kernel_id = notebook_manager.get_kernel_id(notebook_name)
                self.log.info(f"Connected to notebook {notebook_name}, kernel: {kernel_id}")

            # Load conversation history from notebook metadata
            messages = load_conversation_from_notebook(notebook_path)
            self.log.info(f"Loaded {len(messages)} messages from {notebook_name}")

            self.finish({
                "success": True,
                "notebook_name": notebook_name,
                "messages": messages,
                "kernel_id": kernel_id
            })

        except json.JSONDecodeError:
            self.set_status(400)
            self.finish({"error": "Invalid JSON in request body"})
        except Exception as e:
            self.log.error(f"Error connecting to notebook: {e}")
            self.set_status(500)
            self.finish({"error": str(e)})

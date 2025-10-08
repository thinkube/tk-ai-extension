# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Integration tests for HTTP handlers."""

import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from tornado.testing import AsyncHTTPTestCase
from tornado.web import Application
from tk_ai_extension.handlers import MCPHealthHandler, MCPToolsListHandler, MCPToolCallHandler


class TestMCPHealthHandler(AsyncHTTPTestCase):
    """Tests for MCPHealthHandler."""

    def get_app(self):
        """Create test application."""
        return Application([
            (r"/api/tk-ai/mcp/health", MCPHealthHandler),
        ])

    def test_health_check(self):
        """Test health check endpoint."""
        response = self.fetch('/api/tk-ai/mcp/health')

        assert response.code == 200
        data = json.loads(response.body)
        assert data['status'] == 'ok'
        assert data['service'] == 'tk-ai-extension'
        assert 'version' in data


class TestMCPToolsListHandler(AsyncHTTPTestCase):
    """Tests for MCPToolsListHandler."""

    def get_app(self):
        """Create test application."""
        return Application([
            (r"/api/tk-ai/mcp/tools/list", MCPToolsListHandler),
        ])

    @patch('tk_ai_extension.handlers.get_registered_tools')
    def test_list_tools(self, mock_get_tools):
        """Test listing available tools."""
        # Mock registered tools
        mock_tool = MagicMock()
        mock_tool.name = 'test_tool'
        mock_tool.description = 'A test tool'
        mock_tool.input_schema = {
            'type': 'object',
            'properties': {'param': {'type': 'string'}}
        }

        mock_get_tools.return_value = {
            'test_tool': {'instance': mock_tool}
        }

        response = self.fetch('/api/tk-ai/mcp/tools/list')

        assert response.code == 200
        data = json.loads(response.body)
        assert 'tools' in data
        assert len(data['tools']) == 1
        assert data['tools'][0]['name'] == 'test_tool'
        assert data['tools'][0]['description'] == 'A test tool'
        assert 'inputSchema' in data['tools'][0]


class TestMCPToolCallHandler(AsyncHTTPTestCase):
    """Tests for MCPToolCallHandler."""

    def get_app(self):
        """Create test application."""
        return Application([
            (r"/api/tk-ai/mcp/tools/call", MCPToolCallHandler),
        ])

    @patch('tk_ai_extension.handlers.get_registered_tools')
    def test_call_tool_success(self, mock_get_tools):
        """Test successful tool execution."""
        # Mock tool executor
        async def mock_executor(args):
            return {
                'content': [{'type': 'text', 'text': 'Tool executed successfully'}]
            }

        mock_get_tools.return_value = {
            'test_tool': {'executor': mock_executor}
        }

        body = json.dumps({
            'tool': 'test_tool',
            'arguments': {'param': 'value'}
        })

        response = self.fetch(
            '/api/tk-ai/mcp/tools/call',
            method='POST',
            body=body
        )

        assert response.code == 200
        data = json.loads(response.body)
        assert 'content' in data
        assert data['content'][0]['text'] == 'Tool executed successfully'

    @patch('tk_ai_extension.handlers.get_registered_tools')
    def test_call_tool_not_found(self, mock_get_tools):
        """Test calling non-existent tool."""
        mock_get_tools.return_value = {}

        body = json.dumps({
            'tool': 'nonexistent_tool',
            'arguments': {}
        })

        response = self.fetch(
            '/api/tk-ai/mcp/tools/call',
            method='POST',
            body=body
        )

        assert response.code == 404
        data = json.loads(response.body)
        assert 'error' in data
        assert 'not found' in data['error'].lower()

    def test_call_tool_missing_parameter(self):
        """Test calling tool without required tool parameter."""
        body = json.dumps({
            'arguments': {}
        })

        response = self.fetch(
            '/api/tk-ai/mcp/tools/call',
            method='POST',
            body=body
        )

        assert response.code == 400
        data = json.loads(response.body)
        assert 'error' in data
        assert 'required' in data['error'].lower()

    def test_call_tool_invalid_json(self):
        """Test calling tool with invalid JSON."""
        response = self.fetch(
            '/api/tk-ai/mcp/tools/call',
            method='POST',
            body='invalid json'
        )

        assert response.code == 400
        data = json.loads(response.body)
        assert 'error' in data
        assert 'json' in data['error'].lower()


class TestToolsRegistry:
    """Tests for tools registry integration."""

    @patch('tk_ai_extension.agent.tools_registry._jupyter_managers', {
        'contents_manager': AsyncMock(),
        'kernel_manager': MagicMock(),
        'kernel_spec_manager': MagicMock()
    })
    def test_register_and_get_tools(self):
        """Test registering and retrieving tools."""
        from tk_ai_extension.agent.tools_registry import register_tool, get_registered_tools
        from tk_ai_extension.mcp.tools.list_notebooks import ListNotebooksTool

        # Register tool
        tool = ListNotebooksTool()
        register_tool(tool)

        # Retrieve tools
        tools = get_registered_tools()

        assert 'list_notebooks' in tools
        assert 'instance' in tools['list_notebooks']
        assert 'executor' in tools['list_notebooks']
        assert tools['list_notebooks']['instance'].name == 'list_notebooks'

    @pytest.mark.asyncio
    @patch('tk_ai_extension.agent.tools_registry._jupyter_managers', {
        'contents_manager': AsyncMock(),
        'kernel_manager': MagicMock(),
        'kernel_spec_manager': MagicMock()
    })
    async def test_tool_executor_wrapping(self):
        """Test that tool executors are properly wrapped."""
        from tk_ai_extension.agent.tools_registry import register_tool, get_registered_tools
        from tk_ai_extension.mcp.tools.list_kernels import ListKernelsTool

        # Mock kernel manager
        from tk_ai_extension.agent import tools_registry
        tools_registry._jupyter_managers['kernel_manager'].list_kernels.return_value = []

        # Register tool
        tool = ListKernelsTool()
        register_tool(tool)

        # Get executor
        tools = get_registered_tools()
        executor = tools['list_kernels']['executor']

        # Execute
        result = await executor({})

        assert 'content' in result
        assert isinstance(result['content'], list)
        assert result['content'][0]['type'] == 'text'

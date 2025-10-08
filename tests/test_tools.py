# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Unit tests for MCP tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from tk_ai_extension.mcp.tools.list_notebooks import ListNotebooksTool
from tk_ai_extension.mcp.tools.list_cells import ListCellsTool
from tk_ai_extension.mcp.tools.read_cell import ReadCellTool
from tk_ai_extension.mcp.tools.execute_cell import ExecuteCellTool
from tk_ai_extension.mcp.tools.list_kernels import ListKernelsTool


@pytest.fixture
def mock_contents_manager():
    """Create a mock contents manager."""
    manager = AsyncMock()
    return manager


@pytest.fixture
def mock_kernel_manager():
    """Create a mock kernel manager."""
    manager = MagicMock()
    return manager


@pytest.fixture
def mock_kernel_spec_manager():
    """Create a mock kernel spec manager."""
    manager = MagicMock()
    return manager


class TestListNotebooksTool:
    """Tests for ListNotebooksTool."""

    @pytest.mark.asyncio
    async def test_list_notebooks_basic(self, mock_contents_manager, mock_kernel_manager):
        """Test listing notebooks in current directory."""
        # Mock response
        mock_contents_manager.get.return_value = {
            'content': [
                {'name': 'notebook1.ipynb', 'type': 'notebook', 'last_modified': '2025-10-08T12:00:00Z'},
                {'name': 'notebook2.ipynb', 'type': 'notebook', 'last_modified': '2025-10-08T13:00:00Z'},
                {'name': 'data.csv', 'type': 'file'},  # Should be filtered out
            ]
        }

        tool = ListNotebooksTool()
        result = await tool.execute(mock_contents_manager, mock_kernel_manager, path='.')

        assert 'notebook1.ipynb' in result
        assert 'notebook2.ipynb' in result
        assert 'data.csv' not in result
        mock_contents_manager.get.assert_called_once_with('.', content=True)

    @pytest.mark.asyncio
    async def test_list_notebooks_empty(self, mock_contents_manager, mock_kernel_manager):
        """Test listing notebooks when none exist."""
        mock_contents_manager.get.return_value = {
            'content': []
        }

        tool = ListNotebooksTool()
        result = await tool.execute(mock_contents_manager, mock_kernel_manager, path='.')

        assert 'No notebooks found' in result

    @pytest.mark.asyncio
    async def test_list_notebooks_error(self, mock_contents_manager, mock_kernel_manager):
        """Test error handling when directory doesn't exist."""
        mock_contents_manager.get.side_effect = FileNotFoundError()

        tool = ListNotebooksTool()
        result = await tool.execute(mock_contents_manager, mock_kernel_manager, path='nonexistent')

        assert 'Error' in result


class TestListCellsTool:
    """Tests for ListCellsTool."""

    @pytest.mark.asyncio
    async def test_list_cells_basic(self, mock_contents_manager, mock_kernel_manager):
        """Test listing cells in a notebook."""
        mock_contents_manager.get.return_value = {
            'content': {
                'cells': [
                    {'cell_type': 'code', 'source': 'print("hello")', 'execution_count': 1},
                    {'cell_type': 'markdown', 'source': '# Title'},
                    {'cell_type': 'code', 'source': ['import pandas\n', 'df = pd.read_csv("data.csv")']},
                ]
            }
        }

        tool = ListCellsTool()
        result = await tool.execute(mock_contents_manager, mock_kernel_manager, notebook='test.ipynb')

        assert 'test.ipynb' in result
        assert 'code' in result
        assert 'markdown' in result
        assert '[#1]' in result
        mock_contents_manager.get.assert_called_once_with('test.ipynb', content=True, type='notebook')

    @pytest.mark.asyncio
    async def test_list_cells_empty_notebook(self, mock_contents_manager, mock_kernel_manager):
        """Test listing cells in empty notebook."""
        mock_contents_manager.get.return_value = {
            'content': {'cells': []}
        }

        tool = ListCellsTool()
        result = await tool.execute(mock_contents_manager, mock_kernel_manager, notebook='empty.ipynb')

        assert 'no cells' in result.lower()

    @pytest.mark.asyncio
    async def test_list_cells_missing_parameter(self, mock_contents_manager, mock_kernel_manager):
        """Test error when notebook parameter is missing."""
        tool = ListCellsTool()
        result = await tool.execute(mock_contents_manager, mock_kernel_manager)

        assert 'Error' in result
        assert 'required' in result.lower()


class TestReadCellTool:
    """Tests for ReadCellTool."""

    @pytest.mark.asyncio
    async def test_read_cell_code(self, mock_contents_manager, mock_kernel_manager):
        """Test reading a code cell."""
        mock_contents_manager.get.return_value = {
            'content': {
                'cells': [
                    {
                        'cell_type': 'code',
                        'source': 'print("hello world")',
                        'execution_count': 5,
                        'outputs': [
                            {
                                'output_type': 'stream',
                                'name': 'stdout',
                                'text': 'hello world\n'
                            }
                        ]
                    }
                ]
            }
        }

        tool = ReadCellTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            notebook='test.ipynb',
            cell_index=0
        )

        assert 'Cell 0' in result
        assert 'code' in result
        assert 'print("hello world")' in result
        assert 'hello world' in result
        assert 'Execution count: 5' in result

    @pytest.mark.asyncio
    async def test_read_cell_markdown(self, mock_contents_manager, mock_kernel_manager):
        """Test reading a markdown cell."""
        mock_contents_manager.get.return_value = {
            'content': {
                'cells': [
                    {
                        'cell_type': 'markdown',
                        'source': '# My Title\n\nSome text'
                    }
                ]
            }
        }

        tool = ReadCellTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            notebook='test.ipynb',
            cell_index=0
        )

        assert 'markdown' in result
        assert '# My Title' in result

    @pytest.mark.asyncio
    async def test_read_cell_out_of_range(self, mock_contents_manager, mock_kernel_manager):
        """Test reading cell with invalid index."""
        mock_contents_manager.get.return_value = {
            'content': {'cells': [{'cell_type': 'code', 'source': 'test'}]}
        }

        tool = ReadCellTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            notebook='test.ipynb',
            cell_index=10
        )

        assert 'Error' in result
        assert 'out of range' in result.lower()


class TestExecuteCellTool:
    """Tests for ExecuteCellTool."""

    @pytest.mark.asyncio
    async def test_execute_cell_placeholder(self, mock_contents_manager, mock_kernel_manager):
        """Test execute cell (placeholder implementation)."""
        mock_contents_manager.get.return_value = {
            'content': {
                'cells': [
                    {'cell_type': 'code', 'source': 'print("test")'}
                ]
            }
        }

        tool = ExecuteCellTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            notebook='test.ipynb',
            cell_index=0
        )

        # Should return placeholder message
        assert 'not fully implemented' in result
        assert 'print("test")' in result

    @pytest.mark.asyncio
    async def test_execute_non_code_cell(self, mock_contents_manager, mock_kernel_manager):
        """Test executing non-code cell returns error."""
        mock_contents_manager.get.return_value = {
            'content': {
                'cells': [
                    {'cell_type': 'markdown', 'source': '# Title'}
                ]
            }
        }

        tool = ExecuteCellTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            notebook='test.ipynb',
            cell_index=0
        )

        assert 'Error' in result
        assert 'not a code cell' in result


class TestListKernelsTool:
    """Tests for ListKernelsTool."""

    @pytest.mark.asyncio
    async def test_list_kernels_with_running(
        self,
        mock_contents_manager,
        mock_kernel_manager,
        mock_kernel_spec_manager
    ):
        """Test listing running kernels."""
        mock_kernel_manager.list_kernels.return_value = [
            {
                'id': 'abc123-kernel-id',
                'name': 'python3',
                'execution_state': 'idle',
                'connections': 2
            }
        ]
        mock_kernel_spec_manager.get_all_specs.return_value = {
            'python3': {'spec': {'display_name': 'Python 3'}},
            'julia': {'spec': {'display_name': 'Julia 1.8'}}
        }

        tool = ListKernelsTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            mock_kernel_spec_manager
        )

        assert 'Running kernels' in result
        assert 'abc123' in result
        assert 'python3' in result
        assert 'idle' in result
        assert 'Available kernel types' in result
        assert 'Julia 1.8' in result

    @pytest.mark.asyncio
    async def test_list_kernels_none_running(
        self,
        mock_contents_manager,
        mock_kernel_manager,
        mock_kernel_spec_manager
    ):
        """Test listing when no kernels are running."""
        mock_kernel_manager.list_kernels.return_value = []

        tool = ListKernelsTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            mock_kernel_spec_manager
        )

        assert 'No kernels currently running' in result

    @pytest.mark.asyncio
    async def test_list_kernels_error(
        self,
        mock_contents_manager,
        mock_kernel_manager,
        mock_kernel_spec_manager
    ):
        """Test error handling."""
        mock_kernel_manager.list_kernels.side_effect = Exception("Connection error")

        tool = ListKernelsTool()
        result = await tool.execute(
            mock_contents_manager,
            mock_kernel_manager,
            mock_kernel_spec_manager
        )

        assert 'Error listing kernels' in result


class TestToolSchemas:
    """Test tool schema definitions."""

    def test_list_notebooks_schema(self):
        """Test ListNotebooksTool schema."""
        tool = ListNotebooksTool()
        schema = tool.input_schema

        assert schema['type'] == 'object'
        assert 'path' in schema['properties']
        assert schema['properties']['path']['type'] == 'string'

    def test_list_cells_schema(self):
        """Test ListCellsTool schema."""
        tool = ListCellsTool()
        schema = tool.input_schema

        assert 'notebook' in schema['required']
        assert schema['properties']['notebook']['type'] == 'string'

    def test_read_cell_schema(self):
        """Test ReadCellTool schema."""
        tool = ReadCellTool()
        schema = tool.input_schema

        assert 'notebook' in schema['required']
        assert 'cell_index' in schema['required']
        assert schema['properties']['cell_index']['type'] == 'integer'

    def test_execute_cell_schema(self):
        """Test ExecuteCellTool schema."""
        tool = ExecuteCellTool()
        schema = tool.input_schema

        assert 'notebook' in schema['required']
        assert 'cell_index' in schema['required']

    def test_list_kernels_schema(self):
        """Test ListKernelsTool schema."""
        tool = ListKernelsTool()
        schema = tool.input_schema

        assert schema['required'] == []  # No required parameters
        assert schema['properties'] == {}  # No parameters

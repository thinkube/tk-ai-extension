# tk-ai-extension

**AI-powered JupyterLab extension for tk-ai lab (Thinkube's intelligent notebook laboratory)**

[![Github Actions Status](https://github.com/thinkube/tk-ai-extension/workflows/Build/badge.svg)](https://github.com/thinkube/tk-ai-extension/actions/workflows/build.yml)
[![License](https://img.shields.io/badge/License-BSD_3--Clause-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)

## Overview

`tk-ai-extension` brings Claude AI capabilities directly into your Jupyter notebooks through:

- **Chat Sidebar UI** - Modern chat interface with Thinkube branding (NEW!)
- **`%%tk` Magic Commands** - Execute AI prompts in notebook cells
- **MCP Server** - Embedded Model Context Protocol server for tool discovery
- **Claude Code CLI Integration** - Use Claude in JupyterLab terminal with notebook access
- **Autonomous Notebook Operations** - Claude can read, analyze, and execute notebook cells

### What Makes This Special

- **Localhost-only** - No external routing, ingress, or authentication complexity
- **Pod-internal** - Everything runs within your JupyterHub pod
- **Unified Tool Access** - Same MCP tools work from magic commands and CLI
- **Zero Configuration** - Auto-loads when JupyterLab starts

## Quick Start

### Chat Sidebar (NEW!)

1. **Open JupyterLab**
2. **Click "Open tk-ai Chat" in the Launcher**
3. **Start chatting with Claude!**

The chat interface will appear in the right sidebar with:
- Real-time connection status
- Message history with timestamps
- Thinkube-branded design
- Dark theme support

### In a Notebook

```python
%%tk
List all notebooks in the current directory
and tell me which one has the most cells
```

```python
%%tk
Read cell 5 from analysis.ipynb and explain what it does
```

```python
%%tk
Find all code cells that import pandas and summarize their purpose
```

### In Terminal (Claude Code CLI)

```bash
$ claude
> List all running kernels
> Read the first cell from notebook.ipynb
> Execute cell 3 and show me the output
```

## Features

### MCP Tools Available

**Notebook Operations:**
- `list_notebooks` - List all .ipynb files in a directory

**Cell Operations:**
- `list_cells` - List all cells in a notebook with previews
- `read_cell` - Read specific cell by index with outputs
- `execute_cell` - Execute cell (placeholder - coming soon)

**Kernel Operations:**
- `list_kernels` - List running kernels and available kernel specs

### Architecture

```
JupyterHub Pod (tk-ai lab)
│
├── JupyterLab Server (port 8888)
│   │
│   ├── tk-ai-extension (installed)
│   │   ├── MCP Server (http://localhost:8888/api/tk-ai/mcp/)
│   │   │   └── Tools: list_notebooks, read_cell, list_cells, etc.
│   │   │
│   │   ├── Claude Agent SDK
│   │   │   └── Uses MCP tools
│   │   │
│   │   └── Magic Commands (%%tk)
│   │       └── Calls Claude Agent SDK
│   │
│   └── JupyterLab UI (browser)
│       ├── Terminal with Claude Code CLI
│       │   └── ~/.mcp.json → http://localhost:8888/api/tk-ai/mcp/
│       │
│       └── Notebooks
│           └── %%tk magic available
│
└── All self-contained, no external routing needed
```

## Installation

### Requirements

- JupyterLab >= 4.0.0
- Python >= 3.9
- Anthropic API key

### For Production (JupyterHub)

```bash
pip install tk-ai-extension
```

Or add to your JupyterHub Docker image:

```dockerfile
RUN pip install tk-ai-extension
```

### For Development

```bash
# Clone repository
git clone https://github.com/thinkube/tk-ai-extension.git
cd tk-ai-extension

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest tests/
```

## Configuration

### API Key

Set your Anthropic API key as an environment variable:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

For JupyterHub, configure in `jupyterhub_config.py`:

```python
c.Spawner.environment = {
    'ANTHROPIC_API_KEY': os.environ.get('ANTHROPIC_API_KEY'),
}
```

### Claude Code CLI Setup

The extension auto-generates `~/.mcp.json` when JupyterLab starts:

```json
{
  "mcpServers": {
    "tk-ai-lab": {
      "type": "http",
      "url": "http://localhost:8888/api/tk-ai/mcp/",
      "description": "tk-ai lab notebook tools"
    }
  }
}
```

## API Endpoints

### Health Check

```bash
GET http://localhost:8888/api/tk-ai/mcp/health
```

**Response:**
```json
{
  "status": "ok",
  "service": "tk-ai-extension",
  "version": "0.1.0"
}
```

### List Available Tools

```bash
GET http://localhost:8888/api/tk-ai/mcp/tools/list
```

**Response:**
```json
{
  "tools": [
    {
      "name": "list_notebooks",
      "description": "List all Jupyter notebooks in a directory",
      "inputSchema": {
        "type": "object",
        "properties": {
          "path": {
            "type": "string",
            "description": "Directory path (default: current directory)"
          }
        }
      }
    }
  ]
}
```

### Execute Tool

```bash
POST http://localhost:8888/api/tk-ai/mcp/tools/call
Content-Type: application/json

{
  "tool": "list_cells",
  "arguments": {
    "notebook": "analysis.ipynb"
  }
}
```

**Response:**
```json
{
  "content": [
    {
      "type": "text",
      "text": "Cells in 'analysis.ipynb':\n  0. code      [#1]  | import pandas as pd\n  1. markdown        | # Data Analysis\n  2. code      [#2]  | df = pd.read_csv('data.csv')"
    }
  ]
}
```

## Usage Examples

### Example 1: Notebook Analysis

```python
%%tk
Analyze all notebooks in the current directory.
For each notebook:
1. Count the cells
2. List any cells that import libraries
3. Identify the main purpose

Summarize your findings.
```

### Example 2: Code Explanation

```python
%%tk
Read cell 10 from machine_learning.ipynb and explain:
- What libraries are being used
- What the code is trying to accomplish
- Any potential improvements
```

### Example 3: Multi-Notebook Search

```python
%%tk
Search through all notebooks in ./experiments/
and find which ones contain matplotlib visualizations.
List them with the cell numbers that have plots.
```

## Development

### Project Structure

```
tk-ai-extension/
├── tk_ai_extension/           # Python package
│   ├── mcp/                   # MCP server implementation
│   │   └── tools/             # MCP tools
│   │       ├── list_notebooks.py
│   │       ├── list_cells.py
│   │       ├── read_cell.py
│   │       ├── execute_cell.py
│   │       └── list_kernels.py
│   │
│   ├── agent/                 # Claude Agent SDK integration
│   │   └── tools_registry.py  # Tool registration
│   │
│   ├── magics/                # IPython magic commands
│   │   └── tk_magic.py        # %%tk implementation
│   │
│   ├── handlers.py            # HTTP handlers
│   └── extension.py           # JupyterLab extension entry point
│
├── tests/                     # Test suite
│   ├── test_tools.py          # Unit tests for tools
│   └── test_handlers.py       # Integration tests
│
├── examples/                  # Example notebooks
├── pyproject.toml             # Package configuration
├── pytest.ini                 # Test configuration
└── README.md                  # This file
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=tk_ai_extension --cov-report=html

# Run specific test file
pytest tests/test_tools.py

# Run specific test
pytest tests/test_tools.py::TestListNotebooksTool::test_list_notebooks_basic
```

### Code Style

```bash
# Format code
black tk_ai_extension/ tests/

# Lint code
ruff check tk_ai_extension/ tests/
```

## Troubleshooting

### Extension Not Loading

Check if extension is enabled:

```bash
jupyter server extension list
```

You should see:
```
tk_ai_extension enabled
    - Validating tk_ai_extension...
      tk_ai_extension 0.1.0 OK
```

### Magic Command Not Available

Try manually loading the extension:

```python
%load_ext tk_ai_extension
```

### MCP Server Not Responding

Check the MCP server health:

```bash
curl http://localhost:8888/api/tk-ai/mcp/health
```

Check JupyterLab logs:

```bash
journalctl -u jupyterhub -f
```

### API Key Issues

Verify your API key is set:

```python
import os
print(os.environ.get('ANTHROPIC_API_KEY', 'Not set'))
```

## Roadmap

- [x] Phase 1: MCP Foundation
- [x] Phase 2: Claude Agent SDK Integration
- [x] Phase 3: Magic Commands
- [x] Phase 4: Additional Tools & HTTP Handlers
- [x] Phase 5: Testing & Documentation
- [x] Phase 6: Packaging & Deployment
- [x] Phase 7: Chat Sidebar UI ✨ NEW!

### Upcoming Features

- **Full Claude Chat Integration** - Complete backend integration for chat UI
- **Real-time Streaming** - Stream Claude's responses as they generate
- **Conversation History** - Persist chat conversations across sessions
- **Tool Usage Visualization** - Show which tools Claude is using in real-time
- **Full Cell Execution** - Complete implementation of execute_cell tool
- **Cell Insertion/Modification** - Tools to insert and edit cells
- **Kernel Management** - Start, stop, restart kernels

## Contributing

We welcome contributions! Please:

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## License

BSD-3-Clause License - See [LICENSE](LICENSE) for details.

This project incorporates code from:
- [jupyter-mcp-server](https://github.com/datalayer/jupyter-mcp-server) (BSD-3-Clause)
- Inspiration from [jupyter-ai](https://github.com/jupyterlab/jupyter-ai) UX patterns

## Authors

- Alejandro Martínez Corriá and the Thinkube contributors

## Support

- **Documentation**: [Thinkube Docs](https://thinkube.com/docs)
- **Issues**: [GitHub Issues](https://github.com/thinkube/tk-ai-extension/issues)
- **Discussions**: [GitHub Discussions](https://github.com/thinkube/tk-ai-extension/discussions)

---

**🤖 Built with [Claude Code](https://claude.com/claude-code) for the Thinkube platform**

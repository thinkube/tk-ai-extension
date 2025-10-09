# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""%%tk magic command for Claude AI integration."""

import os
from IPython.core.magic import Magics, cell_magic, magics_class
from IPython.display import display, Markdown


@magics_class
class TKMagics(Magics):
    """Magic commands for tk-ai-extension."""

    def __init__(self, shell):
        super().__init__(shell)
        self._load_secrets()
        self._check_api_key()

    def _load_secrets(self):
        """Load secrets from .secrets.env file if it exists."""
        secrets_path = os.path.expanduser('~/thinkube/notebooks/.secrets.env')
        if os.path.exists(secrets_path):
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
                self.shell.system(
                    f'echo "⚠️  Warning: Failed to load secrets from {secrets_path}: {e}"'
                )

    def _check_api_key(self):
        """Check if CLAUDE_CODE_OAUTH_TOKEN or ANTHROPIC_API_KEY is set."""
        if not os.environ.get('CLAUDE_CODE_OAUTH_TOKEN') and not os.environ.get('ANTHROPIC_API_KEY'):
            self.shell.system(
                'echo "⚠️  Warning: Claude API credentials not found. '
                'Add CLAUDE_CODE_OAUTH_TOKEN (for Pro/Max accounts) or ANTHROPIC_API_KEY (for API access) '
                'in thinkube-control Secrets page, then click \'Export to Notebooks\' to make them available here."'
            )

    @cell_magic
    def tk(self, line, cell):
        """Execute Claude AI query with MCP tools.

        Usage:
            %%tk
            Your prompt here
            Can be multiple lines

        Example:
            %%tk
            List all notebooks in the current directory
        """
        try:
            # Import here to avoid issues if not installed
            from claude_agent_sdk import query
            import asyncio

            # Run async query
            loop = asyncio.get_event_loop()
            result = loop.run_until_complete(
                query(prompt=cell)
            )

            # Display result as markdown
            display(Markdown(str(result)))

        except ImportError as e:
            display(Markdown(
                f"❌ **Error**: claude-agent-sdk not installed.\n\n"
                f"Install with: `pip install claude-agent-sdk`\n\n"
                f"Details: {str(e)}"
            ))
        except Exception as e:
            display(Markdown(
                f"❌ **Error**: {str(e)}\n\n"
                f"**Setup required**: Add `CLAUDE_CODE_OAUTH_TOKEN` (for Pro/Max accounts) or `ANTHROPIC_API_KEY` (for API access) "
                f"in thinkube-control Secrets page, then click 'Export to Notebooks' to make credentials available."
            ))


def load_ipython_extension(ipython):
    """Load the extension in IPython."""
    ipython.register_magics(TKMagics)

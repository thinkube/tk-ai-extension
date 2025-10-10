# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Manages per-notebook Claude SDK clients for conversation continuity."""

import logging
from typing import Optional, Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class ClaudeClientManager:
    """Manages per-notebook persistent Claude SDK clients.

    Each notebook gets its own isolated Claude session for conversation
    history. Inactive sessions are automatically cleaned up.
    """

    def __init__(self, max_age_minutes: int = 30):
        """Initialize the client manager.

        Args:
            max_age_minutes: Maximum age for inactive sessions before cleanup
        """
        self._clients: Dict[str, object] = {}  # {notebook_path: ClaudeSDKClient}
        self._options: Dict[str, object] = {}  # {notebook_path: ClaudeAgentOptions}
        self._last_access: Dict[str, datetime] = {}  # {notebook_path: timestamp}
        self._max_age_minutes = max_age_minutes
        logger.info("ClaudeClientManager initialized (multi-client mode)")

    async def get_or_create_client(self, notebook_path: str, options):
        """Get existing client for notebook or create a new one.

        Args:
            notebook_path: Path to the notebook (used as client key)
            options: ClaudeAgentOptions for client configuration

        Returns:
            ClaudeSDKClient instance for this notebook
        """
        from claude_agent_sdk import ClaudeSDKClient

        # Update last access timestamp
        self._last_access[notebook_path] = datetime.now()

        if notebook_path not in self._clients:
            logger.info(f"Creating new Claude client for notebook: {notebook_path}")
            client = ClaudeSDKClient(options=options)
            await client.connect()
            self._clients[notebook_path] = client
            self._options[notebook_path] = options
        else:
            logger.debug(f"Reusing existing Claude client for notebook: {notebook_path}")

        return self._clients[notebook_path]

    async def close_client(self, notebook_path: str):
        """Close and cleanup client for specific notebook.

        Args:
            notebook_path: Path to the notebook
        """
        if notebook_path in self._clients:
            logger.info(f"Closing Claude client for notebook: {notebook_path}")
            try:
                await self._clients[notebook_path].disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting client for {notebook_path}: {e}")
            finally:
                del self._clients[notebook_path]
                del self._options[notebook_path]
                del self._last_access[notebook_path]
                logger.info(f"Client removed for: {notebook_path}")

    async def cleanup_inactive(self):
        """Close sessions inactive for longer than max_age_minutes."""
        now = datetime.now()
        cutoff = now - timedelta(minutes=self._max_age_minutes)

        inactive_paths = [
            path for path, last_access in self._last_access.items()
            if last_access < cutoff
        ]

        for path in inactive_paths:
            logger.info(f"Cleaning up inactive session: {path}")
            await self.close_client(path)

    def get_active_sessions(self) -> list:
        """Get list of active notebook paths with sessions.

        Returns:
            List of notebook paths with active Claude sessions
        """
        return list(self._clients.keys())

    async def reset_client(self, notebook_path: str):
        """Reset the client for a notebook, clearing conversation history.

        Args:
            notebook_path: Path to the notebook
        """
        if notebook_path in self._clients:
            logger.info(f"Resetting Claude client for notebook: {notebook_path}")
            await self.close_client(notebook_path)
            logger.info(f"Client cleared for: {notebook_path}")

    async def shutdown(self):
        """Shutdown all clients gracefully."""
        logger.info(f"Shutting down {len(self._clients)} Claude client(s)")
        notebook_paths = list(self._clients.keys())

        for path in notebook_paths:
            try:
                await self.close_client(path)
            except Exception as e:
                logger.error(f"Error shutting down client for {path}: {e}")

        logger.info("All Claude clients shut down")

# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Manages persistent Claude SDK client for conversation continuity."""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ClaudeClientManager:
    """Manages a single persistent Claude SDK client.

    Thinkube is a single-user environment, so we maintain one client
    to preserve conversation history across requests.
    """

    def __init__(self):
        """Initialize the client manager."""
        self._client: Optional[object] = None
        self._options: Optional[object] = None
        logger.info("ClaudeClientManager initialized")

    async def get_or_create_client(self, options):
        """Get existing client or create a new one.

        Args:
            options: ClaudeAgentOptions for client configuration

        Returns:
            ClaudeSDKClient instance
        """
        from claude_agent_sdk import ClaudeSDKClient

        if self._client is None:
            logger.info("Creating new Claude client")
            self._client = ClaudeSDKClient(options=options)
            await self._client.connect()
            self._options = options
        else:
            logger.debug("Reusing existing Claude client")

        return self._client

    async def reset_client(self):
        """Reset the client, clearing conversation history."""
        if self._client is not None:
            logger.info("Resetting Claude client")
            await self._client.disconnect()
            self._client = None
            self._options = None
            logger.info("Client cleared")

    async def shutdown(self):
        """Shutdown the client gracefully."""
        if self._client is not None:
            logger.info("Shutting down Claude client")
            try:
                await self._client.disconnect()
                logger.info("Claude client shut down successfully")
            except Exception as e:
                logger.error(f"Error disconnecting client: {e}")
            finally:
                self._client = None
                self._options = None

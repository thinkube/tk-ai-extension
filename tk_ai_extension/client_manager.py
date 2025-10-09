# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Manages persistent Claude SDK clients per user for conversation continuity."""

import logging
from typing import Dict, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class ClaudeClientManager:
    """Manages persistent Claude SDK clients per user session.

    This ensures conversation history is maintained across requests
    instead of creating a new client for each chat message.
    """

    def __init__(self):
        """Initialize the client manager."""
        self._clients: Dict[str, Dict] = {}  # user_id -> {client, options}
        logger.info("ClaudeClientManager initialized")

    async def get_or_create_client(self, user_id: str, options):
        """Get existing client for user or create a new one.

        Args:
            user_id: Unique identifier for the user
            options: ClaudeAgentOptions for client configuration

        Returns:
            ClaudeSDKClient instance
        """
        from claude_agent_sdk import ClaudeSDKClient

        if user_id not in self._clients:
            logger.info(f"Creating new Claude client for user: {user_id}")
            client = ClaudeSDKClient(options=options)
            await client.connect()

            self._clients[user_id] = {
                "client": client,
                "options": options,
                "permission_mode": getattr(options, 'permission_mode', 'default')
            }
        else:
            logger.debug(f"Reusing existing Claude client for user: {user_id}")

        return self._clients[user_id]["client"]

    async def set_permission_mode(self, user_id: str, mode: str):
        """Change permission mode for a user's client.

        Args:
            user_id: Unique identifier for the user
            mode: Permission mode (plan/default/acceptEdits)
        """
        if user_id in self._clients:
            logger.info(f"Changing permission mode for {user_id} to {mode}")
            # Disconnect old client
            await self._clients[user_id]["client"].disconnect()
            del self._clients[user_id]
            logger.info(f"Client reset for {user_id}, will recreate with new mode on next request")

    async def reset_client(self, user_id: str):
        """Reset a user's client, clearing conversation history.

        Args:
            user_id: Unique identifier for the user
        """
        if user_id in self._clients:
            logger.info(f"Resetting Claude client for user: {user_id}")
            await self._clients[user_id]["client"].disconnect()
            del self._clients[user_id]
            logger.info(f"Client cleared for {user_id}")

    async def shutdown(self):
        """Shutdown all clients gracefully."""
        logger.info(f"Shutting down {len(self._clients)} Claude clients")
        for user_id, client_data in self._clients.items():
            try:
                await client_data["client"].disconnect()
                logger.debug(f"Disconnected client for {user_id}")
            except Exception as e:
                logger.error(f"Error disconnecting client for {user_id}: {e}")

        self._clients.clear()
        logger.info("All Claude clients shut down")

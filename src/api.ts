// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * API client for tk-ai-extension MCP server
 */

import { URLExt } from '@jupyterlab/coreutils';
import { ServerConnection } from '@jupyterlab/services';

/**
 * Tool definition interface
 */
export interface ITool {
  name: string;
  description: string;
  inputSchema: any;
}

/**
 * Tool execution result
 */
export interface IToolResult {
  content: Array<{
    type: string;
    text: string;
  }>;
  isError?: boolean;
}

/**
 * Chat message interface
 */
export interface IChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

/**
 * MCP API Client
 */
export class MCPClient {
  private serverSettings: ServerConnection.ISettings;
  private baseUrl: string;

  constructor() {
    this.serverSettings = ServerConnection.makeSettings();
    this.baseUrl = URLExt.join(
      this.serverSettings.baseUrl,
      'api',
      'tk-ai',
      'mcp'
    );
  }

  /**
   * Check if MCP server is healthy
   */
  async checkHealth(): Promise<boolean> {
    try {
      const url = URLExt.join(this.baseUrl, 'health');
      const response = await ServerConnection.makeRequest(
        url,
        {},
        this.serverSettings
      );

      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      return data.status === 'ok';
    } catch (error) {
      console.error('Health check failed:', error);
      return false;
    }
  }

  /**
   * List available tools
   */
  async listTools(): Promise<ITool[]> {
    const url = URLExt.join(this.baseUrl, 'tools', 'list');
    const response = await ServerConnection.makeRequest(
      url,
      {},
      this.serverSettings
    );

    if (!response.ok) {
      throw new Error(`Failed to list tools: ${response.statusText}`);
    }

    const data = await response.json();
    return data.tools;
  }

  /**
   * Execute a tool
   */
  async executeTool(toolName: string, args: any): Promise<IToolResult> {
    const url = URLExt.join(this.baseUrl, 'tools', 'call');
    const response = await ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify({
          tool: toolName,
          arguments: args
        })
      },
      this.serverSettings
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Tool execution failed: ${response.statusText}`);
    }

    return await response.json();
  }

  /**
   * Send a chat message and get Claude's response
   * This would integrate with Claude Agent SDK on the backend
   */
  async sendMessage(message: string): Promise<string> {
    // For now, this is a placeholder
    // In the full implementation, this would:
    // 1. Send message to a new endpoint (e.g., /api/tk-ai/mcp/chat)
    // 2. Backend uses Claude Agent SDK with MCP tools
    // 3. Return Claude's response

    // Temporary: Just echo back with a note
    return `Note: Full chat integration coming soon. You sent: "${message}"

For now, use %%tk magic in notebooks.

Available tools:
- list_notebooks
- list_cells
- read_cell
- execute_cell (placeholder)
- list_kernels`;
  }
}

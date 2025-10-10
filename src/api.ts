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
   * Check if AI model (Claude) is accessible
   */
  async checkModelHealth(): Promise<boolean> {
    try {
      const url = URLExt.join(this.baseUrl, 'model-health');
      const response = await ServerConnection.makeRequest(
        url,
        {},
        this.serverSettings
      );

      if (!response.ok) {
        return false;
      }

      const data = await response.json();
      return data.model_available === true;
    } catch (error) {
      console.error('Model health check failed:', error);
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
   */
  async sendMessage(message: string, notebookPath: string | null = null): Promise<string> {
    const url = URLExt.join(this.baseUrl, 'chat');
    const requestBody: any = {
      message: message,
      timestamp: new Date().toISOString()
    };

    // Include notebook path if available
    if (notebookPath) {
      requestBody.notebook_path = notebookPath;
    }

    const response = await ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify(requestBody)
      },
      this.serverSettings
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || error.error || `Chat failed: ${response.statusText}`);
    }

    const data = await response.json();
    return data.response;
  }
}

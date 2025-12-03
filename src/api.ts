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
 * Streaming message types from WebSocket
 */
export type StreamingMessageType =
  | 'token'
  | 'tool_call'
  | 'tool_result'
  | 'done'
  | 'error'
  | 'cancelled';

/**
 * Streaming message from WebSocket
 */
export interface IStreamingMessage {
  type: StreamingMessageType;
  content?: string;
  name?: string;
  args?: any;
  result?: any;
  success?: boolean;
  full_response?: string;
  message?: string;
}

/**
 * Tool execution status for UI feedback
 */
export interface IToolExecution {
  name: string;
  args?: any;
  status: 'running' | 'completed' | 'error';
  startTime: Date;
  endTime?: Date;
}

/**
 * Callbacks for streaming responses
 */
export interface IStreamingCallbacks {
  onToken: (token: string) => void;
  onToolCall?: (name: string, args: any) => void;
  onToolResult?: (name: string, success: boolean, result?: any) => void;
  onDone: (fullResponse: string) => void;
  onError: (error: string) => void;
  onCancelled?: () => void;
  onConnectionChange?: (connected: boolean) => void;
}

/**
 * MCP API Client
 */
export class MCPClient {
  private serverSettings: ServerConnection.ISettings;
  private baseUrl: string;
  private wsBaseUrl: string;
  private ws: WebSocket | null = null;
  private streamingCallbacks: IStreamingCallbacks | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectTimeout: number | null = null;
  private isReconnecting = false;
  private pendingMessage: { message: string; notebookPath: string } | null = null;

  constructor() {
    this.serverSettings = ServerConnection.makeSettings();
    this.baseUrl = URLExt.join(
      this.serverSettings.baseUrl,
      'api',
      'tk-ai',
      'mcp'
    );
    // Build WebSocket URL (convert http(s) to ws(s))
    const wsProtocol = this.serverSettings.baseUrl.startsWith('https') ? 'wss' : 'ws';
    const httpUrl = new URL(this.serverSettings.baseUrl);
    this.wsBaseUrl = `${wsProtocol}://${httpUrl.host}${httpUrl.pathname}api/tk-ai/mcp/stream`;
  }

  /**
   * Connect to streaming WebSocket with auto-reconnect
   */
  private connectWebSocket(): Promise<WebSocket> {
    return new Promise((resolve, reject) => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        resolve(this.ws);
        return;
      }

      // Build WebSocket URL with token for authentication
      const token = this.serverSettings.token;
      const wsUrl = token ? `${this.wsBaseUrl}?token=${token}` : this.wsBaseUrl;

      console.log('Connecting to WebSocket:', this.wsBaseUrl);
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.isReconnecting = false;

        // Notify connection change
        if (this.streamingCallbacks?.onConnectionChange) {
          this.streamingCallbacks.onConnectionChange(true);
        }

        // Resend pending message if we were reconnecting
        if (this.pendingMessage) {
          const { message, notebookPath } = this.pendingMessage;
          this.pendingMessage = null;
          this.ws!.send(JSON.stringify({
            type: 'chat',
            message: message,
            notebook_path: notebookPath
          }));
        }

        resolve(this.ws!);
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        if (!this.isReconnecting) {
          reject(new Error('WebSocket connection failed'));
        }
      };

      this.ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        this.ws = null;

        // Notify connection change
        if (this.streamingCallbacks?.onConnectionChange) {
          this.streamingCallbacks.onConnectionChange(false);
        }

        // Attempt auto-reconnect if not intentionally closed
        if (event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.attemptReconnect();
        }
      };

      this.ws.onmessage = (event) => {
        this.handleStreamingMessage(event.data);
      };
    });
  }

  /**
   * Attempt to reconnect with exponential backoff
   */
  private attemptReconnect(): void {
    if (this.isReconnecting) return;

    this.isReconnecting = true;
    this.reconnectAttempts++;

    // Exponential backoff: 1s, 2s, 4s, 8s, 16s
    const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts - 1), 16000);

    console.log(`Attempting reconnect ${this.reconnectAttempts}/${this.maxReconnectAttempts} in ${delay}ms`);

    this.reconnectTimeout = window.setTimeout(() => {
      this.connectWebSocket().catch(error => {
        console.error('Reconnect failed:', error);
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
          this.isReconnecting = false;
          this.attemptReconnect();
        } else {
          console.error('Max reconnect attempts reached');
          this.isReconnecting = false;
          if (this.streamingCallbacks?.onError) {
            this.streamingCallbacks.onError('Connection lost. Please refresh the page.');
          }
        }
      });
    }, delay);
  }

  /**
   * Handle incoming streaming message
   */
  private handleStreamingMessage(data: string): void {
    if (!this.streamingCallbacks) return;

    try {
      const msg: IStreamingMessage = JSON.parse(data);

      switch (msg.type) {
        case 'token':
          if (msg.content) {
            this.streamingCallbacks.onToken(msg.content);
          }
          break;

        case 'tool_call':
          if (this.streamingCallbacks.onToolCall && msg.name) {
            this.streamingCallbacks.onToolCall(msg.name, msg.args || {});
          }
          break;

        case 'tool_result':
          if (this.streamingCallbacks.onToolResult && msg.name !== undefined) {
            this.streamingCallbacks.onToolResult(msg.name, msg.success ?? false, msg.result);
          }
          break;

        case 'done':
          this.streamingCallbacks.onDone(msg.full_response || '');
          break;

        case 'error':
          this.streamingCallbacks.onError(msg.message || 'Unknown error');
          break;

        case 'cancelled':
          if (this.streamingCallbacks.onCancelled) {
            this.streamingCallbacks.onCancelled();
          }
          break;
      }
    } catch (error) {
      console.error('Error parsing streaming message:', error);
    }
  }

  /**
   * Send a streaming chat message
   */
  async sendMessageStreaming(
    message: string,
    notebookPath: string,
    callbacks: IStreamingCallbacks
  ): Promise<void> {
    this.streamingCallbacks = callbacks;

    try {
      const ws = await this.connectWebSocket();

      ws.send(JSON.stringify({
        type: 'chat',
        message: message,
        notebook_path: notebookPath
      }));
    } catch (error) {
      callbacks.onError(error instanceof Error ? error.message : 'Connection failed');
    }
  }

  /**
   * Cancel the current streaming request
   */
  cancelStreaming(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: 'cancel' }));
    }
  }

  /**
   * Disconnect WebSocket
   */
  disconnectWebSocket(): void {
    // Clear reconnect timeout
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    this.isReconnecting = false;
    this.reconnectAttempts = 0;
    this.pendingMessage = null;

    if (this.ws) {
      this.ws.close(1000, 'Intentional disconnect'); // Normal closure
      this.ws = null;
    }
    this.streamingCallbacks = null;
  }

  /**
   * Check if WebSocket is connected
   */
  isWebSocketConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
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

  /**
   * Connect to a notebook and load conversation history
   */
  async connectNotebook(notebookPath: string): Promise<{
    success: boolean;
    notebook_name: string;
    messages: IChatMessage[];
    kernel_id: string;
  }> {
    const url = URLExt.join(this.baseUrl, 'notebook', 'connect');
    const response = await ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify({ notebook_path: notebookPath })
      },
      this.serverSettings
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Failed to connect to notebook: ${response.statusText}`);
    }

    const data = await response.json();

    // Convert message timestamps from strings to Date objects
    const messages = data.messages.map((msg: any) => ({
      role: msg.role,
      content: msg.content,
      timestamp: msg.timestamp ? new Date(msg.timestamp) : new Date()
    }));

    return {
      success: data.success,
      notebook_name: data.notebook_name,
      messages: messages,
      kernel_id: data.kernel_id
    };
  }

  /**
   * Close Claude session for a notebook
   */
  async closeSession(notebookPath: string): Promise<void> {
    const url = URLExt.join(this.baseUrl, 'session', 'close');
    const response = await ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify({ notebook_path: notebookPath })
      },
      this.serverSettings
    );

    if (!response.ok) {
      console.error('Failed to close session:', response.statusText);
      // Don't throw - this is fire-and-forget cleanup
    }
  }

  /**
   * Clear conversation history for a notebook
   */
  async clearConversation(notebookPath: string): Promise<void> {
    const url = URLExt.join(this.baseUrl, 'conversation', 'clear');
    const response = await ServerConnection.makeRequest(
      url,
      {
        method: 'POST',
        body: JSON.stringify({ notebook_path: notebookPath })
      },
      this.serverSettings
    );

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.error || `Failed to clear conversation: ${response.statusText}`);
    }
  }

  /**
   * Check status of async cell execution
   */
  async checkExecutionStatus(executionId: string): Promise<{
    success: boolean;
    status: 'running' | 'completed' | 'error';
    cell_index: number;
    outputs?: any[];
    error?: string;
  }> {
    const result = await this.executeTool('check_execution_status', {
      execution_id: executionId
    });

    // Tool results come wrapped in content array with stringified text
    // Need to parse the actual dict from the text field
    if (result.content && result.content[0] && result.content[0].text) {
      const textContent = result.content[0].text;
      // Parse the Python dict string (uses single quotes, convert to JSON)
      const jsonContent = textContent.replace(/'/g, '"').replace(/None/g, 'null').replace(/True/g, 'true').replace(/False/g, 'false');
      return JSON.parse(jsonContent);
    }

    return result as any;
  }

  /**
   * Check status of execute_all_cells operation
   */
  async checkAllCellsStatus(executionId: string): Promise<{
    success: boolean;
    status: 'running' | 'completed' | 'error';
    current_cell_index: number | null;
    completed_cells: number;
    total_cells: number;
    progress_percent: number;
    error?: string;
  }> {
    const result = await this.executeTool('check_all_cells_status', {
      execution_id: executionId
    });

    // Tool results come wrapped in content array with stringified text
    // Need to parse the actual dict from the text field
    if (result.content && result.content[0] && result.content[0].text) {
      const textContent = result.content[0].text;
      // Parse the Python dict string (uses single quotes, convert to JSON)
      const jsonContent = textContent.replace(/'/g, '"').replace(/None/g, 'null').replace(/True/g, 'true').replace(/False/g, 'false');
      return JSON.parse(jsonContent);
    }

    return result as any;
  }

  /**
   * Export conversation to markdown format
   */
  exportConversationToMarkdown(
    messages: IChatMessage[],
    notebookName: string
  ): string {
    const lines: string[] = [
      `# Conversation: ${notebookName}`,
      '',
      `*Exported on ${new Date().toLocaleString()}*`,
      '',
      '---',
      ''
    ];

    for (const msg of messages) {
      const role = msg.role === 'user' ? '👤 **User**' : '🤖 **Thinky**';
      const time = msg.timestamp.toLocaleString();

      lines.push(`### ${role}`);
      lines.push(`*${time}*`);
      lines.push('');
      lines.push(msg.content);
      lines.push('');
      lines.push('---');
      lines.push('');
    }

    return lines.join('\n');
  }

  /**
   * Download conversation as markdown file
   */
  downloadConversation(messages: IChatMessage[], notebookName: string): void {
    const markdown = this.exportConversationToMarkdown(messages, notebookName);
    const blob = new Blob([markdown], { type: 'text/markdown' });
    const url = URL.createObjectURL(blob);

    const a = document.createElement('a');
    a.href = url;
    a.download = `${notebookName}-conversation-${new Date().toISOString().split('T')[0]}.md`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }
}

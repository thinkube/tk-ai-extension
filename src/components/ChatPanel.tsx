// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Chat Panel React component
 */

import React, { useState, useEffect, useRef } from 'react';
import { JupyterFrontEnd } from '@jupyterlab/application';
import { MCPClient, IChatMessage } from '../api';
import { renderMarkdown } from '../utils/markdown';

/**
 * Props for ChatPanel component
 */
export interface IChatPanelProps {
  client: MCPClient;
  notebookPath: string | null;
  labShell: JupyterFrontEnd.IShell | null;
}

/**
 * Chat Panel Component
 * Provides a chat interface for interacting with Claude AI
 */
export const ChatPanel: React.FC<IChatPanelProps> = ({ client, notebookPath, labShell }) => {
  /**
   * Get the currently active notebook path at the time of sending a message
   */
  const getCurrentNotebookPath = (): string | null => {
    if (!labShell) {
      return null;
    }

    const current = labShell.currentWidget;
    if (!current) {
      return null;
    }

    // Check if the current widget is a notebook
    const context = (current as any).context;
    if (context && context.path && context.path.endsWith('.ipynb')) {
      return context.path;
    }

    return null;
  };
  const [messages, setMessages] = useState<IChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isModelConnected, setIsModelConnected] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Check connection on mount
  useEffect(() => {
    checkConnection();
  }, []);

  // Auto-scroll to bottom when messages change
  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const checkConnection = async () => {
    const mcpHealthy = await client.checkHealth();
    const modelHealthy = await client.checkModelHealth();

    setIsConnected(mcpHealthy);
    setIsModelConnected(modelHealthy);

    if (!mcpHealthy) {
      setMessages([
        {
          role: 'assistant',
          content:
            '⚠️ Cannot connect to MCP server. Please make sure:\n' +
            '1. tk-ai-extension is properly installed\n' +
            '2. Tk-ai Lab server is running\n' +
            '3. Check server logs for errors',
          timestamp: new Date()
        }
      ]);
    } else if (!modelHealthy) {
      setMessages([
        {
          role: 'assistant',
          content:
            '⚠️ MCP server is running, but Thinky AI is not accessible.\n\n' +
            'Please check:\n' +
            '1. ANTHROPIC_API_KEY environment variable is set\n' +
            '2. API key is valid and has quota remaining\n' +
            '3. Network connectivity to Anthropic API',
          timestamp: new Date()
        }
      ]);
    } else {
      setMessages([
        {
          role: 'assistant',
          content:
            'Hello! I\'m Thinky, your Tk-ai Lab notebook assistant.\n\n' +
            '**To get started:**\n' +
            '1. Tell me which notebook you want to work with\n' +
            '2. I\'ll connect to it and start a kernel\n' +
            '3. Then I can execute cells, modify code, and analyze your work!\n\n' +
            'Try: "Use the notebook Untitled2.ipynb"\n\n' +
            '**I can help you:**\n' +
            '• Connect to notebooks and manage kernels\n' +
            '• Execute and modify cells\n' +
            '• Analyze code and find patterns\n' +
            '• Debug errors and suggest improvements',
          timestamp: new Date()
        }
      ]);
    }
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) {
      return;
    }

    const userMessage: IChatMessage = {
      role: 'user',
      content: inputValue,
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // Get the current notebook path at the time of sending
      const activeNotebookPath = getCurrentNotebookPath();
      const response = await client.sendMessage(inputValue, activeNotebookPath);

      // Collapse multiple consecutive newlines to reduce blank lines
      const cleanedResponse = response.replace(/\n\n+/g, '\n\n');

      const assistantMessage: IChatMessage = {
        role: 'assistant',
        content: cleanedResponse,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: IChatMessage = {
        role: 'assistant',
        content: `Error: ${error instanceof Error ? error.message : 'Unknown error'}`,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const formatTimestamp = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="tk-chat-panel">
      {/* Connection status */}
      <div className="tk-connection-status">
        <div className={`tk-status-item ${isConnected ? 'connected' : 'disconnected'}`}>
          <span className="tk-status-indicator"></span>
          <span className="tk-status-label">MCP Server</span>
        </div>
        <div className={`tk-status-item ${isModelConnected ? 'connected' : 'disconnected'}`}>
          <span className="tk-status-indicator"></span>
          <span className="tk-status-label">AI Model</span>
        </div>
      </div>

      {/* Messages area */}
      <div className="tk-messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`tk-message tk-message-${msg.role}`}>
            <div className="tk-message-header">
              <span className="tk-message-role">
                {msg.role === 'user' ? '👤 You' : '🤖 Thinky'}
              </span>
              <span className="tk-message-time">
                {formatTimestamp(msg.timestamp)}
              </span>
            </div>
            <div
              className="tk-message-content"
              dangerouslySetInnerHTML={{ __html: renderMarkdown(msg.content) }}
            />
          </div>
        ))}
        {isLoading && (
          <div className="tk-message tk-message-assistant">
            <div className="tk-message-header">
              <span className="tk-message-role">🤖 Thinky</span>
            </div>
            <div className="tk-message-content tk-loading">
              <span className="tk-loading-dot"></span>
              <span className="tk-loading-dot"></span>
              <span className="tk-loading-dot"></span>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input area */}
      <div className="tk-input-area">
        <textarea
          className="tk-input"
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyPress={handleKeyPress}
          placeholder="Ask Thinky about your notebooks..."
          disabled={!isConnected || !isModelConnected || isLoading}
          rows={3}
        />
        <button
          className="tk-send-button"
          onClick={handleSend}
          disabled={!isConnected || !isModelConnected || isLoading || !inputValue.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
};

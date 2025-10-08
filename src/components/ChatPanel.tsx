// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Chat Panel React component
 */

import React, { useState, useEffect, useRef } from 'react';
import { MCPClient, IChatMessage } from '../api';

/**
 * Props for ChatPanel component
 */
export interface IChatPanelProps {
  client: MCPClient;
}

/**
 * Chat Panel Component
 * Provides a chat interface for interacting with Claude AI
 */
export const ChatPanel: React.FC<IChatPanelProps> = ({ client }) => {
  const [messages, setMessages] = useState<IChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
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
    const healthy = await client.checkHealth();
    setIsConnected(healthy);

    if (!healthy) {
      setMessages([
        {
          role: 'assistant',
          content:
            '⚠️ Cannot connect to MCP server. Please make sure:\n' +
            '1. tk-ai-extension is properly installed\n' +
            '2. JupyterLab server is running\n' +
            '3. API key is configured (ANTHROPIC_API_KEY)',
          timestamp: new Date()
        }
      ]);
    } else {
      setMessages([
        {
          role: 'assistant',
          content:
            'Hello! I\'m Claude, integrated with your Jupyter notebooks.\n\n' +
            'I can help you with:\n' +
            '• Listing and analyzing notebooks\n' +
            '• Reading and explaining code cells\n' +
            '• Finding specific code patterns\n' +
            '• Checking kernel status\n\n' +
            'Try asking: "List all notebooks in the current directory"',
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
      const response = await client.sendMessage(inputValue);

      const assistantMessage: IChatMessage = {
        role: 'assistant',
        content: response,
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
      <div className={`tk-connection-status ${isConnected ? 'connected' : 'disconnected'}`}>
        <span className="tk-status-indicator"></span>
        {isConnected ? 'Connected to MCP Server' : 'Disconnected'}
      </div>

      {/* Messages area */}
      <div className="tk-messages">
        {messages.map((msg, idx) => (
          <div key={idx} className={`tk-message tk-message-${msg.role}`}>
            <div className="tk-message-header">
              <span className="tk-message-role">
                {msg.role === 'user' ? '👤 You' : '🤖 Claude'}
              </span>
              <span className="tk-message-time">
                {formatTimestamp(msg.timestamp)}
              </span>
            </div>
            <div className="tk-message-content">{msg.content}</div>
          </div>
        ))}
        {isLoading && (
          <div className="tk-message tk-message-assistant">
            <div className="tk-message-header">
              <span className="tk-message-role">🤖 Claude</span>
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
          placeholder="Ask Claude about your notebooks..."
          disabled={!isConnected || isLoading}
          rows={3}
        />
        <button
          className="tk-send-button"
          onClick={handleSend}
          disabled={!isConnected || isLoading || !inputValue.trim()}
        >
          Send
        </button>
      </div>
    </div>
  );
};

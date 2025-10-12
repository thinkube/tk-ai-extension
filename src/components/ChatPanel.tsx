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
export const ChatPanel = React.forwardRef<any, IChatPanelProps>(({ client, notebookPath, labShell }, ref) => {
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

  /**
   * Get cell selection info from the currently active notebook
   */
  const getCellSelectionInfo = (): { activeCellIndex: number; selectedCellIndices: number[] } | null => {
    if (!labShell) {
      return null;
    }

    const current = labShell.currentWidget;
    if (!current) {
      return null;
    }

    // Check if it's a notebook panel
    const notebookPanel = current as any;
    if (!notebookPanel.content?.activeCellIndex) {
      return null;
    }

    try {
      const activeCellIndex = notebookPanel.content.activeCellIndex;
      const selectedCells = notebookPanel.content.selectedCells || [];

      // Get indices of all selected cells
      const selectedCellIndices: number[] = [];
      const widgets = notebookPanel.content.widgets || [];

      for (let i = 0; i < widgets.length; i++) {
        const widget = widgets[i];
        if (selectedCells.includes(widget)) {
          selectedCellIndices.push(i);
        }
      }

      return { activeCellIndex, selectedCellIndices };
    } catch (error) {
      console.warn('Failed to get cell selection info:', error);
      return null;
    }
  };
  const [messages, setMessages] = useState<IChatMessage[]>([]);
  const [inputValue, setInputValue] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isConnected, setIsConnected] = useState(false);
  const [isModelConnected, setIsModelConnected] = useState(false);
  const [connectedNotebook, setConnectedNotebook] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [isExecutingInBackground, setIsExecutingInBackground] = useState(false);
  const [executingCellIndex, setExecutingCellIndex] = useState<number | null>(null);
  const [activeExecutionId, setActiveExecutionId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingIntervalRef = useRef<number | null>(null);

  // Expose methods via ref
  React.useImperativeHandle(ref, () => ({
    restoreConversation: (notebookName: string, restoredMessages: IChatMessage[]) => {
      console.log(`Restoring conversation for ${notebookName}: ${restoredMessages.length} messages`);
      setIsRestoring(true);
      setConnectedNotebook(notebookName);
      setMessages(restoredMessages);
      setTimeout(() => setIsRestoring(false), 500); // Brief restore indicator
    },
    setBackgroundExecution: (isExecuting: boolean, cellIndex?: number) => {
      console.log(`Background execution ${isExecuting ? 'started' : 'ended'}${cellIndex !== undefined ? ` at cell ${cellIndex}` : ''}`);
      setIsExecutingInBackground(isExecuting);
      setExecutingCellIndex(isExecuting && cellIndex !== undefined ? cellIndex : null);
    },
    startExecutionPolling: (executionId: string, cellIndex: number) => {
      startExecutionPolling(executionId, cellIndex);
    }
  }));

  // Check connection on mount
  useEffect(() => {
    checkConnection();
  }, []);

  // Load notebook history when notebook path is available
  useEffect(() => {
    if (notebookPath && isConnected && isModelConnected) {
      loadNotebookHistory();
    }
  }, [notebookPath, isConnected, isModelConnected]);

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
            '2. Thinkube\'s AI Lab server is running\n' +
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
    }
    // Don't set welcome message here - wait for loadNotebookHistory if notebook path exists
  };

  const loadNotebookHistory = async () => {
    if (!notebookPath) return;

    try {
      console.log(`Loading history for notebook: ${notebookPath}`);
      const result = await client.connectNotebook(notebookPath);

      // Set notebook name so navbar appears
      setConnectedNotebook(result.notebook_name);

      // Restore conversation if history exists
      if (result.messages && result.messages.length > 0) {
        console.log(`Restored ${result.messages.length} messages`);
        setMessages(result.messages);
      } else {
        // No history - show welcome message
        console.log('No history found, showing welcome message');
        showWelcomeMessage(result.notebook_name);
      }
    } catch (error) {
      console.error('Failed to load notebook history:', error);
      // Show welcome message even if loading fails
      const notebookName = notebookPath.split('/').pop()?.replace('.ipynb', '') || 'notebook';
      showWelcomeMessage(notebookName);
    }
  };

  const showWelcomeMessage = (notebookName: string) => {
    setMessages([
      {
        role: 'assistant',
        content:
          `Hello! I'm Thinky, your assistant for **Thinkube's AI Lab**.\n\n` +
          `I'm connected to **${notebookName}** and ready to help!\n\n` +
          '**I can help you:**\n' +
          '• Insert and modify cells in your notebook\n' +
          '• Execute code and analyze results\n' +
          '• Debug errors and suggest improvements\n' +
          '• Answer questions about your code and data\n\n' +
          '**Try asking:**\n' +
          '• "Add a cell that imports pandas and loads data.csv"\n' +
          '• "Explain what cell 3 does"\n' +
          '• "Find all cells that use matplotlib"\n' +
          '• "Create a visualization of the results"',
        timestamp: new Date()
      }
    ]);
  };

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  /**
   * Extract execution_id from Claude's response if present
   */
  const extractExecutionId = (text: string): { executionId: string; cellIndex: number } | null => {
    // Look for patterns like "execution_id": "uuid" or execution_id to poll results
    const executionIdMatch = text.match(/execution_id['":\s]+([a-f0-9-]{36})/i);
    const cellIndexMatch = text.match(/cell[_\s]+(\d+)|index[_\s]+(\d+)/i);

    if (executionIdMatch) {
      const cellIndex = cellIndexMatch ? parseInt(cellIndexMatch[1] || cellIndexMatch[2]) : -1;
      return {
        executionId: executionIdMatch[1],
        cellIndex: cellIndex
      };
    }
    return null;
  };

  /**
   * Start polling for async execution status
   */
  const startExecutionPolling = async (executionId: string, cellIndex: number) => {
    console.log(`Starting polling for execution ${executionId}, cell ${cellIndex}`);

    // Clear any existing polling
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current);
    }

    // Set UI indicator
    setActiveExecutionId(executionId);
    setIsExecutingInBackground(true);
    setExecutingCellIndex(cellIndex);

    // Poll every 2 seconds
    const pollInterval = window.setInterval(async () => {
      try {
        const status = await client.checkExecutionStatus(executionId);

        if (status.status === 'completed' || status.status === 'error') {
          // Execution finished
          console.log(`Execution ${executionId} finished with status: ${status.status}`);
          clearInterval(pollInterval);
          pollingIntervalRef.current = null;
          setIsExecutingInBackground(false);
          setExecutingCellIndex(null);
          setActiveExecutionId(null);
        } else {
          // Still running - update cell index if available
          if (status.cell_index !== undefined) {
            setExecutingCellIndex(status.cell_index);
          }
        }
      } catch (error) {
        console.error('Error polling execution status:', error);
        // On error, stop polling
        clearInterval(pollInterval);
        pollingIntervalRef.current = null;
        setIsExecutingInBackground(false);
        setExecutingCellIndex(null);
        setActiveExecutionId(null);
      }
    }, 2000);

    pollingIntervalRef.current = pollInterval;
  };

  // Cleanup polling on unmount
  React.useEffect(() => {
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current);
      }
    };
  }, []);

  const handleSend = async () => {
    if (!inputValue.trim() || isLoading) {
      return;
    }

    // Get cell selection info
    const selectionInfo = getCellSelectionInfo();
    let enhancedMessage = inputValue;

    // Automatically prepend cell selection context if available
    if (selectionInfo) {
      const { activeCellIndex, selectedCellIndices } = selectionInfo;

      // Build context string
      let contextPrefix = '';

      if (selectedCellIndices.length > 1) {
        // Multiple cells selected
        contextPrefix = `[Context: Multiple cells selected - indices ${selectedCellIndices.join(', ')}. Active cell is index ${activeCellIndex}]\n\n`;
      } else if (selectedCellIndices.length === 1) {
        // Single cell selected
        contextPrefix = `[Context: Cell at index ${activeCellIndex} is selected]\n\n`;
      } else {
        // No explicit selection, but there's an active cell
        contextPrefix = `[Context: Active cell is at index ${activeCellIndex}]\n\n`;
      }

      enhancedMessage = contextPrefix + inputValue;
    }

    const userMessage: IChatMessage = {
      role: 'user',
      content: inputValue,  // Show original message to user
      timestamp: new Date()
    };

    setMessages(prev => [...prev, userMessage]);
    setInputValue('');
    setIsLoading(true);

    try {
      // Get the current notebook path at the time of sending
      const activeNotebookPath = getCurrentNotebookPath();
      // Send enhanced message with context to Claude
      const response = await client.sendMessage(enhancedMessage, activeNotebookPath);

      // Replace double newlines with single newlines and trim trailing newlines
      const cleanedResponse = response.replace(/\n\n+/g, '\n').replace(/\n+$/, '');

      const assistantMessage: IChatMessage = {
        role: 'assistant',
        content: cleanedResponse,
        timestamp: new Date()
      };

      setMessages(prev => [...prev, assistantMessage]);

      // Check if response contains an execution_id (async execution started)
      const executionInfo = extractExecutionId(cleanedResponse);
      if (executionInfo) {
        console.log('Detected async execution in response:', executionInfo);
        startExecutionPolling(executionInfo.executionId, executionInfo.cellIndex);
      }
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

  const handleClearHistory = async () => {
    if (!notebookPath) return;

    const confirmed = window.confirm(
      'Clear conversation history?\n\nThis will delete all messages from this notebook and start a fresh conversation with Thinky.'
    );

    if (!confirmed) return;

    try {
      await client.clearConversation(notebookPath);

      // Clear messages and show welcome message
      const notebookName = connectedNotebook || notebookPath.split('/').pop()?.replace('.ipynb', '') || 'notebook';
      showWelcomeMessage(notebookName);
    } catch (error) {
      console.error('Failed to clear conversation:', error);
      alert(`Failed to clear conversation: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  };

  const formatTimestamp = (date: Date) => {
    return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  };

  return (
    <div className="tk-chat-panel">
      {/* Notebook name display */}
      {connectedNotebook && (
        <div className="tk-notebook-navbar">
          <div className="tk-notebook-info">
            <span className="tk-notebook-icon">📓</span>
            <span className="tk-notebook-name">{connectedNotebook}</span>
            {isRestoring && <span className="tk-notebook-restoring">(restoring...)</span>}
            {isExecutingInBackground && (
              <span className="tk-notebook-executing">
                ⚙️ Executing cell {executingCellIndex !== null ? executingCellIndex : '...'}
              </span>
            )}
          </div>
          <button
            className="tk-clear-history-button"
            onClick={handleClearHistory}
            disabled={isLoading || messages.length === 0}
            title="Clear conversation history"
          >
            🗑️
          </button>
        </div>
      )}

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
});

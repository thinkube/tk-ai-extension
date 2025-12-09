// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Chat Panel React component
 */

import React, { useState, useEffect, useRef } from 'react';
import { JupyterFrontEnd } from '@jupyterlab/application';
import { MCPClient, IChatMessage, IStreamingCallbacks, IToolExecution } from '../api';
import { NotebookTools, IExecutionCallbacks } from '../notebook-tools';
import { renderMarkdown } from '../utils/markdown';
import {
  FileText,
  Download,
  Wrench,
  Trash2,
  X,
  Loader2,
  CheckCircle2,
  XCircle,
  Clock,
  ChevronDown,
  ChevronUp
} from 'lucide-react';

/**
 * Props for ChatPanel component
 */
export interface IChatPanelProps {
  client: MCPClient;
  notebookPath: string | null;
  labShell: JupyterFrontEnd.IShell | null;
  notebookTools: NotebookTools | null;
}

/**
 * Chat Panel Component
 * Provides a chat interface for interacting with Claude AI
 */
export const ChatPanel = React.forwardRef<any, IChatPanelProps>(({ client, notebookPath, labShell, notebookTools }, ref) => {
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
  const [isWebSocketConnected, setIsWebSocketConnected] = useState(false);
  const [connectedNotebook, setConnectedNotebook] = useState<string | null>(null);
  const [isRestoring, setIsRestoring] = useState(false);
  const [isExecutingInBackground, setIsExecutingInBackground] = useState(false);
  const [executingCellIndex, setExecutingCellIndex] = useState<number | null>(null);
  const [streamingContent, setStreamingContent] = useState<string>('');
  const [currentToolCall, setCurrentToolCall] = useState<string | null>(null);
  const [toolExecutions, setToolExecutions] = useState<IToolExecution[]>([]);
  const [showToolPanel, setShowToolPanel] = useState(false);
  const [useStreaming] = useState(true);
  const [executionOutput, setExecutionOutput] = useState<string>('');  // Real-time cell output
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pollingIntervalRef = useRef<number | null>(null);
  const activeExecutionIdRef = useRef<string | null>(null);

  // Undo support - track recent cell changes (for future undo button implementation)
  const [, setUndoStack] = useState<Array<{
    type: 'overwrite' | 'insert' | 'delete';
    cellIndex: number;
    previousContent?: string;
    cellType?: string;
  }>>([]);

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

  /**
   * Execute a cell using frontend NotebookTools with IOPub streaming
   * This enables real-time output including tqdm progress bars
   */
  const executeCellFrontend = async (cellIndex: number): Promise<{
    success: boolean;
    error?: string;
    output?: string;
  }> => {
    if (!notebookTools) {
      console.error('NotebookTools not available for frontend execution');
      return { success: false, error: 'NotebookTools not available' };
    }

    console.log(`[Frontend Execution] Starting cell ${cellIndex} with IOPub streaming`);
    setIsExecutingInBackground(true);
    setExecutingCellIndex(cellIndex);
    setExecutionOutput('');

    let outputBuffer = '';

    const callbacks: IExecutionCallbacks = {
      onStream: (text: string, name: 'stdout' | 'stderr') => {
        console.log(`[IOPub ${name}]`, text);
        outputBuffer += text;
        setExecutionOutput(prev => prev + text);
      },
      onDisplayData: (data: any, metadata: any) => {
        console.log('[IOPub display_data]', data);
        // Handle rich display data (images, HTML, etc.)
        if (data['text/plain']) {
          outputBuffer += data['text/plain'] + '\n';
          setExecutionOutput(prev => prev + data['text/plain'] + '\n');
        }
      },
      onExecuteResult: (data: any, metadata: any, executionCount: number) => {
        console.log(`[IOPub execute_result] [${executionCount}]`, data);
        if (data['text/plain']) {
          outputBuffer += `Out[${executionCount}]: ${data['text/plain']}\n`;
          setExecutionOutput(prev => prev + `Out[${executionCount}]: ${data['text/plain']}\n`);
        }
      },
      onError: (ename: string, evalue: string, traceback: string[]) => {
        console.error(`[IOPub error] ${ename}: ${evalue}`);
        const errorText = `${ename}: ${evalue}\n${traceback.join('\n')}`;
        outputBuffer += errorText;
        setExecutionOutput(prev => prev + errorText);
      },
      onStatus: (status: string) => {
        console.log(`[IOPub status] ${status}`);
      }
    };

    try {
      const result = await notebookTools.executeCell(cellIndex, notebookPath || undefined, callbacks);

      setIsExecutingInBackground(false);
      setExecutingCellIndex(null);

      if (result.success) {
        console.log(`[Frontend Execution] Cell ${cellIndex} completed successfully`);
        return { success: true, output: outputBuffer };
      } else {
        console.error(`[Frontend Execution] Cell ${cellIndex} failed:`, result.error);
        return { success: false, error: result.error, output: outputBuffer };
      }
    } catch (error) {
      setIsExecutingInBackground(false);
      setExecutingCellIndex(null);
      const errorMsg = error instanceof Error ? error.message : 'Unknown error';
      console.error(`[Frontend Execution] Cell ${cellIndex} exception:`, errorMsg);
      return { success: false, error: errorMsg, output: outputBuffer };
    }
  };

  /**
   * Add a cell and optionally execute it using frontend tools
   */
  const addCellFrontend = (
    content: string,
    cellType: 'code' | 'markdown' = 'code',
    position: 'above' | 'below' | 'end' = 'end'
  ): { success: boolean; cellIndex?: number; error?: string } => {
    if (!notebookTools) {
      console.error('NotebookTools not available');
      return { success: false, error: 'NotebookTools not available' };
    }

    const result = notebookTools.addCell(content, cellType, position, notebookPath || undefined);
    console.log(`[Frontend] Added ${cellType} cell:`, result);
    return result;
  };

  /**
   * Update cell content using frontend tools
   */
  const updateCellFrontend = (
    cellIndex: number,
    content: string
  ): { success: boolean; error?: string } => {
    if (!notebookTools) {
      return { success: false, error: 'NotebookTools not available' };
    }

    const result = notebookTools.updateCell(cellIndex, content, notebookPath || undefined);
    console.log(`[Frontend] Updated cell ${cellIndex}:`, result);
    return result;
  };

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
    console.log('Checking for execution_id in response:', text.substring(0, 500));

    // Look for UUID patterns - they might appear as:
    // - "execution_id": "uuid"
    // - execution_id: uuid
    // - with ID `uuid`
    // - execution ID uuid
    const uuidPattern = /([a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12})/i;
    const uuidMatch = text.match(uuidPattern);

    if (uuidMatch) {
      const executionId = uuidMatch[1];
      console.log('Found execution_id:', executionId);

      // Look for cell index near the execution_id
      const cellIndexMatch = text.match(/(?:cell|index)[_\s]+(\d+)/i);
      const cellIndex = cellIndexMatch ? parseInt(cellIndexMatch[1]) : -1;

      console.log('Extracted cellIndex:', cellIndex);

      return {
        executionId: executionId,
        cellIndex: cellIndex
      };
    }

    console.log('No execution_id found in response');
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
    activeExecutionIdRef.current = executionId;
    console.log(`Setting background execution indicator: true, cell index: ${cellIndex}`);
    setIsExecutingInBackground(true);
    setExecutingCellIndex(cellIndex);

    // Poll every 2 seconds
    const pollInterval = window.setInterval(async () => {
      try {
        const status = await client.checkExecutionStatus(executionId);
        console.log(`Polling execution ${executionId}, received status:`, JSON.stringify(status, null, 2));

        if (status.status === 'completed' || status.status === 'error') {
          // Execution finished
          console.log(`Execution ${executionId} finished with status: ${status.status}`);
          clearInterval(pollInterval);
          pollingIntervalRef.current = null;
          activeExecutionIdRef.current = null;
          setIsExecutingInBackground(false);
          setExecutingCellIndex(null);
        } else {
          // Still running - update cell index if available
          console.log(`Execution ${executionId} still running with status: ${status.status}`);
          if (status.cell_index !== undefined) {
            setExecutingCellIndex(status.cell_index);
          }
        }
      } catch (error) {
        console.error('Error polling execution status:', error);
        // On error, stop polling
        clearInterval(pollInterval);
        pollingIntervalRef.current = null;
        activeExecutionIdRef.current = null;
        setIsExecutingInBackground(false);
        setExecutingCellIndex(null);
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

  const handleCancel = () => {
    console.log('Cancelling current request...');
    client.cancelStreaming();
    setIsLoading(false);
    setStreamingContent('');
    setCurrentToolCall(null);
  };

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
    setStreamingContent('');
    setCurrentToolCall(null);

    // Get the current notebook path at the time of sending
    const activeNotebookPath = getCurrentNotebookPath();

    // Use streaming if enabled and notebook path is available
    if (useStreaming && activeNotebookPath) {
      const callbacks: IStreamingCallbacks = {
        onToken: (token: string) => {
          setStreamingContent(prev => prev + token);
        },
        onToolCall: async (name: string, args: any) => {
          console.log('Tool call:', name, args);
          setCurrentToolCall(name);
          // Add to tool executions
          setToolExecutions(prev => [...prev, {
            name,
            args,
            status: 'running',
            startTime: new Date()
          }]);

          // FRONTEND EXECUTION: Intercept execute_cell and run locally with IOPub streaming
          // This enables tqdm progress bars and real-time output
          if (notebookTools && (name === 'execute_cell' || name === 'run_cell')) {
            const cellIndex = args.cell_index ?? args.cellIndex;
            if (cellIndex !== undefined) {
              console.log(`[Frontend Intercept] Executing cell ${cellIndex} locally with IOPub streaming`);
              const execResult = await executeCellFrontend(cellIndex);
              // Note: The backend will also try to execute, but frontend wins for streaming output
              console.log(`[Frontend Intercept] Result:`, execResult);
            }
          }

          // FRONTEND CELL MANIPULATION: Intercept insert_cell and add_cell
          if (notebookTools && (name === 'insert_cell' || name === 'add_cell')) {
            const content = args.content ?? args.source ?? '';
            const cellType = args.cell_type ?? args.cellType ?? 'code';
            const position = args.position ?? 'end';
            console.log(`[Frontend Intercept] Adding ${cellType} cell locally`);
            addCellFrontend(content, cellType, position);
          }

          // FRONTEND: Intercept overwrite_cell / update_cell
          if (notebookTools && (name === 'overwrite_cell' || name === 'overwrite_cell_source' || name === 'update_cell')) {
            const cellIndex = args.cell_index ?? args.cellIndex;
            const content = args.content ?? args.source ?? args.new_source ?? '';
            if (cellIndex !== undefined) {
              console.log(`[Frontend Intercept] Updating cell ${cellIndex} locally`);
              updateCellFrontend(cellIndex, content);
            }
          }

          // FRONTEND: Insert and execute
          if (notebookTools && (name === 'insert_and_execute_cell' || name === 'add_and_run_cell')) {
            const content = args.content ?? args.source ?? '';
            const position = args.position ?? 'below';
            console.log(`[Frontend Intercept] Adding and executing cell locally`);
            const addResult = addCellFrontend(content, 'code', position);
            if (addResult.success && addResult.cellIndex !== undefined) {
              await executeCellFrontend(addResult.cellIndex);
            }
          }
        },
        onToolResult: (name: string, success: boolean, result?: any) => {
          console.log('Tool result:', name, success, result);
          setCurrentToolCall(null);
          // Update tool execution status
          setToolExecutions(prev => prev.map(exec =>
            exec.name === name && exec.status === 'running'
              ? { ...exec, status: success ? 'completed' : 'error', endTime: new Date() }
              : exec
          ));
          // Track cell changes for undo (if the tool modified a cell)
          if (success && result && (name === 'overwrite_cell' || name === 'overwrite_cell_source' || name === 'insert_cell' || name === 'delete_cell')) {
            if (result.previous_content !== undefined || result.can_undo) {
              setUndoStack(prev => [...prev.slice(-9), {
                type: name.replace('_cell', '').replace('_source', '') as 'overwrite' | 'insert' | 'delete',
                cellIndex: result.cell_index,
                previousContent: result.previous_content,
                cellType: result.cell_type
              }]);
            }
            // Trigger markdown re-render if this was a markdown cell
            if (result.cell_type === 'markdown' && result.cell_index !== undefined && labShell) {
              console.log(`[NOTEBOOK CELL] Markdown cell ${result.cell_index} modified via tool result`);
              setTimeout(() => {
                const currentWidget = labShell.currentWidget;
                if (currentWidget && (currentWidget as any).content) {
                  const notebook = (currentWidget as any).content;
                  if (notebook && notebook.widgets && notebook.widgets[result.cell_index]) {
                    const cell = notebook.widgets[result.cell_index];
                    // Force re-render by toggling rendered state
                    if (cell.rendered !== undefined) {
                      console.log(`[NOTEBOOK CELL] Toggling rendered state for cell ${result.cell_index}`);
                      cell.rendered = false;
                      requestAnimationFrame(() => {
                        cell.rendered = true;
                        console.log(`[NOTEBOOK CELL] Cell ${result.cell_index} re-rendered`);
                      });
                    }
                  }
                }
              }, 100); // Small delay to ensure YDoc update is complete
            }
          }
        },
        onConnectionChange: (connected: boolean) => {
          setIsWebSocketConnected(connected);
        },
        onCellUpdated: (cellType: string, cellIndex: number) => {
          // Trigger markdown cell re-rendering
          if (cellType === 'markdown' && labShell) {
            console.log(`[NOTEBOOK CELL] Markdown cell ${cellIndex} updated, triggering re-render`);
            const currentWidget = labShell.currentWidget;
            if (currentWidget && (currentWidget as any).content) {
              const notebook = (currentWidget as any).content;
              if (notebook && notebook.widgets && notebook.widgets[cellIndex]) {
                const cell = notebook.widgets[cellIndex];
                // Force re-render by toggling the rendered state
                // First set to false (edit mode), then back to true (render)
                if (cell.rendered !== undefined) {
                  console.log(`[NOTEBOOK CELL] Toggling rendered state for cell ${cellIndex}`);
                  cell.rendered = false;
                  // Use requestAnimationFrame to ensure the toggle happens in next frame
                  requestAnimationFrame(() => {
                    cell.rendered = true;
                    console.log(`[NOTEBOOK CELL] Cell ${cellIndex} re-rendered`);
                  });
                }
              }
            }
          }
        },
        // FRONTEND DELEGATION: Handle tool requests from backend
        // Backend sends tool_request, frontend executes using NotebookTools, returns result
        onToolRequest: async (requestId: string, toolName: string, args: any): Promise<any> => {
          console.log(`[Frontend Delegation] Received tool_request: ${toolName}`, args);

          if (!notebookTools) {
            console.error('[Frontend Delegation] NotebookTools not available');
            return { success: false, error: 'NotebookTools not available' };
          }

          const nbPath = args.notebook_path || activeNotebookPath || undefined;

          try {
            switch (toolName) {
              case 'list_cells': {
                const result = notebookTools.listCells(nbPath);
                console.log(`[Frontend Delegation] list_cells result:`, result);
                return result;
              }

              case 'read_cell': {
                const cellIndex = args.cell_index ?? args.cellIndex;
                if (cellIndex === undefined) {
                  return { success: false, error: 'cell_index is required' };
                }
                const result = notebookTools.getCellInfo(cellIndex, nbPath);
                console.log(`[Frontend Delegation] read_cell result:`, result);
                return result;
              }

              case 'execute_cell': {
                const cellIndex = args.cell_index ?? args.cellIndex;
                if (cellIndex === undefined) {
                  return { success: false, error: 'cell_index is required' };
                }
                console.log(`[Frontend Delegation] Executing cell ${cellIndex} with IOPub streaming`);
                setIsExecutingInBackground(true);
                setExecutingCellIndex(cellIndex);
                setExecutionOutput('');

                let outputBuffer = '';
                const execCallbacks: IExecutionCallbacks = {
                  onStream: (text, name) => {
                    outputBuffer += text;
                    setExecutionOutput(prev => prev + text);
                  },
                  onDisplayData: (data) => {
                    if (data['text/plain']) {
                      outputBuffer += data['text/plain'] + '\n';
                      setExecutionOutput(prev => prev + data['text/plain'] + '\n');
                    }
                  },
                  onExecuteResult: (data, metadata, execCount) => {
                    if (data['text/plain']) {
                      outputBuffer += `Out[${execCount}]: ${data['text/plain']}\n`;
                    }
                  },
                  onError: (ename, evalue, traceback) => {
                    outputBuffer += `${ename}: ${evalue}\n${traceback.join('\n')}`;
                  }
                };

                const result = await notebookTools.executeCell(cellIndex, nbPath, execCallbacks);
                setIsExecutingInBackground(false);
                setExecutingCellIndex(null);
                console.log(`[Frontend Delegation] execute_cell result:`, result);
                return { ...result, output: outputBuffer };
              }

              case 'insert_cell': {
                const content = args.content ?? args.source ?? '';
                const cellType = args.cell_type ?? 'code';
                const position = args.position ?? 'end';
                const result = notebookTools.addCell(content, cellType, position, nbPath);
                console.log(`[Frontend Delegation] insert_cell result:`, result);
                return result;
              }

              case 'overwrite_cell':
              case 'overwrite_cell_source': {
                const cellIndex = args.cell_index ?? args.cellIndex;
                const content = args.content ?? args.source ?? args.new_source ?? '';
                if (cellIndex === undefined) {
                  return { success: false, error: 'cell_index is required' };
                }
                const result = notebookTools.updateCell(cellIndex, content, nbPath);
                console.log(`[Frontend Delegation] overwrite_cell result:`, result);
                return result;
              }

              case 'delete_cell': {
                const cellIndex = args.cell_index ?? args.cellIndex;
                if (cellIndex === undefined) {
                  return { success: false, error: 'cell_index is required' };
                }
                const result = notebookTools.deleteCell(cellIndex, nbPath);
                console.log(`[Frontend Delegation] delete_cell result:`, result);
                return result;
              }

              case 'move_cell': {
                const fromIndex = args.from_index ?? args.fromIndex;
                const toIndex = args.to_index ?? args.toIndex;
                if (fromIndex === undefined || toIndex === undefined) {
                  return { success: false, error: 'from_index and to_index are required' };
                }
                const result = notebookTools.moveCell(fromIndex, toIndex, nbPath);
                console.log(`[Frontend Delegation] move_cell result:`, result);
                return result;
              }

              case 'insert_and_execute_cell': {
                const content = args.content ?? args.source ?? '';
                const position = args.position ?? 'below';
                const result = await notebookTools.insertAndExecute(content, position, nbPath);
                console.log(`[Frontend Delegation] insert_and_execute_cell result:`, result);
                return result;
              }

              case 'execute_all_cells': {
                const result = await notebookTools.executeAllCells(nbPath);
                console.log(`[Frontend Delegation] execute_all_cells result:`, result);
                return result;
              }

              default:
                console.warn(`[Frontend Delegation] Unknown tool: ${toolName}`);
                return { success: false, error: `Unknown tool: ${toolName}` };
            }
          } catch (error) {
            const errorMsg = error instanceof Error ? error.message : 'Unknown error';
            console.error(`[Frontend Delegation] Error executing ${toolName}:`, errorMsg);
            return { success: false, error: errorMsg };
          }
        },
        onDone: (fullResponse: string) => {
          const assistantMessage: IChatMessage = {
            role: 'assistant',
            content: fullResponse,
            timestamp: new Date()
          };
          setMessages(prev => [...prev, assistantMessage]);
          setStreamingContent('');
          setIsLoading(false);
          // Keep tool executions for profiling - user can clear manually via panel

          // Check for async execution
          const executionInfo = extractExecutionId(fullResponse);
          if (executionInfo) {
            console.log('Detected async execution:', executionInfo);
            startExecutionPolling(executionInfo.executionId, executionInfo.cellIndex);
          }
        },
        onError: (error: string) => {
          const errorMessage: IChatMessage = {
            role: 'assistant',
            content: `Error: ${error}`,
            timestamp: new Date()
          };
          setMessages(prev => [...prev, errorMessage]);
          setStreamingContent('');
          setIsLoading(false);
        },
        onCancelled: () => {
          // Add partial response if any
          if (streamingContent) {
            const partialMessage: IChatMessage = {
              role: 'assistant',
              content: streamingContent + '\n\n*[Response cancelled]*',
              timestamp: new Date()
            };
            setMessages(prev => [...prev, partialMessage]);
          }
          setStreamingContent('');
          setIsLoading(false);
        }
      };

      client.sendMessageStreaming(enhancedMessage, activeNotebookPath, callbacks);
    } else {
      // Fallback to non-streaming
      try {
        const response = await client.sendMessage(enhancedMessage, activeNotebookPath);

        const assistantMessage: IChatMessage = {
          role: 'assistant',
          content: response,
          timestamp: new Date()
        };

        setMessages(prev => [...prev, assistantMessage]);

        const executionInfo = extractExecutionId(response);
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

  /**
   * Export conversation to markdown file
   */
  const handleExportConversation = () => {
    if (messages.length === 0) return;
    const notebookName = connectedNotebook || 'conversation';
    client.downloadConversation(messages, notebookName);
  };

  /**
   * Format tool name for display
   */
  const formatToolName = (name: string): string => {
    return name
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase());
  };

  /**
   * Get tool status icon component
   */
  const getToolStatusIcon = (status: 'running' | 'completed' | 'error') => {
    switch (status) {
      case 'running':
        return <Loader2 size={14} className="tk-tool-icon tk-tool-icon-running" />;
      case 'completed':
        return <CheckCircle2 size={14} className="tk-tool-icon tk-tool-icon-completed" />;
      case 'error':
        return <XCircle size={14} className="tk-tool-icon tk-tool-icon-error" />;
    }
  };

  /**
   * Format duration for display
   */
  const formatDuration = (startTime: Date, endTime?: Date): string => {
    const end = endTime || new Date();
    const ms = end.getTime() - startTime.getTime();
    if (ms < 1000) {
      return `${ms}ms`;
    } else if (ms < 60000) {
      return `${(ms / 1000).toFixed(1)}s`;
    } else {
      const mins = Math.floor(ms / 60000);
      const secs = ((ms % 60000) / 1000).toFixed(0);
      return `${mins}m ${secs}s`;
    }
  };

  // State to track expanded tool details
  const [expandedTools, setExpandedTools] = useState<Set<number>>(new Set());

  const toggleToolExpanded = (idx: number) => {
    setExpandedTools(prev => {
      const next = new Set(prev);
      if (next.has(idx)) {
        next.delete(idx);
      } else {
        next.add(idx);
      }
      return next;
    });
  };

  // Debug logging for indicator state
  console.log(`ChatPanel render - isExecutingInBackground: ${isExecutingInBackground}, cellIndex: ${executingCellIndex}`);

  return (
    <div className="tk-chat-panel">
      {/* Notebook name display */}
      {connectedNotebook && (
        <div className="tk-notebook-navbar">
          <div className="tk-notebook-info">
            <FileText size={16} className="tk-notebook-icon" />
            <span className="tk-notebook-name">{connectedNotebook}</span>
            {isRestoring && <span className="tk-notebook-restoring">(restoring...)</span>}
            {isExecutingInBackground && (
              <span className="tk-notebook-executing">
                <Loader2 size={14} className="tk-spin" />
                <span>Cell {executingCellIndex !== null ? executingCellIndex : '...'}</span>
              </span>
            )}
          </div>
          <div className="tk-navbar-actions">
            <button
              className="tk-navbar-button"
              onClick={handleExportConversation}
              disabled={messages.length === 0}
              title="Export conversation to markdown"
            >
              <Download size={16} />
            </button>
            <button
              className={`tk-navbar-button ${showToolPanel ? 'tk-navbar-button-active' : ''}`}
              onClick={() => setShowToolPanel(!showToolPanel)}
              title={showToolPanel ? 'Hide tool activity' : 'Show tool activity'}
            >
              <Wrench size={16} />
              {toolExecutions.length > 0 && (
                <span className="tk-tool-badge">{toolExecutions.length}</span>
              )}
            </button>
            <button
              className="tk-navbar-button tk-clear-button"
              onClick={handleClearHistory}
              disabled={isLoading || messages.length === 0}
              title="Clear conversation history"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      )}

      {/* Connection status */}
      <div className="tk-connection-status">
        <div className={`tk-status-item ${isConnected ? 'connected' : 'disconnected'}`}>
          <span className="tk-status-indicator"></span>
          <span className="tk-status-label">MCP</span>
        </div>
        <div className={`tk-status-item ${isModelConnected ? 'connected' : 'disconnected'}`}>
          <span className="tk-status-indicator"></span>
          <span className="tk-status-label">AI</span>
        </div>
        <div className={`tk-status-item ${isWebSocketConnected ? 'connected' : 'disconnected'}`}>
          <span className="tk-status-indicator"></span>
          <span className="tk-status-label">Stream</span>
        </div>
      </div>

      {/* Tool activity panel */}
      {showToolPanel && (
        <div className="tk-tool-panel">
          <div className="tk-tool-panel-header">
            <div className="tk-tool-panel-title">
              <Wrench size={14} />
              <span>Tool Activity</span>
              {toolExecutions.length > 0 && (
                <span className="tk-tool-count">({toolExecutions.length})</span>
              )}
            </div>
            <div className="tk-tool-panel-actions">
              {toolExecutions.length > 0 && (
                <button
                  className="tk-tool-panel-clear"
                  onClick={() => setToolExecutions([])}
                  title="Clear history"
                >
                  <Trash2 size={12} />
                </button>
              )}
              <button
                className="tk-tool-panel-close"
                onClick={() => setShowToolPanel(false)}
                title="Close panel"
              >
                <X size={14} />
              </button>
            </div>
          </div>
          <div className="tk-tool-list">
            {toolExecutions.length === 0 ? (
              <div className="tk-tool-empty">
                <Wrench size={24} className="tk-tool-empty-icon" />
                <span>No tool activity yet</span>
              </div>
            ) : (
              toolExecutions.slice().reverse().map((exec, idx) => {
                const realIdx = toolExecutions.length - 1 - idx;
                const isExpanded = expandedTools.has(realIdx);
                return (
                  <div
                    key={realIdx}
                    className={`tk-tool-item tk-tool-${exec.status}`}
                    onClick={() => toggleToolExpanded(realIdx)}
                  >
                    <div className="tk-tool-item-header">
                      <span className="tk-tool-status">{getToolStatusIcon(exec.status)}</span>
                      <span className="tk-tool-name">{formatToolName(exec.name)}</span>
                      <span className="tk-tool-time">
                        <Clock size={10} />
                        {exec.startTime.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </span>
                      <span className="tk-tool-duration">
                        {formatDuration(exec.startTime, exec.endTime)}
                      </span>
                      <span className="tk-tool-expand">
                        {isExpanded ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
                      </span>
                    </div>
                    {isExpanded && exec.args && Object.keys(exec.args).length > 0 && (
                      <div className="tk-tool-item-details">
                        <div className="tk-tool-args">
                          {Object.entries(exec.args).map(([key, value]) => (
                            <div key={key} className="tk-tool-arg">
                              <span className="tk-tool-arg-key">{key}:</span>
                              <span className="tk-tool-arg-value">
                                {typeof value === 'string' && value.length > 100
                                  ? value.substring(0, 100) + '...'
                                  : String(value)}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>
      )}

      {/* Real-time execution output panel (for tqdm, progress bars, etc.) */}
      {isExecutingInBackground && executionOutput && (
        <div className="tk-execution-output">
          <div className="tk-execution-header">
            <span>⚡ Cell {executingCellIndex} Output</span>
          </div>
          <pre className="tk-execution-content">{executionOutput}</pre>
        </div>
      )}

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
          <div className="tk-message tk-message-assistant tk-message-streaming">
            <div className="tk-message-header">
              <span className="tk-message-role">🤖 Thinky</span>
              {currentToolCall && (
                <span className="tk-tool-indicator">⚙️ {currentToolCall}</span>
              )}
            </div>
            {streamingContent ? (
              <div
                className="tk-message-content"
                dangerouslySetInnerHTML={{ __html: renderMarkdown(streamingContent) }}
              />
            ) : (
              <div className="tk-message-content tk-loading">
                <span className="tk-loading-dot"></span>
                <span className="tk-loading-dot"></span>
                <span className="tk-loading-dot"></span>
              </div>
            )}
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
        <div className="tk-button-group">
          {isLoading ? (
            <button
              className="tk-cancel-button"
              onClick={handleCancel}
              title="Cancel current request"
            >
              ⏹ Stop
            </button>
          ) : (
            <button
              className="tk-send-button"
              onClick={handleSend}
              disabled={!isConnected || !isModelConnected || !inputValue.trim()}
            >
              Send
            </button>
          )}
        </div>
      </div>
    </div>
  );
});

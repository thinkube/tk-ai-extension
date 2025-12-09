// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Chat Widget using Lumino
 */

import { ReactWidget } from '@jupyterlab/apputils';
import { JupyterFrontEnd } from '@jupyterlab/application';
import React from 'react';
import { MCPClient } from './api';
import { NotebookTools } from './notebook-tools';
import { ChatPanel } from './components/ChatPanel';

/**
 * A widget that hosts the chat UI
 */
export class ChatWidget extends ReactWidget {
  private client: MCPClient;
  private labShell: JupyterFrontEnd.IShell | null;
  private notebookTools: NotebookTools | null;
  private currentNotebookPath: string | null = null;
  private chatPanelRef: React.RefObject<any>;

  constructor(
    labShell: JupyterFrontEnd.IShell | null = null,
    initialNotebookPath: string | null = null,
    notebookTools: NotebookTools | null = null
  ) {
    super();
    this.id = 'tk-ai-chat';
    this.title.label = 'tk-ai Chat';
    this.title.closable = true;
    this.addClass('tk-chat-widget');

    this.client = new MCPClient();
    this.labShell = labShell;
    this.notebookTools = notebookTools;
    this.currentNotebookPath = initialNotebookPath;
    this.chatPanelRef = React.createRef();

    // Connect to notebook if initial path provided
    if (initialNotebookPath) {
      this.updateNotebookContext(initialNotebookPath);
    }
  }

  /**
   * Update the notebook context (connect to new notebook and load conversation)
   */
  async updateNotebookContext(notebookPath: string): Promise<void> {
    if (this.currentNotebookPath === notebookPath) {
      console.log(`Already connected to ${notebookPath}`);
      return;
    }

    console.log(`Switching notebook context: ${this.currentNotebookPath} → ${notebookPath}`);
    this.currentNotebookPath = notebookPath;

    try {
      // Connect to notebook and load conversation history
      const result = await this.client.connectNotebook(notebookPath);
      console.log(`Connected to ${result.notebook_name}, loaded ${result.messages.length} messages`);

      // Update the ChatPanel with new context and messages
      this.update();

      // Trigger conversation restore in ChatPanel
      if (this.chatPanelRef.current && this.chatPanelRef.current.restoreConversation) {
        this.chatPanelRef.current.restoreConversation(
          result.notebook_name,
          result.messages
        );
      }
    } catch (error) {
      console.error('Failed to update notebook context:', error);
    }
  }

  /**
   * Get the current notebook path if one is open
   */
  private getCurrentNotebookPath(): string | null {
    if (!this.labShell) {
      return null;
    }

    const current = this.labShell.currentWidget;
    if (!current) {
      return null;
    }

    // Check if the current widget is a notebook
    const context = (current as any).context;
    if (context && context.path && context.path.endsWith('.ipynb')) {
      return context.path;
    }

    return null;
  }

  render(): JSX.Element {
    const notebookPath = this.currentNotebookPath || this.getCurrentNotebookPath();
    return (
      <ChatPanel
        ref={this.chatPanelRef}
        client={this.client}
        notebookPath={notebookPath}
        labShell={this.labShell}
        notebookTools={this.notebookTools}
      />
    );
  }
}

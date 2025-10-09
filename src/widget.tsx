// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Chat Widget using Lumino
 */

import { ReactWidget } from '@jupyterlab/apputils';
import { JupyterFrontEnd } from '@jupyterlab/application';
import React from 'react';
import { MCPClient } from './api';
import { ChatPanel } from './components/ChatPanel';

/**
 * A widget that hosts the chat UI
 */
export class ChatWidget extends ReactWidget {
  private client: MCPClient;
  private labShell: JupyterFrontEnd.IShell | null;

  constructor(labShell: JupyterFrontEnd.IShell | null = null) {
    super();
    this.id = 'tk-ai-chat';
    this.title.label = 'tk-ai Chat';
    this.title.closable = true;
    this.addClass('tk-chat-widget');

    this.client = new MCPClient();
    this.labShell = labShell;

    // Listen to shell changes to update notebook path
    if (this.labShell) {
      this.labShell.currentChanged?.connect(() => {
        this.update();
      });
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
    const notebookPath = this.getCurrentNotebookPath();
    return <ChatPanel client={this.client} notebookPath={notebookPath} labShell={this.labShell} />;
  }
}

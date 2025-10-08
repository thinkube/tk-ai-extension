// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Chat Widget using Lumino
 */

import { ReactWidget } from '@jupyterlab/apputils';
import React from 'react';
import { MCPClient } from './api';
import { ChatPanel } from './components/ChatPanel';

/**
 * A widget that hosts the chat UI
 */
export class ChatWidget extends ReactWidget {
  private client: MCPClient;

  constructor() {
    super();
    this.id = 'tk-ai-chat';
    this.title.label = 'tk-ai Chat';
    this.title.closable = true;
    this.addClass('tk-chat-widget');

    this.client = new MCPClient();
  }

  render(): JSX.Element {
    return <ChatPanel client={this.client} />;
  }
}

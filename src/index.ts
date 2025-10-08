// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * JupyterLab extension for tk-ai
 */

import {
  JupyterFrontEnd,
  JupyterFrontEndPlugin
} from '@jupyterlab/application';

import { ISettingRegistry } from '@jupyterlab/settingregistry';
import { ICommandPalette } from '@jupyterlab/apputils';
import { ILauncher } from '@jupyterlab/launcher';

import { ChatWidget } from './widget';

/**
 * The command IDs
 */
const CommandIDs = {
  openChat: 'tk-ai:open-chat'
};

/**
 * Initialization data for the tk-ai-extension extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'tk-ai-extension:plugin',
  description: 'AI assistant extension for tk-ai lab (Thinkube JupyterHub)',
  autoStart: true,
  optional: [ISettingRegistry, ICommandPalette, ILauncher],
  activate: (
    app: JupyterFrontEnd,
    settingRegistry: ISettingRegistry | null,
    palette: ICommandPalette | null,
    launcher: ILauncher | null
  ) => {
    console.log('JupyterLab extension tk-ai-extension is activated!');

    // Create a single widget instance
    let widget: ChatWidget;

    // Command to open chat
    app.commands.addCommand(CommandIDs.openChat, {
      label: 'Open tk-ai Chat',
      caption: 'Open the tk-ai chat interface',
      execute: () => {
        if (!widget || widget.isDisposed) {
          widget = new ChatWidget();
          widget.id = 'tk-ai-chat';
          widget.title.label = 'tk-ai Chat';
          widget.title.closable = true;
        }

        if (!widget.isAttached) {
          app.shell.add(widget, 'right', { rank: 500 });
        }

        app.shell.activateById(widget.id);
      }
    });

    // Add to command palette
    if (palette) {
      palette.addItem({
        command: CommandIDs.openChat,
        category: 'tk-ai'
      });
    }

    // Add to launcher
    if (launcher) {
      launcher.add({
        command: CommandIDs.openChat,
        category: 'tk-ai',
        rank: 0
      });
    }

    // Load settings if available
    if (settingRegistry) {
      settingRegistry
        .load(plugin.id)
        .then(settings => {
          console.log('tk-ai-extension settings loaded:', settings.composite);
        })
        .catch(reason => {
          console.error('Failed to load settings for tk-ai-extension.', reason);
        });
    }

    console.log('tk-ai-extension: Chat UI registered successfully');
  }
};

export default plugin;

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
import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { DocumentRegistry } from '@jupyterlab/docregistry';
import { IDisposable } from '@lumino/disposable';
import { ToolbarButton } from '@jupyterlab/apputils';

import { ChatWidget } from './widget';
import { MCPClient } from './api';

/**
 * The command IDs
 */
const CommandIDs = {
  openChat: 'tk-ai:open-chat'
};

/**
 * Shared widget reference holder
 */
class WidgetRef {
  widget: ChatWidget | null = null;
}

/**
 * Toolbar button extension for notebooks
 */
class ThinkyButtonExtension
  implements DocumentRegistry.IWidgetExtension<NotebookPanel, DocumentRegistry.IModel>
{
  constructor(private app: JupyterFrontEnd, private widgetRef: WidgetRef) {}

  createNew(
    panel: NotebookPanel,
    context: DocumentRegistry.IContext<DocumentRegistry.IModel>
  ): IDisposable {
    const button = new ToolbarButton({
      label: '🤖 Thinky',
      onClick: async () => {
        const notebookPath = context.path;
        console.log(`Thinky button clicked for: ${notebookPath}`);

        // Open or focus Thinky widget
        if (!this.widgetRef.widget || this.widgetRef.widget.isDisposed) {
          this.widgetRef.widget = new ChatWidget(this.app.shell, notebookPath);
          this.widgetRef.widget.id = 'tk-ai-chat';
          this.widgetRef.widget.title.label = 'tk-ai Chat';
          this.widgetRef.widget.title.closable = true;
        } else {
          // Update context for existing widget
          await this.widgetRef.widget.updateNotebookContext(notebookPath);
        }

        if (!this.widgetRef.widget.isAttached) {
          this.app.shell.add(this.widgetRef.widget, 'right', { rank: 500 });
        }

        this.app.shell.activateById(this.widgetRef.widget.id);
      },
      tooltip: 'Open Thinky AI Assistant for this notebook'
    });

    panel.toolbar.insertAfter('cellType', 'thinky-button', button);
    return button;
  }
}

/**
 * Initialization data for the tk-ai-extension extension.
 */
const plugin: JupyterFrontEndPlugin<void> = {
  id: 'tk-ai-extension:plugin',
  description: 'AI assistant extension for tk-ai lab (Thinkube JupyterHub)',
  autoStart: true,
  optional: [ISettingRegistry, ICommandPalette, ILauncher, INotebookTracker],
  activate: (
    app: JupyterFrontEnd,
    settingRegistry: ISettingRegistry | null,
    palette: ICommandPalette | null,
    launcher: ILauncher | null,
    notebookTracker: INotebookTracker | null
  ) => {
    console.log('JupyterLab extension tk-ai-extension is activated!');

    // Create a single widget reference (shared across all notebooks)
    const widgetRef = new WidgetRef();
    const client = new MCPClient();

    // Add toolbar button to all notebook panels
    if (notebookTracker) {
      const buttonExtension = new ThinkyButtonExtension(app, widgetRef);
      app.docRegistry.addWidgetExtension('Notebook', buttonExtension);
      console.log('tk-ai-extension: Toolbar button added to notebooks');

      // Auto-detect notebook changes and update widget context
      notebookTracker.currentChanged.connect((tracker, notebookPanel) => {
        if (notebookPanel && widgetRef.widget && !widgetRef.widget.isDisposed && widgetRef.widget.isAttached) {
          const notebookPath = notebookPanel.context.path;
          console.log(`Notebook changed to: ${notebookPath}`);
          widgetRef.widget.updateNotebookContext(notebookPath);
        }
      });

      // Cleanup sessions when notebooks are closed
      // Note: Use widgetAdded to track widgets, then listen to their disposal
      notebookTracker.widgetAdded.connect((sender, notebookPanel) => {
        // Listen for when this specific notebook is disposed
        notebookPanel.disposed.connect(() => {
          const notebookPath = notebookPanel.context.path;
          console.log(`Notebook closed: ${notebookPath}, closing Claude session`);

          // Fire-and-forget cleanup
          client.closeSession(notebookPath).catch(err => {
            console.error('Failed to close session:', err);
          });
        });
      });

      console.log('tk-ai-extension: Notebook tracking enabled');
    }

    // Command to open chat (keep for programmatic access)
    app.commands.addCommand(CommandIDs.openChat, {
      label: 'Open tk-ai Chat',
      caption: 'Open the tk-ai chat interface',
      execute: () => {
        if (!widgetRef.widget || widgetRef.widget.isDisposed) {
          widgetRef.widget = new ChatWidget(app.shell);
          widgetRef.widget.id = 'tk-ai-chat';
          widgetRef.widget.title.label = 'tk-ai Chat';
          widgetRef.widget.title.closable = true;
        }

        if (!widgetRef.widget.isAttached) {
          app.shell.add(widgetRef.widget, 'right', { rank: 500 });
        }

        app.shell.activateById(widgetRef.widget.id);
      }
    });

    // Add to launcher (keep for users who want to open without a notebook)
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

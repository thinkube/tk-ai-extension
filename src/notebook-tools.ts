// Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
// SPDX-License-Identifier: BSD-3-Clause

/**
 * Frontend notebook tools for Thinky
 *
 * These tools manipulate notebooks directly in the frontend using JupyterLab APIs,
 * eliminating the need for backend kernel-client/YDoc synchronization.
 *
 * Based on approach from jupyterlite-ai:
 * - model.sharedModel.addCell() for adding cells
 * - model.sharedModel.deleteCell() for removing cells
 * - CodeCell.execute() for execution with IOPub streaming
 */

import { INotebookTracker, NotebookPanel } from '@jupyterlab/notebook';
import { CodeCell, MarkdownCell } from '@jupyterlab/cells';
import { ICodeCellModel } from '@jupyterlab/cells';
import { KernelMessage } from '@jupyterlab/services';

/**
 * Callback interface for streaming cell execution output
 */
export interface IExecutionCallbacks {
  onStream?: (text: string, name: 'stdout' | 'stderr') => void;
  onDisplayData?: (data: any, metadata: any) => void;
  onExecuteResult?: (data: any, metadata: any, executionCount: number) => void;
  onError?: (ename: string, evalue: string, traceback: string[]) => void;
  onStatus?: (status: string) => void;
}

/**
 * Result of a notebook operation
 */
export interface INotebookResult {
  success: boolean;
  message?: string;
  error?: string;
  cellIndex?: number;
  cellType?: string;
  executionCount?: number;
  outputs?: any[];
}

/**
 * Frontend notebook tools class
 */
export class NotebookTools {
  private notebookTracker: INotebookTracker;

  constructor(notebookTracker: INotebookTracker) {
    this.notebookTracker = notebookTracker;
  }

  /**
   * Get the current notebook panel
   */
  private getCurrentNotebook(): NotebookPanel | null {
    return this.notebookTracker.currentWidget;
  }

  /**
   * Get notebook by path
   */
  private getNotebookByPath(path: string): NotebookPanel | null {
    let found: NotebookPanel | null = null;
    this.notebookTracker.forEach(widget => {
      if (widget.context.path === path) {
        found = widget;
      }
    });
    return found;
  }

  /**
   * Get notebook (by path if provided, otherwise current)
   */
  private getNotebook(path?: string): NotebookPanel | null {
    if (path) {
      return this.getNotebookByPath(path);
    }
    return this.getCurrentNotebook();
  }

  /**
   * Get notebook info
   */
  getNotebookInfo(notebookPath?: string): INotebookResult & {
    notebookName?: string;
    notebookPath?: string;
    cellCount?: number;
    activeCellIndex?: number;
    activeCellType?: string;
  } {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const notebook = panel.content;
    const model = notebook.model;

    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    return {
      success: true,
      notebookName: panel.title.label,
      notebookPath: panel.context.path,
      cellCount: model.cells.length,
      activeCellIndex: notebook.activeCellIndex,
      activeCellType: notebook.activeCell?.model.type || 'unknown'
    };
  }

  /**
   * List all cells in the notebook
   */
  listCells(notebookPath?: string): INotebookResult & {
    cells?: Array<{
      index: number;
      type: string;
      source: string;
      executionCount?: number | null;
    }>;
  } {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const model = panel.content.model;
    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    const cells: Array<{
      index: number;
      type: string;
      source: string;
      executionCount?: number | null;
    }> = [];

    for (let i = 0; i < model.cells.length; i++) {
      const cell = model.cells.get(i);
      const cellData: {
        index: number;
        type: string;
        source: string;
        executionCount?: number | null;
      } = {
        index: i,
        type: cell.type,
        source: cell.sharedModel.getSource()
      };

      if (cell.type === 'code') {
        cellData.executionCount = (cell as ICodeCellModel).executionCount;
      }

      cells.push(cellData);
    }

    return {
      success: true,
      cells
    };
  }

  /**
   * Get cell content and info
   */
  getCellInfo(cellIndex: number, notebookPath?: string): INotebookResult & {
    source?: string;
    outputs?: any[];
    executionCount?: number | null;
  } {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const model = panel.content.model;
    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    if (cellIndex < 0 || cellIndex >= model.cells.length) {
      return {
        success: false,
        error: `Invalid cell index: ${cellIndex}. Notebook has ${model.cells.length} cells.`
      };
    }

    const cell = model.cells.get(cellIndex);
    const cellType = cell.type;
    const source = cell.sharedModel.getSource();

    const result: INotebookResult & {
      source?: string;
      outputs?: any[];
      executionCount?: number | null;
    } = {
      success: true,
      cellIndex,
      cellType,
      source
    };

    // Add outputs for code cells
    if (cellType === 'code') {
      const codeModel = cell as ICodeCellModel;
      result.executionCount = codeModel.executionCount ?? undefined;
      result.outputs = [];
      for (let i = 0; i < codeModel.outputs.length; i++) {
        result.outputs.push(codeModel.outputs.get(i).toJSON());
      }
    }

    return result;
  }

  /**
   * Add a new cell to the notebook
   */
  addCell(
    content: string,
    cellType: 'code' | 'markdown' = 'code',
    position: 'above' | 'below' | 'end' = 'end',
    notebookPath?: string
  ): INotebookResult {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const notebook = panel.content;
    const model = notebook.model;

    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    // Determine insertion index
    let insertIndex: number;
    const activeIndex = notebook.activeCellIndex;

    switch (position) {
      case 'above':
        insertIndex = activeIndex;
        break;
      case 'below':
        insertIndex = activeIndex + 1;
        break;
      case 'end':
      default:
        insertIndex = model.cells.length;
        break;
    }

    // Create the new cell using shared model
    const newCellData = {
      cell_type: cellType,
      source: content || '',
      metadata: cellType === 'code' ? { trusted: true } : {}
    };

    // Insert at the correct position
    model.sharedModel.insertCell(insertIndex, newCellData);

    // Render markdown cells after insertion
    if (cellType === 'markdown' && content) {
      const cellWidget = notebook.widgets[insertIndex];
      if (cellWidget && cellWidget instanceof MarkdownCell) {
        cellWidget.rendered = true;
      }
    }

    return {
      success: true,
      message: `${cellType} cell added at index ${insertIndex}`,
      cellIndex: insertIndex,
      cellType
    };
  }

  /**
   * Update cell content (overwrite)
   */
  updateCell(
    cellIndex: number,
    content: string,
    notebookPath?: string
  ): INotebookResult & { previousContent?: string } {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const model = panel.content.model;
    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    if (cellIndex < 0 || cellIndex >= model.cells.length) {
      return {
        success: false,
        error: `Invalid cell index: ${cellIndex}. Notebook has ${model.cells.length} cells.`
      };
    }

    const cell = model.cells.get(cellIndex);
    const previousContent = cell.sharedModel.getSource();
    const cellType = cell.type;

    // Update the source
    cell.sharedModel.setSource(content);

    // Re-render markdown cells
    if (cellType === 'markdown') {
      const cellWidget = panel.content.widgets[cellIndex];
      if (cellWidget && cellWidget instanceof MarkdownCell) {
        cellWidget.rendered = false;
        requestAnimationFrame(() => {
          cellWidget.rendered = true;
        });
      }
    }

    return {
      success: true,
      message: `Cell ${cellIndex} updated`,
      cellIndex,
      cellType,
      previousContent
    };
  }

  /**
   * Delete a cell
   */
  deleteCell(cellIndex: number, notebookPath?: string): INotebookResult & { deletedContent?: string } {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const model = panel.content.model;
    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    if (cellIndex < 0 || cellIndex >= model.cells.length) {
      return {
        success: false,
        error: `Invalid cell index: ${cellIndex}. Notebook has ${model.cells.length} cells.`
      };
    }

    // Get content before deletion for undo support
    const cell = model.cells.get(cellIndex);
    const deletedContent = cell.sharedModel.getSource();
    const cellType = cell.type;

    // Delete using shared model
    model.sharedModel.deleteCell(cellIndex);

    return {
      success: true,
      message: `Cell ${cellIndex} deleted`,
      cellIndex,
      cellType,
      deletedContent
    };
  }

  /**
   * Move a cell from one position to another
   */
  moveCell(
    fromIndex: number,
    toIndex: number,
    notebookPath?: string
  ): INotebookResult {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const model = panel.content.model;
    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    if (fromIndex < 0 || fromIndex >= model.cells.length) {
      return {
        success: false,
        error: `Invalid source index: ${fromIndex}. Notebook has ${model.cells.length} cells.`
      };
    }

    if (toIndex < 0 || toIndex >= model.cells.length) {
      return {
        success: false,
        error: `Invalid target index: ${toIndex}. Notebook has ${model.cells.length} cells.`
      };
    }

    if (fromIndex === toIndex) {
      return {
        success: true,
        message: `Cell already at index ${toIndex}`,
        cellIndex: toIndex
      };
    }

    // Move using shared model
    model.sharedModel.moveCell(fromIndex, toIndex);

    return {
      success: true,
      message: `Cell moved from ${fromIndex} to ${toIndex}`,
      cellIndex: toIndex
    };
  }

  /**
   * Execute a cell with IOPub streaming for real-time output
   *
   * This is the key function that enables tqdm/progress bar support.
   * Uses kernel.requestExecute() with onIOPub callback for streaming.
   */
  async executeCell(
    cellIndex: number,
    notebookPath?: string,
    callbacks?: IExecutionCallbacks
  ): Promise<INotebookResult> {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const notebook = panel.content;
    const model = notebook.model;

    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    if (cellIndex < 0 || cellIndex >= model.cells.length) {
      return {
        success: false,
        error: `Invalid cell index: ${cellIndex}. Notebook has ${model.cells.length} cells.`
      };
    }

    const cellWidget = notebook.widgets[cellIndex];
    if (!cellWidget) {
      return {
        success: false,
        error: `Cell widget at index ${cellIndex} not found`
      };
    }

    // Only execute code cells
    if (!(cellWidget instanceof CodeCell)) {
      return {
        success: true,
        message: `Cell ${cellIndex} is not a code cell, no execution needed`,
        cellIndex,
        cellType: cellWidget.model.type
      };
    }

    const sessionContext = panel.sessionContext;
    if (!sessionContext.session?.kernel) {
      return {
        success: false,
        error: 'No kernel available. Please start a kernel first.'
      };
    }

    try {
      // Get the code to execute
      const code = cellWidget.model.sharedModel.getSource();

      // Clear previous outputs
      (cellWidget.model as ICodeCellModel).outputs.clear();

      // Execute with IOPub streaming
      const kernel = sessionContext.session.kernel;
      const future = kernel.requestExecute({ code });

      // Set up IOPub handler for streaming output
      future.onIOPub = (msg: KernelMessage.IIOPubMessage) => {
        const msgType = msg.header.msg_type;
        const content = msg.content as any;

        switch (msgType) {
          case 'stream':
            // stdout/stderr - this is where tqdm output comes!
            if (callbacks?.onStream) {
              callbacks.onStream(content.text, content.name);
            }
            // Also add to cell outputs
            (cellWidget.model as ICodeCellModel).outputs.add({
              output_type: 'stream',
              name: content.name,
              text: content.text
            });
            break;

          case 'display_data':
            if (callbacks?.onDisplayData) {
              callbacks.onDisplayData(content.data, content.metadata);
            }
            (cellWidget.model as ICodeCellModel).outputs.add({
              output_type: 'display_data',
              data: content.data,
              metadata: content.metadata
            });
            break;

          case 'execute_result':
            if (callbacks?.onExecuteResult) {
              callbacks.onExecuteResult(content.data, content.metadata, content.execution_count);
            }
            (cellWidget.model as ICodeCellModel).outputs.add({
              output_type: 'execute_result',
              data: content.data,
              metadata: content.metadata,
              execution_count: content.execution_count
            });
            break;

          case 'error':
            if (callbacks?.onError) {
              callbacks.onError(content.ename, content.evalue, content.traceback);
            }
            (cellWidget.model as ICodeCellModel).outputs.add({
              output_type: 'error',
              ename: content.ename,
              evalue: content.evalue,
              traceback: content.traceback
            });
            break;

          case 'status':
            if (callbacks?.onStatus) {
              callbacks.onStatus(content.execution_state);
            }
            break;

          case 'update_display_data':
            // Handle display updates (used by tqdm for progress bar updates)
            if (callbacks?.onDisplayData) {
              callbacks.onDisplayData(content.data, content.metadata);
            }
            // Find and update existing display with same transient.display_id
            // For now, just add as new output
            (cellWidget.model as ICodeCellModel).outputs.add({
              output_type: 'display_data',
              data: content.data,
              metadata: content.metadata
            });
            break;
        }
      };

      // Wait for execution to complete
      const reply = await future.done;

      // Update execution count
      if (reply.content.status === 'ok') {
        const codeModel = cellWidget.model as ICodeCellModel;
        codeModel.executionCount = reply.content.execution_count ?? null;

        return {
          success: true,
          message: `Cell ${cellIndex} executed successfully`,
          cellIndex,
          executionCount: reply.content.execution_count ?? undefined
        };
      } else if (reply.content.status === 'error') {
        return {
          success: false,
          error: `Execution error: ${(reply.content as any).ename}: ${(reply.content as any).evalue}`,
          cellIndex
        };
      } else {
        return {
          success: false,
          error: `Execution aborted`,
          cellIndex
        };
      }
    } catch (error) {
      return {
        success: false,
        error: `Failed to execute cell: ${(error as Error).message}`,
        cellIndex
      };
    }
  }

  /**
   * Execute all cells in the notebook sequentially
   */
  async executeAllCells(
    notebookPath?: string,
    callbacks?: IExecutionCallbacks & {
      onCellStart?: (cellIndex: number, total: number) => void;
      onCellComplete?: (cellIndex: number, total: number, success: boolean) => void;
    }
  ): Promise<INotebookResult & { executedCells?: number; failedAt?: number }> {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const model = panel.content.model;
    if (!model) {
      return {
        success: false,
        error: 'No notebook model available'
      };
    }

    const totalCells = model.cells.length;
    let executedCells = 0;

    for (let i = 0; i < totalCells; i++) {
      const cell = model.cells.get(i);

      // Only execute code cells
      if (cell.type !== 'code') {
        continue;
      }

      if (callbacks?.onCellStart) {
        callbacks.onCellStart(i, totalCells);
      }

      const result = await this.executeCell(i, notebookPath, callbacks);

      if (callbacks?.onCellComplete) {
        callbacks.onCellComplete(i, totalCells, result.success);
      }

      if (!result.success) {
        return {
          success: false,
          error: result.error,
          executedCells,
          failedAt: i
        };
      }

      executedCells++;
    }

    return {
      success: true,
      message: `Executed ${executedCells} code cells`,
      executedCells
    };
  }

  /**
   * Execute the active cell
   */
  async executeActiveCell(
    notebookPath?: string,
    callbacks?: IExecutionCallbacks
  ): Promise<INotebookResult> {
    const panel = this.getNotebook(notebookPath);
    if (!panel) {
      return {
        success: false,
        error: notebookPath
          ? `Notebook not found: ${notebookPath}`
          : 'No active notebook'
      };
    }

    const activeIndex = panel.content.activeCellIndex;
    return this.executeCell(activeIndex, notebookPath, callbacks);
  }

  /**
   * Insert cell and execute it immediately
   * Useful for AI-generated code that should run right away
   */
  async insertAndExecute(
    content: string,
    position: 'above' | 'below' | 'end' = 'below',
    notebookPath?: string,
    callbacks?: IExecutionCallbacks
  ): Promise<INotebookResult> {
    // First add the cell
    const addResult = this.addCell(content, 'code', position, notebookPath);
    if (!addResult.success || addResult.cellIndex === undefined) {
      return addResult;
    }

    // Then execute it
    const execResult = await this.executeCell(addResult.cellIndex, notebookPath, callbacks);

    return {
      ...execResult,
      cellIndex: addResult.cellIndex
    };
  }
}

# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for executing all cells in a notebook."""

import logging
import uuid
import asyncio
from typing import Any, Optional, Dict, List
from ..base import BaseTool
from ..utils import get_notebook_path

logger = logging.getLogger(__name__)

# Shared execution tracking from execute_cell_async
_async_executions_all = {}


class ExecuteAllCellsTool(BaseTool):
    """Execute all code cells in a notebook sequentially."""

    @property
    def name(self) -> str:
        return "execute_all_cells"

    @property
    def description(self) -> str:
        return (
            "Execute all code cells in a notebook sequentially (top to bottom). "
            "This is essential for self-healing workflows where you need to restart and re-run after fixing errors. "
            "Can optionally restart the kernel first. Returns immediately with an execution_id. "
            "Use check_all_cells_status to poll progress. "
            "NOTE: You must call use_notebook first to connect to a notebook and its kernel."
        )

    @property
    def input_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "notebook_path": {
                    "type": "string",
                    "description": "Path to the notebook"
                },
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to use for execution"
                },
                "restart_kernel": {
                    "type": "boolean",
                    "description": "Whether to restart the kernel before executing all cells (default: false)",
                    "default": False
                }
            },
            "required": ["notebook_path", "kernel_id"]
        }

    async def execute(
        self,
        contents_manager: Any,
        kernel_manager: Any,
        kernel_spec_manager: Optional[Any] = None,
        session_manager: Optional[Any] = None,
        notebook_manager: Optional[Any] = None,
        serverapp: Optional[Any] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """Execute all cells asynchronously.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager for tracking
            serverapp: Jupyter ServerApp instance
            notebook_path: Path to notebook
            kernel_id: Kernel ID to use
            restart_kernel: Whether to restart kernel first

        Returns:
            Dict with execution_id for status polling
        """
        notebook_path = kwargs.get("notebook_path")
        kernel_id = kwargs.get("kernel_id")
        restart_kernel = kwargs.get("restart_kernel", False)

        if not serverapp:
            serverapp = getattr(contents_manager, 'parent', None)

        if serverapp:
            serverapp.log.info(f"ExecuteAllCellsTool.execute called: notebook_path={notebook_path}, kernel_id={kernel_id}, restart={restart_kernel}")

        if not notebook_path or not kernel_id:
            return {
                "error": "notebook_path and kernel_id are required",
                "success": False
            }

        try:
            # Check kernel exists
            kernels = list(kernel_manager.list_kernels())
            kernel_info = None
            for k in kernels:
                if k['id'] == kernel_id:
                    kernel_info = k
                    break

            if not kernel_info:
                return {
                    "error": f"Kernel '{kernel_id}' not found",
                    "success": False
                }

            # Check kernel execution state
            execution_state = kernel_info.get('execution_state', 'unknown')
            if execution_state == 'busy':
                return {
                    "error": "Kernel is currently busy executing. Please wait for the current execution to complete.",
                    "success": False,
                    "kernel_id": kernel_id,
                    "execution_state": execution_state
                }

            # Get absolute path and file_id
            abs_path = get_notebook_path(serverapp, notebook_path)
            file_id_manager = serverapp.web_app.settings.get("file_id_manager")
            file_id = file_id_manager.get_id(abs_path)

            # Get YDoc
            ydoc_extensions = serverapp.extension_manager.extension_apps.get("jupyter_server_ydoc", set())
            if not ydoc_extensions:
                return {
                    "error": "jupyter-server-ydoc extension not found",
                    "success": False
                }

            ydoc_extension = next(iter(ydoc_extensions))
            document_id = f"json:notebook:{file_id}"

            ydoc = await ydoc_extension.get_document(room_id=document_id, copy=False)

            if ydoc is None:
                return {
                    "error": f"Document {document_id} not found",
                    "success": False
                }

            # Count code cells
            code_cells = []
            for idx, cell in enumerate(ydoc.ycells):
                if cell.get("cell_type") == "code":
                    source_raw = cell.get("source", "")
                    if isinstance(source_raw, list):
                        source = "".join(source_raw)
                    else:
                        source = str(source_raw)

                    if source.strip():  # Skip empty cells
                        code_cells.append((idx, source))

            if not code_cells:
                return {
                    "error": "No code cells found in notebook",
                    "success": False
                }

            # Generate unique execution ID
            execution_id = str(uuid.uuid4())

            # Initialize execution tracking
            _async_executions_all[execution_id] = {
                "status": "running",
                "current_cell_index": None,
                "total_cells": len(code_cells),
                "completed_cells": 0,
                "failed_cell_index": None,
                "error": None,
                "notebook_path": notebook_path,
                "kernel_id": kernel_id,
                "results": []
            }

            # Start async execution task
            asyncio.create_task(self._execute_all_async(
                execution_id=execution_id,
                serverapp=serverapp,
                kernel_id=kernel_id,
                kernel_manager=kernel_manager,
                ydoc=ydoc,
                code_cells=code_cells,
                restart_kernel=restart_kernel
            ))

            serverapp.log.info(f"Started execute_all {execution_id} for {len(code_cells)} cells")

            return {
                "success": True,
                "execution_id": execution_id,
                "total_cells": len(code_cells),
                "status": "running",
                "restart_kernel": restart_kernel,
                "message": f"Started executing all {len(code_cells)} code cells. Use check_all_cells_status to poll progress."
            }

        except Exception as e:
            if serverapp:
                serverapp.log.error(f"Error starting execute_all: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e)
            }

    async def _execute_all_async(
        self,
        execution_id: str,
        serverapp: Any,
        kernel_id: str,
        kernel_manager: Any,
        ydoc: Any,
        code_cells: List[tuple],
        restart_kernel: bool
    ):
        """Background task for executing all cells."""
        try:
            # Restart kernel if requested
            if restart_kernel:
                serverapp.log.info(f"Execute_all {execution_id}: Restarting kernel {kernel_id}")
                await kernel_manager.restart_kernel(kernel_id)
                # Wait for kernel to be ready
                await asyncio.sleep(2)
                serverapp.log.info(f"Execute_all {execution_id}: Kernel restarted")

            # Execute each cell sequentially
            for cell_idx, source in code_cells:
                _async_executions_all[execution_id]["current_cell_index"] = cell_idx

                serverapp.log.info(f"Execute_all {execution_id}: Executing cell {cell_idx}")

                try:
                    # Execute the cell
                    outputs = await self._execute_code(
                        serverapp=serverapp,
                        kernel_id=kernel_id,
                        kernel_manager=kernel_manager,
                        code=source
                    )

                    # Update YDoc
                    max_count = 0
                    for c in ydoc.ycells:
                        if c.get("cell_type") == "code" and c.get("execution_count"):
                            max_count = max(max_count, c["execution_count"])

                    with ydoc.ycells[cell_idx].doc.transaction():
                        ydoc.ycells[cell_idx]["execution_count"] = max_count + 1
                        del ydoc.ycells[cell_idx]["outputs"][:]
                        for output in outputs:
                            ydoc.ycells[cell_idx]["outputs"].append(output)

                    # Check for errors
                    has_error = any(o.get("output_type") == "error" for o in outputs)

                    _async_executions_all[execution_id]["results"].append({
                        "cell_index": cell_idx,
                        "success": not has_error,
                        "outputs": outputs
                    })

                    _async_executions_all[execution_id]["completed_cells"] += 1

                    if has_error:
                        # Stop on error
                        serverapp.log.warning(f"Execute_all {execution_id}: Cell {cell_idx} failed with error")
                        _async_executions_all[execution_id]["status"] = "error"
                        _async_executions_all[execution_id]["failed_cell_index"] = cell_idx
                        _async_executions_all[execution_id]["error"] = "Cell execution failed with error"
                        return

                except Exception as e:
                    serverapp.log.error(f"Execute_all {execution_id}: Exception in cell {cell_idx}: {e}")
                    _async_executions_all[execution_id]["status"] = "error"
                    _async_executions_all[execution_id]["failed_cell_index"] = cell_idx
                    _async_executions_all[execution_id]["error"] = str(e)
                    return

            # All cells completed successfully
            serverapp.log.info(f"Execute_all {execution_id}: All cells completed successfully")
            _async_executions_all[execution_id]["status"] = "completed"
            _async_executions_all[execution_id]["current_cell_index"] = None

        except Exception as e:
            serverapp.log.error(f"Execute_all {execution_id}: Fatal error: {e}", exc_info=True)
            _async_executions_all[execution_id]["status"] = "error"
            _async_executions_all[execution_id]["error"] = str(e)

    async def _execute_code(
        self,
        serverapp: Any,
        kernel_id: str,
        kernel_manager: Any,
        code: str
    ) -> List[Dict[str, Any]]:
        """Execute code in kernel (same as execute_cell_async)."""
        import asyncio
        import zmq.asyncio
        from inspect import isawaitable

        try:
            lkm = kernel_manager.pinned_superclass.get_kernel(kernel_manager, kernel_id)
            session = lkm.session
            client = lkm.client()

            if not client.channels_running:
                client.start_channels()
                await asyncio.sleep(0.1)

            shell_channel = client.shell_channel
            msg_id = session.msg("execute_request", {
                "code": code,
                "silent": False,
                "store_history": True,
                "user_expressions": {},
                "allow_stdin": False,
                "stop_on_error": False
            })
            shell_channel.send(msg_id)

            await asyncio.sleep(0.01)

            outputs = []
            execution_done = False
            grace_period_ms = 100

            poller = zmq.asyncio.Poller()
            iopub_socket = client.iopub_channel.socket
            shell_socket = shell_channel.socket
            poller.register(iopub_socket, zmq.POLLIN)
            poller.register(shell_socket, zmq.POLLIN)

            execution_done_time = None

            while not execution_done or (execution_done_time and (asyncio.get_event_loop().time() - execution_done_time) * 1000 < grace_period_ms):
                if execution_done and execution_done_time and (asyncio.get_event_loop().time() - execution_done_time) * 1000 >= grace_period_ms:
                    break

                poll_timeout = grace_period_ms / 2 if execution_done else 1000
                events = dict(await poller.poll(poll_timeout))

                if not events:
                    continue

                if iopub_socket in events:
                    msg = client.iopub_channel.get_msg(timeout=0)
                    if isawaitable(msg):
                        msg = await msg

                    if msg and msg.get('parent_header', {}).get('msg_id') == msg_id['header']['msg_id']:
                        msg_type = msg.get('msg_type')
                        content = msg.get('content', {})

                        if msg_type == 'stream':
                            outputs.append({
                                'output_type': 'stream',
                                'name': content.get('name', 'stdout'),
                                'text': content.get('text', '')
                            })
                        elif msg_type == 'execute_result':
                            outputs.append({
                                'output_type': 'execute_result',
                                'data': content.get('data', {}),
                                'metadata': content.get('metadata', {}),
                                'execution_count': content.get('execution_count')
                            })
                        elif msg_type == 'display_data':
                            outputs.append({
                                'output_type': 'display_data',
                                'data': content.get('data', {}),
                                'metadata': content.get('metadata', {})
                            })
                        elif msg_type == 'error':
                            outputs.append({
                                'output_type': 'error',
                                'ename': content.get('ename', ''),
                                'evalue': content.get('evalue', ''),
                                'traceback': content.get('traceback', [])
                            })

                if shell_socket in events:
                    reply = client.shell_channel.get_msg(timeout=0)
                    if isawaitable(reply):
                        reply = await reply

                    if reply and reply.get('parent_header', {}).get('msg_id') == msg_id['header']['msg_id']:
                        execution_done = True
                        execution_done_time = asyncio.get_event_loop().time()

            client.stop_channels()
            return outputs

        except Exception as e:
            serverapp.log.error(f"Error executing code: {e}", exc_info=True)
            return [{
                "output_type": "stream",
                "name": "stderr",
                "text": f"[ERROR: {str(e)}]"
            }]

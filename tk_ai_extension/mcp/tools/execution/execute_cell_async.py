# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for async (fire-and-forget) cell execution."""

import logging
import uuid
import asyncio
from pathlib import Path
from typing import Any, Optional, Dict, List
from ..base import BaseTool
from ..utils import get_notebook_path

logger = logging.getLogger(__name__)

# Global dictionary to track async executions
# Format: {execution_id: {"status": "running|completed|error", "outputs": [...], "cell_index": int, "error": str}}
_async_executions = {}


class ExecuteCellAsyncTool(BaseTool):
    """Execute a cell asynchronously (fire-and-forget) for long-running operations."""

    @property
    def name(self) -> str:
        return "execute_cell_async"

    @property
    def description(self) -> str:
        return (
            "Execute a code cell asynchronously (fire-and-forget) without blocking. "
            "This is ideal for long-running operations like model training that may take hours. "
            "Returns immediately with an execution_id that can be used with check_execution_status. "
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
                "cell_index": {
                    "type": "integer",
                    "description": "Index of the cell to execute (0-based)"
                },
                "kernel_id": {
                    "type": "string",
                    "description": "ID of the kernel to use for execution"
                }
            },
            "required": ["notebook_path", "cell_index", "kernel_id"]
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
        """Start async cell execution.

        Args:
            contents_manager: Jupyter contents manager
            kernel_manager: Jupyter kernel manager
            kernel_spec_manager: Kernel spec manager (unused)
            session_manager: Session manager (unused)
            notebook_manager: Notebook manager for tracking
            serverapp: Jupyter ServerApp instance
            notebook_path: Path to notebook
            cell_index: Cell index to execute
            kernel_id: Kernel ID to use

        Returns:
            Dict with execution_id for status polling
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")
        kernel_id = kwargs.get("kernel_id")

        if not serverapp:
            serverapp = getattr(contents_manager, 'parent', None)

        if serverapp:
            serverapp.log.info(f"ExecuteCellAsyncTool.execute called: notebook_path={notebook_path}, cell_index={cell_index}, kernel_id={kernel_id}")

        if not notebook_path or cell_index is None or not kernel_id:
            return {
                "error": "notebook_path, cell_index, and kernel_id are required",
                "success": False
            }

        try:
            # Check kernel execution state (natural lock mechanism)
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

            execution_state = kernel_info.get('execution_state', 'unknown')
            if execution_state == 'busy':
                return {
                    "error": "Kernel is currently busy executing another cell. Please wait for the current execution to complete.",
                    "success": False,
                    "kernel_id": kernel_id,
                    "execution_state": execution_state
                }

            # Get absolute path and file_id
            abs_path = get_notebook_path(serverapp, notebook_path)
            file_id_manager = serverapp.web_app.settings.get("file_id_manager")
            file_id = file_id_manager.get_id(abs_path)

            # Get YDoc via jupyter-server-ydoc extension
            ydoc_extensions = serverapp.extension_manager.extension_apps.get("jupyter_server_ydoc", set())
            if not ydoc_extensions:
                return {
                    "error": "jupyter-server-ydoc extension not found",
                    "success": False
                }

            ydoc_extension = next(iter(ydoc_extensions))
            document_id = f"json:notebook:{file_id}"

            serverapp.log.info(f"Getting YDoc for document {document_id}")

            # Get the YNotebook document
            ydoc = await ydoc_extension.get_document(room_id=document_id, copy=False)

            if ydoc is None:
                return {
                    "error": f"Document {document_id} not found",
                    "success": False
                }

            # Validate cell index
            if cell_index < 0 or cell_index >= len(ydoc.ycells):
                return {
                    "error": f"Cell index {cell_index} out of range. Notebook has {len(ydoc.ycells)} cells.",
                    "success": False
                }

            cell = ydoc.ycells[cell_index]

            # Only execute code cells
            cell_type = cell.get("cell_type", "")
            if cell_type != "code":
                return {
                    "error": f"Cell {cell_index} is not a code cell (type: {cell_type})",
                    "success": False
                }

            # Get cell source
            source_raw = cell.get("source", "")
            if isinstance(source_raw, list):
                source = "".join(source_raw)
            else:
                source = str(source_raw)

            if not source:
                return {
                    "error": "Cell is empty",
                    "success": False
                }

            # Generate unique execution ID
            execution_id = str(uuid.uuid4())

            # Initialize execution tracking
            _async_executions[execution_id] = {
                "status": "running",
                "outputs": [],
                "cell_index": cell_index,
                "error": None,
                "notebook_path": notebook_path,
                "kernel_id": kernel_id
            }

            # Start async execution task (fire-and-forget)
            asyncio.create_task(self._execute_async(
                execution_id=execution_id,
                serverapp=serverapp,
                kernel_id=kernel_id,
                kernel_manager=kernel_manager,
                source=source,
                ydoc=ydoc,
                cell_index=cell_index
            ))

            serverapp.log.info(f"Started async execution {execution_id} for cell {cell_index}")

            return {
                "success": True,
                "execution_id": execution_id,
                "cell_index": cell_index,
                "status": "running",
                "message": f"Async execution started for cell {cell_index}. Use check_execution_status with execution_id to poll results."
            }

        except Exception as e:
            if serverapp:
                serverapp.log.error(f"Error starting async execution: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "cell_index": cell_index
            }

    async def _execute_async(
        self,
        execution_id: str,
        serverapp: Any,
        kernel_id: str,
        kernel_manager: Any,
        source: str,
        ydoc: Any,
        cell_index: int
    ):
        """Background task for async execution.

        This runs independently and updates the global execution state.
        """
        try:
            serverapp.log.info(f"Async execution {execution_id}: Starting cell {cell_index} execution")

            # Execute code using kernel directly (no timeout for async)
            execution_count, outputs = await self._execute_code(
                serverapp=serverapp,
                kernel_id=kernel_id,
                kernel_manager=kernel_manager,
                code=source
            )

            serverapp.log.info(f"Async execution {execution_id}: Execution completed with {len(outputs)} outputs, execution_count={execution_count}")

            # Update execution count and outputs in YDoc with transaction (required for RTC broadcast)
            # Use the execution count from the kernel (not calculated from notebook)
            with ydoc.ycells[cell_index].doc.transaction():
                ydoc.ycells[cell_index]["execution_count"] = execution_count
                # Clear existing outputs and add new ones
                del ydoc.ycells[cell_index]["outputs"][:]
                for output in outputs:
                    ydoc.ycells[cell_index]["outputs"].append(output)

            serverapp.log.info(f"Async execution {execution_id}: Updated YDoc - RTC will sync to UI")

            # Update execution status
            _async_executions[execution_id]["status"] = "completed"
            _async_executions[execution_id]["outputs"] = outputs

        except Exception as e:
            serverapp.log.error(f"Async execution {execution_id}: Error: {e}", exc_info=True)
            _async_executions[execution_id]["status"] = "error"
            _async_executions[execution_id]["error"] = str(e)

    async def _execute_code(
        self,
        serverapp: Any,
        kernel_id: str,
        kernel_manager: Any,
        code: str
    ) -> tuple[int, List[Dict[str, Any]]]:
        """Execute code in kernel and collect outputs (no timeout for async).

        Returns:
            Tuple of (execution_count, outputs) where execution_count is from the kernel

        Adapted from ExecuteCellTool._execute_code but without timeout.
        """
        import asyncio
        import zmq.asyncio
        from inspect import isawaitable

        try:
            # Get the kernel using pinned_superclass pattern
            lkm = kernel_manager.pinned_superclass.get_kernel(kernel_manager, kernel_id)
            session = lkm.session
            client = lkm.client()

            # Ensure channels are started
            if not client.channels_running:
                client.start_channels()
                await asyncio.sleep(0.1)

            # Send execute request on shell channel
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

            # Prepare to collect outputs and execution count
            outputs = []
            execution_count = None
            execution_done = False
            grace_period_ms = 100

            # Poll for messages (no timeout for async execution)
            poller = zmq.asyncio.Poller()
            iopub_socket = client.iopub_channel.socket
            shell_socket = shell_channel.socket
            poller.register(iopub_socket, zmq.POLLIN)
            poller.register(shell_socket, zmq.POLLIN)

            execution_done_time = None

            while not execution_done or (execution_done_time and (asyncio.get_event_loop().time() - execution_done_time) * 1000 < grace_period_ms):
                # If execution is done and grace period expired, exit
                if execution_done and execution_done_time and (asyncio.get_event_loop().time() - execution_done_time) * 1000 >= grace_period_ms:
                    break

                # Use shorter poll timeout during grace period
                poll_timeout = grace_period_ms / 2 if execution_done else 1000
                events = dict(await poller.poll(poll_timeout))

                if not events:
                    continue

                # Process IOPub messages BEFORE shell
                if iopub_socket in events:
                    msg = client.iopub_channel.get_msg(timeout=0)
                    if isawaitable(msg):
                        msg = await msg

                    if msg and msg.get('parent_header', {}).get('msg_id') == msg_id['header']['msg_id']:
                        msg_type = msg.get('msg_type')
                        content = msg.get('content', {})

                        # Collect output messages
                        if msg_type == 'stream':
                            outputs.append({
                                'output_type': 'stream',
                                'name': content.get('name', 'stdout'),
                                'text': content.get('text', '')
                            })
                        elif msg_type == 'execute_result':
                            # Capture execution count from kernel
                            if execution_count is None:
                                execution_count = content.get('execution_count')
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

                # Check for shell reply (execution complete)
                if shell_socket in events:
                    reply = client.shell_channel.get_msg(timeout=0)
                    if isawaitable(reply):
                        reply = await reply

                    if reply and reply.get('parent_header', {}).get('msg_id') == msg_id['header']['msg_id']:
                        execution_done = True
                        execution_done_time = asyncio.get_event_loop().time()
                        # Capture execution_count from shell reply if not already captured
                        if execution_count is None:
                            reply_content = reply.get('content', {})
                            execution_count = reply_content.get('execution_count')

            # Clean up
            client.stop_channels()

            # Kernel must return execution_count - fail if it doesn't
            if execution_count is None:
                raise RuntimeError("Kernel did not return execution_count in shell reply")

            return (execution_count, outputs)

        except Exception as e:
            serverapp.log.error(f"Error executing code: {e}", exc_info=True)
            raise

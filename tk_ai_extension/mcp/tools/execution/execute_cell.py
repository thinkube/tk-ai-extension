# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""MCP tool for executing notebook cells."""

import logging
from pathlib import Path
from typing import Any, Optional, Dict, List
from ..base import BaseTool
from ..utils import get_notebook_path

logger = logging.getLogger(__name__)


class ExecuteCellTool(BaseTool):
    """Execute a cell in a Jupyter notebook."""

    @property
    def name(self) -> str:
        return "execute_cell"

    @property
    def description(self) -> str:
        return "Execute a code cell in a Jupyter notebook and return its output. NOTE: You must call use_notebook first to connect to a notebook and its kernel."

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
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "Maximum time to wait for execution (default: 300)",
                    "default": 300
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
        """Execute a cell by directly accessing DocumentRoom and YDoc.

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
            timeout_seconds: Execution timeout

        Returns:
            Dict with execution results
        """
        notebook_path = kwargs.get("notebook_path")
        cell_index = kwargs.get("cell_index")
        kernel_id = kwargs.get("kernel_id")
        timeout_seconds = kwargs.get("timeout_seconds", 300)

        if not serverapp:
            serverapp = getattr(contents_manager, 'parent', None)

        if serverapp:
            serverapp.log.info(f"ExecuteCellTool.execute called: notebook_path={notebook_path}, cell_index={cell_index}, kernel_id={kernel_id}")

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

            # Get YDoc via jupyter-server-ydoc extension (same as jupyter-server-nbmodel does)
            ydoc_extensions = serverapp.extension_manager.extension_apps.get("jupyter_server_ydoc", set())
            if not ydoc_extensions:
                return {
                    "error": "jupyter-server-ydoc extension not found",
                    "success": False
                }

            ydoc_extension = next(iter(ydoc_extensions))
            document_id = f"json:notebook:{file_id}"

            serverapp.log.info(f"Getting YDoc for document {document_id}")

            # Get the YNotebook document (this is what jupyter-server-nbmodel does)
            ydoc = await ydoc_extension.get_document(room_id=document_id, copy=False)

            if ydoc is None:
                return {
                    "error": f"Document {document_id} not found",
                    "success": False
                }

            serverapp.log.info(f"Got YDoc for document {document_id}")

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

            serverapp.log.info(f"Executing cell {cell_index} source: {source[:100]}...")

            # Execute code using kernel directly (adapted from jupyter-mcp-server)
            execution_count, outputs = await self._execute_code(
                serverapp=serverapp,
                kernel_id=kernel_id,
                code=source,
                timeout=timeout_seconds
            )

            serverapp.log.info(f"Execution completed with {len(outputs)} outputs, execution_count={execution_count}")

            # Update execution count and outputs in YDoc with transaction (required for RTC broadcast)
            # Use the execution count from the kernel (not calculated from notebook)
            with cell.doc.transaction():
                cell["execution_count"] = execution_count
                # Clear existing outputs and add new ones
                del cell["outputs"][:]
                for output in outputs:
                    cell["outputs"].append(output)

            serverapp.log.info(f"Updated cell {cell_index} outputs in YDoc ({len(outputs)} outputs) - RTC will sync to UI")

            return {
                "success": True,
                "cell_index": cell_index,
                "outputs": outputs
            }

        except Exception as e:
            if serverapp:
                serverapp.log.error(f"Error executing cell: {e}", exc_info=True)
            return {
                "success": False,
                "error": str(e),
                "cell_index": cell_index
            }

    async def _execute_code(
        self,
        serverapp: Any,
        kernel_id: str,
        code: str,
        timeout: int = 300
    ) -> tuple[int, List[Dict[str, Any]]]:
        """Execute code in kernel and collect outputs.

        Returns:
            Tuple of (execution_count, outputs) where execution_count is from the kernel

        Adapted from jupyter-mcp-server's execute_code_local().
        """
        import asyncio
        import zmq.asyncio
        from inspect import isawaitable

        try:
            # Get kernel manager
            kernel_manager = serverapp.kernel_manager

            # Get the kernel using pinned_superclass pattern
            lkm = kernel_manager.pinned_superclass.get_kernel(kernel_manager, kernel_id)
            session = lkm.session
            client = lkm.client()

            # Ensure channels are started (critical for receiving IOPub messages!)
            if not client.channels_running:
                client.start_channels()
                # Wait for channels to be ready
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

            # Give a moment for messages to start flowing
            await asyncio.sleep(0.01)

            # Prepare to collect outputs and execution count
            outputs = []
            execution_count = None
            execution_done = False
            grace_period_ms = 100  # Wait 100ms after shell reply for remaining IOPub messages
            execution_done_time = None

            # Poll for messages with timeout
            poller = zmq.asyncio.Poller()
            iopub_socket = client.iopub_channel.socket
            shell_socket = shell_channel.socket
            poller.register(iopub_socket, zmq.POLLIN)
            poller.register(shell_socket, zmq.POLLIN)

            timeout_ms = timeout * 1000
            start_time = asyncio.get_event_loop().time()

            while not execution_done or (execution_done_time and (asyncio.get_event_loop().time() - execution_done_time) * 1000 < grace_period_ms):
                elapsed_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                remaining_ms = max(0, timeout_ms - elapsed_ms)

                # If execution is done and grace period expired, exit
                if execution_done and execution_done_time and (asyncio.get_event_loop().time() - execution_done_time) * 1000 >= grace_period_ms:
                    break

                if remaining_ms <= 0:
                    client.stop_channels()
                    serverapp.log.warning(f"Code execution timeout after {timeout}s, collected {len(outputs)} outputs")
                    return [{
                        "output_type": "stream",
                        "name": "stderr",
                        "text": f"[TIMEOUT: Code execution exceeded {timeout} seconds]"
                    }]

                # Use shorter poll timeout during grace period
                poll_timeout = min(remaining_ms, grace_period_ms / 2) if execution_done else remaining_ms
                events = dict(await poller.poll(poll_timeout))

                if not events:
                    continue  # No messages, continue polling

                # Process IOPub messages BEFORE shell to collect outputs before marking done
                if iopub_socket in events:
                    msg = client.iopub_channel.get_msg(timeout=0)
                    # Handle async get_msg
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

                # Check for shell reply (execution complete) - AFTER processing IOPub
                if shell_socket in events:
                    reply = client.shell_channel.get_msg(timeout=0)
                    # Handle async get_msg
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

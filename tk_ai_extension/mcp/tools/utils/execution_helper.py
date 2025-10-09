# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Helper functions for code execution and output formatting."""

import asyncio
import logging
from typing import List, Any, Optional, Union

logger = logging.getLogger(__name__)


async def execute_code_with_timeout(
    kernel_manager: Any,
    kernel_id: str,
    code: str,
    timeout_seconds: int = 300
) -> List[str]:
    """Execute code in a kernel with timeout.

    Args:
        kernel_manager: Jupyter kernel manager
        kernel_id: ID of the kernel to execute in
        code: Code to execute
        timeout_seconds: Maximum time to wait

    Returns:
        List of output strings
    """
    if not code or not code.strip():
        return ["[Empty code]"]

    try:
        # Get kernel
        kernel = kernel_manager.get_kernel(kernel_id)

        # Create a new kernel client for this execution
        client = kernel.client()
        client.start_channels()

        # Wait for client to be ready
        await asyncio.sleep(0.5)

        # Execute code - this is synchronous but returns immediately
        msg_id = client.execute(code, silent=False, store_history=True)

        # Collect outputs with timeout
        outputs = []
        start_time = asyncio.get_event_loop().time()
        execution_done = False

        while not execution_done:
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                # Interrupt kernel
                try:
                    await kernel_manager.interrupt_kernel(kernel_id)
                except Exception as e:
                    logger.warning(f"Failed to interrupt kernel: {e}")
                client.stop_channels()
                return [f"[TIMEOUT ERROR: Execution exceeded {timeout_seconds} seconds]"]

            # Get messages (non-blocking)
            try:
                # Run blocking call in thread pool
                msg = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.get_iopub_msg(timeout=0.5)
                )

                if msg['parent_header'].get('msg_id') == msg_id:
                    msg_type = msg['header']['msg_type']
                    content = msg['content']

                    if msg_type == 'stream':
                        outputs.append(content.get('text', ''))
                    elif msg_type == 'execute_result':
                        data = content.get('data', {})
                        outputs.append(data.get('text/plain', str(data)))
                    elif msg_type == 'display_data':
                        data = content.get('data', {})
                        outputs.append(data.get('text/plain', str(data)))
                    elif msg_type == 'error':
                        ename = content.get('ename', 'Unknown')
                        evalue = content.get('evalue', '')
                        traceback = '\n'.join(content.get('traceback', []))
                        outputs.append(f"[ERROR: {ename}: {evalue}\n{traceback}]")
                    elif msg_type == 'status':
                        if content.get('execution_state') == 'idle':
                            execution_done = True

            except Exception as e:
                # No message available or timeout, wait a bit
                await asyncio.sleep(0.1)

        # Stop client channels
        client.stop_channels()

        return outputs if outputs else ["[No output]"]

    except Exception as e:
        logger.error(f"Execution error: {e}", exc_info=True)
        return [f"[ERROR: {str(e)}]"]


def format_outputs(outputs: List[Any]) -> List[str]:
    """Format outputs for display.

    Args:
        outputs: List of output objects

    Returns:
        List of formatted output strings
    """
    if not outputs:
        return ["[No output]"]

    formatted = []
    for output in outputs:
        if isinstance(output, str):
            formatted.append(output)
        elif isinstance(output, dict):
            # Handle nbformat output structure
            if 'text' in output:
                formatted.append(output['text'])
            elif 'data' in output:
                data = output['data']
                if 'text/plain' in data:
                    formatted.append(data['text/plain'])
                else:
                    formatted.append(str(data))
            else:
                formatted.append(str(output))
        else:
            formatted.append(str(output))

    return formatted if formatted else ["[No output]"]

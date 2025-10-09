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
        empty_reads = 0  # Track consecutive empty reads
        max_empty_reads = 20  # Exit after 2 seconds of no messages (20 * 0.1s)

        while not execution_done:
            # Check timeout
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout_seconds:
                # Interrupt kernel
                logger.warning(f"Execution timeout after {elapsed}s")
                try:
                    await kernel_manager.interrupt_kernel(kernel_id)
                except Exception as e:
                    logger.warning(f"Failed to interrupt kernel: {e}")
                client.stop_channels()
                return [f"[TIMEOUT ERROR: Execution exceeded {timeout_seconds} seconds]"]

            # Check if we've been getting no messages for too long
            if empty_reads >= max_empty_reads:
                logger.info(f"No messages for {max_empty_reads * 0.1}s, assuming execution complete")
                execution_done = True
                break

            # Get messages (non-blocking)
            try:
                # Run blocking call in thread pool with short timeout
                msg = await asyncio.get_event_loop().run_in_executor(
                    None,
                    lambda: client.get_iopub_msg(timeout=0.5)
                )

                # Reset empty reads counter - we got a message
                empty_reads = 0

                if msg['parent_header'].get('msg_id') == msg_id:
                    msg_type = msg['header']['msg_type']
                    content = msg['content']

                    logger.debug(f"Got message type: {msg_type}")

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
                            logger.info("Kernel returned to idle state")
                            execution_done = True

            except Exception:
                # No message available, increment empty reads counter
                empty_reads += 1
                await asyncio.sleep(0.1)

        # Stop client channels
        client.stop_channels()

        logger.info(f"Execution completed with {len(outputs)} outputs")
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

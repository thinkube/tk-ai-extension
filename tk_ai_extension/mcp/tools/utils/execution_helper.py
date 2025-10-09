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
        # Get kernel client
        kernel = kernel_manager.get_kernel(kernel_id)
        client = kernel.client()

        # Execute code
        msg_id = client.execute(code)

        # Collect outputs with timeout
        outputs = []
        start_time = asyncio.get_event_loop().time()

        while True:
            # Check timeout
            if asyncio.get_event_loop().time() - start_time > timeout_seconds:
                # Interrupt kernel
                try:
                    await kernel_manager.interrupt_kernel(kernel_id)
                except Exception as e:
                    logger.warning(f"Failed to interrupt kernel: {e}")
                return [f"[TIMEOUT ERROR: Execution exceeded {timeout_seconds} seconds]"]

            # Get messages (non-blocking)
            try:
                msg = client.get_iopub_msg(timeout=1)

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
                        outputs.append(f"[ERROR: {content.get('ename', 'Unknown')}: {content.get('evalue', '')}]")
                    elif msg_type == 'status':
                        if content.get('execution_state') == 'idle':
                            break

            except Exception:
                # No message available, wait a bit
                await asyncio.sleep(0.1)

        return outputs if outputs else ["[No output]"]

    except Exception as e:
        logger.error(f"Execution error: {e}")
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

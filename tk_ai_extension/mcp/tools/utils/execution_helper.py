# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# Copyright (c) 2023-2024 Datalayer, Inc.
# SPDX-License-Identifier: BSD-3-Clause

"""Helper functions for code execution and output formatting."""

import asyncio
import logging
import re
from typing import List, Any, Optional, Union

logger = logging.getLogger(__name__)


def strip_ansi_codes(text: str) -> str:
    """Remove ANSI escape sequences from text."""
    ansi_escape = re.compile(r'\x1b\[[0-9;]*m')
    return ansi_escape.sub('', text)


def extract_output(output: Union[dict, Any]) -> str:
    """Extract readable output from a Jupyter cell output dictionary.

    Args:
        output: The output from a Jupyter cell (dict).

    Returns:
        str: A string representation of the output.
    """
    # Handle lists (common in error tracebacks)
    if isinstance(output, list):
        return '\n'.join(extract_output(item) for item in output)

    # Handle non-dict output
    if not isinstance(output, dict):
        return strip_ansi_codes(str(output))

    output_type = output.get("output_type")

    if output_type == "stream":
        text = output.get("text", "")
        if isinstance(text, list):
            text = ''.join(text)
        return strip_ansi_codes(str(text))

    elif output_type in ["display_data", "execute_result"]:
        data = output.get("data", {})
        if "text/plain" in data:
            plain_text = data["text/plain"]
            return strip_ansi_codes(str(plain_text))
        elif "text/html" in data:
            return "[HTML Output]"
        elif "image/png" in data:
            return "[Image Output (PNG)]"
        else:
            return f"[{output_type} Data: keys={list(data.keys())}]"

    elif output_type == "error":
        traceback = output.get("traceback", [])
        if isinstance(traceback, list):
            clean_traceback = []
            for line in traceback:
                clean_traceback.append(strip_ansi_codes(str(line)))
            return '\n'.join(clean_traceback)
        else:
            return strip_ansi_codes(str(traceback))

    else:
        return f"[Unknown output type: {output_type}]"


def safe_extract_outputs(outputs: Any) -> List[str]:
    """Safely extract all outputs from a cell.

    Args:
        outputs: Cell outputs (list of output dicts)

    Returns:
        list[str]: List of output strings
    """
    if not outputs:
        return []

    result = []

    # Handle list of outputs
    if hasattr(outputs, '__iter__') and not isinstance(outputs, (str, dict)):
        try:
            for output in outputs:
                extracted = extract_output(output)
                if extracted:
                    result.append(extracted)
        except Exception as e:
            result.append(f"[Error extracting output: {str(e)}]")
    else:
        # Handle single output
        extracted = extract_output(outputs)
        if extracted:
            result.append(extracted)

    return result


async def execute_via_execution_stack(
    serverapp: Any,
    kernel_id: str,
    code: str,
    document_id: Optional[str] = None,
    cell_id: Optional[str] = None,
    timeout: int = 300,
    poll_interval: float = 0.1
) -> List[str]:
    """Execute code using ExecutionStack (non-blocking, preferred method).

    This uses the ExecutionStack from jupyter-server-nbmodel extension directly,
    avoiding blocking client.get_iopub_msg() calls. This is the preferred method
    for code execution in JUPYTER_SERVER mode.

    Args:
        serverapp: Jupyter server application instance
        kernel_id: Kernel ID to execute in
        code: Code to execute
        document_id: Optional document ID for RTC integration (format: json:notebook:<file_id>)
        cell_id: Optional cell ID for RTC integration
        timeout: Maximum time to wait for execution (seconds)
        poll_interval: Time between polling for results (seconds)

    Returns:
        List of formatted output strings

    Raises:
        RuntimeError: If jupyter-server-nbmodel extension is not installed
        TimeoutError: If execution exceeds timeout
    """
    if not code or not code.strip():
        return ["[Empty code]"]

    try:
        # Get the ExecutionStack from the jupyter_server_nbmodel extension
        nbmodel_extensions = serverapp.extension_manager.extension_apps.get("jupyter_server_nbmodel", set())
        if not nbmodel_extensions:
            raise RuntimeError("jupyter_server_nbmodel extension not found. Please install it.")

        nbmodel_ext = next(iter(nbmodel_extensions))
        execution_stack = nbmodel_ext._Extension__execution_stack

        # Build metadata for RTC integration if available
        metadata = {}
        if document_id and cell_id:
            metadata = {
                "document_id": document_id,
                "cell_id": cell_id
            }

        # Submit execution request
        logger.info(f"Submitting execution request to kernel {kernel_id}")
        request_id = execution_stack.put(kernel_id, code, metadata)
        logger.info(f"Execution request {request_id} submitted")

        # Poll for results
        start_time = asyncio.get_event_loop().time()
        while True:
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed > timeout:
                raise TimeoutError(f"Execution timed out after {timeout} seconds")

            # Get result (returns None if pending, result dict if complete)
            result = execution_stack.get(kernel_id, request_id)

            if result is not None:
                # Execution complete
                logger.info(f"Execution request {request_id} completed")

                # Check for errors
                if "error" in result:
                    error_info = result["error"]
                    logger.error(f"Execution error: {error_info}")
                    return [f"[ERROR: {error_info.get('ename', 'Unknown')}: {error_info.get('evalue', '')}]"]

                # Check for pending input (shouldn't happen with allow_stdin=False)
                if "input_request" in result:
                    logger.warning("Unexpected input request during execution")
                    return ["[ERROR: Unexpected input request]"]

                # Extract outputs
                outputs = result.get("outputs", [])

                # Parse JSON string if needed (ExecutionStack returns JSON string)
                if isinstance(outputs, str):
                    import json
                    try:
                        outputs = json.loads(outputs)
                    except json.JSONDecodeError:
                        logger.error(f"Failed to parse outputs JSON: {outputs}")
                        return [f"[ERROR: Invalid output format]"]

                if outputs:
                    formatted = safe_extract_outputs(outputs)
                    logger.info(f"Execution completed with {len(formatted)} formatted outputs")
                    return formatted
                else:
                    logger.info("Execution completed with no outputs")
                    return ["[No output generated]"]

            # Still pending, wait before next poll
            await asyncio.sleep(poll_interval)

    except Exception as e:
        logger.error(f"Error executing via ExecutionStack: {e}", exc_info=True)
        return [f"[ERROR: {str(e)}]"]


async def execute_code_with_timeout(
    kernel_manager: Any,
    kernel_id: str,
    code: str,
    timeout_seconds: int = 300,
    serverapp: Optional[Any] = None
) -> List[str]:
    """Execute code in a kernel with timeout.

    This function tries to use ExecutionStack if serverapp is provided,
    otherwise falls back to the legacy blocking method.

    Args:
        kernel_manager: Jupyter kernel manager
        kernel_id: ID of the kernel to execute in
        code: Code to execute
        timeout_seconds: Maximum time to wait
        serverapp: Optional Jupyter ServerApp instance (for ExecutionStack)

    Returns:
        List of output strings
    """
    # Try ExecutionStack first if serverapp is available
    if serverapp is not None:
        try:
            return await execute_via_execution_stack(
                serverapp=serverapp,
                kernel_id=kernel_id,
                code=code,
                timeout=timeout_seconds
            )
        except RuntimeError as e:
            logger.warning(f"ExecutionStack not available, falling back to legacy method: {e}")
            # Fall through to legacy method
        except Exception as e:
            logger.error(f"ExecutionStack failed, falling back to legacy method: {e}")
            # Fall through to legacy method

    # Legacy blocking method (DEPRECATED - causes 300s timeout issues)
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

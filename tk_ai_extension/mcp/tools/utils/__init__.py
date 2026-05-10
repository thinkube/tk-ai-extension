# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Shared utilities for MCP tools."""

from inspect import isawaitable
from typing import Any

from .ydoc_helper import get_jupyter_ydoc, get_notebook_path
from .execution_helper import execute_code_with_timeout, format_outputs


async def cm_call(result: Any) -> Any:
    """Await a contents_manager method result if it's a coroutine.

    Jupytext replaces the default AsyncContentsManager with a synchronous
    TextFileContentsManager. This helper handles both:
        model = await cm_call(contents_manager.get(...))
    """
    return await result if isawaitable(result) else result


__all__ = [
    'get_jupyter_ydoc',
    'get_notebook_path',
    'execute_code_with_timeout',
    'format_outputs',
    'cm_call',
]

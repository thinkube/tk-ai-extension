# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""Contents manager fallback for cell manipulation when YDoc is unavailable.

Used when the notebook is not open in JupyterLab (no YDoc room), e.g.,
when Claude Code calls tools via the MCP bridge.

WARNING: These operations are NOT collaborative — they read/modify/save the
notebook file directly. If the notebook is open in JupyterLab simultaneously,
changes may conflict. The YDoc path should always be tried first.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


async def _get_notebook(contents_manager: Any, notebook_path: str) -> Dict[str, Any]:
    """Read notebook via contents_manager."""
    from . import cm_call
    return await cm_call(contents_manager.get(notebook_path, content=True, type='notebook'))


async def _save_notebook(contents_manager: Any, notebook_path: str, model: Dict[str, Any]) -> None:
    """Save notebook via contents_manager."""
    from . import cm_call
    await cm_call(contents_manager.save(model, notebook_path))


async def list_cells_via_contents(
    contents_manager: Any,
    notebook_path: str
) -> str:
    """List cells using contents_manager (same as backend ListCellsTool)."""
    model = await _get_notebook(contents_manager, notebook_path)
    cells = model.get('content', {}).get('cells', [])

    if not cells:
        return f"Notebook '{notebook_path}' has no cells"

    result = [f"Cells in '{notebook_path}':"]
    result.append("-" * 90)
    result.append("index | exec_count | type      | preview")
    result.append("-" * 90)

    for i, cell in enumerate(cells):
        cell_type = cell.get('cell_type', 'unknown')
        source = cell.get('source', '')
        if isinstance(source, list):
            source = ''.join(source)
        preview = source[:60].replace('\n', ' ')
        if len(source) > 60:
            preview += "..."

        exec_count_str = ""
        if cell_type == "code":
            ec = cell.get('execution_count')
            exec_count_str = f"[{ec}]" if ec is not None else "[-]"

        result.append(f"{i:5d} | {exec_count_str:10s} | {cell_type:9s} | {preview}")

    return "\n".join(result)


async def insert_cell_via_contents(
    contents_manager: Any,
    notebook_path: str,
    cell_index: int,
    cell_type: str = "code",
    source: str = ""
) -> Dict[str, Any]:
    """Insert a cell using contents_manager."""
    try:
        model = await _get_notebook(contents_manager, notebook_path)
        cells = model['content']['cells']

        new_cell = {
            "cell_type": cell_type,
            "source": source,
            "metadata": {},
        }
        if cell_type == "code":
            new_cell["execution_count"] = None
            new_cell["outputs"] = []

        # Clamp index
        idx = min(cell_index, len(cells))
        cells.insert(idx, new_cell)

        await _save_notebook(contents_manager, notebook_path, model)

        return {
            "success": True,
            "cell_index": idx,
            "cell_type": cell_type,
            "message": f"{cell_type.capitalize()} cell inserted at index {idx}"
        }
    except Exception as e:
        logger.error(f"insert_cell_via_contents failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def overwrite_cell_via_contents(
    contents_manager: Any,
    notebook_path: str,
    cell_index: int,
    source: str
) -> Dict[str, Any]:
    """Overwrite a cell's source using contents_manager."""
    try:
        model = await _get_notebook(contents_manager, notebook_path)
        cells = model['content']['cells']

        if cell_index < 0 or cell_index >= len(cells):
            return {
                "success": False,
                "error": f"Cell index {cell_index} out of range. Notebook has {len(cells)} cells"
            }

        old_source = cells[cell_index].get('source', '')
        if isinstance(old_source, list):
            old_source = ''.join(old_source)

        cells[cell_index]['source'] = source

        await _save_notebook(contents_manager, notebook_path, model)

        return {
            "success": True,
            "cell_index": cell_index,
            "cell_type": cells[cell_index].get('cell_type', 'code'),
            "message": f"Cell {cell_index} overwritten successfully",
            "previous_content": old_source
        }
    except Exception as e:
        logger.error(f"overwrite_cell_via_contents failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def delete_cell_via_contents(
    contents_manager: Any,
    notebook_path: str,
    cell_index: int
) -> Dict[str, Any]:
    """Delete a cell using contents_manager."""
    try:
        model = await _get_notebook(contents_manager, notebook_path)
        cells = model['content']['cells']

        if cell_index < 0 or cell_index >= len(cells):
            return {
                "success": False,
                "error": f"Cell index {cell_index} out of range. Notebook has {len(cells)} cells"
            }

        removed = cells.pop(cell_index)
        old_source = removed.get('source', '')
        if isinstance(old_source, list):
            old_source = ''.join(old_source)

        await _save_notebook(contents_manager, notebook_path, model)

        return {
            "success": True,
            "cell_index": cell_index,
            "cell_type": removed.get('cell_type', 'code'),
            "message": f"Cell at index {cell_index} deleted successfully",
            "previous_content": old_source
        }
    except Exception as e:
        logger.error(f"delete_cell_via_contents failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}


async def move_cell_via_contents(
    contents_manager: Any,
    notebook_path: str,
    from_index: int,
    to_index: int
) -> Dict[str, Any]:
    """Move a cell using contents_manager."""
    try:
        model = await _get_notebook(contents_manager, notebook_path)
        cells = model['content']['cells']

        if from_index < 0 or from_index >= len(cells):
            return {
                "success": False,
                "error": f"from_index {from_index} out of range. Notebook has {len(cells)} cells"
            }
        if to_index < 0 or to_index >= len(cells):
            return {
                "success": False,
                "error": f"to_index {to_index} out of range. Notebook has {len(cells)} cells"
            }

        cell = cells.pop(from_index)
        cells.insert(to_index, cell)

        await _save_notebook(contents_manager, notebook_path, model)

        return {
            "success": True,
            "from_index": from_index,
            "to_index": to_index,
            "message": f"Cell moved from index {from_index} to {to_index}"
        }
    except Exception as e:
        logger.error(f"move_cell_via_contents failed: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

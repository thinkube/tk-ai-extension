# tk-ai-extension Improvement Recommendations

**Date:** 2025-11-25
**Based on:** Analysis of Claude Code capabilities and patterns
**Status:** Proposed

---

## Executive Summary

This document outlines 12 improvement recommendations for the tk-ai-extension based on patterns and capabilities observed in Claude Code. These improvements focus on:

- Real-time streaming for better UX
- Subagent architecture for task optimization
- Extensibility via hooks
- Better context management
- Enhanced MCP compliance

---

## Table of Contents

1. [Streaming Responses](#1-streaming-responses)
2. [Subagent Pattern](#2-subagent-pattern)
3. [Hooks System](#3-hooks-system)
4. [Dynamic Context Management](#4-dynamic-context-management)
5. [Tool Result Truncation](#5-tool-result-truncation)
6. [Parallel Tool Execution](#6-parallel-tool-execution)
7. [Plan Mode](#7-plan-mode)
8. [Todo/Progress Tracking](#8-todoprogress-tracking)
9. [MCP Server Enhancements](#9-mcp-server-enhancements)
10. [WebSocket Real-time Updates](#10-websocket-real-time-updates)
11. [Enhanced Error Recovery](#11-enhanced-error-recovery)
12. [CLAUDE.md Support](#12-claudemd-support)

---

## 1. Streaming Responses

**Priority:** HIGH
**Impact:** Immediate UX improvement
**Effort:** Medium

### Current State

The current implementation collects the full response before displaying:

```python
# handlers.py:341-350
await client.query(user_message)
async for message in client.receive_response():
    if isinstance(message, AssistantMessage):
        for block in message.content:
            if isinstance(block, TextBlock):
                response_text += block.text
# Only after loop completes does user see response
```

### Problem

Users see nothing until the entire response is generated, which can take 10-30+ seconds for complex queries. This creates a perception of slowness and uncertainty.

### Proposed Solution

Implement Server-Sent Events (SSE) for real-time streaming:

#### Backend Changes

```python
# New file: tk_ai_extension/handlers_streaming.py

from tornado import web, gen
from tornado.iostream import StreamClosedError
import json

class MCPChatStreamHandler(JupyterHandler):
    """Streaming chat endpoint using SSE."""

    def set_default_headers(self):
        self.set_header('Content-Type', 'text/event-stream')
        self.set_header('Cache-Control', 'no-cache')
        self.set_header('Connection', 'keep-alive')
        self.set_header('X-Accel-Buffering', 'no')  # Disable nginx buffering

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/chat/stream"""
        try:
            body = json.loads(self.request.body.decode('utf-8'))
            user_message = body.get('message')
            notebook_path = body.get('notebook_path')

            # ... setup client ...

            await client.query(user_message)

            # Stream tokens as they arrive
            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            # Send each chunk immediately
                            event_data = json.dumps({
                                'type': 'text',
                                'content': block.text
                            })
                            self.write(f"data: {event_data}\n\n")
                            await self.flush()

                        elif isinstance(block, ToolUseBlock):
                            # Notify frontend of tool usage
                            event_data = json.dumps({
                                'type': 'tool_use',
                                'tool': block.name,
                                'status': 'started'
                            })
                            self.write(f"data: {event_data}\n\n")
                            await self.flush()

            # Send completion event
            self.write(f"data: {json.dumps({'type': 'done'})}\n\n")
            await self.flush()

        except StreamClosedError:
            # Client disconnected
            pass
        except Exception as e:
            error_data = json.dumps({'type': 'error', 'message': str(e)})
            self.write(f"data: {error_data}\n\n")
            await self.flush()
```

#### Frontend Changes

```typescript
// src/api.ts - Add streaming method

export class MCPClient {
  /**
   * Send a chat message with streaming response
   */
  async sendMessageStream(
    message: string,
    notebookPath: string | null,
    onChunk: (chunk: { type: string; content?: string; tool?: string }) => void
  ): Promise<void> {
    const url = URLExt.join(this.baseUrl, 'chat', 'stream');

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...this.getAuthHeaders()
      },
      body: JSON.stringify({
        message,
        notebook_path: notebookPath
      })
    });

    const reader = response.body?.getReader();
    const decoder = new TextDecoder();

    while (reader) {
      const { done, value } = await reader.read();
      if (done) break;

      const text = decoder.decode(value);
      const lines = text.split('\n');

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = JSON.parse(line.slice(6));
          onChunk(data);
        }
      }
    }
  }
}
```

```typescript
// src/components/ChatPanel.tsx - Use streaming

const handleSend = async () => {
  // ... setup ...

  let responseText = '';

  // Add placeholder message that will be updated
  const assistantMessage: IChatMessage = {
    role: 'assistant',
    content: '',
    timestamp: new Date(),
    isStreaming: true
  };
  setMessages(prev => [...prev, assistantMessage]);

  await client.sendMessageStream(
    enhancedMessage,
    activeNotebookPath,
    (chunk) => {
      if (chunk.type === 'text') {
        responseText += chunk.content;
        // Update the last message in place
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            ...updated[updated.length - 1],
            content: responseText
          };
          return updated;
        });
      } else if (chunk.type === 'tool_use') {
        // Show tool usage indicator
        setCurrentTool(chunk.tool);
      } else if (chunk.type === 'done') {
        // Mark streaming complete
        setMessages(prev => {
          const updated = [...prev];
          updated[updated.length - 1].isStreaming = false;
          return updated;
        });
      }
    }
  );
};
```

---

## 2. Subagent Pattern

**Priority:** MEDIUM
**Impact:** Cost optimization, faster responses for simple tasks
**Effort:** Medium

### Current State

All requests use the same Claude model regardless of task complexity.

### Problem

Simple tasks (listing notebooks) use the same expensive model as complex tasks (refactoring code), wasting resources and adding latency.

### Proposed Solution

Implement task-specific subagents with appropriate models:

```python
# New file: tk_ai_extension/agent/subagents.py

from dataclasses import dataclass
from typing import List, Optional
from enum import Enum

class ModelTier(Enum):
    FAST = "claude-3-haiku-20240307"      # Quick, cheap tasks
    BALANCED = "claude-3-5-sonnet-20241022"  # Default
    POWERFUL = "claude-3-opus-20240229"   # Complex reasoning

@dataclass
class SubagentConfig:
    name: str
    description: str
    tools: List[str]
    model: ModelTier
    system_prompt_addon: str = ""

SUBAGENT_CONFIGS = {
    "notebook-explorer": SubagentConfig(
        name="notebook-explorer",
        description="Fast exploration of notebook contents and structure",
        tools=[
            "list_notebooks",
            "list_cells",
            "read_cell",
            "list_kernels",
            "get_kernel_status"
        ],
        model=ModelTier.FAST,
        system_prompt_addon="""
You are a fast notebook explorer. Your job is to quickly find and summarize
notebook content. Be concise and efficient.
"""
    ),

    "code-executor": SubagentConfig(
        name="code-executor",
        description="Execute and debug code cells with careful error handling",
        tools=[
            "execute_cell",
            "execute_cell_async",
            "insert_and_execute",
            "check_execution_status",
            "execute_all_cells",
            "check_all_cells_status"
        ],
        model=ModelTier.BALANCED,
        system_prompt_addon="""
You are a careful code executor. Always check kernel status before execution.
Handle errors gracefully and suggest fixes when execution fails.
"""
    ),

    "notebook-modifier": SubagentConfig(
        name="notebook-modifier",
        description="Complex notebook restructuring and refactoring",
        tools=[
            "insert_cell",
            "delete_cell",
            "move_cell",
            "overwrite_cell",
            "create_notebook"
        ],
        model=ModelTier.POWERFUL,
        system_prompt_addon="""
You are a careful notebook modifier. Plan changes before executing them.
Preserve existing functionality while making improvements.
Consider the impact of cell reordering on variable dependencies.
"""
    ),

    "module-inspector": SubagentConfig(
        name="module-inspector",
        description="Analyze Python environment and package dependencies",
        tools=[
            "list_python_modules",
            "get_module_info",
            "check_module"
        ],
        model=ModelTier.FAST,
        system_prompt_addon="""
You are a Python environment inspector. Help users understand what
packages are available and their capabilities.
"""
    )
}


class SubagentRouter:
    """Route requests to appropriate subagent based on intent."""

    @staticmethod
    def classify_intent(message: str) -> str:
        """Classify user intent to select appropriate subagent."""
        message_lower = message.lower()

        # Exploration patterns
        if any(word in message_lower for word in [
            'list', 'show', 'what', 'find', 'search', 'which', 'how many'
        ]):
            if 'module' in message_lower or 'package' in message_lower:
                return "module-inspector"
            return "notebook-explorer"

        # Execution patterns
        if any(word in message_lower for word in [
            'run', 'execute', 'eval', 'test', 'debug'
        ]):
            return "code-executor"

        # Modification patterns
        if any(word in message_lower for word in [
            'add', 'insert', 'delete', 'remove', 'move', 'change',
            'modify', 'update', 'refactor', 'rewrite', 'create'
        ]):
            return "notebook-modifier"

        # Default to balanced
        return "code-executor"

    @staticmethod
    def get_config(subagent_type: str) -> SubagentConfig:
        """Get configuration for a subagent type."""
        return SUBAGENT_CONFIGS.get(subagent_type, SUBAGENT_CONFIGS["code-executor"])


# Usage in handlers.py
class MCPChatHandler(JupyterHandler):
    async def post(self):
        # ... setup ...

        # Route to appropriate subagent
        subagent_type = SubagentRouter.classify_intent(user_message)
        config = SubagentRouter.get_config(subagent_type)

        self.log.info(f"Routing to subagent: {subagent_type} (model: {config.model.value})")

        # Configure options with subagent-specific settings
        options = ClaudeAgentOptions(
            model=config.model.value,
            allowed_tools=[f"mcp__jupyter__{t}" for t in config.tools],
            system_prompt=base_prompt + config.system_prompt_addon,
            # ... rest of options
        )
```

---

## 3. Hooks System

**Priority:** HIGH
**Impact:** Extensibility, debugging, safety
**Effort:** Medium

### Current State

Tool execution is hardcoded with no extension points.

### Problem

- Can't add logging/monitoring without modifying core code
- Can't add safety checks (e.g., confirm before delete)
- Can't integrate with external systems

### Proposed Solution

Add a hooks system inspired by Claude Code:

```python
# New file: tk_ai_extension/hooks/__init__.py

from typing import Callable, Dict, Any, List, Optional
from dataclasses import dataclass
from enum import Enum
import asyncio

class HookPhase(Enum):
    PRE_TOOL = "pre_tool"
    POST_TOOL = "post_tool"
    PRE_QUERY = "pre_query"
    POST_RESPONSE = "post_response"

@dataclass
class HookResult:
    """Result from a hook execution."""
    proceed: bool = True  # If False, abort the operation
    modified_data: Optional[Dict[str, Any]] = None
    message: Optional[str] = None  # Message to show user

HookFunction = Callable[[str, Dict[str, Any]], HookResult]

class HookManager:
    """Manages lifecycle hooks for tool execution."""

    def __init__(self):
        self._hooks: Dict[HookPhase, List[HookFunction]] = {
            phase: [] for phase in HookPhase
        }
        self._register_default_hooks()

    def _register_default_hooks(self):
        """Register built-in safety hooks."""

        # Safety hook: confirm destructive operations
        async def confirm_destructive(tool_name: str, args: Dict[str, Any]) -> HookResult:
            destructive_tools = ['delete_cell', 'overwrite_cell', 'move_cell']
            if tool_name in destructive_tools:
                # Log the operation (could also prompt user in future)
                return HookResult(
                    proceed=True,
                    message=f"Executing destructive operation: {tool_name}"
                )
            return HookResult(proceed=True)

        self.register(HookPhase.PRE_TOOL, confirm_destructive)

        # Logging hook: log all tool calls
        async def log_tool_call(tool_name: str, args: Dict[str, Any]) -> HookResult:
            import logging
            logging.info(f"[HOOK] Tool call: {tool_name} with args: {list(args.keys())}")
            return HookResult(proceed=True)

        self.register(HookPhase.PRE_TOOL, log_tool_call)

    def register(self, phase: HookPhase, hook: HookFunction):
        """Register a hook for a specific phase."""
        self._hooks[phase].append(hook)

    def unregister(self, phase: HookPhase, hook: HookFunction):
        """Unregister a hook."""
        if hook in self._hooks[phase]:
            self._hooks[phase].remove(hook)

    async def run_hooks(
        self,
        phase: HookPhase,
        context_name: str,
        data: Dict[str, Any]
    ) -> HookResult:
        """Run all hooks for a phase."""
        current_data = data.copy()
        messages = []

        for hook in self._hooks[phase]:
            try:
                result = await hook(context_name, current_data)

                if not result.proceed:
                    return HookResult(
                        proceed=False,
                        message=result.message or f"Hook blocked operation: {hook.__name__}"
                    )

                if result.modified_data:
                    current_data = result.modified_data

                if result.message:
                    messages.append(result.message)

            except Exception as e:
                # Hook errors shouldn't block execution by default
                import logging
                logging.warning(f"Hook {hook.__name__} failed: {e}")

        return HookResult(
            proceed=True,
            modified_data=current_data,
            message="; ".join(messages) if messages else None
        )


# Global hook manager instance
_hook_manager = HookManager()

def get_hook_manager() -> HookManager:
    return _hook_manager


# Example custom hooks users can add:

async def auto_save_hook(tool_name: str, args: Dict[str, Any]) -> HookResult:
    """Auto-save notebook before any modification."""
    modification_tools = ['delete_cell', 'insert_cell', 'overwrite_cell', 'move_cell']
    if tool_name in modification_tools:
        # Trigger notebook save
        # await save_notebook(args.get('notebook_path'))
        pass
    return HookResult(proceed=True)


async def rate_limit_hook(tool_name: str, args: Dict[str, Any]) -> HookResult:
    """Rate limit tool calls."""
    # Implement rate limiting logic
    return HookResult(proceed=True)


async def audit_log_hook(tool_name: str, args: Dict[str, Any]) -> HookResult:
    """Log all tool calls to external audit system."""
    # Send to audit logging service
    return HookResult(proceed=True)
```

#### Integration with tools_registry.py

```python
# Modified tools_registry.py

from .hooks import get_hook_manager, HookPhase

async def tool_executor(args: Dict[str, Any]) -> Dict[str, Any]:
    """Execute tool with hooks."""
    hook_manager = get_hook_manager()

    # Run pre-tool hooks
    pre_result = await hook_manager.run_hooks(
        HookPhase.PRE_TOOL,
        tool_instance.name,
        args
    )

    if not pre_result.proceed:
        return {
            "content": [{
                "type": "text",
                "text": f"Operation blocked: {pre_result.message}"
            }],
            "isError": True
        }

    # Use potentially modified args
    args = pre_result.modified_data or args

    # Execute tool
    result = await tool_instance.execute(...)

    # Run post-tool hooks
    post_result = await hook_manager.run_hooks(
        HookPhase.POST_TOOL,
        tool_instance.name,
        {"args": args, "result": result}
    )

    return {
        "content": [{
            "type": "text",
            "text": str(result)
        }]
    }
```

---

## 4. Dynamic Context Management

**Priority:** HIGH
**Impact:** Better AI responses, fewer tool calls
**Effort:** Medium

### Current State

System prompt is static, built once per request.

### Problem

- AI doesn't know notebook structure without calling tools
- Repeated queries waste tokens re-fetching same context
- No awareness of recent operations

### Proposed Solution

Build dynamic, cached context:

```python
# New file: tk_ai_extension/context/manager.py

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import asyncio

@dataclass
class CellSummary:
    index: int
    cell_type: str
    preview: str  # First 100 chars
    has_output: bool
    execution_count: Optional[int]

@dataclass
class NotebookContext:
    path: str
    name: str
    cell_count: int
    cells: List[CellSummary]
    kernel_status: str
    last_updated: datetime
    recently_accessed_cells: List[int] = field(default_factory=list)
    recently_modified_cells: List[int] = field(default_factory=list)

class ContextManager:
    """Manages dynamic context for AI prompts."""

    def __init__(self, cache_ttl_seconds: int = 60):
        self._cache: Dict[str, NotebookContext] = {}
        self._cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._recent_tool_calls: List[Dict[str, Any]] = []
        self._max_recent_calls = 10

    async def get_notebook_context(
        self,
        notebook_path: str,
        contents_manager,
        kernel_manager,
        force_refresh: bool = False
    ) -> NotebookContext:
        """Get or build notebook context."""

        # Check cache
        if not force_refresh and notebook_path in self._cache:
            cached = self._cache[notebook_path]
            if datetime.now() - cached.last_updated < self._cache_ttl:
                return cached

        # Build fresh context
        context = await self._build_context(
            notebook_path,
            contents_manager,
            kernel_manager
        )
        self._cache[notebook_path] = context
        return context

    async def _build_context(
        self,
        notebook_path: str,
        contents_manager,
        kernel_manager
    ) -> NotebookContext:
        """Build context from notebook."""

        # Load notebook
        model = await asyncio.to_thread(
            contents_manager.get,
            notebook_path,
            content=True
        )

        nb_content = model['content']
        cells = nb_content.get('cells', [])

        # Build cell summaries
        cell_summaries = []
        for i, cell in enumerate(cells):
            source = cell.get('source', '')
            if isinstance(source, list):
                source = ''.join(source)

            cell_summaries.append(CellSummary(
                index=i,
                cell_type=cell.get('cell_type', 'code'),
                preview=source[:100].replace('\n', ' '),
                has_output=bool(cell.get('outputs')),
                execution_count=cell.get('execution_count')
            ))

        # Get kernel status
        kernel_status = "unknown"
        # ... get kernel status logic ...

        return NotebookContext(
            path=notebook_path,
            name=notebook_path.split('/')[-1].replace('.ipynb', ''),
            cell_count=len(cells),
            cells=cell_summaries,
            kernel_status=kernel_status,
            last_updated=datetime.now()
        )

    def record_cell_access(self, notebook_path: str, cell_index: int):
        """Record that a cell was accessed."""
        if notebook_path in self._cache:
            recent = self._cache[notebook_path].recently_accessed_cells
            if cell_index not in recent:
                recent.insert(0, cell_index)
                self._cache[notebook_path].recently_accessed_cells = recent[:5]

    def record_cell_modification(self, notebook_path: str, cell_index: int):
        """Record that a cell was modified."""
        if notebook_path in self._cache:
            recent = self._cache[notebook_path].recently_modified_cells
            if cell_index not in recent:
                recent.insert(0, cell_index)
                self._cache[notebook_path].recently_modified_cells = recent[:5]

    def record_tool_call(self, tool_name: str, args: Dict[str, Any], result: Any):
        """Record a tool call for context."""
        self._recent_tool_calls.insert(0, {
            'tool': tool_name,
            'args': args,
            'timestamp': datetime.now().isoformat(),
            'success': not isinstance(result, Exception)
        })
        self._recent_tool_calls = self._recent_tool_calls[:self._max_recent_calls]

    def build_context_prompt(self, notebook_context: NotebookContext) -> str:
        """Build context section for system prompt."""
        lines = [
            "## Current Notebook Context",
            f"**Notebook:** {notebook_context.name}",
            f"**Cells:** {notebook_context.cell_count}",
            f"**Kernel:** {notebook_context.kernel_status}",
            ""
        ]

        # Add cell structure overview
        lines.append("### Cell Structure")
        for cell in notebook_context.cells[:20]:  # Limit to first 20
            exec_marker = f"[{cell.execution_count}]" if cell.execution_count else "[ ]"
            output_marker = "📊" if cell.has_output else ""
            lines.append(
                f"  {cell.index}. {cell.cell_type:8} {exec_marker:5} {output_marker} {cell.preview[:50]}..."
            )

        if notebook_context.cell_count > 20:
            lines.append(f"  ... and {notebook_context.cell_count - 20} more cells")

        # Add recently accessed context
        if notebook_context.recently_accessed_cells:
            lines.append("")
            lines.append(f"### Recently Accessed Cells: {notebook_context.recently_accessed_cells}")

        if notebook_context.recently_modified_cells:
            lines.append(f"### Recently Modified Cells: {notebook_context.recently_modified_cells}")

        # Add recent tool calls
        if self._recent_tool_calls:
            lines.append("")
            lines.append("### Recent Operations")
            for call in self._recent_tool_calls[:5]:
                status = "✓" if call['success'] else "✗"
                lines.append(f"  {status} {call['tool']}({list(call['args'].keys())})")

        return "\n".join(lines)


# Global context manager
_context_manager = ContextManager()

def get_context_manager() -> ContextManager:
    return _context_manager
```

---

## 5. Tool Result Truncation

**Priority:** MEDIUM
**Impact:** Prevent context overflow, handle large outputs
**Effort:** Low

### Current State

Tool results are returned as-is, potentially very large.

### Problem

- Large cell outputs can overflow context window
- Expensive to process large results
- May contain irrelevant data

### Proposed Solution

```python
# New file: tk_ai_extension/utils/truncation.py

from typing import Any, Dict, Optional
import json

class OutputTruncator:
    """Intelligently truncate tool outputs."""

    DEFAULT_MAX_CHARS = 30000
    DEFAULT_MAX_LINES = 500
    DEFAULT_MAX_ITEMS = 100

    @classmethod
    def truncate(
        cls,
        result: Any,
        max_chars: int = DEFAULT_MAX_CHARS,
        max_lines: int = DEFAULT_MAX_LINES,
        context: Optional[str] = None
    ) -> str:
        """Truncate result to fit within limits."""

        result_str = cls._to_string(result)
        original_len = len(result_str)

        # Check if truncation needed
        if original_len <= max_chars:
            lines = result_str.split('\n')
            if len(lines) <= max_lines:
                return result_str

        # Truncate
        truncated = cls._smart_truncate(result_str, max_chars, max_lines)

        # Add truncation notice
        truncated += f"\n\n... [Output truncated: {original_len:,} chars → {len(truncated):,} chars]"

        if context:
            truncated += f"\n[Context: {context}]"

        return truncated

    @classmethod
    def _to_string(cls, result: Any) -> str:
        """Convert result to string."""
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            return json.dumps(result, indent=2, default=str)
        if isinstance(result, (list, tuple)):
            if len(result) > cls.DEFAULT_MAX_ITEMS:
                return json.dumps(
                    list(result[:cls.DEFAULT_MAX_ITEMS]) +
                    [f"... and {len(result) - cls.DEFAULT_MAX_ITEMS} more items"],
                    indent=2,
                    default=str
                )
            return json.dumps(list(result), indent=2, default=str)
        return str(result)

    @classmethod
    def _smart_truncate(cls, text: str, max_chars: int, max_lines: int) -> str:
        """Smart truncation preserving structure."""
        lines = text.split('\n')

        # First, limit lines
        if len(lines) > max_lines:
            # Keep first and last portions
            head_lines = max_lines // 2
            tail_lines = max_lines - head_lines - 1
            lines = (
                lines[:head_lines] +
                [f"... ({len(lines) - max_lines} lines omitted) ..."] +
                lines[-tail_lines:]
            )

        result = '\n'.join(lines)

        # Then limit chars
        if len(result) > max_chars:
            # Keep first portion
            head_chars = max_chars - 100  # Leave room for notice
            result = result[:head_chars]

            # Try to break at a reasonable point
            last_newline = result.rfind('\n')
            if last_newline > head_chars * 0.8:
                result = result[:last_newline]

        return result

    @classmethod
    def truncate_cell_outputs(cls, outputs: list) -> list:
        """Truncate cell outputs specifically."""
        truncated_outputs = []
        total_size = 0
        max_total = 10000  # Total output limit

        for output in outputs:
            output_str = cls._to_string(output)

            if total_size + len(output_str) > max_total:
                remaining = max_total - total_size
                if remaining > 100:
                    truncated_outputs.append({
                        "output_type": "truncated",
                        "text": output_str[:remaining] + "... [truncated]"
                    })
                break

            truncated_outputs.append(output)
            total_size += len(output_str)

        if len(truncated_outputs) < len(outputs):
            truncated_outputs.append({
                "output_type": "notice",
                "text": f"[{len(outputs) - len(truncated_outputs)} outputs omitted]"
            })

        return truncated_outputs
```

#### Integration

```python
# In tools_registry.py

from .utils.truncation import OutputTruncator

async def tool_executor(args: Dict[str, Any]) -> Dict[str, Any]:
    result = await tool_instance.execute(...)

    # Truncate result
    result_str = OutputTruncator.truncate(
        result,
        context=f"Tool: {tool_instance.name}"
    )

    return {
        "content": [{
            "type": "text",
            "text": result_str
        }]
    }
```

---

## 6. Parallel Tool Execution

**Priority:** MEDIUM
**Impact:** Faster multi-tool operations
**Effort:** Medium

### Current State

Tools execute sequentially, even when independent.

### Problem

Operations like "read cells 1, 3, and 5" execute three separate sequential calls.

### Proposed Solution

```python
# New file: tk_ai_extension/mcp/tools/batch.py

from typing import List, Dict, Any, Tuple
import asyncio
from .base import BaseTool

class BatchExecutor:
    """Execute multiple tool calls in parallel when possible."""

    # Tools that can safely run in parallel
    PARALLELIZABLE_TOOLS = {
        'read_cell',
        'list_cells',
        'list_notebooks',
        'check_module',
        'get_module_info',
        'get_kernel_status'
    }

    # Tools that must run sequentially
    SEQUENTIAL_TOOLS = {
        'execute_cell',
        'insert_cell',
        'delete_cell',
        'move_cell',
        'overwrite_cell'
    }

    @classmethod
    async def execute_batch(
        cls,
        tool_calls: List[Tuple[str, Dict[str, Any]]],
        executor_map: Dict[str, callable]
    ) -> List[Dict[str, Any]]:
        """Execute a batch of tool calls, parallelizing where safe."""

        # Group by parallelizability
        parallel_calls = []
        sequential_calls = []

        for tool_name, args in tool_calls:
            if tool_name in cls.PARALLELIZABLE_TOOLS:
                parallel_calls.append((tool_name, args))
            else:
                sequential_calls.append((tool_name, args))

        results = []

        # Execute parallel calls concurrently
        if parallel_calls:
            parallel_tasks = [
                executor_map[name](args)
                for name, args in parallel_calls
            ]
            parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)
            results.extend(zip(parallel_calls, parallel_results))

        # Execute sequential calls in order
        for name, args in sequential_calls:
            try:
                result = await executor_map[name](args)
                results.append(((name, args), result))
            except Exception as e:
                results.append(((name, args), e))

        return results


# New tool for batch cell reading
class ReadCellsBatchTool(BaseTool):
    """Read multiple cells in parallel."""

    name = "read_cells_batch"
    description = "Read multiple cells from a notebook in parallel. More efficient than multiple read_cell calls."

    input_schema = {
        "type": "object",
        "properties": {
            "notebook_path": {
                "type": "string",
                "description": "Path to the notebook"
            },
            "cell_indices": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "List of cell indices to read"
            }
        },
        "required": ["notebook_path", "cell_indices"]
    }

    async def execute(
        self,
        contents_manager,
        notebook_path: str,
        cell_indices: List[int],
        **kwargs
    ) -> Dict[str, Any]:
        """Read multiple cells in parallel."""

        # Load notebook once
        model = await asyncio.to_thread(
            contents_manager.get,
            notebook_path,
            content=True
        )

        cells = model['content'].get('cells', [])

        results = {}
        for idx in cell_indices:
            if 0 <= idx < len(cells):
                cell = cells[idx]
                results[idx] = {
                    "cell_type": cell.get('cell_type'),
                    "source": cell.get('source'),
                    "outputs": cell.get('outputs', [])[:3],  # Limit outputs
                    "execution_count": cell.get('execution_count')
                }
            else:
                results[idx] = {"error": f"Cell index {idx} out of range"}

        return {
            "success": True,
            "notebook": notebook_path,
            "cells": results
        }
```

---

## 7. Plan Mode

**Priority:** MEDIUM
**Impact:** Safety for complex operations, user control
**Effort:** High

### Current State

All operations execute immediately without preview.

### Problem

Complex operations (refactoring, restructuring) can't be reviewed before execution.

### Proposed Solution

```python
# New file: tk_ai_extension/planning/__init__.py

from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime
import uuid

class PlanStatus(Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

@dataclass
class PlanStep:
    id: str
    tool: str
    args: Dict[str, Any]
    description: str
    status: str = "pending"
    result: Optional[Any] = None
    error: Optional[str] = None

@dataclass
class ExecutionPlan:
    id: str
    notebook_path: str
    description: str
    steps: List[PlanStep]
    status: PlanStatus
    created_at: datetime
    approved_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    @classmethod
    def create(cls, notebook_path: str, description: str) -> 'ExecutionPlan':
        return cls(
            id=str(uuid.uuid4()),
            notebook_path=notebook_path,
            description=description,
            steps=[],
            status=PlanStatus.DRAFT,
            created_at=datetime.now()
        )

    def add_step(self, tool: str, args: Dict[str, Any], description: str):
        step = PlanStep(
            id=str(uuid.uuid4()),
            tool=tool,
            args=args,
            description=description
        )
        self.steps.append(step)

    def to_markdown(self) -> str:
        """Render plan as markdown for review."""
        lines = [
            f"# Execution Plan",
            f"**ID:** `{self.id}`",
            f"**Notebook:** {self.notebook_path}",
            f"**Description:** {self.description}",
            f"**Status:** {self.status.value}",
            "",
            "## Steps",
            ""
        ]

        for i, step in enumerate(self.steps, 1):
            status_icon = {
                "pending": "⏳",
                "running": "🔄",
                "completed": "✅",
                "failed": "❌"
            }.get(step.status, "❓")

            lines.append(f"### {i}. {step.description} {status_icon}")
            lines.append(f"**Tool:** `{step.tool}`")
            lines.append(f"**Args:** `{step.args}`")
            if step.result:
                lines.append(f"**Result:** {step.result}")
            if step.error:
                lines.append(f"**Error:** {step.error}")
            lines.append("")

        return "\n".join(lines)


class PlanManager:
    """Manage execution plans."""

    def __init__(self):
        self._plans: Dict[str, ExecutionPlan] = {}

    def create_plan(self, notebook_path: str, description: str) -> ExecutionPlan:
        plan = ExecutionPlan.create(notebook_path, description)
        self._plans[plan.id] = plan
        return plan

    def get_plan(self, plan_id: str) -> Optional[ExecutionPlan]:
        return self._plans.get(plan_id)

    def approve_plan(self, plan_id: str) -> bool:
        plan = self._plans.get(plan_id)
        if plan and plan.status == PlanStatus.PENDING_APPROVAL:
            plan.status = PlanStatus.APPROVED
            plan.approved_at = datetime.now()
            return True
        return False

    def cancel_plan(self, plan_id: str) -> bool:
        plan = self._plans.get(plan_id)
        if plan and plan.status in [PlanStatus.DRAFT, PlanStatus.PENDING_APPROVAL]:
            plan.status = PlanStatus.CANCELLED
            return True
        return False

    async def execute_plan(
        self,
        plan_id: str,
        tool_executors: Dict[str, callable]
    ) -> ExecutionPlan:
        """Execute an approved plan."""
        plan = self._plans.get(plan_id)
        if not plan:
            raise ValueError(f"Plan {plan_id} not found")

        if plan.status != PlanStatus.APPROVED:
            raise ValueError(f"Plan must be approved before execution")

        plan.status = PlanStatus.EXECUTING

        try:
            for step in plan.steps:
                step.status = "running"

                try:
                    executor = tool_executors.get(step.tool)
                    if not executor:
                        raise ValueError(f"Unknown tool: {step.tool}")

                    result = await executor(step.args)
                    step.result = result
                    step.status = "completed"

                except Exception as e:
                    step.error = str(e)
                    step.status = "failed"
                    plan.status = PlanStatus.FAILED
                    return plan

            plan.status = PlanStatus.COMPLETED
            plan.completed_at = datetime.now()

        except Exception as e:
            plan.status = PlanStatus.FAILED

        return plan


# Global plan manager
_plan_manager = PlanManager()

def get_plan_manager() -> PlanManager:
    return _plan_manager
```

#### New Handlers

```python
# Add to handlers.py

class CreatePlanHandler(JupyterHandler):
    """Create a new execution plan."""

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/plan/create"""
        body = json.loads(self.request.body.decode('utf-8'))

        plan_manager = get_plan_manager()
        plan = plan_manager.create_plan(
            notebook_path=body['notebook_path'],
            description=body['description']
        )

        self.finish({
            "plan_id": plan.id,
            "status": plan.status.value
        })


class ApprovePlanHandler(JupyterHandler):
    """Approve a plan for execution."""

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/plan/approve"""
        body = json.loads(self.request.body.decode('utf-8'))

        plan_manager = get_plan_manager()
        success = plan_manager.approve_plan(body['plan_id'])

        self.finish({"success": success})


class ExecutePlanHandler(JupyterHandler):
    """Execute an approved plan."""

    @web.authenticated
    async def post(self):
        """POST /api/tk-ai/mcp/plan/execute"""
        body = json.loads(self.request.body.decode('utf-8'))

        plan_manager = get_plan_manager()
        tools = get_registered_tools()

        executors = {
            name: data['direct_executor']
            for name, data in tools.items()
        }

        plan = await plan_manager.execute_plan(body['plan_id'], executors)

        self.finish({
            "plan_id": plan.id,
            "status": plan.status.value,
            "markdown": plan.to_markdown()
        })
```

---

## 8. Todo/Progress Tracking

**Priority:** LOW
**Impact:** Better UX for long operations
**Effort:** Medium

### Proposed Solution

```typescript
// src/components/TodoTracker.tsx

import React from 'react';

export interface ITodoItem {
  id: string;
  content: string;
  activeForm: string;
  status: 'pending' | 'in_progress' | 'completed' | 'error';
}

interface ITodoTrackerProps {
  todos: ITodoItem[];
}

export const TodoTracker: React.FC<ITodoTrackerProps> = ({ todos }) => {
  if (todos.length === 0) return null;

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'pending': return '⏳';
      case 'in_progress': return '🔄';
      case 'completed': return '✅';
      case 'error': return '❌';
      default: return '❓';
    }
  };

  const currentTask = todos.find(t => t.status === 'in_progress');
  const completedCount = todos.filter(t => t.status === 'completed').length;

  return (
    <div className="tk-todo-tracker">
      {currentTask && (
        <div className="tk-current-task">
          <span className="tk-task-icon">🔄</span>
          <span className="tk-task-text">{currentTask.activeForm}</span>
        </div>
      )}

      <div className="tk-progress">
        <div
          className="tk-progress-bar"
          style={{ width: `${(completedCount / todos.length) * 100}%` }}
        />
      </div>

      <div className="tk-todo-list">
        {todos.map(todo => (
          <div key={todo.id} className={`tk-todo-item tk-status-${todo.status}`}>
            <span className="tk-todo-icon">{getStatusIcon(todo.status)}</span>
            <span className="tk-todo-content">{todo.content}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
```

---

## 9. MCP Server Enhancements

**Priority:** LOW
**Impact:** Better MCP compliance, more capabilities
**Effort:** Medium

### Add MCP Resources

```python
# New file: tk_ai_extension/mcp/resources.py

from typing import List, Dict, Any
from dataclasses import dataclass

@dataclass
class MCPResource:
    uri: str
    name: str
    description: str
    mimeType: str

class ResourceManager:
    """Manage MCP resources (notebooks as resources)."""

    def __init__(self, contents_manager):
        self.contents_manager = contents_manager

    async def list_resources(self, path: str = "") -> List[MCPResource]:
        """List available notebook resources."""
        resources = []

        model = self.contents_manager.get(path, content=True)

        for item in model.get('content', []):
            if item['type'] == 'notebook':
                resources.append(MCPResource(
                    uri=f"notebook://{item['path']}",
                    name=item['name'],
                    description=f"Jupyter notebook: {item['name']}",
                    mimeType="application/x-ipynb+json"
                ))

        return resources

    async def read_resource(self, uri: str) -> Dict[str, Any]:
        """Read a resource by URI."""
        if uri.startswith("notebook://"):
            path = uri[11:]  # Remove "notebook://"
            model = self.contents_manager.get(path, content=True)
            return {
                "uri": uri,
                "mimeType": "application/x-ipynb+json",
                "content": model['content']
            }

        raise ValueError(f"Unknown resource URI: {uri}")
```

### Add MCP Prompts

```python
# New file: tk_ai_extension/mcp/prompts.py

from typing import Dict, List

MCP_PROMPTS = {
    "debug_cell": {
        "name": "debug_cell",
        "description": "Analyze a cell for errors and suggest fixes",
        "arguments": [
            {
                "name": "cell_index",
                "description": "Index of the cell to debug",
                "required": True
            }
        ],
        "template": """Analyze cell {cell_index} for potential errors:
1. Check for syntax errors
2. Look for undefined variables
3. Identify potential runtime errors
4. Suggest improvements

First read the cell, then provide your analysis."""
    },

    "optimize_notebook": {
        "name": "optimize_notebook",
        "description": "Review notebook and suggest performance improvements",
        "arguments": [],
        "template": """Review this notebook and suggest optimizations:
1. Identify slow operations
2. Find redundant calculations
3. Suggest caching opportunities
4. Recommend better data structures

List all cells and analyze each one."""
    },

    "document_cells": {
        "name": "document_cells",
        "description": "Add documentation to all code cells",
        "arguments": [],
        "template": """Add documentation comments to all code cells:
1. List all cells
2. For each code cell without documentation, add a markdown cell above it
3. Document the purpose, inputs, and outputs of each code section"""
    },

    "explain_notebook": {
        "name": "explain_notebook",
        "description": "Explain what the notebook does",
        "arguments": [],
        "template": """Explain this notebook:
1. What is its overall purpose?
2. What data does it process?
3. What are the key outputs?
4. How do the cells relate to each other?

Read all cells and provide a comprehensive explanation."""
    }
}

def get_prompt(name: str, **kwargs) -> str:
    """Get a prompt template with arguments filled in."""
    prompt_config = MCP_PROMPTS.get(name)
    if not prompt_config:
        raise ValueError(f"Unknown prompt: {name}")

    return prompt_config['template'].format(**kwargs)
```

---

## 10. WebSocket Real-time Updates

**Priority:** HIGH
**Impact:** Better UX, remove polling
**Effort:** High

### Proposed Solution

```python
# New file: tk_ai_extension/handlers_websocket.py

from tornado.websocket import WebSocketHandler
from tornado import gen
import json
import asyncio

class MCPWebSocketHandler(WebSocketHandler):
    """WebSocket handler for real-time communication."""

    clients = set()

    def check_origin(self, origin):
        # Allow same-origin requests
        return True

    def open(self):
        MCPWebSocketHandler.clients.add(self)
        self.notebook_path = None
        self.write_message(json.dumps({
            "type": "connected",
            "message": "WebSocket connection established"
        }))

    def on_close(self):
        MCPWebSocketHandler.clients.discard(self)

    async def on_message(self, message):
        data = json.loads(message)
        msg_type = data.get('type')

        if msg_type == 'subscribe':
            # Subscribe to notebook updates
            self.notebook_path = data.get('notebook_path')
            await self.send_json({
                "type": "subscribed",
                "notebook_path": self.notebook_path
            })

        elif msg_type == 'chat':
            # Handle chat message with streaming
            await self.handle_chat(data)

        elif msg_type == 'execute_cell':
            # Execute cell with progress updates
            await self.handle_execute(data)

    async def handle_chat(self, data):
        """Handle chat with streaming response."""
        message = data.get('message')
        notebook_path = data.get('notebook_path') or self.notebook_path

        # Send acknowledgment
        await self.send_json({
            "type": "chat_started",
            "message_id": data.get('id')
        })

        # Stream response
        # ... integrate with Claude Agent SDK streaming ...

        async for chunk in stream_claude_response(message, notebook_path):
            await self.send_json({
                "type": "chat_chunk",
                "content": chunk
            })

        await self.send_json({
            "type": "chat_complete"
        })

    async def handle_execute(self, data):
        """Handle cell execution with progress updates."""
        cell_index = data.get('cell_index')

        await self.send_json({
            "type": "execution_started",
            "cell_index": cell_index
        })

        # Execute and stream progress
        # ...

        await self.send_json({
            "type": "execution_complete",
            "cell_index": cell_index,
            "outputs": []
        })

    async def send_json(self, data):
        """Send JSON message."""
        try:
            self.write_message(json.dumps(data))
        except Exception as e:
            print(f"WebSocket send error: {e}")

    @classmethod
    async def broadcast(cls, message: dict, notebook_path: str = None):
        """Broadcast message to all connected clients."""
        for client in cls.clients:
            if notebook_path is None or client.notebook_path == notebook_path:
                await client.send_json(message)
```

---

## 11. Enhanced Error Recovery

**Priority:** MEDIUM
**Impact:** Better reliability
**Effort:** Medium

### Proposed Solution

```python
# New file: tk_ai_extension/resilience/__init__.py

import asyncio
from typing import TypeVar, Callable, Optional
from functools import wraps

T = TypeVar('T')

class RetryConfig:
    def __init__(
        self,
        max_retries: int = 3,
        initial_delay: float = 1.0,
        max_delay: float = 30.0,
        exponential_base: float = 2.0,
        retryable_exceptions: tuple = (Exception,)
    ):
        self.max_retries = max_retries
        self.initial_delay = initial_delay
        self.max_delay = max_delay
        self.exponential_base = exponential_base
        self.retryable_exceptions = retryable_exceptions


def with_retry(config: RetryConfig = None):
    """Decorator for retry logic."""
    if config is None:
        config = RetryConfig()

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            delay = config.initial_delay

            for attempt in range(config.max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except config.retryable_exceptions as e:
                    last_exception = e

                    if attempt < config.max_retries:
                        await asyncio.sleep(delay)
                        delay = min(
                            delay * config.exponential_base,
                            config.max_delay
                        )

            raise last_exception

        return wrapper
    return decorator


class CircuitBreaker:
    """Circuit breaker pattern for external services."""

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 60.0
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.last_failure_time = None
        self.state = "closed"  # closed, open, half-open

    def can_execute(self) -> bool:
        if self.state == "closed":
            return True

        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
                return True
            return False

        # half-open
        return True

    def record_success(self):
        self.failures = 0
        self.state = "closed"

    def record_failure(self):
        self.failures += 1
        self.last_failure_time = asyncio.get_event_loop().time()

        if self.failures >= self.failure_threshold:
            self.state = "open"

    def _should_attempt_reset(self) -> bool:
        if self.last_failure_time is None:
            return True

        elapsed = asyncio.get_event_loop().time() - self.last_failure_time
        return elapsed >= self.recovery_timeout


class GracefulDegradation:
    """Provide fallback responses when services fail."""

    @staticmethod
    def kernel_unavailable(operation: str) -> dict:
        return {
            "success": False,
            "error": "Kernel unavailable",
            "suggestion": "Try restarting the kernel with restart_kernel tool",
            "fallback": True,
            "operation": operation
        }

    @staticmethod
    def notebook_not_found(path: str) -> dict:
        return {
            "success": False,
            "error": f"Notebook not found: {path}",
            "suggestion": "Use list_notebooks to see available notebooks",
            "fallback": True
        }

    @staticmethod
    def cell_index_invalid(index: int, max_index: int) -> dict:
        return {
            "success": False,
            "error": f"Cell index {index} is out of range (0-{max_index})",
            "suggestion": "Use list_cells to see valid cell indices",
            "fallback": True
        }
```

---

## 12. CLAUDE.md Support

**Priority:** LOW
**Impact:** User customization
**Effort:** Low

### Current State

Using `setting_sources=["project"]` but limited customization.

### Proposed Enhancement

```python
# New file: tk_ai_extension/config/claude_md.py

from pathlib import Path
from typing import Optional, Dict, Any
import yaml

class ClaudeMdLoader:
    """Load and parse CLAUDE.md files for notebook customization."""

    @staticmethod
    async def load_instructions(notebook_path: str) -> Optional[str]:
        """Load CLAUDE.md instructions for a notebook."""
        notebook_dir = Path(notebook_path).parent

        # Check multiple locations
        locations = [
            notebook_dir / "CLAUDE.md",
            notebook_dir / ".claude" / "instructions.md",
            Path.home() / "thinkube" / "notebooks" / "CLAUDE.md"
        ]

        for location in locations:
            if location.exists():
                return location.read_text()

        return None

    @staticmethod
    async def load_settings(notebook_path: str) -> Dict[str, Any]:
        """Load .claude/settings.json for a notebook."""
        notebook_dir = Path(notebook_path).parent
        settings_path = notebook_dir / ".claude" / "settings.json"

        if settings_path.exists():
            import json
            return json.loads(settings_path.read_text())

        return {}

    @staticmethod
    async def load_notebook_metadata_instructions(
        notebook_path: str,
        contents_manager
    ) -> Optional[str]:
        """Load instructions from notebook metadata."""
        try:
            model = contents_manager.get(notebook_path, content=True)
            metadata = model['content'].get('metadata', {})
            return metadata.get('claude_instructions')
        except:
            return None

    @classmethod
    async def build_custom_instructions(
        cls,
        notebook_path: str,
        contents_manager
    ) -> str:
        """Build combined custom instructions from all sources."""
        instructions = []

        # 1. Load from CLAUDE.md file
        file_instructions = await cls.load_instructions(notebook_path)
        if file_instructions:
            instructions.append(f"## User Instructions (CLAUDE.md)\n{file_instructions}")

        # 2. Load from notebook metadata
        metadata_instructions = await cls.load_notebook_metadata_instructions(
            notebook_path,
            contents_manager
        )
        if metadata_instructions:
            instructions.append(f"## Notebook Instructions\n{metadata_instructions}")

        # 3. Load settings
        settings = await cls.load_settings(notebook_path)
        if settings:
            if settings.get('preferred_model'):
                instructions.append(f"Preferred model: {settings['preferred_model']}")
            if settings.get('max_tokens'):
                instructions.append(f"Max tokens: {settings['max_tokens']}")

        return "\n\n".join(instructions) if instructions else ""
```

---

## Implementation Priority

| Priority | Improvement | Effort | Impact |
|----------|-------------|--------|--------|
| 1 | Streaming Responses | Medium | High |
| 2 | WebSocket Updates | High | High |
| 3 | Hooks System | Medium | High |
| 4 | Dynamic Context | Medium | High |
| 5 | Subagent Pattern | Medium | Medium |
| 6 | Error Recovery | Medium | Medium |
| 7 | Plan Mode | High | Medium |
| 8 | Tool Truncation | Low | Medium |
| 9 | Parallel Execution | Medium | Medium |
| 10 | Todo Tracking | Medium | Low |
| 11 | MCP Enhancements | Medium | Low |
| 12 | CLAUDE.md Support | Low | Low |

---

## Next Steps

1. Review and approve priority items
2. Create GitHub issues for each improvement
3. Implement in priority order
4. Test each improvement in isolation
5. Integration testing
6. Documentation updates
7. Release new version

---

**Document created by Claude Code analysis**
**Date:** 2025-11-25

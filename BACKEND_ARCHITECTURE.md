# Backend Architecture - tk-ai-extension

This document describes the backend architecture of tk-ai-extension, focusing on the notebook management and code execution systems.

## Overview

tk-ai-extension provides Thinky (AI assistant) with direct access to Jupyter notebooks through MCP (Model Context Protocol) tools. The system operates in JUPYTER_SERVER mode, where tools have direct access to Jupyter managers rather than making HTTP requests.

## Core Components

### 1. NotebookManager

**Location**: `tk_ai_extension/notebook_manager.py`

**Purpose**: Centralized tracking of active notebooks and their associated kernels.

**Key Features**:
- Maps user-friendly notebook names to paths and kernel IDs
- Maintains "current notebook" pointer for operations
- Simplified for local-only operation (no HTTP/WebSocket)

**API**:
```python
# Add a notebook to tracking
notebook_manager.add_notebook(name, kernel_info, path)

# Switch current notebook
notebook_manager.set_current_notebook(name)

# Get current notebook info
current_path = notebook_manager.get_current_notebook_path()
current_kernel_id = notebook_manager.get_current_kernel_id()
```

**Use Case**: Solves the "which notebook?" problem - Thinky must explicitly connect to notebooks before operating on them.

### 2. use_notebook Tool

**Location**: `tk_ai_extension/mcp/tools/use_notebook.py`

**Purpose**: Allows Thinky to explicitly connect to notebooks and their kernels.

**Workflow**:
1. Validates notebook path exists (or parent exists for create mode)
2. Creates new notebook if `mode="create"`
3. Starts new kernel or connects to existing kernel
4. **Waits for kernel to be ready** (critical - kernels take time to start)
5. Creates Jupyter session to link kernel with notebook
6. Adds notebook to NotebookManager
7. Sets as current notebook

**Key Implementation Details**:
```python
# Kernel readiness wait (lines 178-201)
max_wait_time = 30  # seconds
wait_interval = 0.5
kernel_ready = False

while elapsed < max_wait_time:
    try:
        kernel_model = kernel_manager.get_kernel(kernel_id)
        if kernel_model is not None:
            # Check if ready by getting connection info
            kernel_manager.get_connection_info(kernel_id)
            kernel_ready = True
            break
    except:
        pass  # Still starting

    await asyncio.sleep(wait_interval)
    elapsed += wait_interval
```

**Session Creation** (critical for JupyterLab UI):
```python
session_dict = await session_manager.create_session(
    path=notebook_path,
    kernel_id=kernel_id,
    type="notebook",
    name=notebook_path
)
```

### 3. ExecutionStack Integration

**Location**: `tk_ai_extension/mcp/tools/utils/execution_helper.py`

**Problem Solved**: The original implementation used blocking `client.get_iopub_msg()` calls that caused 300-second timeout issues.

**Solution**: Use jupyter-server-nbmodel's ExecutionStack for non-blocking execution.

#### execute_via_execution_stack()

**How It Works**:
1. Gets ExecutionStack from jupyter-server-nbmodel extension
2. Submits execution request (returns immediately with request_id)
3. Polls for results with configurable interval (default 0.1s)
4. Returns when execution completes or timeout reached

**Key Code**:
```python
# Submit execution (non-blocking)
request_id = execution_stack.put(kernel_id, code, metadata)

# Poll for results
while True:
    result = execution_stack.get(kernel_id, request_id)
    if result is not None:
        # Execution complete - extract outputs
        outputs = result.get("outputs", [])
        return safe_extract_outputs(outputs)

    # Still pending
    await asyncio.sleep(poll_interval)
```

**Advantages**:
- **Non-blocking**: No waiting on iopub messages
- **Timeout control**: Explicit timeout with clean interrupt
- **RTC integration**: Supports collaborative editing via document_id/cell_id
- **Error handling**: Clear error vs success paths

#### Fallback Mechanism

```python
async def execute_code_with_timeout(..., serverapp=None):
    # Try ExecutionStack first if serverapp available
    if serverapp is not None:
        try:
            return await execute_via_execution_stack(...)
        except RuntimeError as e:
            logger.warning("ExecutionStack not available, falling back...")

    # Legacy blocking method (DEPRECATED)
    # Uses client.get_iopub_msg() with thread pool executor
```

### 4. Manager Propagation

**Problem**: Tools need access to serverapp for ExecutionStack, but tools are registered at startup.

**Solution**: Global manager registry passed through tool execution chain.

**Flow**:
```
extension.py (startup)
  ↓ set_jupyter_managers(serverapp=self.serverapp)
tools_registry.py (_jupyter_managers global dict)
  ↓ tool_executor wrapper
tool.execute(serverapp=_jupyter_managers.get('serverapp'))
  ↓
execute_code_with_timeout(serverapp=serverapp)
  ↓
execute_via_execution_stack(serverapp)
```

**Implementation**:
```python
# extension.py initialization
set_jupyter_managers(
    contents_manager,
    kernel_manager,
    kernel_spec_manager,
    session_manager,
    notebook_manager,
    self.serverapp  # Pass serverapp for ExecutionStack
)

# tools_registry.py - tool executor wrapper
result = await tool_instance.execute(
    contents_manager=_jupyter_managers.get('contents_manager'),
    kernel_manager=_jupyter_managers.get('kernel_manager'),
    kernel_spec_manager=_jupyter_managers.get('kernel_spec_manager'),
    session_manager=_jupyter_managers.get('session_manager'),
    notebook_manager=_jupyter_managers.get('notebook_manager'),
    serverapp=_jupyter_managers.get('serverapp'),
    **args
)
```

### 5. BaseTool Signature

**Location**: `tk_ai_extension/mcp/tools/base.py`

All tools inherit from BaseTool and implement this signature:

```python
@abstractmethod
async def execute(
    self,
    contents_manager: Any,
    kernel_manager: Any,
    kernel_spec_manager: Optional[Any] = None,
    session_manager: Optional[Any] = None,
    notebook_manager: Optional[Any] = None,
    serverapp: Optional[Any] = None,
    **kwargs
) -> Any:
    """Execute the tool logic with direct manager access."""
    pass
```

**Manager Usage**:
- `contents_manager`: File operations (read/write notebooks)
- `kernel_manager`: Kernel lifecycle (start/stop/interrupt)
- `kernel_spec_manager`: Available kernel specs
- `session_manager`: Create kernel-notebook sessions
- `notebook_manager`: Track active notebooks
- `serverapp`: Access ExecutionStack

### 6. Output Extraction

**Location**: `tk_ai_extension/mcp/tools/utils/execution_helper.py`

Handles all Jupyter output types consistently.

**Output Types Supported**:
- `stream`: stdout/stderr text
- `execute_result`: Code execution results with data dict
- `display_data`: Rich display outputs (HTML, images, etc.)
- `error`: Exception tracebacks

**Key Functions**:

```python
def extract_output(output: Union[dict, Any]) -> str:
    """Extract readable output from Jupyter output dict."""
    output_type = output.get("output_type")

    if output_type == "stream":
        return strip_ansi_codes(output.get("text", ""))
    elif output_type in ["display_data", "execute_result"]:
        data = output.get("data", {})
        return strip_ansi_codes(data.get("text/plain", ""))
    elif output_type == "error":
        traceback = output.get("traceback", [])
        return '\n'.join(strip_ansi_codes(line) for line in traceback)

def safe_extract_outputs(outputs: Any) -> List[str]:
    """Safely extract all outputs, handling lists and errors."""
    result = []
    for output in outputs:
        extracted = extract_output(output)
        if extracted:
            result.append(extracted)
    return result
```

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Frontend (ChatPanel.tsx)                                     │
│ - Sends user messages to /api/tk-ai/mcp/chat               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ MCPChatHandler (handlers.py)                                │
│ - Loads secrets (.secrets.env)                              │
│ - Creates ClaudeSDKClient with MCP server                   │
│ - Passes query to Claude Agent SDK                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Claude Agent SDK                                            │
│ - Receives user message                                     │
│ - Decides which tools to call                               │
│ - Returns formatted response                                │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ tools_registry.py                                           │
│ - Stores _jupyter_managers (global)                         │
│ - tool_executor wrapper adds managers to all tool calls     │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Tool Implementation (e.g., use_notebook, execute_ipython)   │
│ - Receives all managers as parameters                       │
│ - Uses notebook_manager for notebook tracking               │
│ - Uses serverapp for ExecutionStack access                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ execute_via_execution_stack()                               │
│ - Accesses jupyter-server-nbmodel extension                 │
│ - Submits execution request (non-blocking)                  │
│ - Polls for results                                         │
│ - Extracts and formats outputs                              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ↓
┌─────────────────────────────────────────────────────────────┐
│ Jupyter Kernel                                              │
│ - Executes code                                             │
│ - Sends outputs to ExecutionStack                           │
└─────────────────────────────────────────────────────────────┘
```

## Tool Categories

### Basic Notebook Operations
- `list_notebooks`: List available notebooks in directory
- `list_cells`: List cells in a notebook
- `read_cell`: Read cell source code
- `create_notebook`: Create new notebook

### Notebook Connection
- `use_notebook`: **Connect to notebook** (must be called first!)

### Kernel Management
- `list_kernels`: List available kernel specs
- `list_running_kernels`: List active kernels
- `get_kernel_status`: Check kernel state
- `restart_kernel`: Restart kernel
- `interrupt_kernel`: Interrupt execution

### Code Execution
- `execute_ipython`: Execute code without modifying notebook
- `execute_cell`: Execute existing cell by index
- `insert_and_execute_cell`: Insert new cell and execute

### Cell Manipulation
- `insert_cell`: Add new cell
- `delete_cell`: Remove cell
- `overwrite_cell`: Replace cell content
- `move_cell`: Reorder cells

## Key Design Decisions

### 1. Explicit Notebook Connection
**Decision**: Require explicit `use_notebook` call before operations.

**Rationale**:
- Auto-detection doesn't work reliably in single-user environment
- Makes notebook context explicit to AI assistant
- Allows managing multiple notebooks simultaneously
- Clearer error messages when notebook not connected

### 2. ExecutionStack over Direct Client
**Decision**: Use ExecutionStack when available, fall back to direct client.

**Rationale**:
- ExecutionStack is non-blocking (avoids 300s timeout)
- Better integration with jupyter-server-nbmodel
- Supports collaborative editing (RTC)
- Cleaner error handling

**Trade-off**: Requires jupyter-server-nbmodel extension installed.

### 3. Global Manager Registry
**Decision**: Store managers in global dict in tools_registry.py.

**Rationale**:
- Tools registered at extension startup (before request handling)
- Can't pass managers at registration time
- Extension creates managers once, tools use many times
- Wrapper function adds managers to each tool call

**Alternative Considered**: Pass managers in tool registration - rejected because tools are singleton instances.

### 4. Kernel Readiness Wait
**Decision**: Wait up to 30s for kernel to be ready after start.

**Rationale**:
- `start_kernel()` returns immediately but kernel takes time to start
- Executing on unready kernel causes failures
- 30s is reasonable (most kernels ready in 2-5s)
- Log warning if not ready after 30s but continue

**Implementation**: Poll `get_connection_info()` every 0.5s.

### 5. Session Creation for UI Integration
**Decision**: Always create Jupyter session when connecting notebook.

**Rationale**:
- JupyterLab UI needs session to show kernel-notebook connection
- Without session, notebook appears disconnected in UI
- Session links kernel lifecycle to notebook
- Allows user to see what Thinky is doing

## Common Issues and Solutions

### Issue: 300-second timeout on code execution
**Cause**: Blocking `client.get_iopub_msg()` call in legacy execution method.

**Solution**: Use `execute_via_execution_stack()` which polls non-blockingly.

**How to Verify**: Check logs for "Submitting execution request to kernel" message.

### Issue: Notebook not found in NotebookManager
**Cause**: User didn't call `use_notebook` before executing code.

**Solution**: Add proactive error message in execution tools:
```python
if not notebook_manager or notebook_manager.is_empty():
    return {"error": "No notebook connected. Please use the use_notebook tool first."}
```

### Issue: Kernel not ready immediately after start
**Cause**: Kernel process takes time to initialize (2-5 seconds typical).

**Solution**: Kernel readiness wait loop in `use_notebook` tool (lines 178-201).

**Verify**: Check logs for "Kernel 'xxx' is ready (took X.Xs)" message.

### Issue: jupyter-server-nbmodel not installed
**Cause**: Extension missing from environment.

**Solution**: ExecutionStack automatically falls back to legacy method. Install nbmodel:
```bash
pip install jupyter-server-nbmodel
```

## Testing Strategy

### Unit Testing (TODO)
- Test NotebookManager add/remove/switch operations
- Test output extraction for all Jupyter output types
- Test kernel readiness wait with mock kernel_manager

### Integration Testing
1. **use_notebook workflow**:
   - Create new notebook → verify exists
   - Connect to notebook → verify kernel started
   - Switch between notebooks → verify current_notebook changes

2. **Code execution**:
   - Execute simple code → verify output captured
   - Execute long-running code → verify no timeout
   - Execute error code → verify traceback extracted

3. **Session integration**:
   - Connect notebook → verify session created
   - Check JupyterLab UI → verify notebook shows connected kernel

### Manual Testing Checklist
- [ ] Start tk-ai-extension → verify MCP tools registered
- [ ] Ask Thinky to use a notebook → verify use_notebook called
- [ ] Ask Thinky to execute code → verify ExecutionStack used
- [ ] Check logs for "Submitting execution request" message
- [ ] Verify no 300s timeouts in execution
- [ ] Check JupyterLab UI shows kernel connected to notebook

## Future Enhancements

### Short-term
1. Add proactive error messages to execution tools
2. Update tool descriptions to mention use_notebook requirement
3. Add unuse_notebook tool to disconnect notebooks
4. Add list_managed_notebooks tool to show connected notebooks

### Medium-term
1. Support for notebook-specific execution (use current_notebook from NotebookManager)
2. Better progress reporting for long-running executions
3. Support for execution interruption
4. Cell-level execution with RTC integration (document_id/cell_id)

### Long-term
1. Multi-user support (separate NotebookManager per user)
2. Execution queue management (prevent concurrent executions in same kernel)
3. Kernel resource monitoring (memory, CPU usage)
4. Automatic kernel restart on failure

## References

- **jupyter-mcp-server**: Reference implementation for many patterns
  - Location: `/home/thinkube/jupyter-mcp-server/`
  - Key files: `utils.py`, `use_notebook_tool.py`
- **jupyter-server-nbmodel**: ExecutionStack implementation
  - Extension providing non-blocking execution
- **Claude Agent SDK**: MCP tool integration
  - Tool registration and execution framework
- **Phase 9.1 Design**: Original architecture document
  - JUPYTER_SERVER mode decision
  - Direct manager access pattern

## Glossary

- **MCP (Model Context Protocol)**: Protocol for exposing tools to AI assistants
- **JUPYTER_SERVER mode**: Local operation with direct API access (vs HTTP mode)
- **ExecutionStack**: Non-blocking execution queue from jupyter-server-nbmodel
- **NotebookManager**: Custom class tracking active notebooks and kernels
- **RTC (Real-Time Collaboration)**: Jupyter's collaborative editing system
- **YDoc**: Collaborative document format (CRDT-based)
- **Session**: Jupyter's kernel-notebook association object
- **IOPub**: Kernel's output broadcast channel (publish-subscribe)

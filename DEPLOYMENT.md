# tk-ai-extension Deployment Guide

This guide covers deploying `tk-ai-extension` to tk-ai lab (Thinkube's JupyterHub).

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Building the Package](#building-the-package)
3. [JupyterHub Integration](#jupyterhub-integration)
4. [Configuration](#configuration)
5. [Verification](#verification)
6. [Troubleshooting](#troubleshooting)

---

## Prerequisites

### Required Components

- **JupyterHub** - Running tk-ai lab instance
- **Python 3.9+** - In the JupyterHub user image
- **Anthropic API Key** - For Claude AI access
- **Docker** - For building custom JupyterHub images

### API Key Setup

Get your Anthropic API key:
1. Visit https://console.anthropic.com/
2. Create an account or sign in
3. Navigate to API Keys
4. Generate a new key

**Store securely** - This key provides access to Claude AI.

---

## Building the Package

### Option 1: Install from PyPI (Production)

```bash
pip install tk-ai-extension
```

### Option 2: Build from Source (Development)

```bash
# Clone repository
git clone https://github.com/thinkube/tk-ai-extension.git
cd tk-ai-extension

# Build package
python -m build

# Install locally
pip install dist/tk_ai_extension-*.whl
```

---

## JupyterHub Integration

### Method 1: Dockerfile Approach (Recommended)

Add to your JupyterHub user image Dockerfile:

```dockerfile
# Base image (your existing JupyterHub image)
FROM your-jupyterhub-base:latest

# Install tk-ai-extension
RUN pip install tk-ai-extension

# Install Claude Code CLI (optional but recommended)
RUN curl -fsSL https://claude.ai/install.sh | sh

# Auto-load extension
RUN mkdir -p /etc/jupyter/jupyter_server_config.d && \
    echo '{"ServerApp": {"jpserver_extensions": {"tk_ai_extension": true}}}' > \
    /etc/jupyter/jupyter_server_config.d/tk_ai_extension.json

# Cleanup
RUN pip cache purge && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
```

Build and push the image:

```bash
docker build -t your-registry/tk-ai-lab:latest .
docker push your-registry/tk-ai-lab:latest
```

### Method 2: JupyterHub Spawner Hooks

Add to `jupyterhub_config.py`:

```python
def pre_spawn_hook(spawner):
    """Install tk-ai-extension before spawning user server."""
    spawner.environment.update({
        'JUPYTER_ENABLE_LAB': 'yes',
    })

    # Install extension on first spawn
    spawner.pre_spawn_cmd = [
        'pip', 'install', '--user', 'tk-ai-extension'
    ]

c.Spawner.pre_spawn_hook = pre_spawn_hook
```

**Note**: This approach is slower as it installs per-user.

### Method 3: Ansible Deployment (Thinkube Standard)

Update `thinkube-control` deployment:

```yaml
# In ansible playbook for JupyterHub
- name: Add tk-ai-extension to JupyterHub image
  blockinfile:
    path: /path/to/jupyterhub/Dockerfile
    marker: "# {mark} TK-AI-EXTENSION"
    block: |
      RUN pip install tk-ai-extension
      RUN mkdir -p /etc/jupyter/jupyter_server_config.d && \
          echo '{"ServerApp": {"jpserver_extensions": {"tk_ai_extension": true}}}' > \
          /etc/jupyter/jupyter_server_config.d/tk_ai_extension.json

- name: Rebuild JupyterHub image
  docker_image:
    name: "{{ jupyterhub_image }}"
    build:
      path: /path/to/jupyterhub
    source: build
    force_source: yes
```

---

## Configuration

### 1. API Key Configuration

#### Environment Variable (Recommended)

Add to `jupyterhub_config.py`:

```python
import os

c.Spawner.environment = {
    'ANTHROPIC_API_KEY': os.environ.get('ANTHROPIC_API_KEY'),
}
```

Set on JupyterHub server:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
systemctl restart jupyterhub
```

#### Per-User Configuration

Users can set their own API keys:

```python
# In user's notebook or ~/.bashrc
import os
os.environ['ANTHROPIC_API_KEY'] = 'sk-ant-...'
```

### 2. Claude Code CLI Configuration

Auto-generate `.mcp.json` for users:

Create `/etc/skel/.mcp.json`:

```json
{
  "mcpServers": {
    "tk-ai-lab": {
      "type": "http",
      "url": "http://localhost:8888/api/tk-ai/mcp/",
      "description": "tk-ai lab notebook tools"
    }
  }
}
```

Or add to spawner hook:

```python
def post_start_hook(spawner):
    """Create MCP config after user server starts."""
    import json
    import os

    mcp_config = {
        "mcpServers": {
            "tk-ai-lab": {
                "type": "http",
                "url": "http://localhost:8888/api/tk-ai/mcp/",
                "description": "tk-ai lab notebook tools"
            }
        }
    }

    config_path = os.path.join(spawner.get_env()['HOME'], '.mcp.json')
    with open(config_path, 'w') as f:
        json.dump(mcp_config, f, indent=2)

c.Spawner.post_start_hook = post_start_hook
```

### 3. Extension Auto-Loading

Create `/etc/jupyter/jupyter_server_config.d/tk_ai_extension.json`:

```json
{
  "ServerApp": {
    "jpserver_extensions": {
      "tk_ai_extension": true
    }
  }
}
```

This ensures the extension loads automatically when JupyterLab starts.

---

## Verification

### 1. Check Extension is Installed

```bash
jupyter server extension list
```

Expected output:
```
Config dir: /etc/jupyter
    tk_ai_extension enabled
    - Validating tk_ai_extension...
      tk_ai_extension 0.1.0 OK
```

### 2. Test MCP Server

```bash
curl http://localhost:8888/api/tk-ai/mcp/health
```

Expected response:
```json
{
  "status": "ok",
  "service": "tk-ai-extension",
  "version": "0.1.0"
}
```

### 3. Test Magic Command

In a notebook:

```python
%load_ext tk_ai_extension

%%tk
List all notebooks in the current directory
```

Should return notebook listing or Claude's response.

### 4. Test Claude Code CLI

In JupyterLab terminal:

```bash
claude
> list notebooks
```

Should connect to MCP server and execute commands.

---

## Troubleshooting

### Extension Not Loading

**Symptom**: `jupyter server extension list` doesn't show tk_ai_extension

**Solutions**:
1. Check installation:
   ```bash
   pip show tk-ai-extension
   ```

2. Manually enable:
   ```bash
   jupyter server extension enable tk_ai_extension
   ```

3. Check config file exists:
   ```bash
   ls /etc/jupyter/jupyter_server_config.d/tk_ai_extension.json
   ```

### API Key Not Working

**Symptom**: "API key not found" or authentication errors

**Solutions**:
1. Verify key is set:
   ```python
   import os
   print(os.environ.get('ANTHROPIC_API_KEY'))
   ```

2. Check spawner environment in logs:
   ```bash
   journalctl -u jupyterhub | grep ANTHROPIC
   ```

3. Test key directly:
   ```bash
   curl https://api.anthropic.com/v1/messages \
     -H "x-api-key: $ANTHROPIC_API_KEY" \
     -H "anthropic-version: 2023-06-01" \
     -H "content-type: application/json" \
     -d '{"model": "claude-3-5-sonnet-20241022", "max_tokens": 10, "messages": [{"role": "user", "content": "Hi"}]}'
   ```

### MCP Server Not Responding

**Symptom**: 404 errors when accessing /api/tk-ai/mcp/*

**Solutions**:
1. Check extension logs:
   ```bash
   jupyter lab --debug
   ```

2. Verify handlers registered:
   ```python
   from tk_ai_extension.extension import TKAIExtension
   ext = TKAIExtension()
   print(ext.handlers)
   ```

3. Restart JupyterLab server

### Magic Command Not Found

**Symptom**: `UsageError: Line magic function '%%tk' not found`

**Solutions**:
1. Load extension manually:
   ```python
   %load_ext tk_ai_extension
   ```

2. Check IPython can import extension:
   ```python
   import tk_ai_extension.magics.tk_magic
   ```

3. Verify IPython is running:
   ```python
   from IPython import get_ipython
   print(get_ipython())
   ```

### Permission Errors

**Symptom**: Permission denied when installing or loading

**Solutions**:
1. Install system-wide (in Dockerfile):
   ```dockerfile
   RUN pip install tk-ai-extension
   ```

2. Or install per-user:
   ```bash
   pip install --user tk-ai-extension
   ```

3. Check file permissions:
   ```bash
   ls -la /etc/jupyter/jupyter_server_config.d/
   ```

---

## Production Checklist

Before deploying to production:

- [ ] API key stored securely (not in Dockerfile or git)
- [ ] Extension auto-loads on JupyterLab start
- [ ] MCP server health check passes
- [ ] Magic commands work in notebooks
- [ ] Claude Code CLI connects successfully
- [ ] User documentation provided
- [ ] Logs configured for monitoring
- [ ] Backup of previous JupyterHub image
- [ ] Rollback plan prepared
- [ ] Test with non-admin user account

---

## Monitoring

### Health Checks

Add to monitoring system:

```bash
# Endpoint health
curl -f http://localhost:8888/api/tk-ai/mcp/health || exit 1

# Extension loaded
jupyter server extension list | grep -q "tk_ai_extension enabled" || exit 1
```

### Logs to Monitor

```bash
# JupyterHub logs
journalctl -u jupyterhub -f

# Extension-specific logs
journalctl -u jupyterhub | grep tk-ai-extension

# User errors
tail -f /var/log/jupyterhub/*.log | grep ERROR
```

---

## Updating

### Update Procedure

1. **Backup current image**:
   ```bash
   docker tag your-registry/tk-ai-lab:latest your-registry/tk-ai-lab:backup-$(date +%Y%m%d)
   ```

2. **Update package version in Dockerfile**:
   ```dockerfile
   RUN pip install tk-ai-extension==0.2.0
   ```

3. **Rebuild image**:
   ```bash
   docker build -t your-registry/tk-ai-lab:latest .
   ```

4. **Test in staging**:
   ```bash
   # Deploy to staging JupyterHub
   kubectl set image deployment/jupyterhub jupyterhub=your-registry/tk-ai-lab:latest -n staging
   ```

5. **Verify functionality**

6. **Deploy to production**:
   ```bash
   kubectl set image deployment/jupyterhub jupyterhub=your-registry/tk-ai-lab:latest -n production
   ```

7. **Monitor for issues**

### Rollback

If issues occur:

```bash
docker tag your-registry/tk-ai-lab:backup-20250108 your-registry/tk-ai-lab:latest
docker push your-registry/tk-ai-lab:latest
kubectl rollout restart deployment/jupyterhub -n production
```

---

## Security Considerations

### API Key Protection

- **Never commit** API keys to git
- **Use secrets management** (e.g., Kubernetes Secrets, Vault)
- **Rotate keys regularly** (every 90 days)
- **Monitor usage** for unexpected spikes

### Network Security

- MCP server runs on **localhost only** - no external exposure
- No ingress rules needed
- No authentication complexity

### User Isolation

- Each user has **separate JupyterLab instance**
- MCP server per-user (not shared)
- API keys can be per-user or shared

---

## Support

For deployment issues:

- **GitHub Issues**: https://github.com/thinkube/tk-ai-extension/issues
- **Thinkube Docs**: https://thinkube.com/docs
- **Discussions**: https://github.com/thinkube/tk-ai-extension/discussions

---

**🤖 Generated with Claude Code for the Thinkube platform**

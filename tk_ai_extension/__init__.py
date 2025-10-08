# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""tk-ai-extension: AI assistant for tk-ai lab (Thinkube JupyterHub)."""

try:
    from ._version import __version__
except ImportError:
    # Fallback when using the package in dev mode without installing
    # in editable mode with pip. It is highly recommended to install
    # the package from a stable release or in editable mode: https://pip.pypa.io/en/stable/topics/local-project-installs/#editable-installs
    import warnings
    warnings.warn("Importing 'tk_ai_extension' outside a proper installation.")
    __version__ = "dev"


def _jupyter_labextension_paths():
    return [{
        "src": "labextension",
        "dest": "tk-ai-extension"
    }]


def _jupyter_server_extension_points():
    """Entry point for jupyter_server."""
    from .extension import _jupyter_server_extension_points
    return _jupyter_server_extension_points()

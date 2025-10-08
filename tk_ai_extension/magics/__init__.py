# Copyright 2025 Alejandro Martínez Corriá and the Thinkube contributors
# SPDX-License-Identifier: BSD-3-Clause

"""IPython magic commands for tk-ai-extension."""

from .tk_magic import TKMagics, load_ipython_extension

__all__ = ["TKMagics", "load_ipython_extension"]

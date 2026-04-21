"""
DEPRECATED: use `src/transfer/main.py` instead.

This file previously contained hardcoded credentials. It now shells out to the new,
environment-variable-driven transfer entrypoint.
"""

from __future__ import annotations

import runpy


if __name__ == "__main__":
    runpy.run_module("src.transfer.main", run_name="__main__")
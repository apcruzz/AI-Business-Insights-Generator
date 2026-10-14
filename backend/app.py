"""Backend public entry point.

The implementation is split into focused modules, while this file preserves the
older import path used by the root launcher and tests.
"""
from __future__ import annotations

from backend.data_loader import frame_from_payload
from backend.normalizer import normalize, suggest_mapping
from backend.server import main

__all__ = ["frame_from_payload", "main", "normalize", "suggest_mapping"]


if __name__ == "__main__":
    main()

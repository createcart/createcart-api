"""Vercel serverless entrypoint for the CreateCart API.

Vercel's Python runtime serves the ASGI ``app`` exposed here, and ``vercel.json``
rewrites every route to this function. We add ``src/`` to ``sys.path`` so the
package imports without needing to be pip-installed (the SDKs and other deps come
from ``pyproject.toml``, which is what Vercel's ``uv`` build installs).
"""

import os
import sys

_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from createcart_api.main import app  # noqa: E402  (ASGI app Vercel will serve)

__all__ = ["app"]

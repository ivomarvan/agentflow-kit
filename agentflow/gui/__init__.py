"""Optional GUI package for agentflow.

Install with::

    pip install agentflow[gui]

Usage::

    from agentflow.gui import serve
    from my_app import MyApp

    serve(MyApp())   # starts FastAPI + opens browser on http://localhost:8765
"""

from agentflow.gui.server import GuiServer, serve

__all__ = ["GuiServer", "serve"]

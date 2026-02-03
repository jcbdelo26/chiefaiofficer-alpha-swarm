"""
Debug MCP Server
================

Full-stack debugging and error correlation for the CAIO dashboard.

Components:
- server.py: Main MCP server with tool definitions
- correlator.py: Frontend/backend error correlation
- log_parser.py: Unified log aggregation
- ui_capture.py: Visual debugging via Playwright
"""

from .correlator import ErrorCorrelator, CorrelatedError, FrontendError, BackendError
from .log_parser import LogParser, LogSource
from .ui_capture import UICapture

__all__ = [
    "ErrorCorrelator",
    "CorrelatedError",
    "FrontendError",
    "BackendError",
    "LogParser",
    "LogSource",
    "UICapture"
]

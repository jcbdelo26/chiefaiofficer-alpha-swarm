#!/usr/bin/env python3
"""
Legacy entrypoint shim.

Use the deterministic replay harness as the regression gate.
"""

from replay_harness import main


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""PreToolUse hook entrypoint."""

from __future__ import annotations

import hook_policy


if __name__ == "__main__":
    raise SystemExit(hook_policy.main_pre_tool_use())

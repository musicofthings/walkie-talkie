"""Watches Claude Desktop for new AI responses via macOS Accessibility API."""

from __future__ import annotations

import asyncio
import subprocess
from collections.abc import Awaitable, Callable

import structlog

logger = structlog.get_logger(__name__)

# Minimum new characters to count as a real response (not a UI artifact)
_MIN_RESPONSE_CHARS = 20


def _read_claude_text() -> str:
    """Extract all AXStaticText values from Claude Desktop's front window."""
    script = """
tell application "System Events"
    if not (exists (processes whose name is "Claude")) then return ""
    tell process "Claude"
        try
            set allText to ""
            repeat with elem in entire contents of front window
                try
                    if (role of elem) is "AXStaticText" then
                        set v to value of elem
                        if v is not missing value and v is not "" then
                            set allText to allText & v & "\n"
                        end if
                    end if
                end try
            end repeat
            return allText
        on error
            return ""
        end try
    end tell
end tell
"""
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=12,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError) as exc:
        logger.warning("response_watcher.read_failed", error=str(exc))
        return ""


class ResponseWatcher:
    """Polls Claude Desktop and fires a callback when a new response appears."""

    def __init__(self, on_response: Callable[[str], Awaitable[None]]) -> None:
        self._on_response = on_response
        self._baseline: str = ""
        self._active: bool = False

    def snapshot_baseline(self) -> None:
        """Call this just before injecting text to capture the current state."""
        self._baseline = _read_claude_text()
        logger.debug("response_watcher.baseline", chars=len(self._baseline))

    async def watch(self, poll_interval: float = 1.5, timeout_secs: int = 90) -> None:
        """Poll for new response text, fire callback on first detection."""
        if self._active:
            return
        self._active = True
        try:
            await self._poll(poll_interval, timeout_secs)
        finally:
            self._active = False

    async def _poll(self, interval: float, timeout_secs: int) -> None:
        baseline_len = len(self._baseline)
        iterations = int(timeout_secs / interval)

        for _ in range(iterations):
            await asyncio.sleep(interval)
            current = _read_claude_text()
            if not current or len(current) <= baseline_len + _MIN_RESPONSE_CHARS:
                continue

            # Extract delta: everything after the baseline
            new_text = current[baseline_len:].strip()
            if len(new_text) < _MIN_RESPONSE_CHARS:
                continue

            logger.info("response_watcher.detected", new_chars=len(new_text))
            self._baseline = current
            await self._on_response(new_text)
            return

        logger.debug("response_watcher.timeout_no_response")

"""macOS Claude Desktop injection via AppleScript System Events."""

from __future__ import annotations

import subprocess

import structlog

from mozhi_agent.injection.base import BaseInjector

logger = structlog.get_logger(__name__)


class MacOSInjector(BaseInjector):
    """Inject text to Claude Desktop on macOS."""

    def inject(self, text: str, press_enter: bool = True) -> None:
        escaped = text.replace('\\', '\\\\').replace('"', '\\"')
        script = [
            'tell application "Claude" to activate',
            'tell application "System Events"',
            f'keystroke "{escaped}"',
        ]
        if press_enter:
            script.append('key code 36')
        script.append('end tell')
        try:
            subprocess.run(["osascript", "-e", "\n".join(script)], check=True,
                           capture_output=True)
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            if "1002" in stderr or "not allowed" in stderr.lower():
                logger.error(
                    "injection.accessibility_denied",
                    fix="Go to System Settings → Privacy & Security → Accessibility "
                        "and add your Terminal app (or grant access to osascript).",
                )
            else:
                logger.error("injection.failed", stderr=stderr, returncode=exc.returncode)

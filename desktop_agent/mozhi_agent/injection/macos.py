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
        enter_line = '\n        key code 36' if press_enter else ''
        # Target Claude's process directly so keystrokes reach it regardless
        # of which app has visual focus at the moment of execution.
        script = f'''\
tell application "Claude" to activate
delay 0.4
tell application "System Events"
    tell process "Claude"
        keystroke "{escaped}"{enter_line}
    end tell
end tell'''
        try:
            subprocess.run(["osascript", "-e", script], check=True, capture_output=True)
            logger.info("injection.ok", chars=len(text))
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            if "1002" in stderr or "not allowed" in stderr.lower():
                print(
                    "\n⚠️  ACCESSIBILITY PERMISSION REQUIRED\n"
                    "   System Settings → Privacy & Security → Accessibility\n"
                    "   Add Terminal (or your shell app) to the allowed list.\n",
                    flush=True,
                )
                logger.error("injection.accessibility_denied")
            else:
                logger.error("injection.failed", stderr=stderr, returncode=exc.returncode)
            raise  # re-raise so bridge.py can log and still send transcript to mobile

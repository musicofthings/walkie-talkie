"""macOS Claude Desktop injection via AX focus + clipboard paste.

Claude Desktop is an Electron app: its composer is a web ``contenteditable``
(exposed to the raw AX API as a single ``AXTextArea`` described "Write your
prompt to Claude").  AppleScript ``keystroke`` is unreliable for unicode/long
text, so we paste from the clipboard instead.

Focus is the subtle part: Claude only auto-focuses the composer when the app is
*switched to*.  If Claude is already frontmost (e.g. consecutive utterances) a
plain ``activate`` is a no-op and the paste lands nowhere.  We therefore set
``AXFocused`` on the composer element directly — coordinate-free and reliable
whether Claude is open, minimized, quit, or already frontmost — then verify the
paste by reading the composer's ``AXValue`` back.

Pasting appends to whatever conversation/tab is active and preserves context,
which the response-watcher TTS loop depends on.
"""

from __future__ import annotations

import subprocess
import time

import structlog

from walkietalkie_agent import macos_ax
from walkietalkie_agent.injection.base import BaseInjector

logger = structlog.get_logger(__name__)

# Foreground Claude and restore any minimized window. {delay} adapts to cold start.
_FOREGROUND_SCRIPT = '''\
tell application "Claude" to activate
delay {delay}
tell application "System Events"
    tell process "Claude"
        try
            repeat with w in windows
                if value of attribute "AXMinimized" of w is true then
                    set value of attribute "AXMinimized" of w to false
                end if
            end repeat
        end try
        set frontmost to true
    end tell
end tell'''

_PASTE_SCRIPT = '''\
tell application "System Events"
    keystroke "v" using {{command down}}{enter}
end tell'''


class MacOSInjector(BaseInjector):
    """Inject text into Claude Desktop on macOS via AX focus + clipboard paste."""

    def inject(self, text: str, press_enter: bool = True) -> None:
        saved_clipboard = self._read_clipboard()
        cold_start = self._ensure_running()
        self._write_clipboard(text)
        try:
            delay = "2.5" if cold_start else "0.45"
            subprocess.run(
                ["osascript", "-e", _FOREGROUND_SCRIPT.format(delay=delay)],
                check=True, capture_output=True,
            )
            if not macos_ax.focus_composer():
                logger.warning("injection.composer_not_found")
            time.sleep(0.1)

            enter_line = '\n    delay 0.15\n    key code 36' if press_enter else ''
            subprocess.run(
                ["osascript", "-e", _PASTE_SCRIPT.format(enter=enter_line)],
                check=True, capture_output=True,
            )
            if not press_enter:
                self._verify_pasted(text)
            logger.info("injection.ok", chars=len(text), pressed_enter=press_enter, cold_start=cold_start)
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
        finally:
            self._restore_clipboard(saved_clipboard)

    @staticmethod
    def _verify_pasted(text: str) -> None:
        """Closed-loop check: confirm the composer actually received the text."""
        value = macos_ax.composer_value() or ""
        if text.strip() and text.strip() not in value:
            logger.warning("injection.verify_failed", composer_chars=len(value))

    @staticmethod
    def _ensure_running() -> bool:
        """Launch Claude if it isn't running. Returns True if a cold start occurred."""
        if macos_ax.claude_pid() is not None:
            return False
        logger.info("injection.launching_claude")
        subprocess.run(["open", "-a", "Claude"])
        for _ in range(20):  # wait for Electron cold start (~up to 6 s)
            time.sleep(0.3)
            if macos_ax.claude_pid() is not None:
                break
        return True

    @staticmethod
    def _read_clipboard() -> str:
        try:
            return subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        except OSError:
            return ""

    @staticmethod
    def _write_clipboard(text: str) -> None:
        subprocess.run(["pbcopy"], input=text, text=True)

    @staticmethod
    def _restore_clipboard(text: str) -> None:
        time.sleep(0.3)  # let the paste read the injected text before restoring
        try:
            subprocess.run(["pbcopy"], input=text, text=True)
        except OSError:
            pass

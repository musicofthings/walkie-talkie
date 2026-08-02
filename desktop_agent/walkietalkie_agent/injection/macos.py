"""macOS desktop app injection via AX focus + clipboard paste.

The target app is usually an Electron or web-style UI: the composer is often
exposed to the raw AX API as an ``AXTextArea`` or ``AXTextField``. AppleScript
``keystroke`` is unreliable for unicode/long text, so we paste from the
clipboard instead.

Focus is the subtle part: many agent apps only auto-focus the composer when the
app is *switched to*. If the app is already frontmost (e.g. consecutive
utterances) a plain ``activate`` can be a no-op and the paste lands nowhere.
We therefore set ``AXFocused`` on the composer element directly — coordinate-
free and reliable whether the app is open, minimized, quit, or already
frontmost — then verify the paste by reading the composer's ``AXValue`` back.

Pasting appends to whatever conversation/tab is active and preserves context.
"""

from __future__ import annotations

import subprocess
import time

import structlog

from walkietalkie_agent import macos_ax
from walkietalkie_agent.injection.base import BaseInjector
from walkietalkie_agent.targets import DesktopTargetProfile

logger = structlog.get_logger(__name__)

_FOREGROUND_SCRIPT = '''\
tell application "{app_name}" to activate
delay {delay}
tell application "System Events"
    tell process "{process_name}"
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
    """Inject text into the active target app on macOS via AX focus + paste."""

    def __init__(self, target: DesktopTargetProfile) -> None:
        self._target = target

    def inject(self, text: str, press_enter: bool = True) -> None:
        saved_clipboard = self._read_clipboard()
        cold_start = self._ensure_running()
        self._write_clipboard(text)
        try:
            delay = "2.5" if cold_start else "0.45"
            subprocess.run(
                [
                    "osascript",
                    "-e",
                    _FOREGROUND_SCRIPT.format(
                        app_name=self._target.app_name,
                        process_name=self._target.process_names[0],
                        delay=delay,
                    ),
                ],
                check=True,
                capture_output=True,
            )
            if not macos_ax.focus_composer(self._target.composer_descriptions, self._target.process_names):
                logger.warning("injection.composer_not_found", target=self._target.display_name)
            time.sleep(0.1)

            enter_line = "\n    delay 0.15\n    key code 36" if press_enter else ""
            subprocess.run(
                ["osascript", "-e", _PASTE_SCRIPT.format(enter=enter_line)],
                check=True,
                capture_output=True,
            )
            if not press_enter:
                self._verify_pasted(text)
            logger.info(
                "injection.ok",
                chars=len(text),
                pressed_enter=press_enter,
                cold_start=cold_start,
                target=self._target.display_name,
            )
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr.decode(errors="replace") if exc.stderr else ""
            if "1002" in stderr or "not allowed" in stderr.lower():
                print(
                    "\n⚠️  ACCESSIBILITY PERMISSION REQUIRED\n"
                    "   System Settings → Privacy & Security → Accessibility\n"
                    "   Add Terminal (or your shell app) to the allowed list.\n",
                    flush=True,
                )
                logger.error("injection.accessibility_denied", target=self._target.display_name)
            else:
                logger.error(
                    "injection.failed",
                    stderr=stderr,
                    returncode=exc.returncode,
                    target=self._target.display_name,
                )
            raise
        finally:
            self._restore_clipboard(saved_clipboard)

    @staticmethod
    def _verify_pasted(text: str) -> None:
        """Closed-loop check: confirm the composer actually received the text."""
        value = macos_ax.composer_value() or ""
        if text.strip() and text.strip() not in value:
            logger.warning("injection.verify_failed", composer_chars=len(value))

    def _ensure_running(self) -> bool:
        """Launch the target app if it isn't running. Returns True on cold start."""
        if macos_ax.app_pid(self._target.process_names) is not None:
            return False
        logger.info("injection.launching_app", target=self._target.display_name)
        subprocess.run(["open", "-a", self._target.app_name])
        for _ in range(20):  # wait for Electron/WebView cold start (~up to 6 s)
            time.sleep(0.3)
            if macos_ax.app_pid(self._target.process_names) is not None:
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

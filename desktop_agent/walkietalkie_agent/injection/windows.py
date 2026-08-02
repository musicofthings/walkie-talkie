"""Windows Claude Desktop injection via UIAutomation and SendKeys."""

from __future__ import annotations

from pywinauto import Application, keyboard

from walkietalkie_agent.injection.base import BaseInjector


class WindowsInjector(BaseInjector):
    """Inject text to Claude Desktop on Windows."""

    def inject(self, text: str, press_enter: bool = True) -> None:
        app = Application(backend="uia").connect(title_re=".*Claude.*")
        window = app.top_window()
        window.set_focus()
        keyboard.send_keys(text, with_spaces=True, pause=0.01)
        if press_enter:
            keyboard.send_keys("{ENTER}")

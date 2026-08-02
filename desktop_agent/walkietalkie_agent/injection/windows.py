"""Windows desktop app injection via UIAutomation and SendKeys."""

from __future__ import annotations

import re

from pywinauto import Application, keyboard

from walkietalkie_agent.injection.base import BaseInjector
from walkietalkie_agent.targets import DesktopTargetProfile


class WindowsInjector(BaseInjector):
    """Inject text to the active target app on Windows."""

    def __init__(self, target: DesktopTargetProfile) -> None:
        self._target = target

    def inject(self, text: str, press_enter: bool = True) -> None:
        title_re = "|".join(re.escape(name) for name in (self._target.process_names or (self._target.app_name,)))
        app = Application(backend="uia").connect(title_re=f".*({title_re}).*")
        window = app.top_window()
        window.set_focus()
        keyboard.send_keys(text, with_spaces=True, pause=0.01)
        if press_enter:
            keyboard.send_keys("{ENTER}")

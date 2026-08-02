"""macOS Accessibility (AX) helpers for desktop agent apps.

AppleScript's ``entire contents`` cannot cross the ``AXWebArea`` boundary, so it
sees none of the app content in Electron/WebView-based agents. The raw
``AXUIElement`` API (what screen readers use) can, and is fast enough for
focus/readback loops.

This module is intentionally target-agnostic: it supports focusing a composer
field, reading its value, and walking static text nodes for response capture.
Target-specific labels and process names are provided by higher-level profiles.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable

from ApplicationServices import (  # type: ignore[import-not-found]
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
)

_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}$")
_MODEL_NAME = re.compile(r"^(Sonnet|Opus|Haiku)\b")


def app_pid(process_names: Iterable[str]) -> int | None:
    """Return the first matching process id for an app target."""
    for process_name in process_names:
        out = subprocess.run(["pgrep", "-x", process_name], capture_output=True, text=True).stdout.split()
        if out:
            return int(out[0])
    return None


def _attr(element, name):
    err, value = AXUIElementCopyAttributeValue(element, name, None)
    return value if err == 0 else None


def app_element(process_names: Iterable[str]):
    pid = app_pid(process_names)
    return AXUIElementCreateApplication(pid) if pid else None


def _find(element, role=None, desc=None, depth=0):
    if depth > 60:
        return None
    if (role is None or _attr(element, "AXRole") == role) and (
        desc is None or _attr(element, "AXDescription") == desc
    ):
        return element
    children = _attr(element, "AXChildren")
    if children:
        for child in children:
            found = _find(child, role, desc, depth + 1)
            if found is not None:
                return found
    return None


def _find_any(element, roles: tuple[str, ...], desc_candidates: tuple[str, ...], depth=0):
    if depth > 60:
        return None
    role = _attr(element, "AXRole")
    desc = _attr(element, "AXDescription")
    if (role in roles) and (not desc_candidates or desc in desc_candidates):
        return element
    children = _attr(element, "AXChildren")
    if children:
        for child in children:
            found = _find_any(child, roles, desc_candidates, depth + 1)
            if found is not None:
                return found
    return None


def find_composer(
    composer_descriptions: Iterable[str] | None = None,
    process_names: Iterable[str] = ("Claude",),
    app=None,
):
    """Find a target composer field.

    If one of the supplied descriptions matches, it is preferred. Otherwise the
    first editable AX text control is returned as a best-effort fallback.
    """
    app = app or app_element(process_names)
    if app is None:
        return None

    desc_candidates = tuple(composer_descriptions or ())
    if desc_candidates:
        found = _find_any(app, ("AXTextArea", "AXTextField"), desc_candidates)
        if found is not None:
            return found

    return _find_any(app, ("AXTextArea", "AXTextField"), ())


def focus_composer(
    composer_descriptions: Iterable[str] | None = None,
    process_names: Iterable[str] = ("Claude",),
    app=None,
) -> bool:
    """Set keyboard focus on the composer."""
    composer = find_composer(composer_descriptions, process_names, app)
    if composer is None:
        return False
    AXUIElementSetAttributeValue(composer, "AXFocused", True)
    return True


def composer_value(
    composer_descriptions: Iterable[str] | None = None,
    process_names: Iterable[str] = ("Claude",),
    app=None,
) -> str | None:
    composer = find_composer(composer_descriptions, process_names, app)
    return _attr(composer, "AXValue") if composer is not None else None


def read_conversation_static_texts(
    process_names: Iterable[str] = ("Claude",),
    sidebar_title: str = "Sidebar",
    app=None,
) -> list[str]:
    """Document-order AXStaticText values from the main content (sidebar excluded)."""
    app = app or app_element(process_names)
    if app is None:
        return []
    out: list[str] = []

    def walk(element, depth: int, in_sidebar: bool) -> None:
        if depth > 60:
            return
        role = _attr(element, "AXRole")
        in_sidebar = in_sidebar or (role == "AXGroup" and _attr(element, "AXTitle") == sidebar_title)
        if not in_sidebar and role == "AXStaticText":
            value = _attr(element, "AXValue")
            if isinstance(value, str) and value.strip():
                out.append(value.strip())
        children = _attr(element, "AXChildren")
        if children:
            for child in children:
                walk(child, depth + 1, in_sidebar)

    walk(app, 0, False)
    return out


def extract_latest_response(
    texts: list[str],
    user_message: str = "",
    user_label: str = "You said:",
    assistant_label: str = "Assistant responded:",
    chrome: Iterable[str] = (),
) -> str:
    """Pull the assistant reply out of a static-text snapshot."""
    user_message = user_message.strip()
    chrome_set = frozenset(chrome)
    anchor = None
    for i, t in enumerate(texts):
        if t.startswith(user_label) or (user_message and t == user_message):
            anchor = i
    tail = texts[anchor + 1:] if anchor is not None else texts

    parts: list[str] = []
    for t in tail:
        if t in chrome_set or t.startswith(user_label):
            continue
        if user_message and t == user_message:
            continue
        if _TIMESTAMP.match(t) or _MODEL_NAME.match(t):
            continue
        if t.startswith(assistant_label):
            continue
        parts.append(t)
    return " ".join(" ".join(parts).split())


# Claude compatibility wrappers retained for existing paths.
def claude_pid() -> int | None:
    return app_pid(("Claude",))


def app_element_claude():
    return app_element(("Claude",))


def focus_claude_composer() -> bool:
    return focus_composer(("Write your prompt to Claude", "Write a message…"), ("Claude",))


def composer_value_claude() -> str | None:
    return composer_value(("Write your prompt to Claude", "Write a message…"), ("Claude",))


"""macOS Accessibility (AX) helpers for Claude Desktop's Electron UI.

AppleScript's ``entire contents`` cannot cross the ``AXWebArea`` boundary, so it
sees none of Claude's web content.  The raw ``AXUIElement`` API (what screen
readers use) can, and is fast (~0.35 s for a full window walk).  We use it both
to focus the composer for injection and to read streamed responses.

macOS-only: imports ``ApplicationServices`` (pyobjc).  Import this module lazily
on non-macOS platforms.
"""

from __future__ import annotations

import re
import subprocess

from ApplicationServices import (  # type: ignore[import-not-found]
    AXUIElementCopyAttributeValue,
    AXUIElementCreateApplication,
    AXUIElementSetAttributeValue,
)

# AXDescription of the message composer text area.
COMPOSER_DESC = "Write your prompt to Claude"

# Response lifecycle signals exposed as AXStaticText in the conversation.
STATUS_RESPONDING = "Claude is responding"
STATUS_DONE = "Claude finished the response"

# Static text that is UI chrome rather than conversation content.
CHROME = frozenset({
    "Skip to content",
    "Write a message…",
    "Adaptive",
    "Claude is AI and can make mistakes. Please double-check responses.",
    STATUS_RESPONDING,
    STATUS_DONE,
})

_TIMESTAMP = re.compile(r"^\d{1,2}:\d{2}$")
_MODEL_NAME = re.compile(r"^(Sonnet|Opus|Haiku)\b")
_USER_LABEL = "You said:"
_ASSISTANT_LABEL = "Claude responded:"


def claude_pid() -> int | None:
    out = subprocess.run(["pgrep", "-x", "Claude"], capture_output=True, text=True).stdout.split()
    return int(out[0]) if out else None


def _attr(element, name):
    err, value = AXUIElementCopyAttributeValue(element, name, None)
    return value if err == 0 else None


def app_element():
    pid = claude_pid()
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


def find_composer(app=None):
    app = app or app_element()
    if app is None:
        return None
    return _find(app, role="AXTextArea", desc=COMPOSER_DESC)


def focus_composer(app=None) -> bool:
    """Set keyboard focus on the composer. Works even when Claude is already frontmost."""
    composer = find_composer(app)
    if composer is None:
        return False
    AXUIElementSetAttributeValue(composer, "AXFocused", True)
    return True


def composer_value(app=None) -> str | None:
    composer = find_composer(app)
    return _attr(composer, "AXValue") if composer is not None else None


def read_conversation_static_texts(app=None) -> list[str]:
    """Document-order AXStaticText values from the main content (sidebar excluded)."""
    app = app or app_element()
    if app is None:
        return []
    out: list[str] = []

    def walk(element, depth: int, in_sidebar: bool) -> None:
        if depth > 60:
            return
        role = _attr(element, "AXRole")
        in_sidebar = in_sidebar or (role == "AXGroup" and _attr(element, "AXTitle") == "Sidebar")
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


def extract_latest_response(texts: list[str], user_message: str = "") -> str:
    """Pull the assistant's reply out of a static-text snapshot.

    The reply is everything after the user's message bubble (anchored by the
    "You said:" label), minus chrome, timestamps, and the model selector.  On
    completion the reply carries a "Claude responded:" prefix, which is stripped.
    """
    user_message = user_message.strip()
    anchor = None
    for i, t in enumerate(texts):
        if t.startswith(_USER_LABEL) or (user_message and t == user_message):
            anchor = i
    tail = texts[anchor + 1:] if anchor is not None else texts

    parts: list[str] = []
    for t in tail:
        if t in CHROME or t.startswith(_USER_LABEL):
            continue
        if user_message and t == user_message:
            continue
        if _TIMESTAMP.match(t) or _MODEL_NAME.match(t):
            continue
        # On completion an aria-label summary node ("Claude responded: <full>")
        # appears alongside the per-sentence body nodes; skip it to avoid dupes.
        if t.startswith(_ASSISTANT_LABEL):
            continue
        parts.append(t)
    # Collapse all whitespace so node-boundary spacing is stable between polls
    # (the reply is split across AXStaticText nodes that re-segment as it streams).
    return " ".join(" ".join(parts).split())

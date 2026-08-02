"""Supported desktop agent targets and accessibility profiles."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class ResponseCaptureProfile:
    """Accessibility markers for a target app's streamed reply surface."""

    process_names: tuple[str, ...]
    status_responding: str
    status_done: str
    user_label: str = "You said:"
    assistant_label: str = "Assistant responded:"
    chrome: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class DesktopTargetProfile:
    """Desktop app automation profile."""

    key: str
    display_name: str
    app_name: str
    process_names: tuple[str, ...]
    composer_descriptions: tuple[str, ...] = ()
    response_capture: ResponseCaptureProfile | None = None


_CLAUDE_RESPONSE_CAPTURE = ResponseCaptureProfile(
    process_names=("Claude",),
    status_responding="Claude is responding",
    status_done="Claude finished the response",
    user_label="You said:",
    assistant_label="Claude responded:",
    chrome=frozenset({
        "Skip to content",
        "Write a message…",
        "Adaptive",
        "Claude is AI and can make mistakes. Please double-check responses.",
        "Claude is responding",
        "Claude finished the response",
    }),
)


DESKTOP_TARGETS: dict[str, DesktopTargetProfile] = {
    "claude": DesktopTargetProfile(
        key="claude",
        display_name="Claude Desktop",
        app_name="Claude",
        process_names=("Claude",),
        composer_descriptions=("Write your prompt to Claude", "Write a message…"),
        response_capture=_CLAUDE_RESPONSE_CAPTURE,
    ),
    "chatgpt": DesktopTargetProfile(
        key="chatgpt",
        display_name="ChatGPT Desktop",
        app_name="ChatGPT",
        process_names=("ChatGPT",),
        composer_descriptions=("Message ChatGPT", "Ask anything", "Write a message…"),
    ),
    "codex": DesktopTargetProfile(
        key="codex",
        display_name="Codex Desktop",
        app_name="Codex",
        process_names=("Codex", "ChatGPT"),
        composer_descriptions=("Ask Codex", "Type a prompt", "Write a message…"),
    ),
    "cursor": DesktopTargetProfile(
        key="cursor",
        display_name="Cursor",
        app_name="Cursor",
        process_names=("Cursor",),
        composer_descriptions=("Ask Cursor", "Type a message", "Write a message…"),
    ),
}

_ALIASES = {
    "claude desktop": "claude",
    "claude-desktop": "claude",
    "chatgpt desktop": "chatgpt",
    "chatgpt-desktop": "chatgpt",
    "codex desktop": "codex",
    "codex-desktop": "codex",
    "cursor desktop": "cursor",
    "cursor-desktop": "cursor",
}


def normalize_desktop_target(value: str) -> str:
    """Canonicalize user input into a supported target key."""
    key = value.strip().lower().replace("_", "-")
    return _ALIASES.get(key, key)


def get_desktop_target(value: str) -> DesktopTargetProfile:
    """Resolve a supported desktop target profile."""
    key = normalize_desktop_target(value)
    if key not in DESKTOP_TARGETS:
        supported = ", ".join(sorted(DESKTOP_TARGETS))
        raise ValueError(f"Unsupported desktop target '{value}'. Supported targets: {supported}")
    return DESKTOP_TARGETS[key]

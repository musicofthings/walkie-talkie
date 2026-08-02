"""Supported CLI agent targets and command specifications."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CliTargetProfile:
    """Command-line agent target profile."""

    key: str
    display_name: str
    command: str
    args: tuple[str, ...] = ()


CLI_TARGETS: dict[str, CliTargetProfile] = {
    "claude": CliTargetProfile(key="claude", display_name="Claude CLI", command="claude"),
    "chatgpt": CliTargetProfile(key="chatgpt", display_name="ChatGPT CLI", command="chatgpt"),
    "codex": CliTargetProfile(key="codex", display_name="Codex CLI", command="codex"),
    "cursor": CliTargetProfile(key="cursor", display_name="Cursor CLI", command="cursor"),
}

_ALIASES = {
    "claude-cli": "claude",
    "chatgpt-cli": "chatgpt",
    "codex-cli": "codex",
    "cursor-cli": "cursor",
}


def normalize_cli_target(value: str) -> str:
    key = value.strip().lower().replace("_", "-")
    return _ALIASES.get(key, key)


def get_cli_target(value: str) -> CliTargetProfile:
    key = normalize_cli_target(value)
    if key not in CLI_TARGETS:
        supported = ", ".join(sorted(CLI_TARGETS))
        raise ValueError(f"Unsupported CLI target '{value}'. Supported targets: {supported}")
    return CLI_TARGETS[key]

"""Supported CLI agent targets and command specifications."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from enum import Enum


class CliMode(Enum):
    """CLI interaction mode: one-shot subprocess or persistent session."""

    ONE_SHOT = "one_shot"
    SESSION = "session"


@dataclass(frozen=True, slots=True)
class CliTargetProfile:
    """Command-line agent target profile."""

    key: str
    display_name: str
    command: str
    args: tuple[str, ...] = ()
    mode: CliMode = CliMode.ONE_SHOT
    available: bool = False

    def check_available(self) -> bool:
        """Check if the CLI command is available in PATH."""
        return shutil.which(self.command) is not None


CLI_TARGETS: dict[str, CliTargetProfile] = {
    "claude": CliTargetProfile(
        key="claude",
        display_name="Claude CLI",
        command="claude",
        mode=CliMode.SESSION,
    ),
    "chatgpt": CliTargetProfile(
        key="chatgpt",
        display_name="ChatGPT CLI",
        command="chatgpt",
        args=("--model", "gpt-4"),
        mode=CliMode.SESSION,
    ),
    "codex": CliTargetProfile(
        key="codex",
        display_name="Codex CLI",
        command="copilot",
        args=("-a",),
        mode=CliMode.SESSION,
    ),
    "cursor": CliTargetProfile(
        key="cursor",
        display_name="Cursor CLI",
        command="cursor",
        mode=CliMode.ONE_SHOT,
    ),
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

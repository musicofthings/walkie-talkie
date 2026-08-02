"""Factory for current-platform injector selection."""

from __future__ import annotations

import platform

from walkietalkie_agent.injection.base import BaseInjector
from walkietalkie_agent.cli_targets import get_cli_target
from walkietalkie_agent.injection.cli import CliInjector
from walkietalkie_agent.targets import get_desktop_target


def get_injector(target_name: str, surface_kind: str = "desktop") -> BaseInjector:
    """Return a supported platform injector instance.

    Platform-specific imports are deferred to avoid ImportError on
    systems where the other platform's dependencies are absent.
    """
    if surface_kind == "cli":
        cli_target = get_cli_target(target_name)
        if cli_target.mode.value == "session":
            from walkietalkie_agent.injection.cli_session import CliSessionInjector

            return CliSessionInjector(cli_target)
        else:
            return CliInjector(cli_target)

    target = get_desktop_target(target_name)
    system = platform.system().lower()
    if system == "windows":
        from walkietalkie_agent.injection.windows import WindowsInjector

        return WindowsInjector(target)
    if system == "darwin":
        from walkietalkie_agent.injection.macos import MacOSInjector

        return MacOSInjector(target)
    raise NotImplementedError(f"Unsupported platform for input injection: {system}")

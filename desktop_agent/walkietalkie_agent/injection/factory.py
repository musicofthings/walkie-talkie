"""Factory for current-platform injector selection."""

from __future__ import annotations

import platform

from walkietalkie_agent.injection.base import BaseInjector
from walkietalkie_agent.targets import get_desktop_target


def get_injector(target_name: str) -> BaseInjector:
    """Return a supported platform injector instance.

    Platform-specific imports are deferred to avoid ImportError on
    systems where the other platform's dependencies are absent.
    """
    target = get_desktop_target(target_name)
    system = platform.system().lower()
    if system == "windows":
        from walkietalkie_agent.injection.windows import WindowsInjector

        return WindowsInjector(target)
    if system == "darwin":
        from walkietalkie_agent.injection.macos import MacOSInjector

        return MacOSInjector(target)
    raise NotImplementedError(f"Unsupported platform for input injection: {system}")

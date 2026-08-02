"""Factory for current-platform injector selection."""

from __future__ import annotations

import platform

from walkietalkie_agent.injection.base import BaseInjector


def get_injector() -> BaseInjector:
    """Return a supported platform injector instance.

    Platform-specific imports are deferred to avoid ImportError on
    systems where the other platform's dependencies are absent.
    """
    system = platform.system().lower()
    if system == "windows":
        from walkietalkie_agent.injection.windows import WindowsInjector

        return WindowsInjector()
    if system == "darwin":
        from walkietalkie_agent.injection.macos import MacOSInjector

        return MacOSInjector()
    raise NotImplementedError(f"Unsupported platform for input injection: {system}")

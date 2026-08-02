"""Injection interface used by platform-specific adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseInjector(ABC):
    """Abstract text injector for a desktop agent app."""

    @abstractmethod
    def inject(self, text: str, press_enter: bool = True) -> str | None:
        """Inject text into the active target composer and optionally return a reply."""

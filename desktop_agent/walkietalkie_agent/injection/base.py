"""Injection interface used by platform-specific adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod


class BaseInjector(ABC):
    """Abstract text injector for Claude Desktop cowork input."""

    @abstractmethod
    def inject(self, text: str, press_enter: bool = True) -> None:
        """Inject text into active Claude input field."""

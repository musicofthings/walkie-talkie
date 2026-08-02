"""System tray bootstrap wrapper."""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


def start_tray() -> None:
    """Start tray icon if optional dependencies are installed."""
    try:
        import pystray
        from PIL import Image

        image = Image.new("RGB", (16, 16), "#3c7")
        icon = pystray.Icon("WalkieTalkie", image=image, title="WalkieTalkie Agent")
        icon.run_detached()
        logger.info("tray.started")
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("tray.unavailable", error=str(exc))

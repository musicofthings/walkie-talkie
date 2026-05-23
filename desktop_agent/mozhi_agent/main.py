"""Entrypoint for Mozhi desktop agent service."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from mozhi_agent.audio.server import AudioIngressServer, run_server
from mozhi_agent.config import settings
from mozhi_agent.injection.factory import get_injector
from mozhi_agent.observability.logging_utils import configure_logging
from mozhi_agent.pipeline.bridge import VoiceBridgePipeline
from mozhi_agent.risk.filter import RiskFilter
from mozhi_agent.security.pairing import PairingManager
from mozhi_agent.security.pairing_qr import build_pairing_payload, render_pairing_qr
from mozhi_agent.stt.transcriber import WhisperTranscriber
from mozhi_agent.ui.tray import start_tray

logger = structlog.get_logger(__name__)


async def _async_main() -> None:
    configure_logging(settings.log_level)
    logger.info("agent.starting", env=settings.env, debug=settings.debug)
    start_tray()

    pairing = PairingManager(token_ttl_seconds=settings.token_ttl_seconds)

    payload = build_pairing_payload(settings, pairing)
    payload_json = render_pairing_qr(payload)
    logger.info("pairing.ready", listening_on=payload["ws_url"])
    Path("pairing_qr.json").write_text(payload_json)
    print("\n" + "=" * 60)
    print("  COPY THIS LINE INTO THE APP  →  'Enter Manually'")
    print("=" * 60)
    print(payload_json)
    print("=" * 60)
    print("  (also saved to pairing_qr.json)")
    print("=" * 60 + "\n")

    transcriber = WhisperTranscriber(
        model_size=settings.model_size,
        compute_type=settings.compute_type,
        language=settings.language,
    )
    risk_filter = RiskFilter(settings.action_log_path, settings.require_confirmation)
    injector = get_injector()
    server = AudioIngressServer(pairing, on_audio=lambda _: None, on_flush=None)
    pipeline = VoiceBridgePipeline(
        settings, transcriber, risk_filter, injector, send_tts=server.send_tts
    )
    server._on_audio = pipeline.handle_audio
    server._on_flush = pipeline.flush_buffer
    await run_server(settings.bind_host, settings.bind_port, server)


def run() -> None:
    """Console script runner."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    run()

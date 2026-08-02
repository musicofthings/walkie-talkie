"""Entrypoint for WalkieTalkie desktop agent service."""

from __future__ import annotations

import asyncio
from pathlib import Path

import structlog

from walkietalkie_agent.audio.server import AudioIngressServer, run_server
from walkietalkie_agent.config import settings
from walkietalkie_agent.injection.factory import get_injector
from walkietalkie_agent.observability.logging_utils import configure_logging
from walkietalkie_agent.pipeline.bridge import VoiceBridgePipeline
from walkietalkie_agent.risk.filter import RiskFilter
from walkietalkie_agent.security.pairing import PairingManager
from walkietalkie_agent.security.pairing_qr import build_pairing_payload, render_pairing_qr
from walkietalkie_agent.targets import get_desktop_target
from walkietalkie_agent.stt.transcriber import WhisperTranscriber
from walkietalkie_agent.ui.tray import start_tray
from walkietalkie_agent.response_watcher import ResponseWatcher

logger = structlog.get_logger(__name__)


async def _async_main() -> None:
    configure_logging(settings.log_level)
    logger.info("agent.starting", env=settings.env, debug=settings.debug)
    start_tray()

    target = get_desktop_target(settings.desktop_target)
    logger.info("agent.target", target=target.key, app_name=target.app_name)
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
    server = AudioIngressServer(pairing, on_audio=lambda _: None, on_flush=None)
    injector = get_injector(settings.desktop_target)
    response_watcher = (
        ResponseWatcher(server.send_tts, target.response_capture)
        if target.response_capture is not None
        else None
    )
    pipeline = VoiceBridgePipeline(
        settings, transcriber, risk_filter, injector,
        target_label=target.display_name,
        response_watcher=response_watcher,
        send_tts=server.send_tts,
        send_transcript=server.send_transcript,
    )
    server._on_audio = pipeline.handle_audio
    server._on_flush = pipeline.flush_buffer
    await run_server(settings.bind_host, settings.bind_port, server)


def run() -> None:
    """Console script runner."""
    asyncio.run(_async_main())


if __name__ == "__main__":
    run()

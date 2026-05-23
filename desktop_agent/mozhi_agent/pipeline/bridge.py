"""End-to-end audio->STT->risk->injection pipeline."""

from __future__ import annotations

import asyncio
import functools
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

import structlog

from mozhi_agent.config import AgentSettings
from mozhi_agent.injection.base import BaseInjector
from mozhi_agent.models import ActionLogEntry
from mozhi_agent.response_watcher import ResponseWatcher
from mozhi_agent.risk.filter import RiskFilter
from mozhi_agent.stt.transcriber import WhisperTranscriber
from mozhi_agent.ui.confirm import confirm_injection

logger = structlog.get_logger(__name__)

SendTtsCallback = Callable[[str], Awaitable[None]]
SendTranscriptCallback = Callable[[str], Awaitable[None]]


class VoiceBridgePipeline:
    """Processes PCM audio frames and executes controlled text injection.

    Incoming audio packets are accumulated in a buffer.  Once the buffer
    reaches ``_buffer_threshold`` bytes (default 3 s of PCM16 mono @16 kHz)
    the aggregated chunk is sent to the Whisper transcriber.  Call
    ``flush_buffer()`` when a push-to-talk session ends to process the
    remaining audio.
    """

    # 3 seconds of PCM16 mono @ 16 kHz → 16000 samples/s × 2 bytes × 3 s
    _BUFFER_THRESHOLD = 16000 * 2 * 3

    def __init__(
        self,
        settings: AgentSettings,
        transcriber: WhisperTranscriber,
        risk_filter: RiskFilter,
        injector: BaseInjector,
        send_tts: SendTtsCallback | None = None,
        send_transcript: SendTranscriptCallback | None = None,
    ) -> None:
        self._settings = settings
        self._transcriber = transcriber
        self._risk_filter = risk_filter
        self._injector = injector
        self._send_tts = send_tts
        self._send_transcript = send_transcript
        self._audio_buffer = bytearray()
        self._pending_text: list[str] = []
        # The watcher streams Claude's reply to send_tts sentence-by-sentence.
        self._response_watcher = ResponseWatcher(self._send_tts) if send_tts else None

    async def handle_audio(self, pcm_bytes: bytes) -> None:
        """Buffer incoming PCM. Transcribe rolling chunks but defer injection."""
        self._audio_buffer.extend(pcm_bytes)
        if len(self._audio_buffer) < self._BUFFER_THRESHOLD:
            return
        chunk = bytes(self._audio_buffer)
        self._audio_buffer.clear()
        await self._transcribe_to_pending(chunk)

    async def flush_buffer(self) -> None:
        """On PTT release: transcribe remainder, then inject full combined text."""
        if self._audio_buffer:
            chunk = bytes(self._audio_buffer)
            self._audio_buffer.clear()
            await self._transcribe_to_pending(chunk)
        if self._pending_text:
            combined = " ".join(self._pending_text).strip()
            self._pending_text.clear()
            await self._process_chunk(combined)

    async def _transcribe_to_pending(self, pcm_bytes: bytes) -> None:
        """Transcribe a PCM chunk and append the text to the pending buffer."""
        loop = asyncio.get_running_loop()
        transcript = await loop.run_in_executor(
            None, self._transcriber.transcribe_pcm16_mono, pcm_bytes,
        )
        if not transcript.text:
            return
        logger.info(
            "stt.chunk",
            text=transcript.text,
            confidence=transcript.confidence,
            latency_ms=transcript.latency_ms,
        )
        self._pending_text.append(transcript.text)

    async def _process_chunk(self, combined_text: str) -> None:
        """Risk-check and inject the fully assembled utterance."""
        loop = asyncio.get_running_loop()

        self._risk_filter.append_audit(
            ActionLogEntry(
                ts_utc=datetime.now(UTC),
                action="transcribed",
                transcript=combined_text,
                details="combined",
            )
        )
        logger.info("stt.completed", text=combined_text)

        decision = self._risk_filter.evaluate(combined_text)
        if decision.needs_confirmation:
            approved = await loop.run_in_executor(
                None,
                functools.partial(
                    confirm_injection, combined_text, decision.keyword or "unknown",
                ),
            )
            self._risk_filter.append_audit(
                ActionLogEntry(
                    ts_utc=datetime.now(UTC),
                    action="confirmed" if approved else "blocked",
                    transcript=combined_text,
                    details=f"keyword={decision.keyword}",
                )
            )
            if not approved:
                logger.warning("risk.blocked", keyword=decision.keyword)
                return

        # Send transcript to mobile immediately — before injection — so the
        # user's bubble appears regardless of whether injection succeeds.
        print(f"[mozhi] _process_chunk: scheduling send_transcript, send_fn={self._send_transcript is not None}", flush=True)
        if self._send_transcript is not None:
            asyncio.create_task(self._send_transcript(combined_text))

        if self._response_watcher is not None:
            self._response_watcher.snapshot_baseline(combined_text)

        injected = False
        try:
            await loop.run_in_executor(
                None,
                functools.partial(
                    self._injector.inject, combined_text, press_enter=self._settings.auto_send,
                ),
            )
            injected = True
        except Exception as exc:
            logger.error("injection.error", error=str(exc))

        self._risk_filter.append_audit(
            ActionLogEntry(
                ts_utc=datetime.now(UTC),
                action="injected" if injected else "inject_failed",
                transcript=combined_text,
                details=f"auto_send={self._settings.auto_send}",
            )
        )

        if injected and self._response_watcher is not None:
            asyncio.create_task(self._response_watcher.watch())

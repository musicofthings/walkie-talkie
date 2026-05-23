"""Local speech transcription wrapper around Faster-Whisper."""

from __future__ import annotations

import io
import time
import wave

import numpy as np
import structlog
from faster_whisper import WhisperModel

from mozhi_agent.models import TranscriptEvent

logger = structlog.get_logger(__name__)

# RMS below this level is treated as silence — Whisper hallucinates on silent audio.
# PCM16 range is 0-32767; typical speech sits around 500-5000.
_SILENCE_RMS_THRESHOLD = 150


class WhisperTranscriber:
    """Manages whisper model and performs local inference."""

    def __init__(self, model_size: str, compute_type: str, language: str) -> None:
        self._model = WhisperModel(model_size, compute_type=compute_type)
        self._language = language

    def transcribe_pcm16_mono(self, pcm_bytes: bytes, sample_rate: int = 16000) -> TranscriptEvent:
        """Transcribe raw PCM16 mono bytes and return text with latency metadata."""
        samples = np.frombuffer(pcm_bytes, dtype=np.int16).astype(np.float32)
        rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) else 0.0
        logger.debug("stt.audio_energy", rms=round(rms, 1), samples=len(samples))

        if rms < _SILENCE_RMS_THRESHOLD:
            logger.info("stt.skipped_silence", rms=round(rms, 1))
            return TranscriptEvent(text="", confidence=0.0, latency_ms=0)

        start = time.perf_counter()
        wav_bytes = self._pcm_to_wav_bytes(samples, sample_rate)
        segments, info = self._model.transcribe(io.BytesIO(wav_bytes), language=self._language)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        latency_ms = int((time.perf_counter() - start) * 1000)
        confidence = float(max(0.0, min(1.0, info.language_probability)))
        return TranscriptEvent(text=text, confidence=confidence, latency_ms=latency_ms)

    @staticmethod
    def _pcm_to_wav_bytes(samples: np.ndarray, sample_rate: int) -> bytes:
        pcm16 = samples.astype(np.int16)
        with io.BytesIO() as buffer:
            with wave.open(buffer, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(sample_rate)
                wf.writeframes(pcm16.tobytes())
            return buffer.getvalue()

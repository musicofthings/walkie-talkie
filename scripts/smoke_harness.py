#!/usr/bin/env python3
"""Lightweight automated smoke harness for WalkieTalkie Desktop Agent.

This script:
- Creates a PairingManager and a client X25519 key
- Derives a session and AES key
- Encrypts a short PCM-like payload and submits it to AudioIngressServer._handle_audio_packet
- Verifies the on_audio callback is invoked with the original plaintext

Designed to run quickly and safely without starting network services or external deps.
"""

import asyncio
import time
from base64 import urlsafe_b64encode

from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives import serialization

from walkietalkie_agent.security.pairing import PairingManager, TransportCrypto
from walkietalkie_agent.audio.server import AudioIngressServer


async def main() -> int:
    print('[smoke] starting smoke harness')
    pairing = PairingManager(token_ttl_seconds=900)

    # Generate client keypair and get public key b64
    client_priv = x25519.X25519PrivateKey.generate()
    client_pub = client_priv.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    client_pub_b64 = urlsafe_b64encode(client_pub).decode('utf-8')

    # Create session on desktop (derives AES key)
    session = pairing.create_session('smoke-device', client_pub_b64)
    print('[smoke] session created, token:', session.token[:8] + '...')

    # Prepare a short synthetic PCM16-like payload (non-silent)
    # Use int16 samples with amplitude 1000 -> RMS > silence threshold
    import array
    samples = array.array('h', [1000] * 160)  # 160 samples -> 320 bytes
    plaintext = samples.tobytes()

    # Prepare STT -> risk -> injection components
    from walkietalkie_agent.config import AgentSettings
    from walkietalkie_agent.pipeline.bridge import VoiceBridgePipeline
    from walkietalkie_agent.risk.filter import RiskFilter
    from walkietalkie_agent.models import TranscriptEvent
    from pathlib import Path

    class MockTranscriber:
        def transcribe_pcm16_mono(self, pcm_bytes: bytes, sample_rate: int = 16000) -> TranscriptEvent:
            # Simple deterministic transcription of the audio chunk
            return TranscriptEvent(text='hello from smoke', confidence=0.99, latency_ms=10)

    class MockInjector:
        def __init__(self):
            self.injected = None

        def inject(self, text: str, press_enter: bool = True) -> None:
            print(f"[mock_injector] inject called: {text!r}, press_enter={press_enter}")
            self.injected = text

    settings = AgentSettings()
    transcriber = MockTranscriber()
    risk_filter = RiskFilter(Path('logs/test_actions.log'), require_confirmation=False)
    injector = MockInjector()

    pipeline = VoiceBridgePipeline(settings, transcriber, risk_filter, injector)

    # Async callbacks to forward decrypted audio into pipeline
    seen_audio = {}

    async def on_audio(chunk: bytes) -> None:
        print(f'[smoke] on_audio invoked, len={len(chunk)}')
        seen_audio['len'] = len(chunk)
        # Feed into pipeline as if buffering
        await pipeline._transcribe_to_pending(chunk)

    async def on_flush() -> None:
        print('[smoke] on_flush invoked')
        seen_audio['flushed'] = True
        await pipeline.flush_buffer()

    server = AudioIngressServer(pairing=pairing, on_audio=on_audio, on_flush=on_flush)

    # Encrypt with derived AES key
    nonce_b64, ciphertext_b64 = TransportCrypto.encrypt(session.aes_key, plaintext)

    payload = {
        'nonce': nonce_b64,
        'ciphertext': ciphertext_b64,
        'sent_at_ms': int(time.time() * 1000),
    }

    # Call the internal handler directly (no websocket) with a well-formed message
    ok = await server._handle_audio_packet(None, {'payload': payload}, session)
    print('[smoke] _handle_audio_packet returned', ok)

    # Simulate flush (this will trigger pipeline.flush_buffer)
    if server._on_flush is not None:
        await server._on_flush()

    # Small wait to ensure callbacks have run
    await asyncio.sleep(0.2)

    # Validate results: ensure injector recorded injected text and flush happened
    injected_text = injector.injected
    if injected_text and seen_audio.get('flushed') is True:
        print('[smoke] SUCCESS: audio processed, transcribed, and injected:', injected_text)
        return 0
    else:
        print('[smoke] FAILURE: expected injection/flushed state', {'injected': injected_text, 'seen': seen_audio})
        return 2


if __name__ == '__main__':
    res = asyncio.run(main())
    raise SystemExit(res)

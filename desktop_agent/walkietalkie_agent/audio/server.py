"""Encrypted WebSocket audio ingestion server."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable

import structlog
import websockets
from cryptography.exceptions import InvalidTag
from pydantic import ValidationError
from websockets.asyncio.server import ServerConnection

from walkietalkie_agent.models import EncryptedAudioPacket, PairingRequest
from walkietalkie_agent.security.pairing import PairingManager, SessionContext, TransportCrypto

logger = structlog.get_logger(__name__)

AudioCallback = Callable[[bytes], Awaitable[None]]
FlushCallback = Callable[[], Awaitable[None]]


class AudioIngressServer:
    """Handles pairing, authentication, and encrypted audio packet receipt."""

    def __init__(
        self,
        pairing: PairingManager,
        on_audio: AudioCallback,
        on_flush: FlushCallback | None = None,
    ) -> None:
        self._pairing = pairing
        self._on_audio = on_audio
        self._on_flush = on_flush
        self._active_ws: ServerConnection | None = None

    async def send_tts(self, text: str) -> None:
        """Push a TTS message to the connected mobile client."""
        if self._active_ws is None:
            return
        try:
            await self._active_ws.send(json.dumps({"type": "tts", "text": text}))
            logger.info("tts.sent", chars=len(text))
        except Exception as exc:
            logger.warning("tts.send_failed", error=str(exc))

    async def send_transcript(self, text: str) -> None:
        """Confirm the injected transcript back to mobile for chat display."""
        if self._active_ws is None:
            print(f"[walkietalkie] send_transcript: no active WS, skipping", flush=True)
            return
        try:
            await self._active_ws.send(json.dumps({"type": "transcript", "text": text}))
            print(f"[walkietalkie] → transcript sent to mobile: {text[:60]}", flush=True)
        except Exception as exc:
            print(f"[walkietalkie] send_transcript FAILED: {exc}", flush=True)
            logger.warning("transcript.send_failed", error=str(exc))

    async def handler(self, websocket: ServerConnection) -> None:
        """Websocket lifecycle entrypoint."""
        self._active_ws = websocket
        print("[walkietalkie] client connected, active_ws set", flush=True)
        session: SessionContext | None = None
        try:
            async for payload in websocket:
                try:
                    message = json.loads(payload)
                except (json.JSONDecodeError, TypeError) as exc:
                    logger.warning("ws.invalid_payload", error=str(exc))
                    await websocket.send(json.dumps({"type": "error", "message": "invalid_json"}))
                    continue
                event_type = message.get("type")
                if event_type == "pair":
                    session = await self._handle_pairing(websocket, message)
                    continue
                if event_type == "audio":
                    if session is None:
                        token = message.get("token", "")
                        session = self._pairing.validate_token(token)
                        if session is None:
                            await websocket.send(json.dumps({"type": "error", "message": "invalid_token"}))
                            continue
                    await self._handle_audio_packet(websocket, message, session)
                    continue
                if event_type == "flush":
                    if session is None:
                        await websocket.send(json.dumps({"type": "error", "message": "not_paired"}))
                        continue
                    if self._on_flush is not None:
                        await self._on_flush()
                    await websocket.send(json.dumps({"type": "flush_ack"}))
                    continue
                await websocket.send(json.dumps({"type": "error", "message": "unknown_event_type"}))
        finally:
            if self._active_ws is websocket:
                self._active_ws = None

    async def _handle_pairing(self, websocket: ServerConnection, message: dict) -> SessionContext | None:
        payload = message.get("payload")
        if payload is None:
            await websocket.send(json.dumps({"type": "error", "message": "missing_payload"}))
            return None
        try:
            req = PairingRequest.model_validate(payload)
        except ValidationError:
            await websocket.send(json.dumps({"type": "error", "message": "invalid_pair_payload"}))
            return None
        try:
            session = self._pairing.create_session(req.device_id, req.client_public_key)
        except (ValueError, Exception):
            await websocket.send(json.dumps({"type": "error", "message": "invalid_public_key"}))
            return None
        response = {
            "type": "pair_ack",
            "payload": {
                "desktop_public_key": self._pairing.desktop_public_key_b64(),
                "session_token": session.token,
                "expires_at_utc": session.expires_at_utc.isoformat(),
            },
        }
        await websocket.send(json.dumps(response))
        logger.info("pairing.completed", device_id=req.device_id, device_name=req.device_name)
        return session

    async def _handle_audio_packet(self, websocket: ServerConnection, message: dict, session: SessionContext) -> bool:
        payload = message.get("payload")
        if payload is None:
            await websocket.send(json.dumps({"type": "error", "message": "missing_payload"}))
            return False

        try:
            packet = EncryptedAudioPacket.model_validate(payload)
        except ValidationError:
            await websocket.send(json.dumps({"type": "error", "message": "invalid_audio_payload"}))
            return False

        try:
            plaintext = TransportCrypto.decrypt(session.aes_key, packet.nonce, packet.ciphertext)
        except (InvalidTag, ValueError):
            await websocket.send(json.dumps({"type": "error", "message": "decrypt_failed"}))
            return False

        await self._on_audio(plaintext)
        return True


async def run_server(host: str, port: int, server: AudioIngressServer) -> None:
    """Start audio server and run forever."""
    async with websockets.serve(server.handler, host, port, max_size=2**22):
        logger.info("audio.server.started", host=host, port=port)
        await asyncio.Future()

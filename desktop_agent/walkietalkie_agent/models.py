"""Core domain models and wire protocol objects."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class PairingRequest(BaseModel):
    """First pairing handshake message from mobile client."""

    device_id: str
    device_name: str
    client_public_key: str


class PairingResponse(BaseModel):
    """Desktop response to pairing request."""

    desktop_public_key: str
    session_token: str
    expires_at_utc: datetime


class EncryptedAudioPacket(BaseModel):
    """Encrypted packet carrying Opus/PCM payload bytes encoded as base64."""

    nonce: str
    ciphertext: str
    sent_at_ms: int


class TranscriptEvent(BaseModel):
    """Normalized transcript event emitted by the STT pipeline."""

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    latency_ms: int


class RiskDecision(BaseModel):
    """Risk filter decision for a transcript candidate."""

    allowed: bool
    needs_confirmation: bool
    keyword: str | None = None


class ActionLogEntry(BaseModel):
    """Audit log item for all user-impacting actions."""

    ts_utc: datetime
    action: Literal["transcribed", "blocked", "injected", "confirmed"]
    transcript: str
    details: str

"""Secure device pairing primitives using X25519 + AES-GCM."""

from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


@dataclass(slots=True)
class SessionContext:
    """A paired session with derived symmetric key and token metadata."""

    device_id: str
    token: str
    expires_at_utc: datetime
    aes_key: bytes


class PairingManager:
    """Issues and validates paired sessions for mobile devices."""

    def __init__(self, token_ttl_seconds: int) -> None:
        self._private_key = x25519.X25519PrivateKey.generate()
        self._sessions: dict[str, SessionContext] = {}
        self._token_ttl_seconds = token_ttl_seconds

    def desktop_public_key_b64(self) -> str:
        """Return desktop X25519 public key in URL-safe base64."""
        public_key = self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        return base64.urlsafe_b64encode(public_key).decode("utf-8")

    def create_session(self, device_id: str, client_public_key_b64: str) -> SessionContext:
        """Create authenticated session context by deriving shared secret via HKDF."""
        client_public_key = x25519.X25519PublicKey.from_public_bytes(
            _b64decode(client_public_key_b64)
        )
        shared_secret = self._private_key.exchange(client_public_key)
        derived_key = HKDF(
            algorithm=hashes.SHA256(),
            length=32,
            salt=None,
            info=b"mozhi-audio-transport",
        ).derive(shared_secret)
        token = secrets.token_urlsafe(32)
        session = SessionContext(
            device_id=device_id,
            token=token,
            expires_at_utc=datetime.now(UTC) + timedelta(seconds=self._token_ttl_seconds),
            aes_key=derived_key,
        )
        self._sessions[token] = session
        return session

    def validate_token(self, token: str) -> SessionContext | None:
        """Return active session or None if invalid/expired."""
        session = self._sessions.get(token)
        if session is None:
            return None
        if session.expires_at_utc <= datetime.now(UTC):
            self._sessions.pop(token, None)
            return None
        return session


def _b64decode(s: str) -> bytes:
    """Decode base64url without requiring padding characters."""
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class TransportCrypto:
    """AES-GCM decrypt/encrypt helper for transport packets."""

    @staticmethod
    def decrypt(aes_key: bytes, nonce_b64: str, ciphertext_b64: str) -> bytes:
        nonce = _b64decode(nonce_b64)
        ciphertext = _b64decode(ciphertext_b64)
        return AESGCM(aes_key).decrypt(nonce, ciphertext, None)

    @staticmethod
    def encrypt(aes_key: bytes, plaintext: bytes) -> tuple[str, str]:
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(aes_key).encrypt(nonce, plaintext, None)
        return (
            base64.urlsafe_b64encode(nonce).decode("utf-8"),
            base64.urlsafe_b64encode(ciphertext).decode("utf-8"),
        )

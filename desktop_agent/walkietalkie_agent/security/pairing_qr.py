"""Pairing payload generation and QR rendering utilities."""

from __future__ import annotations

import json
from pathlib import Path

import qrcode

from walkietalkie_agent.config import AgentSettings
from walkietalkie_agent.security.pairing import PairingManager


def build_pairing_payload(settings: AgentSettings, pairing: PairingManager) -> dict[str, str | int]:
    """Create pairing payload consumed by the mobile QR scanner."""
    return {
        "ws_url": f"ws://{settings.advertised_host}:{settings.bind_port}",
        "desktop_public_key": pairing.desktop_public_key_b64(),
        "version": 1,
    }


def render_pairing_qr(payload: dict[str, str | int], output_path: Path = Path("pairing_qr.png")) -> str:
    """Render payload to terminal ASCII QR and PNG file, returning JSON payload string."""
    payload_json = json.dumps(payload)
    qr = qrcode.QRCode(border=1)
    qr.add_data(payload_json)
    qr.make(fit=True)
    qr.print_ascii(invert=True)
    image = qr.make_image(fill_color="black", back_color="white")
    image.save(output_path)
    return payload_json

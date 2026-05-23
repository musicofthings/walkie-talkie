# CLAUDE.md — Mozhi Session Handover

## Project Purpose
Mozhi is a production-focused, cross-platform voice bridge that enables users to speak into a mobile app and inject the resulting transcript into Claude Desktop Cowork input with low latency, local speech recognition, and strong transport security.

Primary goals:
- No cloud STT dependency (local Faster-Whisper on desktop)
- Secure pairing + encrypted audio transport
- Risk-aware command gating before text injection
- Enterprise-safe architecture and auditability

---

## What Has Been Implemented

### 1) Repository/Foundation
- Full multi-surface project scaffold for desktop (Python) and mobile (Flutter).
- `.gitignore`, `.env.example`, Python packaging metadata (`pyproject.toml`, `setup.py`), and platform packaging scripts.
- Comprehensive `.gitignore` covering Python, Flutter, IDE, and platform artifacts.

### 2) Desktop Agent (Python 3.11+)
Fully implemented modular desktop service under `desktop_agent/mozhi_agent`:

- **Configuration** (`config.py`)
  - Environment-driven settings via `pydantic-settings`.
  - Fields: `bind_host`, `bind_port`, `advertised_host`, `model_size`, `compute_type`, `language`, `token_ttl_seconds`, `auto_send`, `require_confirmation`, `action_log_path`.

- **Observability** (`observability/logging_utils.py`)
  - Structured JSON logging via `structlog`.

- **Domain Models** (`models.py`)
  - All Pydantic BaseModel: `PairingRequest`, `PairingResponse`, `EncryptedAudioPacket`, `TranscriptEvent`, `RiskDecision`, `ActionLogEntry`.

- **Secure Pairing + Crypto** (`security/pairing.py`)
  - X25519 key agreement with HKDF-SHA256 key derivation (`info=b"mozhi-audio-transport"`).
  - Short-lived session tokens with expiry validation.
  - AES-GCM encrypt/decrypt helpers (`TransportCrypto`).

- **QR Pairing Display** (`security/pairing_qr.py`)
  - Generates JSON pairing payload with `ws_url` and `desktop_public_key`.
  - Renders QR code to terminal ASCII + PNG file using `qrcode` library.
  - Integrated into `main.py` — QR displayed on startup.

- **Encrypted Audio Ingress Server** (`audio/server.py`)
  - Async WebSocket server via `websockets`.
  - Pairing handshake, token/session validation, encrypted audio ingestion.
  - `flush` event support for end-of-stream signaling.
  - JSON parse error handling on all payloads.

- **STT Layer** (`stt/transcriber.py`)
  - Faster-Whisper wrapper for local transcription.
  - PCM16 mono -> WAV -> transcribe pipeline with confidence and latency metrics.

- **Risk Filter** (`risk/filter.py`)
  - Keyword detection: `delete`, `remove`, `overwrite`, `deploy`, `execute`, `run`, `drop`, `purge`.
  - Configurable confirmation requirement.
  - Newline-delimited audit log persistence.

- **Injection Layer** (`injection/`)
  - Abstract `BaseInjector` with platform factory (deferred imports to avoid cross-platform ImportError).
  - macOS (`injection/macos.py`): **AX focus + clipboard paste** (NOT `keystroke`). Claude Desktop is Electron — its composer is a web `contenteditable` exposed as the single `AXTextArea` described "Write your prompt to Claude". Flow: `open -a Claude` if not running → `activate` + deminimize → `macos_ax.focus_composer()` (sets `AXFocused`; required because a plain `activate` only auto-focuses on app-switch, so consecutive utterances fail without it) → `Cmd+V` paste (unicode-safe, appends to active tab) → optional Enter → verify via composer `AXValue` → restore clipboard.
  - Windows: `pywinauto` + `keyboard.send_keys` (unchanged; AX work is macOS-only so far).
  - **Why not the `claude://` deeplink:** it targets a surface but always starts a NEW session and CANNOT auto-send (prefill-only) — wrong for an append-and-send conversational loop.

- **macOS Accessibility helpers** (`macos_ax.py`)
  - Raw AX API (pyobjc `ApplicationServices`) — the only way to read/focus Claude's Electron web content (AppleScript `entire contents` can't cross the `AXWebArea`). ~0.35s full window walk.
  - `focus_composer()`, `composer_value()`, `read_conversation_static_texts()` (sidebar excluded), `extract_latest_response()` (anchors on the "You said:" label; skips chrome, timestamps, model name, and the duplicate "Claude responded:" summary node).
  - Lifecycle signals exposed as static text: `"Claude is responding"` → `"Claude finished the response"`.
  - Requires `pyobjc-framework-ApplicationServices` (added to pyproject `[macos]` extra).

- **Real-time Response Watcher** (`response_watcher.py`)
  - Polls AX (~0.5s) and streams Claude's reply to TTS **sentence-by-sentence as it is generated** (low latency for hands-free conversation), instead of waiting for the whole response.
  - Completion detected via the `"Claude finished the response"` status signal, not a timing heuristic.
  - Diffs new content by already-spoken-text **prefix** (with whitespace normalization + common-prefix resync), NOT an integer offset — AXStaticText re-segments between polls, which would otherwise cause mid-word breaks/duplicates.
  - Wired in `bridge.py`: `ResponseWatcher(self._send_tts)`; `snapshot_baseline(combined_text)` before injection; `watch()` task after a successful inject.

- **Confirmation UI + Tray** (`ui/`)
  - Tkinter confirmation dialog for risky transcripts.
  - Optional system tray bootstrap via `pystray`.

- **End-to-End Pipeline** (`pipeline/bridge.py`)
  - Audio chunk buffering (3s threshold at PCM16 mono 16kHz).
  - `handle_audio()` -> buffer -> `_process_chunk()` -> STT -> risk -> confirm -> inject.
  - `flush_buffer()` for processing remaining audio on PTT release.
  - All blocking work (Whisper, UI, injection) runs via `run_in_executor`.

- **Entrypoint** (`main.py`)
  - Async main wiring: logging -> tray -> pairing -> QR display -> transcriber -> risk -> injector -> pipeline -> server.

### 3) Mobile App (Flutter)
Fully implemented mobile client under `mobile_app/`:

- **App Shell** (`main.dart`)
  - Material dark theme with teal accent.

- **Push-to-Talk Screen** (`screens/push_to_talk_screen.dart`)
  - QR scan button navigates to `QrScanScreen`.
  - Push-to-talk microphone with `Listener` (pointer events).
  - Animated mic button with streaming visual feedback.
  - Disconnect button in app bar.
  - Error display for pairing/streaming failures.
  - Proper `dispose()` cleanup.

- **QR Scanner Screen** (`screens/qr_scan_screen.dart`)
  - `mobile_scanner` camera-based QR reader.
  - Returns raw JSON string via `Navigator.pop`.

- **Pairing Service** (`services/pairing_service.dart`)
  - Accepts scanned QR JSON (`ws_url`, `desktop_public_key`).
  - Generates X25519 key pair via `cryptography` package.
  - Opens WebSocket to desktop agent.
  - Sends `pair` message, receives `pair_ack`.
  - Derives AES-256 key via HKDF-SHA256 (matching desktop `info` string).
  - Saves `PairingSession` to `SessionStore`.
  - Exposes `channel` for audio streaming reuse.

- **Audio Stream Service** (`services/audio_stream_service.dart`)
  - Captures PCM16 mono 16kHz via `record` plugin with autoGain, echoCancellation, noiseSuppression.
  - Buffers PCM into ~1s chunks (32KB).
  - Encrypts each chunk with AES-GCM via `CryptoHelper`.
  - Sends encrypted packets over existing WebSocket.
  - `stopStreaming()` flushes remaining buffer and sends `flush` event.

- **Crypto Helper** (`services/crypto_helper.dart`)
  - X25519 key pair generation.
  - HKDF-SHA256 key derivation (matching desktop `info=b"mozhi-audio-transport"`).
  - AES-GCM-256 encryption with 12-byte nonce.

- **Session Model + Store** (`models/pairing_session.dart`, `services/session_store.dart`)
  - In-memory singleton holding: `wsUrl`, `desktopPublicKey`, `clientPrivateKey`, `clientPublicKey`, `sharedSecret`, `sessionToken`.

- **Dependencies** (`pubspec.yaml`)
  - `mobile_scanner` (QR), `cryptography` (X25519/AES-GCM), `qr_flutter`, `web_socket_channel`, `record` (mic capture).
  - Dev: `flutter_test`, `flutter_lints`.

### 4) Docs and Build
- `README.md` covering architecture, setup, pairing flow, runtime behavior, security, observability, packaging, Phase 2 design.
- `scripts/build_windows.ps1` (PyInstaller), `scripts/build_macos.sh` (py2app).

### 5) Code Quality
- Python: all files compile, deferred platform imports, HKDF crypto, `run_in_executor` for blocking ops.
- Flutter: `flutter analyze` clean, widget test passing.
- Comprehensive `.gitignore`, auto-generated files untracked.

---

## Current E2E Flow

1. **Desktop starts** -> loads Whisper model -> displays QR code (terminal ASCII + PNG).
2. **Mobile scans QR** -> extracts `ws_url` + `desktop_public_key`.
3. **Mobile pairs** -> generates X25519 keypair -> WebSocket connect -> sends `pair` -> receives `pair_ack` -> HKDF derives AES key -> stores session.
4. **User holds mic button** -> mobile captures PCM16 mono 16kHz -> buffers 1s chunks -> AES-GCM encrypts -> sends over WebSocket.
5. **Desktop receives** -> decrypts AES-GCM -> buffers 3s of PCM -> transcribes via Whisper -> evaluates risk keywords -> optional confirmation dialog -> AX-focus composer + paste into active Claude tab + Enter.
6. **User releases mic** -> mobile flushes remaining audio -> sends `flush` -> desktop processes remaining buffer.
7. **Downlink (bidirectional TTS)** -> after injection, `ResponseWatcher` polls Claude's AX tree -> streams each completed sentence of Claude's reply over the WebSocket (`type: "tts"`) -> mobile `TtsService` queues and speaks them in order (barge-in via `flush()`).

---

## Known Gaps / Remaining Work

### Hardening and Resilience
1. WebSocket heartbeat/keepalive and reconnection logic.
2. Token refresh on expiry (currently session just expires).
3. Replay protection (nonce tracking window).
4. Rate limiting and per-device quotas.
5. Secure persistence for trusted devices (currently in-memory only).

### Test Coverage
1. No unit tests for crypto helpers, risk filter, pairing handshake.
2. No integration tests for encrypted round-trip or pipeline branching.
3. Widget test is basic smoke test only.

### Operational Maturity
1. No metrics endpoint or health checks.
2. No crash recovery or auto-restart.
3. Tray icon has no stop/cleanup mechanism.

### UX Polish
1. ~~Claude window detection could be more robust.~~ **DONE** — AX focus + paste handles open/minimized/quit/already-frontmost (macOS).
2. No "preview transcript before send" mode.
3. No per-workspace risk policies.
4. No persistent device trust (re-pair needed on restart).
5. `SessionStore` is in-memory only.

---

## Suggested Next Steps

### Phase B — Reliability and Security Hardening
1. Add WebSocket heartbeat, timeout handling, token refresh, and reconnect strategy.
2. Introduce replay protection (nonce tracking/window) and strict packet validation.
3. Add rate limiting and per-device quotas.
4. Persist trusted devices in OS keychain / `flutter_secure_storage`.

### Phase C — Production Readiness
1. Add automated tests:
   - Unit: risk filter, crypto helpers, token expiry, packet model validation.
   - Integration: pairing handshake, encrypted round-trip, pipeline branching.
2. Add CI pipelines (lint, type checks, tests, packaging smoke tests).
3. Add metrics and health endpoints.
4. Improve desktop process lifecycle (auto-start, tray controls, graceful shutdown).

### Phase D — UX and Injection Quality
1. Improve Claude window detection and input targeting.
2. Add "preview transcript before send" mode.
3. Add per-workspace risk policies and user-tunable keyword severity.
4. Add VAD/endpointing for smarter chunk boundaries.

### Phase 2 — Bidirectional TTS (Design Reference)
- Capture Claude output from desktop.
- Synthesize speech locally (platform TTS abstraction).
- Stream encrypted audio downlink to mobile playback buffer.
- Add playback controls + barge-in behavior.

---

## Handover Notes for Next Session
- The core E2E pipeline is now complete: mobile captures -> encrypts -> streams -> desktop decrypts -> transcribes -> risk-checks -> injects, **and streams Claude's reply back as TTS sentence-by-sentence** (bidirectional).
- **Injection / downlink are macOS-only** so far (raw AX API). Windows still uses `pywinauto`; no Windows response watcher yet.
- **Accessibility permission required:** the agent's *terminal* (not VSCode) must be in System Settings → Privacy & Security → Accessibility, or AX focus + `osascript` keystrokes silently no-op.
- **macOS AX is brittle to Claude UI changes:** the composer is matched by AXDescription `"Write your prompt to Claude"`, and the watcher keys off the status strings `"Claude is responding"` / `"Claude finished the response"` and the `"You said:"` / `"Claude responded:"` labels. If a Claude Desktop update renames these, update `macos_ax.py`.
- **Future direction (per project owner):** moving STT to a Gemini real-time, multilingual voice model — likely Gemini Live, which handles bidirectional streaming natively and would supersede the Whisper + AX-scrape + TTS pipeline. Don't over-invest in the AX approach.
- `poll_interval` (default 0.5s) in `ResponseWatcher` trades downlink latency for CPU; AX read is ~0.35s so 0.3s is feasible.
- Priority should also include hardening (heartbeat, reconnect, token refresh) and test coverage.
- HKDF info string `"mozhi-audio-transport"` MUST match between desktop and mobile.
- Desktop uses `qrcode[pil]` — ensure it is installed (`pip install qrcode[pil]`). Install macOS extras for AX: `pip install -e .[macos]`.
- Mobile uses `record` plugin — requires microphone permission on iOS/Android. `TtsService` uses queue mode (`setQueueMode(1)`) so streamed sentences play in order; `flush()` interrupts for a new turn.
- Keep all new modules typed, async where applicable, and with structured logs.

# WalkieTalkie

The first **two-way conversational** voice bridge for remote-controlling Claude Desktop, hands-free (on the go, in the car). It captures speech on mobile, streams securely to desktop, transcribes locally with Faster-Whisper, risk-filters content, injects text into the active Claude Desktop tab, and **streams Claude's reply back as speech sentence-by-sentence** as it is generated.

For the GitHub Pages landing page, see [index.html](./index.html).

## Project Structure

```text
.
├── desktop_agent/
│   └── walkietalkie_agent/
│       ├── audio/
│       ├── injection/         # macOS: AX focus + clipboard paste; Windows: pywinauto
│       ├── observability/
│       ├── pipeline/
│       ├── risk/
│       ├── security/
│       ├── stt/
│       ├── ui/
│       ├── config.py
│       ├── macos_ax.py        # raw AX read/focus of Claude's Electron UI (macOS)
│       ├── response_watcher.py # real-time sentence-by-sentence reply streaming
│       ├── main.py
│       └── models.py
├── mobile_app/
│   └── lib/
│       ├── screens/
│       ├── services/
│       ├── models/
│       └── widgets/
├── scripts/
│   ├── build_macos.sh
│   └── build_windows.ps1
├── .env.example
├── pyproject.toml
└── README.md
```

## Desktop Agent Setup

1. Install Python 3.11+.
2. Create virtual env and install dependencies:
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -U pip
   pip install -e .[tray]
   ```
3. Copy `.env.example` to `.env` and tune values. Environment keys now use the `WALKIETALKIE_` prefix.
   - `WALKIETALKIE_SURFACE_KIND=desktop|cli`
   - `WALKIETALKIE_DESKTOP_TARGET=claude|chatgpt|codex|cursor`
4. Run agent:
   ```bash
   walkietalkie-agent
   ```

> **macOS:** install the platform extras for text injection and reply capture (raw Accessibility API):
> ```bash
> pip install -e .[macos]
> ```
> Then grant **Accessibility** permission to the terminal you run the agent from
> (System Settings → Privacy & Security → Accessibility). Without it, injection
> and reply reading silently no-op.

## Mobile App Setup (Flutter)

1. Install Flutter stable + platform SDKs.
2. In `mobile_app/`:
   ```bash
   flutter pub get
   flutter run
   ```

## Automated Smoke Harness

Run the local harness to verify pairing, transport crypto, STT, risk filtering, and injection wiring without starting real devices:

```bash
python3 scripts/smoke_harness.py
```

It uses mocked STT/injection components so it is fast, deterministic, and safe to run on a development machine.

## Secure Pairing Flow

1. Desktop shows QR containing websocket endpoint + desktop public key fingerprint.
2. Mobile scans QR and sends pairing request (`device_id`, `device_name`, client public key).
3. Desktop derives shared key via X25519 and returns short-lived session token.
4. Mobile encrypts all audio packets with AES-GCM (shared key), includes token per session.

## Runtime Pipeline

1. Mobile press-and-hold streams encrypted PCM chunks.
2. Desktop decrypts packet and sends chunk to Faster-Whisper.
3. Transcript confidence + latency are logged.
4. Risk filter checks destructive keywords: `delete`, `remove`, `overwrite`, `deploy`, `execute`, `run`, `drop`, `purge`.
5. If risky, confirmation dialog is required before injection.
6. Approved text is injected into the active Claude Desktop tab and optionally Enter is pressed (see Injection below).
7. The response watcher reads Claude's streamed reply and sends it back to mobile as TTS, sentence-by-sentence (see Bidirectional TTS below).

## Injection (macOS)

Claude Desktop is an Electron app, so its composer is a web `contenteditable`,
not a native control. Injection therefore:

1. Launches Claude (`open -a Claude`) if it isn't running; restores it if minimized.
2. Focuses the composer via the raw Accessibility API (the one `AXTextArea`
   described "Write your prompt to Claude") — reliable even when Claude is
   already frontmost, where a plain `activate` would not re-focus it.
3. Pastes the text from the clipboard (`Cmd+V`, unicode-safe, appends to the
   current conversation), optionally presses Enter, and restores the clipboard.
4. Verifies the paste by reading the composer's `AXValue`.

> `keystroke` is not used (unreliable for unicode/long text), and the
> `claude://…/new` deeplink is not used (it can't auto-send and always starts a
> new session — wrong for an append-and-send conversational loop).

## Bidirectional TTS (downlink)

After injection, `response_watcher.py` polls Claude's Accessibility tree (~0.5s)
and streams the reply back **as each sentence completes**, so playback starts
while Claude is still writing. Completion is detected via Claude's own status
text ("Claude finished the response"). Each chunk is sent over the existing
encrypted WebSocket as `{type: "tts", text}`; the mobile `TtsService` queues and
speaks chunks in order, with `flush()` for barge-in on a new turn.

## Packaging Instructions

### Windows EXE

```powershell
./scripts/build_windows.ps1
```

Artifacts are generated by PyInstaller under `dist/`.

### macOS App Bundle

```bash
./scripts/build_macos.sh
```

Artifacts are generated by py2app under `dist/`.

## Observability

- Structured JSON logs via `structlog`
- Audit log at `WALKIETALKIE_ACTION_LOG_PATH`
- Transcript confidence and latency are tracked per chunk
- `WALKIETALKIE_DEBUG=true` for verbose diagnostics

## Security Notes

- No plaintext audio streaming
- AES-GCM packet encryption
- X25519 key agreement for pairing
- Session token expiry enforced server-side
- Local-only speech-to-text (no cloud dependency)

## Desktop Targets

The desktop injector is target-aware on macOS and Windows. Start with:

- `claude` for the current Claude Desktop flow
- `chatgpt` for ChatGPT Desktop
- `codex` for Codex Desktop
- `cursor` for Cursor

## CLI Targets

Set `WALKIETALKIE_SURFACE_KIND=cli` to route prompts through a command-line adapter.
The initial CLI profiles are:

- `claude`
- `chatgpt`
- `codex`
- `cursor`

If your local command names differ, update the target profile definitions before use.
CLI stdout responses are routed back through the same transcript/TTS callbacks as desktop replies.

## Phase 2 — Bidirectional voice (status)

Claude response readout to mobile. **Implemented on macOS** (see Bidirectional
TTS above): desktop response capture via the raw AX API, sentence-streamed over
the existing encrypted channel, queued playback on mobile with barge-in. The
remaining items below are future work (Windows capture, local TTS on desktop
instead of mobile, jitter buffer, policy layer). Note: STT/voice is expected to
move to a Gemini real-time multilingual model, which would supersede the
Whisper + AX-scrape pipeline.

### Components

1. **Desktop Response Capture** — *done (macOS)*
   - Detect latest Claude response text region via accessibility APIs.
   - Use event-driven hooks to avoid polling where possible.
2. **Desktop TTS Service**
   - Local TTS engine abstraction (macOS `NSSpeechSynthesizer`, Windows SAPI, optional Coqui).
   - Chunk response into sentence units for low-latency streaming.
3. **Secure Downlink Stream**
   - Reuse paired session key + token.
   - Add `tts_audio` event type over same encrypted channel.
4. **Mobile Playback Buffer**
   - Jitter buffer and audio output controls (pause/skip/repeat).
   - Optional barge-in: cancel playback when user starts push-to-talk.
5. **Policy Layer**
   - Per-workspace controls (disable TTS for sensitive sessions).
   - Audit response playback events.

### NFR Targets

- First audio byte under 700 ms after Claude response completion
- Maintain encrypted transport and token auth parity with uplink path
- Preserve <2 s end-to-end for user speech-to-text injection path

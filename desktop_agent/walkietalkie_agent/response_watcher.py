"""Real-time watcher for Claude Desktop responses (macOS).

Polls Claude's Electron UI via the raw AX API and streams the assistant's reply
out **sentence-by-sentence as it is generated**, so downlink TTS can start
speaking while Claude is still writing — essential for a hands-free, two-way
conversation.  Completion is detected via Claude's own AX status text
("Claude finished the response") rather than a timing heuristic.
"""

from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable

import structlog

logger = structlog.get_logger(__name__)

# A sentence boundary: . ! ? or … followed by whitespace or end-of-text.
_SENTENCE_END = re.compile(r"[.!?…]+(?:\s|$)")


def _common_prefix(a: str, b: str) -> str:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return a[:i]


class ResponseWatcher:
    """Streams Claude Desktop's reply to a sink, sentence by sentence.

    ``on_text`` is awaited with each newly-completed chunk (one or more whole
    sentences).  ``on_complete`` if provided is awaited once with the full reply.
    """

    def __init__(
        self,
        on_text: Callable[[str], Awaitable[None]],
        on_complete: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        self._on_text = on_text
        self._on_complete = on_complete
        self._user_message = ""
        self._spoken = ""  # normalized assistant text already emitted to TTS
        self._active = False

    def snapshot_baseline(self, user_message: str = "") -> None:
        """Call just before injection: records the user's message and resets state."""
        self._user_message = user_message
        self._spoken = ""

    async def watch(self, poll_interval: float = 0.5, timeout_secs: int = 120) -> None:
        if self._active:
            return
        self._active = True
        try:
            await self._poll(poll_interval, timeout_secs)
        finally:
            self._active = False

    async def _poll(self, interval: float, timeout_secs: int) -> None:
        # Imported lazily so non-macOS imports of this module don't fail.
        from walkietalkie_agent import macos_ax

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout_secs
        saw_responding = False

        while loop.time() < deadline:
            await asyncio.sleep(interval)
            texts = await loop.run_in_executor(None, macos_ax.read_conversation_static_texts)
            if macos_ax.STATUS_RESPONDING in texts:
                saw_responding = True
            done = macos_ax.STATUS_DONE in texts
            assistant = macos_ax.extract_latest_response(texts, self._user_message)

            await self._emit_ready_sentences(assistant)

            if done and (saw_responding or assistant):
                remainder = self._pending(assistant).strip()
                if remainder:
                    await self._on_text(remainder)
                self._spoken = assistant
                logger.info("response_watcher.complete", chars=len(assistant))
                if self._on_complete is not None:
                    await self._on_complete(assistant)
                return

        logger.debug("response_watcher.timeout_no_completion")

    def _pending(self, assistant: str) -> str:
        """The part of the (normalized) reply not yet emitted.

        The reply is append-only in meaning but its AXStaticText segmentation can
        shift between polls, so we diff against the already-spoken text by prefix
        (resyncing to the common prefix when an earlier shift occurs) rather than
        a brittle integer offset.
        """
        if not assistant.startswith(self._spoken):
            self._spoken = _common_prefix(self._spoken, assistant)
        return assistant[len(self._spoken):]

    async def _emit_ready_sentences(self, assistant: str) -> None:
        """Emit whole sentences that have appeared since the last emission."""
        pending = self._pending(assistant)
        if not pending:
            return
        ends = list(_SENTENCE_END.finditer(pending))
        if not ends:
            return
        cut = ends[-1].end()
        chunk = pending[:cut].strip()
        if chunk:
            logger.info("response_watcher.chunk", chars=len(chunk))
            await self._on_text(chunk)
        self._spoken += pending[:cut]

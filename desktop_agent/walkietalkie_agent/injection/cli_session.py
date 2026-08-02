"""CLI session adapter for stateful command-line agents.

Maintains a persistent subprocess session so context carries across multiple
turns (e.g., `claude-cli` or `chatgpt-cli` with persistent conversation state).
"""

from __future__ import annotations

import subprocess
import threading
from collections.abc import Iterable

import structlog

from walkietalkie_agent.cli_targets import CliTargetProfile
from walkietalkie_agent.injection.base import BaseInjector

logger = structlog.get_logger(__name__)


class CliSessionInjector(BaseInjector):
    """Send prompts to a long-running CLI agent session."""

    def __init__(self, target: CliTargetProfile) -> None:
        self._target = target
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def inject(self, text: str, press_enter: bool = True) -> str | None:
        with self._lock:
            if self._process is None:
                self._start_session()
            if self._process is None:
                logger.error("cli_session.start_failed", target=self._target.display_name)
                raise RuntimeError(f"Failed to start CLI session for {self._target.display_name}")

            prompt = text if press_enter else text.rstrip("\n")
            try:
                self._process.stdin.write(prompt + "\n")
                self._process.stdin.flush()
                logger.info("cli_session.prompt_sent", target=self._target.display_name, chars=len(text))

                response_lines: list[str] = []
                while True:
                    line = self._process.stdout.readline()
                    if not line:
                        break
                    line_str = line.decode(errors="replace").rstrip("\n")
                    if not line_str:
                        continue
                    response_lines.append(line_str)
                    if self._is_prompt_marker(line_str):
                        break

                response = "\n".join(response_lines[:-1]) if response_lines else None
                if response and response.strip():
                    logger.info("cli_session.response", target=self._target.display_name, chars=len(response))
                    return response.strip()
                return None
            except (BrokenPipeError, OSError) as exc:
                logger.error("cli_session.send_failed", target=self._target.display_name, error=str(exc))
                self._process = None
                raise

    def _start_session(self) -> None:
        """Start a long-running CLI session."""
        try:
            self._process = subprocess.Popen(
                [self._target.command, *self._target.args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            logger.info("cli_session.started", target=self._target.display_name, command=self._target.command)
        except FileNotFoundError as exc:
            logger.error("cli_session.command_missing", target=self._target.display_name, command=self._target.command)
            raise

    def _is_prompt_marker(self, line: str) -> bool:
        """Detect end-of-response markers (customizable per CLI tool)."""
        markers = ["> ", ">> ", "$ ", "# ", ">>> ", "> "]
        return any(line.endswith(marker) for marker in markers)

    def close(self) -> None:
        """Close the CLI session."""
        with self._lock:
            if self._process is not None:
                try:
                    self._process.stdin.close()
                    self._process.terminate()
                    self._process.wait(timeout=5)
                except Exception as exc:
                    logger.warning("cli_session.close_failed", error=str(exc))
                self._process = None

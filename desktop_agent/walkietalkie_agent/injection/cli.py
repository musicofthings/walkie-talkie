"""CLI agent injection via stdin-based subprocess execution."""

from __future__ import annotations

import subprocess

import structlog

from walkietalkie_agent.cli_targets import CliTargetProfile
from walkietalkie_agent.injection.base import BaseInjector

logger = structlog.get_logger(__name__)


class CliInjector(BaseInjector):
    """Send prompts to a CLI agent process."""

    def __init__(self, target: CliTargetProfile) -> None:
        self._target = target

    def inject(self, text: str, press_enter: bool = True) -> None:
        prompt = text if press_enter else text.rstrip("\n")
        try:
            completed = subprocess.run(
                [self._target.command, *self._target.args],
                input=prompt + "\n",
                text=True,
                capture_output=True,
                check=True,
                timeout=120,
            )
            if completed.stdout.strip():
                logger.info(
                    "cli.inject.output",
                    target=self._target.display_name,
                    chars=len(completed.stdout.strip()),
                )
            logger.info("cli.inject.ok", target=self._target.display_name, chars=len(text))
        except FileNotFoundError as exc:
            logger.error("cli.inject.command_missing", target=self._target.display_name, command=self._target.command)
            raise
        except subprocess.CalledProcessError as exc:
            stderr = exc.stderr or ""
            logger.error(
                "cli.inject.failed",
                target=self._target.display_name,
                returncode=exc.returncode,
                stderr=stderr[:500],
            )
            raise

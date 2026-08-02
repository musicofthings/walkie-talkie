"""Risk filtering for destructive intent transcription content."""

from __future__ import annotations

import re
import structlog
from pathlib import Path

from walkietalkie_agent.models import ActionLogEntry, RiskDecision

logger = structlog.get_logger(__name__)

RISK_KEYWORDS = (
    "delete",
    "remove",
    "overwrite",
    "deploy",
    "execute",
    "run",
    "drop",
    "purge",
)


class RiskFilter:
    """Detects risky commands and records action audit logs."""

    def __init__(self, action_log_path: Path, require_confirmation: bool) -> None:
        self._path = action_log_path
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._require_confirmation = require_confirmation

    def evaluate(self, text: str) -> RiskDecision:
        """Evaluate text against risky keyword list."""
        lower_text = text.lower()
        for keyword in RISK_KEYWORDS:
            if re.search(rf"\b{re.escape(keyword)}\b", lower_text):
                return RiskDecision(
                    allowed=not self._require_confirmation,
                    needs_confirmation=self._require_confirmation,
                    keyword=keyword,
                )
        return RiskDecision(allowed=True, needs_confirmation=False, keyword=None)

    def append_audit(self, entry: ActionLogEntry) -> None:
        """Persist action to newline-delimited audit log."""
        line = (
            f"{entry.ts_utc.isoformat()}\t{entry.action}\t"
            f"{entry.transcript.replace(chr(9), ' ')}\t{entry.details}\n"
        )
        try:
            with self._path.open('a', encoding='utf-8') as handle:
                handle.write(line)
        except OSError as exc:
            logger.error("audit.write_failed", path=str(self._path), error=str(exc))

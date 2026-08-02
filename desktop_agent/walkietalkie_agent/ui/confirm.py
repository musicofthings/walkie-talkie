"""User confirmation dialog for risky transcript injection."""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox


def confirm_injection(transcript: str, keyword: str, target_label: str = "Claude") -> bool:
    """Display modal confirmation, returning True if user approves."""
    root = tk.Tk()
    root.withdraw()
    approved = messagebox.askyesno(
        title="WalkieTalkie Risk Guard",
        message=(
            f"Detected risky keyword '{keyword}'.\n\n"
            f"Transcript:\n{transcript}\n\n"
            f"Inject into {target_label} anyway?"
        ),
    )
    root.destroy()
    return bool(approved)

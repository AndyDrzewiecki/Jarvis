"""
DiscordNotifier — push alerts to a Discord webhook.

Config:  JARVIS_DISCORD_WEBHOOK env var.
         If unset, messages are printed to stdout only (no crash).

Usage:
    from jarvis.notifier import notify
    notify("Chicken expires tomorrow", title="Pantry Alert")

    # or use the class directly
    from jarvis.notifier import DiscordNotifier
    n = DiscordNotifier()
    n.notify("Markets shifted to stress regime", title="Investor Alert")
"""
from __future__ import annotations
import os

import requests


class DiscordNotifier:
    """Post messages to a Discord webhook, or stdout if webhook not configured."""

    def __init__(self, webhook: str | None = None) -> None:
        self._webhook = webhook if webhook is not None else os.getenv(
            "JARVIS_DISCORD_WEBHOOK", ""
        )

    def notify(self, message: str, title: str = "Jarvis") -> bool:
        """
        Send a notification. Returns True on success.
        If no webhook is configured, prints to stdout and returns True.
        Never raises.
        """
        if not self._webhook:
            print(f"[Jarvis] {title}: {message}")
            return True
        payload = {"content": f"**{title}**\n{message}"}
        try:
            r = requests.post(self._webhook, json=payload, timeout=10)
            r.raise_for_status()
            return True
        except Exception as e:
            print(f"[Jarvis] Discord notification failed: {e}")
            return False


# Module-level singleton — callers can use jarvis.notifier.notify() directly.
_notifier = DiscordNotifier()


def notify(message: str, title: str = "Jarvis") -> bool:
    return _notifier.notify(message, title)

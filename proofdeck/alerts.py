"""Where alerts go. Slack incoming webhook if SLACK_WEBHOOK_URL is set, else the console."""
from __future__ import annotations

import logging
import os
from typing import Protocol

import httpx

log = logging.getLogger(__name__)


class Notifier(Protocol):
    def send(self, text: str) -> None: ...


class ConsoleNotifier:
    def __init__(self):
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)
        print(text)


class SlackWebhookNotifier:
    def __init__(self, url: str, http: httpx.Client | None = None):
        self.url = url
        self.http = http or httpx.Client(timeout=5)

    def send(self, text: str) -> None:
        try:
            self.http.post(self.url, json={"text": text}).raise_for_status()
        except httpx.HTTPError:
            log.exception("slack alert failed")


def default_notifier() -> Notifier:
    url = os.getenv("SLACK_WEBHOOK_URL")
    return SlackWebhookNotifier(url) if url else ConsoleNotifier()

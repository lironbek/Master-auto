"""Drop-in usage reporter for Python services. Same env vars as the TS version:
CC_USAGE_URL, CC_REPORT_TOKEN, CC_WORKSPACE_ID. Fire-and-forget."""

from __future__ import annotations

import json
import os
import threading
import urllib.request


def report_usage(entries: list[dict]) -> None:
    url, token, ws = os.getenv("CC_USAGE_URL"), os.getenv("CC_REPORT_TOKEN"), os.getenv("CC_WORKSPACE_ID")
    if not (url and token and ws and entries):
        return

    def _send() -> None:
        try:
            req = urllib.request.Request(url, data=json.dumps({"workspace_id": ws, "entries": entries}).encode(),
                                         headers={"Content-Type": "application/json", "X-Report-Token": token}, method="POST")
            urllib.request.urlopen(req, timeout=5).read()
        except Exception:
            pass  # metering must never break the product

    threading.Thread(target=_send, daemon=True).start()


def report_claude(client: str, iface: str, model: str, usage, call_id: str) -> None:
    report_usage([
        {"provider": "claude", "metric": "requests", "quantity": 1, "interface": iface, "client": client, "model": model, "external_id": f"{call_id}:req"},
        {"provider": "claude", "metric": "tokens_in", "quantity": usage.input_tokens, "interface": iface, "client": client, "model": model, "external_id": f"{call_id}:in"},
        {"provider": "claude", "metric": "tokens_out", "quantity": usage.output_tokens, "interface": iface, "client": client, "model": model, "external_id": f"{call_id}:out"},
    ])


def report_whatsapp(client: str, iface: str, messages: int, recipients: int, batch_id: str) -> None:
    report_usage([{"provider": "whatsapp", "metric": "messages", "quantity": messages, "recipients": recipients,
                   "interface": iface, "client": client, "external_id": f"wa:{batch_id}"}])

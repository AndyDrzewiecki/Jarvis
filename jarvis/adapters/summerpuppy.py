"""
SummerPuppyAdapter — wraps the SummerPuppy security ops platform.

Source:  C:/AI-Lab/SummerPuppy/
Port:    8002 (SUMMERPUPPY_URL env var to override)
Auth:    Bearer JWT from SUMMERPUPPY_TOKEN env var
Context: SUMMERPUPPY_CUSTOMER_ID env var

All requests include Authorization: Bearer {token} header.

Capabilities (9 total):
  dashboard_summary    — GET /dashboard/summary
  submit_event         — POST /events
  event_status         — GET /events/{id}
  trust_score          — GET /dashboard/trust
  pending_approvals    — GET /approvals?status=pending
  submit_and_wait      — submit event, poll until complete (timeout 120s)
  approve_event        — POST /events/{id}/approve
  event_history        — GET /dashboard/events?hours=N
  notification_channels — GET /notifications/channels
"""
from __future__ import annotations
import os
import time
from typing import Any

import requests

from jarvis.adapters.base import BaseAdapter, AdapterResult

SUMMERPUPPY_URL = os.getenv("SUMMERPUPPY_URL", "http://localhost:8002")
SUMMERPUPPY_TOKEN = os.getenv("SUMMERPUPPY_TOKEN", "")
SUMMERPUPPY_CUSTOMER_ID = os.getenv("SUMMERPUPPY_CUSTOMER_ID", "")


class SummerPuppyAdapter(BaseAdapter):
    name = "summerpuppy"
    description = (
        "Security ops: ingest events, view trust score, check dashboard, review pending approvals"
    )
    capabilities = [
        "dashboard_summary",
        "submit_event",
        "event_status",
        "trust_score",
        "pending_approvals",
        "submit_and_wait",
        "approve_event",
        "event_history",
        "notification_channels",
    ]

    def _base_url(self) -> str:
        return SUMMERPUPPY_URL.rstrip("/")

    def _headers(self) -> dict:
        token = os.getenv("SUMMERPUPPY_TOKEN", "")
        if not token:
            raise ValueError(
                "SUMMERPUPPY_TOKEN env var not set. "
                "Set it to a valid JWT before using SummerPuppy."
            )
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def _customer_id(self) -> str:
        cid = os.getenv("SUMMERPUPPY_CUSTOMER_ID", "")
        if not cid:
            raise ValueError(
                "SUMMERPUPPY_CUSTOMER_ID env var not set."
            )
        return cid

    def _service_down(self) -> AdapterResult:
        url = self._base_url()
        return AdapterResult(
            success=False,
            text=(
                f"SummerPuppy not reachable at {url}. "
                "Start with: uvicorn main:app --port 8002"
            ),
            adapter=self.name,
        )

    def run(self, capability: str, params: dict[str, Any]) -> AdapterResult:
        base = self._base_url()
        try:
            headers = self._headers()
            cid = self._customer_id()

            if capability == "dashboard_summary":
                r = requests.get(
                    f"{base}/api/v1/customers/{cid}/dashboard/summary",
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "submit_event":
                r = requests.post(
                    f"{base}/api/v1/customers/{cid}/events",
                    json=params,
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True,
                    text=f"Event submitted: {data}",
                    data=data,
                    adapter=self.name,
                )

            elif capability == "event_status":
                event_id = params.get("event_id")
                if not event_id:
                    return AdapterResult(
                        success=False,
                        text="[summerpuppy] event_status requires 'event_id' param",
                        adapter=self.name,
                    )
                r = requests.get(
                    f"{base}/api/v1/customers/{cid}/events/{event_id}",
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "trust_score":
                r = requests.get(
                    f"{base}/api/v1/customers/{cid}/dashboard/trust",
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "pending_approvals":
                r = requests.get(
                    f"{base}/api/v1/customers/{cid}/approvals",
                    params={"status": "pending"},
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "submit_and_wait":
                # Submit event, then poll until status != RUNNING (timeout 120s).
                r = requests.post(
                    f"{base}/api/v1/customers/{cid}/events",
                    json=params,
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                submit_data = r.json()
                event_id = submit_data.get("event_id") or submit_data.get("id")
                if not event_id:
                    return AdapterResult(
                        success=True,
                        text=f"Event submitted (no event_id to poll): {submit_data}",
                        data=submit_data,
                        adapter=self.name,
                    )
                deadline = time.time() + 120
                while time.time() < deadline:
                    poll = requests.get(
                        f"{base}/api/v1/customers/{cid}/events/{event_id}",
                        headers=headers,
                        timeout=10,
                    )
                    poll.raise_for_status()
                    poll_data = poll.json()
                    status = str(poll_data.get("status", "")).upper()
                    if status not in ("RUNNING", "PENDING", ""):
                        return AdapterResult(
                            success=True,
                            text=f"Event {event_id} completed with status {status}",
                            data=poll_data,
                            adapter=self.name,
                        )
                    time.sleep(5)
                return AdapterResult(
                    success=False,
                    text=f"[summerpuppy] Timed out waiting for event {event_id}",
                    adapter=self.name,
                )

            elif capability == "approve_event":
                event_id = params.get("event_id")
                if not event_id:
                    return AdapterResult(
                        success=False,
                        text="[summerpuppy] approve_event requires 'event_id' param",
                        adapter=self.name,
                    )
                approved = params.get("approved", True)
                reason = params.get("reason", "")
                r = requests.post(
                    f"{base}/api/v1/customers/{cid}/events/{event_id}/approve",
                    json={"approved": approved, "reason": reason},
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                action = "approved" if approved else "rejected"
                return AdapterResult(
                    success=True,
                    text=f"Event {event_id} {action}.",
                    data=data,
                    adapter=self.name,
                )

            elif capability == "event_history":
                hours = params.get("hours", 24)
                r = requests.get(
                    f"{base}/api/v1/customers/{cid}/dashboard/events",
                    params={"hours": hours},
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            elif capability == "notification_channels":
                r = requests.get(
                    f"{base}/api/v1/customers/{cid}/notifications/channels",
                    headers=headers,
                    timeout=10,
                )
                r.raise_for_status()
                data = r.json()
                return AdapterResult(
                    success=True, text=str(data), data=data, adapter=self.name
                )

            else:
                return AdapterResult(
                    success=False,
                    text=f"[summerpuppy] Unknown capability: {capability}",
                    adapter=self.name,
                )

        except requests.exceptions.ConnectionError:
            return self._service_down()
        except requests.exceptions.Timeout:
            return AdapterResult(
                success=False,
                text=f"[summerpuppy] Request timed out for capability '{capability}'",
                adapter=self.name,
            )
        except requests.exceptions.HTTPError as e:
            return AdapterResult(
                success=False,
                text=f"[summerpuppy] HTTP error: {e}",
                adapter=self.name,
            )
        except ValueError as e:
            return AdapterResult(
                success=False,
                text=f"[summerpuppy] Configuration error: {e}",
                adapter=self.name,
            )

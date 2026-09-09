from __future__ import annotations

import threading
import time
from typing import Any

import requests


class TicketPollerAgent:
    def __init__(self, config, workflow_factory, initial_state_builder):
        self._config = config
        self._workflow_factory = workflow_factory
        self._initial_state_builder = initial_state_builder
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._resolved_tickets: set[str] = set()
        self._processed_tickets: set[str] = set()
        self._in_progress: set[str] = set()
        self.last_polled_at: float | None = None
        self.last_run_result: dict[str, Any] | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run_loop, name="ticket-poller", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()

    def status(self) -> dict[str, Any]:
        return {
            "enabled": bool(self._config.ticket_poller_enabled),
            "interval_seconds": self._config.ticket_poller_interval_seconds,
            "resolved_tickets": sorted(self._resolved_tickets),
            "processed_tickets": sorted(self._processed_tickets),
            "in_progress": sorted(self._in_progress),
            "last_polled_at": self.last_polled_at,
            "last_run_result": self.last_run_result,
        }

    def scan_once(self) -> dict[str, Any]:
        open_ids = self._fetch_open_ticket_ids()
        candidate_ids = [
            ticket_id
            for ticket_id in open_ids
            if ticket_id not in self._processed_tickets and ticket_id not in self._in_progress
        ]
        for ticket_id in candidate_ids:
            resolved = self._handle_new_ticket(ticket_id)
            self._processed_tickets.add(ticket_id)
            if resolved:
                self._resolved_tickets.add(ticket_id)
        return {
            "processed_tickets": candidate_ids,
            "open_tickets": open_ids,
            "last_run_result": self.last_run_result,
        }

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            self.scan_once()

            self._stop_event.wait(max(1, self._config.ticket_poller_interval_seconds))

    def _fetch_open_ticket_ids(self) -> list[str]:
        self.last_polled_at = time.time()
        try:
            base = self._config.jira_base_url.rstrip("/")
            response = requests.get(
                f"{base}{self._config.jira_get_open_ticket_path}",
                timeout=self._config.http_request_timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            return self._normalize_ticket_ids(payload)
        except Exception as exc:
            self.last_run_result = {
                "status": "POLL_FAILED",
                "error": str(exc),
            }
            return []

    @staticmethod
    def _normalize_ticket_ids(payload: Any) -> list[str]:
        if isinstance(payload, list):
            return [str(x) for x in payload if str(x).strip()]
        if isinstance(payload, dict):
            body = payload.get("body")
            if isinstance(body, list):
                return [str(x) for x in body if str(x).strip()]
            if isinstance(body, str) and body.strip():
                return [body.strip()]
        if isinstance(payload, str) and payload.strip():
            return [payload.strip()]
        return []

    def _handle_new_ticket(self, ticket_id: str) -> bool:
        if ticket_id in self._in_progress:
            return False

        self._in_progress.add(ticket_id)
        try:
            details = self._fetch_ticket_details(ticket_id)
            if self._is_auto_generated_ticket(details):
                self.last_run_result = {
                    "status": "SKIPPED_AUTO_GENERATED_TICKET",
                    "ticket_id": ticket_id,
                }
                return True

            payload = {
                "project_name": self._config.ticket_poller_default_project_name,
                "domain": self._config.ticket_poller_default_domain,
                "trigger_bug_generation": False,
                "max_retries": self._config.workflow_default_max_retries,
                "source_ticket_id": ticket_id,
                "source_ticket_details": details,
            }
            workflow = self._workflow_factory()
            result = workflow.invoke(self._initial_state_builder(payload, self._config))

            self.last_run_result = {
                "status": "WORKFLOW_TRIGGERED",
                "ticket_id": ticket_id,
                "build_status": result.get("build_status", "UNKNOWN"),
                "jira_ticket_status": result.get("jira_ticket_status", ""),
                "source_ticket_comment_status": result.get("source_ticket_comment_status", ""),
                "source_ticket_status_update": result.get("source_ticket_status_update", ""),
            }
            return result.get("build_status") == "SUCCESS"
        except Exception as exc:
            self.last_run_result = {
                "status": "WORKFLOW_FAILED",
                "ticket_id": ticket_id,
                "error": str(exc),
            }
            return False
        finally:
            self._in_progress.discard(ticket_id)

    def _fetch_ticket_details(self, ticket_id: str) -> dict[str, Any]:
        try:
            base = self._config.jira_base_url.rstrip("/")
            response = requests.get(
                f"{base}/jira/issue/{ticket_id}",
                timeout=self._config.http_request_timeout_seconds,
            )
            if response.ok:
                payload = response.json()
                return payload if isinstance(payload, dict) else {"raw": payload}
        except Exception:
            pass
        return {"id": ticket_id}

    @staticmethod
    def _is_auto_generated_ticket(details: dict[str, Any]) -> bool:
        if not isinstance(details, dict):
            return False

        summary = str(details.get("summary") or details.get("title") or "")
        description = str(details.get("description") or details.get("body") or "")
        combined = f"{summary}\n{description}".lower()

        return (
            "fr autofix failed" in combined
            or "auto-created by agent workflow" in combined
        )

from __future__ import annotations

import contextvars
import copy
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Optional


# LangGraph builds its channel set from the AgentState TypedDict, so any extra
# keys we stuff into the state (e.g. a "_progress_callback") get stripped before
# the first node executes and the callback never fires. To deliver progress
# reliably we keep the active callback in a context variable bound to the thread
# that drives workflow.invoke(). Each worker thread starts with a fresh context,
# so runs stay isolated from one another.
_active_progress_callback: contextvars.ContextVar[Optional[Callable[..., None]]] = (
    contextvars.ContextVar("active_progress_callback", default=None)
)


def set_progress_callback(callback: Optional[Callable[..., None]]) -> None:
    _active_progress_callback.set(callback)


def get_progress_callback() -> Optional[Callable[..., None]]:
    return _active_progress_callback.get()


def sanitize_state(state: dict[str, Any]) -> dict[str, Any]:
    sanitized: dict[str, Any] = {}
    for key, value in state.items():
        if key.startswith("_"):
            continue
        if callable(value):
            continue
        sanitized[key] = value
    return sanitized


class WorkflowRunStore:
    def __init__(self, max_runs: int = 20):
        self._lock = threading.Lock()
        self._runs: dict[str, dict[str, Any]] = {}
        self._ordered_ids: deque[str] = deque(maxlen=max_runs)

    def create_run(self, payload: dict[str, Any]) -> str:
        run_id = str(uuid.uuid4())
        now = time.time()
        record = {
            "run_id": run_id,
            "status": "QUEUED",
            "payload": copy.deepcopy(payload),
            "created_at": now,
            "started_at": None,
            "finished_at": None,
            "current_step": "queued",
            "events": [],
            "result": None,
            "error": None,
        }
        with self._lock:
            evicted_id = None
            if len(self._ordered_ids) == self._ordered_ids.maxlen:
                evicted_id = self._ordered_ids[0]
            self._ordered_ids.append(run_id)
            self._runs[run_id] = record
            if evicted_id and evicted_id in self._runs:
                del self._runs[evicted_id]
        return run_id

    def start_run(self, run_id: str) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run["status"] = "RUNNING"
            run["started_at"] = time.time()
            run["current_step"] = "starting"

    def append_event(
        self,
        run_id: str,
        node: str,
        status: str,
        message: str = "",
        snapshot: dict[str, Any] | None = None,
    ) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            event = {
                "timestamp": time.time(),
                "node": node,
                "status": status,
                "message": message,
            }
            run["events"].append(event)
            run["current_step"] = node
            if snapshot is not None:
                run["result"] = sanitize_state(snapshot)

    def finish_run(self, run_id: str, result: dict[str, Any]) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run["status"] = "COMPLETED"
            run["finished_at"] = time.time()
            run["current_step"] = "completed"
            run["result"] = sanitize_state(result)

    def fail_run(self, run_id: str, error: Exception, snapshot: dict[str, Any] | None = None) -> None:
        with self._lock:
            run = self._runs.get(run_id)
            if not run:
                return
            run["status"] = "FAILED"
            run["finished_at"] = time.time()
            run["current_step"] = "failed"
            run["error"] = {
                "type": type(error).__name__,
                "message": str(error),
            }
            if snapshot is not None:
                run["result"] = sanitize_state(snapshot)

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            run = self._runs.get(run_id)
            return copy.deepcopy(run) if run else None

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            return [copy.deepcopy(self._runs[run_id]) for run_id in reversed(self._ordered_ids) if run_id in self._runs]


workflow_run_store = WorkflowRunStore()
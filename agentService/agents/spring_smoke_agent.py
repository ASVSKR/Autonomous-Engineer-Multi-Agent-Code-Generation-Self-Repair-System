from __future__ import annotations

from typing import Any

import requests

from agent_runtime import load_runtime_config


def _safe_json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text


def spring_smoke_agent(state):
    config = load_runtime_config()
    base = config.jira_base_url.rstrip("/")
    timeout = config.http_request_timeout_seconds

    # Keep smoke checks non-destructive. Do not create tickets from smoke flow.
    smoke_calls = [
        ("GET", f"{base}{config.jira_get_open_ticket_path}", None),
    ]

    results: list[dict[str, Any]] = []
    overall_ok = True

    for method, url, payload in smoke_calls:
        try:
            if method == "POST":
                resp = requests.post(url, json=payload, timeout=timeout)
            else:
                resp = requests.get(url, timeout=timeout)

            ok = 200 <= resp.status_code < 300
            overall_ok = overall_ok and ok
            results.append(
                {
                    "method": method,
                    "url": url,
                    "status_code": resp.status_code,
                    "ok": ok,
                    "body": _safe_json(resp),
                }
            )
        except Exception as exc:
            overall_ok = False
            results.append(
                {
                    "method": method,
                    "url": url,
                    "status_code": 0,
                    "ok": False,
                    "error": str(exc),
                }
            )

    state["spring_smoke_status"] = "SUCCESS" if overall_ok else "FAILED"
    state["spring_smoke_results"] = results

    print("Spring Smoke Agent Executed")
    return state

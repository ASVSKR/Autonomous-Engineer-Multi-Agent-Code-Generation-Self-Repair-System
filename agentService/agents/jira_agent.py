from datetime import datetime, timezone
from pathlib import Path
import re

import requests

from agent_runtime import load_runtime_config


def _render_issue_path(path_template: str, issue_id: str) -> str:
    return path_template.replace("__ISSUE_ID__", issue_id).replace("{issueId}", issue_id)


def _update_source_ticket_status(ticket_id: str, status: str, config) -> str:
    if not ticket_id:
        return "NO_SOURCE_TICKET"
    base_url = config.jira_base_url.rstrip("/")
    update_path = _render_issue_path(config.jira_update_status_path_template, ticket_id)
    update_url = f"{base_url}{update_path}"
    try:
        response = requests.post(
            update_url,
            params={"status": status},
            timeout=config.http_request_timeout_seconds,
        )
        if response.ok:
            return f"SOURCE_STATUS_UPDATED:{status}"
        return f"SOURCE_STATUS_FAILED_{response.status_code}"
    except Exception as exc:
        return f"SOURCE_STATUS_ERROR: {exc}"


def _update_ticket_labels(ticket_id: str, add_label: str, remove_label: str, config) -> str:
    if not ticket_id:
        return "NO_TICKET"
    # Local/stub or unavailable tickets cannot be relabeled on the real Jira.
    if ticket_id in {"UNAVAILABLE"} or "LOCAL" in ticket_id:
        return "LABELS_SKIPPED_LOCAL"
    base_url = config.jira_base_url.rstrip("/")
    labels_path = _render_issue_path(config.jira_labels_path_template, ticket_id)
    labels_url = f"{base_url}{labels_path}"
    try:
        response = requests.post(
            labels_url,
            params={"add": add_label, "remove": remove_label},
            timeout=config.http_request_timeout_seconds,
        )
        if response.ok:
            return f"LABELS_UPDATED:+{add_label}/-{remove_label}"
        return f"LABELS_FAILED_{response.status_code}"
    except Exception as exc:
        return f"LABELS_ERROR: {exc}"


def _post_source_ticket_comment(ticket_id: str, comment: str, config) -> str:
    if not ticket_id:
        return "NO_SOURCE_TICKET"
    base_url = config.jira_base_url.rstrip("/")
    comment_path = _render_issue_path(config.jira_comment_path_template, ticket_id)
    comment_url = f"{base_url}{comment_path}"
    try:
        response = requests.post(
            comment_url,
            params={"text": comment},
            timeout=config.http_request_timeout_seconds,
        )
        if response.ok:
            return "SOURCE_COMMENT_POSTED"
        return f"SOURCE_COMMENT_FAILED_{response.status_code}"
    except Exception as exc:
        return f"SOURCE_COMMENT_ERROR: {exc}"


def _extract_java_class_name(code: str, fallback: str) -> str:
    match = re.search(r"class\s+([A-Za-z_][A-Za-z0-9_]*)", code or "")
    if match:
        return match.group(1)
    return fallback


def _attach_file_to_ticket(ticket_id: str, file_path: Path, config) -> str:
    if not ticket_id or not file_path.exists():
        return f"ATTACHMENT_SKIPPED:{file_path.name}"

    base_url = config.jira_base_url.rstrip("/")
    attachment_path = _render_issue_path(config.jira_attachment_path_template, ticket_id)
    attachment_url = f"{base_url}{attachment_path}"

    try:
        with file_path.open("rb") as file_stream:
            response = requests.post(
                attachment_url,
                files={"file": (file_path.name, file_stream, "text/plain")},
                timeout=config.http_request_timeout_seconds,
            )
        if response.ok:
            return f"ATTACHED:{file_path.name}"
        return f"ATTACHMENT_FAILED_{response.status_code}:{file_path.name}"
    except Exception as exc:
        return f"ATTACHMENT_ERROR:{file_path.name}:{exc}"


def _attach_generated_artifacts(state, ticket_id: str, config) -> str:
    project_path = Path(state.get("java_project_path", "") or "")
    if not project_path.exists():
        return "ATTACHMENT_SKIPPED:NO_PROJECT_PATH"

    generated_code = state.get("generated_code", "")
    generated_test = state.get("generated_test", "")

    service_class = _extract_java_class_name(generated_code, "GeneratedService")
    test_class = _extract_java_class_name(generated_test, f"{service_class}Test")

    source_file = project_path / "src" / "main" / "java" / "com" / "demo" / f"{service_class}.java"
    test_file = project_path / "src" / "test" / "java" / "com" / "demo" / f"{test_class}.java"

    results = [
        _attach_file_to_ticket(ticket_id, source_file, config),
        _attach_file_to_ticket(ticket_id, test_file, config),
    ]
    return " | ".join(results)


def source_ticket_in_progress_agent(state):
    config = load_runtime_config()
    source_ticket_id = state.get("source_ticket_id", "")
    if not source_ticket_id:
        state["source_ticket_status_update"] = "NO_SOURCE_TICKET"
        return state

    state["source_ticket_status_update"] = _update_source_ticket_status(
        source_ticket_id,
        config.jira_in_progress_status_value,
        config,
    )
    return state


def _maybe_handoff_to_developer(state, config) -> None:
    """When the AI fix loop is exhausted and the build is still broken, relabel the
    ticket from `ai-fix` to `developer-fix`. The poller's JQL only matches `ai-fix`
    tickets, so this hands the FR off to a human and stops further auto-retries.
    """
    build_ok = state.get("build_status") == "SUCCESS"
    max_retries = int(state.get("max_retries", 0) or 0)
    retries_exhausted = max_retries > 0 and int(state.get("retry_count", 0) or 0) >= max_retries

    if build_ok or not retries_exhausted:
        state["developer_handoff_status"] = "NOT_REQUIRED"
        return

    # Relabel whichever real ticket(s) represent this FR.
    candidate_ids = {
        state.get("jira_ticket_id", ""),
        state.get("source_ticket_id", ""),
    }
    results = []
    for ticket_id in candidate_ids:
        if not ticket_id:
            continue
        results.append(
            f"{ticket_id}:{_update_ticket_labels(ticket_id, config.jira_developer_fix_label, config.jira_ai_fix_label, config)}"
        )
    state["developer_handoff_status"] = " | ".join(results) if results else "NO_TICKET_TO_HANDOFF"


def source_ticket_finalize_agent(state):
    config = load_runtime_config()

    # Escalate to a developer if the AI could not resolve the FR within the retry budget.
    _maybe_handoff_to_developer(state, config)

    source_ticket_id = state.get("source_ticket_id", "")
    if not source_ticket_id:
        state["source_ticket_comment_status"] = "NO_SOURCE_TICKET"
        return state

    rca_comment = (state.get("fix_rca_comment") or "").strip()
    if not rca_comment:
        rca_comment = (
            "Root Cause Analysis:\n"
            "- Auto-fix flow completed but no structured RCA was returned by fixer agent.\n\n"
            "Solution Applied:\n"
            "- Generated and validated code/test updates via workflow.\n\n"
            "Validation:\n"
            f"- Build status: {state.get('build_status', 'UNKNOWN')}\n"
            f"- Retry count: {state.get('retry_count', 0)}/{state.get('max_retries', 0)}"
        )

    state["source_ticket_comment_status"] = _post_source_ticket_comment(source_ticket_id, rca_comment, config)

    if state.get("build_status") == "SUCCESS":
        state["source_ticket_status_update"] = _update_source_ticket_status(
            source_ticket_id,
            config.jira_done_status_value,
            config,
        )
    else:
        state["source_ticket_status_update"] = "SOURCE_LEFT_IN_PROGRESS"

    return state


def jira_agent(state):
    config = load_runtime_config()

    existing_ticket = (state.get("jira_ticket_id") or "").strip()
    if existing_ticket:
        # Avoid opening duplicate Jira issues across retries/failure branches.
        state["jira_ticket_status"] = state.get("jira_ticket_status") or "CREATED"
        return state

    project_name = state.get("project_name", "unknown-project")
    domain = state.get("domain", "unknown-domain")
    source_ticket_id = state.get("source_ticket_id", "")
    # If this run was triggered from an existing source ticket, do not open another ticket.
    if source_ticket_id:
        state["jira_ticket_id"] = source_ticket_id
        state["jira_ticket_status"] = "SKIPPED_SOURCE_FLOW"
        return state

    source_ticket_details = state.get("source_ticket_details", {})
    build_stderr = state.get("build_stderr", "")
    build_stdout = state.get("build_stdout", "")
    compile_status = state.get("compile_status", "")
    test_status = state.get("test_status", "")
    detected_exception_type = state.get("detected_exception_type", "")
    detected_exception_message = state.get("detected_exception_message", "")

    source_class = state.get("source_class", "")
    source_method = state.get("source_method", "")
    source_file_path = state.get("source_file_path", "")
    failing_test_class = state.get("failing_test_class", "")
    failing_test_method = state.get("failing_test_method", "")
    failing_test_line = state.get("failing_test_line", "")
    failing_test_file_path = state.get("failing_test_file_path", "")

    failure_location = ""
    if source_class and source_method:
        failure_location = f"{source_class}.{source_method}()"
    elif source_class:
        failure_location = source_class

    failing_test_ref = ""
    if failing_test_class and failing_test_method:
        failing_test_ref = f"{failing_test_class}.{failing_test_method}"
        if failing_test_line:
            failing_test_ref = f"{failing_test_ref}:{failing_test_line}"

    # Summary must convey WHAT failed and WHERE at a glance.
    summary = f"[AutoFix] Test failure in {project_name}"
    if detected_exception_type and failure_location:
        summary = f"[AutoFix] {detected_exception_type} in {failure_location} ({project_name})"
    elif detected_exception_type:
        summary = f"[AutoFix] {detected_exception_type} detected in {project_name}"
    elif failure_location:
        summary = f"[AutoFix] Test failure in {failure_location} ({project_name})"

    source_context = ""
    if isinstance(source_ticket_details, dict) and source_ticket_details:
        source_context = (
            "Source ticket context:\n"
            f"{str(source_ticket_details)[:1000]}\n\n"
        )

    stdout_tail = build_stdout[-1500:] if build_stdout else ""
    description = (
        "WHAT FAILED\n"
        "-----------\n"
        f"A newly added corner-case test detected a runtime defect in the generated service.\n"
        f"Exception type : {detected_exception_type or 'UNKNOWN'}\n"
        f"Exception detail: {detected_exception_message or 'N/A'}\n\n"
        "WHERE (LOCATION)\n"
        "----------------\n"
        f"Service class  : {source_class or 'UNKNOWN'}\n"
        f"Service method : {source_method or 'UNKNOWN'}\n"
        f"Source file    : {source_file_path or 'UNKNOWN'}\n"
        f"Failing test   : {failing_test_ref or 'UNKNOWN'}\n"
        f"Test file      : {failing_test_file_path or 'UNKNOWN'}\n\n"
        "HOW TO REPRODUCE\n"
        "----------------\n"
        f"1. cd {project_name}\n"
        "2. Run: mvn test\n"
        f"3. Observe failure in {failing_test_ref or 'the corner-case test'} due to {detected_exception_type or 'a runtime exception'}.\n\n"
        "PIPELINE STATUS\n"
        "---------------\n"
        f"Compile status : {compile_status or 'UNKNOWN'} (code compiles cleanly)\n"
        f"Baseline tests : {state.get('baseline_test_status', 'UNKNOWN')}\n"
        f"Corner-case test: {state.get('edge_case_test_status', 'UNKNOWN')}\n"
        f"Overall test    : {test_status or 'UNKNOWN'}\n"
        f"Retry count     : {state.get('retry_count', 0)} / {state.get('max_retries', 0)}\n\n"
        "ACTION FOR FIX AGENT\n"
        "--------------------\n"
        f"Modify ONLY the source file ({source_file_path or 'service class'}) with a minimal change so that\n"
        f"{source_method or 'the business method'} no longer throws {detected_exception_type or 'the runtime exception'}.\n"
        "Do NOT modify the test files.\n\n"
        f"Reported at: {datetime.now(timezone.utc).isoformat()}\n"
        f"Project: {project_name} | Domain: {domain}\n\n"
        f"{source_context}"
        f"Build log tail (truncated):\n{stdout_tail}\n\n"
        f"Build stderr (truncated):\n{build_stderr[:800]}"
    )

    payload = {
        "summary": summary,
        "description": description,
        "priority": "High",
    }

    # Persist for dashboard visibility and downstream agents.
    state["jira_summary"] = summary
    state["jira_description"] = description

    if config.jira_stub_enabled:
        state["jira_ticket_id"] = f"{config.jira_project_key}-LOCAL-{int(datetime.now().timestamp())}"
        state["jira_ticket_status"] = "CREATED"
        state["jira_attachment_status"] = "ATTACHMENT_SKIPPED:STUB_MODE"
        return state

    base_url = config.jira_base_url.rstrip("/")
    jira_service_url = f"{base_url}{config.jira_create_path}"
    try:
        response = requests.post(
            jira_service_url,
            json=payload,
            timeout=config.http_request_timeout_seconds,
        )
        response.raise_for_status()
        response_json = response.json()
        body = response_json.get("body", {})
        ticket_key = body.get("key") or "UNKNOWN"
        state["jira_ticket_id"] = ticket_key
        state["jira_ticket_status"] = "CREATED"
        state["jira_attachment_status"] = _attach_generated_artifacts(state, ticket_key, config)
    except Exception as exc:
        state["jira_ticket_id"] = "UNAVAILABLE"
        state["jira_ticket_status"] = f"FAILED_TO_CREATE: {exc}"
        state["jira_attachment_status"] = "ATTACHMENT_SKIPPED:CREATE_FAILED"

    return state


def jira_close_agent(state):
    config = load_runtime_config()
    ticket_id = state.get("jira_ticket_id", "")
    if not ticket_id:
        state["jira_ticket_status"] = "NO_TICKET"
        return state

    update_path = _render_issue_path(config.jira_update_status_path_template, ticket_id)
    base_url = config.jira_base_url.rstrip("/")
    update_url = f"{base_url}{update_path}"

    try:
        requests.post(
            update_url,
            params={"status": config.jira_done_status_value},
            timeout=config.http_request_timeout_seconds,
        )
        state["jira_ticket_status"] = "DONE"
    except Exception:
        state["jira_ticket_status"] = "DONE_LOCAL_ONLY"

    return state

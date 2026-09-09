import os
import threading

from flask import Flask, jsonify, render_template, request

from agents.ticket_poller_agent import TicketPollerAgent
from agent_runtime import load_api_schema, load_runtime_config, summarize_api_schema
from workflow_run_store import sanitize_state, set_progress_callback, workflow_run_store
from workflows.langgraph_workflow_llm import create_workflow as create_llm_workflow


_ticket_poller: TicketPollerAgent | None = None


def _initial_state(payload: dict, config) -> dict:
    return {
        "project_name": payload.get("project_name", ""),
        "domain": payload.get("domain", ""),
        "java_project_path": "",
        "generated_code": "",
        "generated_test": "",
        "build_status": "",
        "test_status": "",
        "baseline_test_status": "NOT_RUN",
        "edge_case_test_status": "NOT_RUN",
        "compile_status": "",
        "build_stdout": "",
        "build_stderr": "",
        "detected_exception_type": "",
        "detected_exception_message": "",
        "source_class": "",
        "source_method": "",
        "source_file_path": "",
        "failing_test_class": "",
        "failing_test_method": "",
        "failing_test_line": "",
        "failing_test_file_path": "",
        "trigger_bug_generation": bool(payload.get("trigger_bug_generation", False)),
        "api_schema_summary": "",
        "jira_ticket_id": "",
        "jira_ticket_status": "",
        "jira_summary": "",
        "jira_description": "",
        "git_commit_message": payload.get("git_commit_message", config.workflow_default_git_commit_message),
        "git_commit_result": "",
        "jenkins_status": "",
        "jenkins_build_url": "",
        "spring_smoke_status": "",
        "spring_smoke_results": [],
        "injected_exception_type": "",
        "injected_exception_scenario": "",
        "source_ticket_id": payload.get("source_ticket_id", ""),
        "source_ticket_details": payload.get("source_ticket_details", {}),
        "fix_rca_comment": "",
        "fix_solution_summary": "",
        "fix_strategy": "",
        "fix_test_modified": "NO",
        "fix_llm_error": "",
        "source_ticket_comment_status": "",
        "source_ticket_status_update": "",
        "jira_attachment_status": "",
        "developer_handoff_status": "",
        "workflow_run_id": payload.get("workflow_run_id", ""),
        "workflow_status": "QUEUED",
        "workflow_current_step": "queued",
        "workflow_events": [],
        "retry_count": 0,
        "max_retries": int(payload.get("max_retries", config.workflow_default_max_retries)),
    }


def _should_start_background_worker(config) -> bool:
    if not config.ticket_poller_enabled:
        return False
    if not config.flask_debug:
        return True
    return os.environ.get("WERKZEUG_RUN_MAIN") == "true"


def _build_progress_callback(run_id: str):
    def callback(node_name: str, status: str, message: str, snapshot: dict) -> None:
        workflow_run_store.append_event(
            run_id,
            node=node_name,
            status=status,
            message=message,
            snapshot=sanitize_state(snapshot),
        )

    return callback


def _execute_workflow_run(payload: dict, config, run_id: str | None = None) -> dict:
    workflow = create_llm_workflow()
    initial_payload = dict(payload)
    if run_id:
        initial_payload["workflow_run_id"] = run_id

    initial_state = _initial_state(initial_payload, config)
    if run_id:
        # Bind the progress callback to this worker thread's context. LangGraph
        # strips non-channel keys from state, so a callback embedded in state
        # would silently never fire (runs would appear stuck in "starting"
        # with no events). The contextvar reporter is read by _emit_progress.
        set_progress_callback(_build_progress_callback(run_id))
        initial_state["workflow_run_id"] = run_id
        workflow_run_store.start_run(run_id)

    try:
        result = workflow.invoke(initial_state)
        if run_id:
            workflow_run_store.finish_run(run_id, result)
        return result
    except Exception as exc:
        if run_id:
            workflow_run_store.fail_run(run_id, exc, initial_state)
        raise
    finally:
        if run_id:
            set_progress_callback(None)


def create_app() -> Flask:
    global _ticket_poller
    app = Flask(__name__)
    config = load_runtime_config()
    app.config['RUNTIME_CONFIG'] = config

    if _ticket_poller is None and _should_start_background_worker(config):
        _ticket_poller = TicketPollerAgent(config, create_llm_workflow, _initial_state)
        _ticket_poller.start()

    @app.get("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.get("/health")
    def health():
        return jsonify({"status": "ok"})

    @app.get("/runtime")
    def runtime():
        return jsonify(
            {
                "workspace_root": str(config.workspace_root),
                "local_java_home": str(config.local_java_home) if config.local_java_home else "",
                "local_java_bin": str(config.local_java_bin) if config.local_java_bin else "",
                "local_maven_home": str(config.local_maven_home) if config.local_maven_home else "",
                "local_maven_repo": str(config.local_maven_repo) if config.local_maven_repo else "",
                "local_python_root": str(config.local_python_root),
                "local_python_executable": str(config.local_python_executable) if config.local_python_executable else "",
                "schema_path": str(config.schema_path),
                "jenkins_base_url": config.jenkins_base_url or "",
                "jenkins_job_name": config.jenkins_job_name or "",
                "jira_base_url": config.jira_base_url,
                "llm_model": config.llm_model,
                "flask_port": config.flask_port,
            }
        )

    @app.get("/schema/summary")
    def schema_summary():
        schema = load_api_schema(config)
        return jsonify({"summary": summarize_api_schema(schema), "paths": list((schema.get("paths") or {}).keys())})

    @app.post("/workflow/run")
    def run_workflow():
        payload = request.get_json(silent=True) or {}
        try:
            result = _execute_workflow_run(payload, config)
            return jsonify(result)
        except Exception as exc:
            return (
                jsonify(
                    {
                        "status": "WORKFLOW_ERROR",
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    }
                ),
                500,
            )

    @app.post("/workflow/start")
    def start_workflow():
        payload = request.get_json(silent=True) or {}
        run_id = workflow_run_store.create_run(payload)

        thread = threading.Thread(
            target=_execute_workflow_run,
            kwargs={"payload": payload, "config": config, "run_id": run_id},
            name=f"workflow-run-{run_id[:8]}",
            daemon=True,
        )
        thread.start()

        return jsonify({"run_id": run_id, "status": "QUEUED"}), 202

    @app.get("/workflow/runs")
    def list_workflow_runs():
        return jsonify({"runs": workflow_run_store.list_runs()})

    @app.get("/workflow/runs/<run_id>")
    def get_workflow_run(run_id: str):
        run = workflow_run_store.get_run(run_id)
        if not run:
            return jsonify({"status": "NOT_FOUND", "run_id": run_id}), 404
        return jsonify(run)

    @app.get("/config/active")
    def active_config():
        return jsonify(
            {
                "app_host": config.flask_host,
                "app_port": config.flask_port,
                "app_debug": config.flask_debug,
                "llm_model": config.llm_model,
                "workflow_default_max_retries": config.workflow_default_max_retries,
                "workflow_default_git_commit_message": config.workflow_default_git_commit_message,
                "http_request_timeout_seconds": config.http_request_timeout_seconds,
                "jenkins_base_url": config.jenkins_base_url,
                "jenkins_job_name": config.jenkins_job_name,
                "jenkins_poll_attempts": config.jenkins_poll_attempts,
                "jenkins_poll_interval_seconds": config.jenkins_poll_interval_seconds,
                "jira_base_url": config.jira_base_url,
                "jira_get_open_ticket_path": config.jira_get_open_ticket_path,
                "jira_comment_path_template": config.jira_comment_path_template,
                "jira_attachment_path_template": config.jira_attachment_path_template,
                "jira_labels_path_template": config.jira_labels_path_template,
                "jira_ai_fix_label": config.jira_ai_fix_label,
                "jira_developer_fix_label": config.jira_developer_fix_label,
                "jira_in_progress_status_value": config.jira_in_progress_status_value,
                "jira_stub_enabled": config.jira_stub_enabled,
                "jira_project_key": config.jira_project_key,
                "ticket_poller_enabled": config.ticket_poller_enabled,
                "ticket_poller_interval_seconds": config.ticket_poller_interval_seconds,
                "ticket_poller_default_project_name": config.ticket_poller_default_project_name,
                "ticket_poller_default_domain": config.ticket_poller_default_domain,
                "maven_wrapper_distribution_url": config.maven_wrapper_distribution_url,
            }
        )

    @app.get("/poller/status")
    def poller_status():
        if _ticket_poller is None:
            return jsonify({"enabled": False, "status": "NOT_RUNNING"})
        return jsonify(_ticket_poller.status())

    @app.post("/poller/scan-now")
    def poller_scan_now():
        if _ticket_poller is None:
            return jsonify({"enabled": False, "status": "NOT_RUNNING"}), 503
        return jsonify(_ticket_poller.scan_once())

    return app


app = create_app()


if __name__ == "__main__":
    config = load_runtime_config()
    app.run(host=config.flask_host, port=config.flask_port, debug=config.flask_debug)

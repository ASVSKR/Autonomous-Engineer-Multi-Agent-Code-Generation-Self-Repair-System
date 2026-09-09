import time
from pathlib import Path

import requests

from agent_runtime import commit_all_changes, load_runtime_config


def git_commit_agent(state):
    config = load_runtime_config()
    project_path = Path(state["java_project_path"])
    message = state.get("git_commit_message") or config.workflow_default_git_commit_message
    result = commit_all_changes(project_path=project_path, message=message, config=config)
    state["git_commit_result"] = result
    return state


def jenkins_check_agent(state):
    config = load_runtime_config()

    if not config.jenkins_base_url or not config.jenkins_job_name:
        state["jenkins_status"] = "SKIPPED_NO_CONFIG"
        state["jenkins_build_url"] = ""
        return state

    auth = None
    if config.jenkins_user and config.jenkins_token:
        auth = (config.jenkins_user, config.jenkins_token)

    trigger_url = f"{config.jenkins_base_url.rstrip('/')}/job/{config.jenkins_job_name}/build"

    try:
        trigger_response = requests.post(
            trigger_url,
            auth=auth,
            timeout=config.http_request_timeout_seconds,
        )
        if trigger_response.status_code not in (200, 201, 202):
            state["jenkins_status"] = f"TRIGGER_FAILED_{trigger_response.status_code}"
            state["jenkins_build_url"] = trigger_url
            return state

        api_url = (
            f"{config.jenkins_base_url.rstrip('/')}/job/"
            f"{config.jenkins_job_name}/lastBuild/api/json"
        )

        for _ in range(config.jenkins_poll_attempts):
            result = requests.get(
                api_url,
                auth=auth,
                timeout=config.http_request_timeout_seconds,
            )
            if result.status_code != 200:
                time.sleep(config.jenkins_poll_interval_seconds)
                continue
            build_data = result.json()
            if build_data.get("building"):
                time.sleep(config.jenkins_poll_interval_seconds)
                continue
            build_result = build_data.get("result", "UNKNOWN")
            state["jenkins_status"] = build_result
            state["jenkins_build_url"] = build_data.get("url", api_url)
            return state

        state["jenkins_status"] = "TIMEOUT"
        state["jenkins_build_url"] = api_url
        return state
    except Exception as exc:
        state["jenkins_status"] = f"ERROR: {exc}"
        state["jenkins_build_url"] = trigger_url
        return state

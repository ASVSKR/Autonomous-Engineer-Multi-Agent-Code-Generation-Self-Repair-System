import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
AGENT_ROOT = Path(__file__).resolve().parent
DEFAULT_SERVICE_ROOT = WORKSPACE_ROOT / "service" / "service"
DEFAULT_SCHEMA_PATH = DEFAULT_SERVICE_ROOT / "openapi-schema.yaml"
DEFAULT_MAVEN_DIST = (
    "https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/"
    "3.9.9/apache-maven-3.9.9-bin.zip"
)
CONFIG_FILE = AGENT_ROOT / "application.yaml"
DOTENV_FILE = AGENT_ROOT / ".env"
_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)(?::([^}]*))?\}")


load_dotenv(dotenv_path=str(DOTENV_FILE), encoding="utf-8-sig", override=True)


def _parse_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _parse_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _expand_env_placeholders(raw_text: str) -> str:
    def replace(match: re.Match[str]) -> str:
        env_name = match.group(1)
        fallback = match.group(2) if match.group(2) is not None else ""
        return os.getenv(env_name, fallback)

    return _ENV_PATTERN.sub(replace, raw_text)


def _load_yaml_config() -> dict[str, Any]:
    if not CONFIG_FILE.exists():
        return {}
    raw = CONFIG_FILE.read_text(encoding="utf-8")
    expanded = _expand_env_placeholders(raw)
    return yaml.safe_load(expanded) or {}


def _cfg(config_map: dict[str, Any], path: str, default: Any = None) -> Any:
    value: Any = config_map
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return default
        value = value[key]
    return value


@dataclass(frozen=True)
class RuntimeConfig:
    workspace_root: Path
    agent_root: Path
    generated_projects_dir: Path
    local_java_home: Path | None
    local_java_bin: Path | None
    local_maven_home: Path | None
    local_maven_bin: Path | None
    local_maven_repo: Path | None
    local_python_root: Path
    local_python_executable: Path | None
    service_root: Path
    schema_path: Path
    flask_host: str
    flask_port: int
    flask_debug: bool
    llm_model: str
    llm_fallback_model: str
    llm_api_key: str
    workflow_default_max_retries: int
    workflow_default_git_commit_message: str
    http_request_timeout_seconds: int
    jenkins_base_url: str | None
    jenkins_job_name: str | None
    jenkins_user: str | None
    jenkins_token: str | None
    jenkins_poll_attempts: int
    jenkins_poll_interval_seconds: int
    jira_base_url: str
    jira_create_path: str
    jira_get_open_ticket_path: str
    jira_comment_path_template: str
    jira_attachment_path_template: str
    jira_update_status_path_template: str
    jira_labels_path_template: str
    jira_ai_fix_label: str
    jira_developer_fix_label: str
    jira_in_progress_status_value: str
    jira_done_status_value: str
    jira_stub_enabled: bool
    jira_project_key: str
    ticket_poller_enabled: bool
    ticket_poller_interval_seconds: int
    ticket_poller_default_project_name: str
    ticket_poller_default_domain: str
    maven_wrapper_distribution_url: str


_cached_config: RuntimeConfig | None = None


def _find_first_existing(paths: list[Path]) -> Path | None:
    for candidate in paths:
        if candidate.exists():
            return candidate
    return None


def _resolve_java_home(workspace_root: Path, configured_java_home: str) -> Path | None:
    java_binary_name = "java.exe" if os.name == "nt" else "java"

    if configured_java_home:
        candidate = Path(configured_java_home)
        if (candidate / "bin" / java_binary_name).exists():
            return candidate
        return None

    candidates = [
        workspace_root / "java",
        workspace_root / "jdk",
        workspace_root / "local-java",
    ]
    for candidate in candidates:
        if (candidate / "bin" / java_binary_name).exists():
            return candidate
    return None


def _resolve_maven_home(workspace_root: Path, configured_maven_home: str) -> Path | None:
    """Locate a bundled Apache Maven distribution so builds need no system Maven.

    Looks for ``maven/bin/mvn(.cmd)`` directly under the workspace, and also
    inside a versioned ``maven/apache-maven-*`` folder (the layout produced when
    the official Maven zip is extracted as-is).
    """

    mvn_binary_name = "mvn.cmd" if os.name == "nt" else "mvn"

    search_roots: list[Path] = []
    if configured_maven_home:
        search_roots.append(Path(configured_maven_home))
    search_roots.extend(
        [
            workspace_root / "maven",
            workspace_root / "apache-maven",
            workspace_root / "local-maven",
        ]
    )

    for root in search_roots:
        if (root / "bin" / mvn_binary_name).exists():
            return root
        # Versioned extraction, e.g. maven/apache-maven-3.9.9/bin/mvn.cmd
        if root.exists():
            for nested in sorted(root.glob("apache-maven-*")):
                if (nested / "bin" / mvn_binary_name).exists():
                    return nested
    return None


def _resolve_maven_repo(workspace_root: Path, configured_repo: str) -> Path | None:
    """Locate a bundled local Maven repository for fully offline builds."""

    if configured_repo:
        candidate = Path(configured_repo)
        return candidate if candidate.exists() else None
    for name in (".m2-repo", "maven-repo", ".m2/repository"):
        candidate = workspace_root / name
        if candidate.exists():
            return candidate
    return None


def _resolve_python_executable(local_python_root: Path) -> Path | None:
    candidates = [
        local_python_root / "python.exe",
        local_python_root / "PCbuild" / "amd64" / "python.exe",
        local_python_root / "PCbuild" / "win32" / "python.exe",
    ]
    return _find_first_existing(candidates)


def load_runtime_config(refresh: bool = False) -> RuntimeConfig:
    global _cached_config
    if _cached_config is not None and not refresh:
        return _cached_config

    conf = _load_yaml_config()

    workspace_override = _cfg(conf, "paths.workspace_root", "")
    workspace_root = Path(workspace_override) if workspace_override else WORKSPACE_ROOT

    generated_projects_override = _cfg(conf, "paths.generated_projects_dir", "")
    generated_projects_dir = (
        Path(generated_projects_override)
        if generated_projects_override
        else AGENT_ROOT / "generated_projects"
    )

    service_root_override = _cfg(conf, "paths.service_root", "")
    service_root = Path(service_root_override) if service_root_override else DEFAULT_SERVICE_ROOT

    schema_path_override = _cfg(conf, "paths.schema_path", "")
    schema_path = Path(schema_path_override) if schema_path_override else (service_root / "openapi-schema.yaml")

    local_java_home_override = _cfg(conf, "paths.local_java_home", "")
    local_java_home = _resolve_java_home(workspace_root, str(local_java_home_override or ""))
    local_java_bin = local_java_home / "bin" if local_java_home else None

    local_maven_home_override = _cfg(conf, "paths.local_maven_home", "")
    local_maven_home = _resolve_maven_home(workspace_root, str(local_maven_home_override or ""))
    local_maven_bin = local_maven_home / "bin" if local_maven_home else None

    local_maven_repo_override = _cfg(conf, "paths.local_maven_repo", "")
    local_maven_repo = _resolve_maven_repo(workspace_root, str(local_maven_repo_override or ""))

    local_python_root_override = _cfg(conf, "paths.local_python_root", "")
    local_python_root = Path(local_python_root_override) if local_python_root_override else (workspace_root / "Python")
    local_python_executable = _resolve_python_executable(local_python_root)

    cfg = RuntimeConfig(
        workspace_root=workspace_root,
        agent_root=AGENT_ROOT,
        generated_projects_dir=generated_projects_dir,
        local_java_home=local_java_home,
        local_java_bin=local_java_bin,
        local_maven_home=local_maven_home,
        local_maven_bin=local_maven_bin,
        local_maven_repo=local_maven_repo,
        local_python_root=local_python_root,
        local_python_executable=local_python_executable,
        service_root=service_root,
        schema_path=schema_path,
        flask_host=str(_cfg(conf, "app.host", "0.0.0.0")),
        flask_port=_parse_int(_cfg(conf, "app.port", 5000), 5000),
        flask_debug=_parse_bool(_cfg(conf, "app.debug", True), True),
        llm_model=str(_cfg(conf, "llm.model", "llama-3.3-70b-versatile")),
        llm_fallback_model=str(_cfg(conf, "llm.fallback_model", "") or ""),
        llm_api_key=str(_cfg(conf, "llm.api_key", os.getenv("GROQ_API_KEY", ""))),
        workflow_default_max_retries=_parse_int(
            _cfg(conf, "workflow.default_max_retries", 2),
            2,
        ),
        workflow_default_git_commit_message=str(
            _cfg(conf, "workflow.default_git_commit_message", "chore: automated agent commit")
        ),
        http_request_timeout_seconds=_parse_int(_cfg(conf, "http.request_timeout_seconds", 20), 20),
        jenkins_base_url=str(_cfg(conf, "jenkins.base_url", "") or "") or None,
        jenkins_job_name=str(_cfg(conf, "jenkins.job_name", "") or "") or None,
        jenkins_user=str(_cfg(conf, "jenkins.user", "") or "") or None,
        jenkins_token=str(_cfg(conf, "jenkins.token", "") or "") or None,
        jenkins_poll_attempts=_parse_int(_cfg(conf, "jenkins.poll_attempts", 20), 20),
        jenkins_poll_interval_seconds=_parse_int(_cfg(conf, "jenkins.poll_interval_seconds", 3), 3),
        jira_base_url=str(_cfg(conf, "jira.base_url", "http://localhost:8080")),
        jira_create_path=str(_cfg(conf, "jira.create_path", "/jira/create")),
        jira_get_open_ticket_path=str(_cfg(conf, "jira.get_open_ticket_path", "/jira/getOpenTicket")),
        jira_comment_path_template=str(_cfg(conf, "jira.comment_path_template", "/jira/issue/__ISSUE_ID__/comment")),
        jira_attachment_path_template=str(
            _cfg(conf, "jira.attachment_path_template", "/jira/issue/__ISSUE_ID__/attachments")
        ),
        jira_update_status_path_template=str(
            _cfg(conf, "jira.update_status_path_template", "/jira/updateStatus/__ISSUE_ID__")
        ),
        jira_labels_path_template=str(
            _cfg(conf, "jira.labels_path_template", "/jira/issue/__ISSUE_ID__/labels")
        ),
        jira_ai_fix_label=str(_cfg(conf, "jira.ai_fix_label", "ai-fix")),
        jira_developer_fix_label=str(_cfg(conf, "jira.developer_fix_label", "developer-fix")),
        jira_in_progress_status_value=str(_cfg(conf, "jira.in_progress_status_value", "In Progress")),
        jira_done_status_value=str(_cfg(conf, "jira.done_status_value", "Done")),
        jira_stub_enabled=_parse_bool(_cfg(conf, "jira.stub_enabled", False), False),
        jira_project_key=str(_cfg(conf, "jira.project_key", "HACK")),
        ticket_poller_enabled=_parse_bool(_cfg(conf, "jira.ticket_poller_enabled", True), True),
        ticket_poller_interval_seconds=_parse_int(_cfg(conf, "jira.ticket_poller_interval_seconds", 30), 30),
        ticket_poller_default_project_name=str(
            _cfg(conf, "jira.ticket_poller_default_project_name", "inventory-management-system")
        ),
        ticket_poller_default_domain=str(_cfg(conf, "jira.ticket_poller_default_domain", "inventory")),
        maven_wrapper_distribution_url=str(
            _cfg(conf, "maven.wrapper_distribution_url", DEFAULT_MAVEN_DIST)
        ),
    )

    _cached_config = cfg
    return cfg


def build_subprocess_env(config: RuntimeConfig) -> dict[str, str]:
    env = os.environ.copy()
    if config.local_java_home is not None:
        env["JAVA_HOME"] = str(config.local_java_home)
    if config.local_java_bin is not None:
        env["PATH"] = str(config.local_java_bin) + os.pathsep + env.get("PATH", "")
    if config.local_maven_home is not None:
        env["MAVEN_HOME"] = str(config.local_maven_home)
        env["M2_HOME"] = str(config.local_maven_home)
    if config.local_maven_bin is not None:
        # Put bundled Maven first so the generated `mvnw.cmd` (which calls `mvn`)
        # resolves to the portable distribution rather than a system install.
        env["PATH"] = str(config.local_maven_bin) + os.pathsep + env.get("PATH", "")
    if config.local_maven_repo is not None:
        # Maven 3.9+ honours MAVEN_ARGS; point builds at the bundled offline repo.
        repo_arg = "-Dmaven.repo.local=" + str(config.local_maven_repo)
        existing_args = env.get("MAVEN_ARGS", "").strip()
        env["MAVEN_ARGS"] = (existing_args + " " + repo_arg).strip() if existing_args else repo_arg
    if config.local_python_executable is not None:
        env["AGENT_PYTHON_EXECUTABLE"] = str(config.local_python_executable)
    else:
        env["AGENT_PYTHON_EXECUTABLE"] = sys.executable
    return env


def load_api_schema(config: RuntimeConfig | None = None) -> dict[str, Any]:
    runtime = config or load_runtime_config()
    if not runtime.schema_path.exists():
        return {"paths": {}, "components": {"schemas": {}}}
    return yaml.safe_load(runtime.schema_path.read_text(encoding="utf-8")) or {}


def summarize_api_schema(schema: dict[str, Any]) -> str:
    path_items = schema.get("paths", {})
    summaries = []
    for route, methods in path_items.items():
        for method, spec in methods.items():
            summary = spec.get("summary", route)
            summaries.append(f"{method.upper()} {route}: {summary}")
    return "\n".join(summaries)


def run_command(command: list[str], cwd: Path, config: RuntimeConfig) -> subprocess.CompletedProcess[str]:
    env = build_subprocess_env(config)
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
    )


def ensure_git_repo(project_path: Path, config: RuntimeConfig) -> None:
    git_dir = project_path / ".git"
    if git_dir.exists():
        return
    run_command(["git", "init"], project_path, config)
    run_command(["git", "branch", "-M", "main"], project_path, config)


def commit_all_changes(project_path: Path, message: str, config: RuntimeConfig) -> str:
    ensure_git_repo(project_path, config)
    run_command(["git", "add", "."], project_path, config)
    status = run_command(["git", "status", "--porcelain"], project_path, config)
    if not status.stdout.strip():
        return "No changes to commit"
    commit = run_command(["git", "commit", "-m", message], project_path, config)
    return (commit.stdout + commit.stderr).strip()


def create_local_wrapper(project_path: Path, config: RuntimeConfig) -> None:
    mvn_wrapper_dir = project_path / ".mvn" / "wrapper"
    mvn_wrapper_dir.mkdir(parents=True, exist_ok=True)

    wrapper_properties = "distributionUrl=" + config.maven_wrapper_distribution_url + "\n"
    (mvn_wrapper_dir / "maven-wrapper.properties").write_text(
        wrapper_properties,
        encoding="utf-8",
    )

    mvnw_cmd = """@echo off
REM Maven wrapper - runs mvn in the current directory
mvn %*
"""
    (project_path / "mvnw.cmd").write_text(mvnw_cmd, encoding="utf-8")

    mvnw_sh = """#!/bin/sh
# Maven wrapper - runs mvn in the current directory
exec mvn "$@"
"""
    (project_path / "mvnw").write_text(mvnw_sh, encoding="utf-8")


def duplicate_project_if_needed(generated_projects_dir: Path, project_name: str) -> Path:
    base_project_path = generated_projects_dir / project_name
    if not base_project_path.exists():
        return base_project_path

    counter = 2
    while True:
        new_project_name = f"{project_name}_v{counter}"
        new_project_path = generated_projects_dir / new_project_name
        if not new_project_path.exists():
            shutil.copytree(base_project_path, new_project_path)
            return new_project_path
        counter += 1


def copy_or_return_project_dir(
    generated_projects_dir: Path, project_name: str, source: Path
) -> Path:
    target = generated_projects_dir / project_name
    if target.exists():
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target)
    return target

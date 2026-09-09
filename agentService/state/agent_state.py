from typing import TypedDict

class AgentState(TypedDict):

    project_name: str
    domain: str

    java_project_path: str

    generated_code: str
    generated_test: str

    build_status: str
    test_status: str
    baseline_test_status: str
    edge_case_test_status: str
    compile_status: str
    build_stdout: str
    build_stderr: str
    detected_exception_type: str
    detected_exception_message: str

    source_class: str
    source_method: str
    source_file_path: str
    failing_test_class: str
    failing_test_method: str
    failing_test_line: str
    failing_test_file_path: str

    trigger_bug_generation: bool
    api_schema_summary: str

    jira_ticket_id: str
    jira_ticket_status: str
    jira_summary: str
    jira_description: str

    git_commit_message: str
    git_commit_result: str

    jenkins_status: str
    jenkins_build_url: str

    spring_smoke_status: str
    spring_smoke_results: list

    injected_exception_type: str
    injected_exception_scenario: str

    source_ticket_id: str
    source_ticket_details: dict
    fix_rca_comment: str
    fix_solution_summary: str
    fix_strategy: str
    fix_test_modified: str
    fix_llm_error: str
    source_ticket_comment_status: str
    source_ticket_status_update: str
    jira_attachment_status: str
    developer_handoff_status: str

    workflow_run_id: str
    workflow_status: str
    workflow_current_step: str
    workflow_events: list

    retry_count: int
    max_retries: int
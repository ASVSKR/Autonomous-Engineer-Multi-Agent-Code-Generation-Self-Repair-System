from langgraph.graph import StateGraph

from state.agent_state import AgentState
from workflow_run_store import get_progress_callback

from agents.project_generator_agent import project_generator
from agents.llm_code_generator_agent import llm_code_generator
from agents.llm_test_generator_agent import llm_test_generator
from agents.build_agent import build_agent
from agents.llm_fix_agent import llm_fix_agent
from agents.llm_file_writer_agent import llm_file_writer
from agents.jira_agent import (
    jira_agent,
    jira_close_agent,
    source_ticket_in_progress_agent,
    source_ticket_finalize_agent,
)
from agents.git_ci_agent import git_commit_agent, jenkins_check_agent
from agents.spring_smoke_agent import spring_smoke_agent


def _emit_progress(state, node_name, status, message=""):
    events = list(state.get("workflow_events", []))
    event = {
        "node": node_name,
        "status": status,
        "message": message,
    }
    events.append(event)
    state["workflow_events"] = events
    state["workflow_current_step"] = node_name
    state["workflow_status"] = status

    # Prefer the context-bound callback (survives LangGraph channel filtering);
    # fall back to a state-embedded callback for direct/legacy invocations.
    callback = get_progress_callback() or state.get("_progress_callback")
    if callback:
        callback(node_name=node_name, status=status, message=message, snapshot=state)


def _tracked(node_name, handler):
    def wrapped(state):
        _emit_progress(state, node_name, "RUNNING")
        result = handler(state)
        _emit_progress(result, node_name, "COMPLETED")
        return result

    return wrapped


def _jira_failure_capture_agent(state):
    # Failure-path capture: create/update Jira context immediately, then continue retries.
    return jira_agent(state)


def build_router(state):
    if state.get("build_status") == "SUCCESS" and state.get("test_status") == "PASSED":
        return "success"

    return "failed"


def retry_router(state):
    retry_count = state.get("retry_count", 0)
    max_retries = state.get("max_retries", 2)
    if retry_count >= max_retries:
        return "no_retry"
    return "retry"


def jenkins_router(state):
    status = state.get("jenkins_status", "")
    if status == "SUCCESS" or status == "SKIPPED_NO_CONFIG":
        return "ok"
    return "failed"


def smoke_router(state):
    if state.get("build_status") == "SUCCESS" and state.get("test_status") == "PASSED":
        return "after_success"
    return "after_failure"


def create_workflow():

    graph = StateGraph(AgentState)

    graph.add_node(
        "project_generator",
        _tracked("project_generator", project_generator)
    )

    graph.add_node(
        "llm_code_generator",
        _tracked("llm_code_generator", llm_code_generator)
    )

    graph.add_node(
        "llm_test_generator",
        _tracked("llm_test_generator", llm_test_generator)
    )

    graph.add_node(
        "llm_file_writer",
        _tracked("llm_file_writer", llm_file_writer)
    )

    graph.add_node(
        "build_agent",
        _tracked("build_agent", build_agent)
    )

    graph.add_node(
        "llm_fix_agent",
        _tracked("llm_fix_agent", llm_fix_agent)
    )

    graph.add_node(
        "jira_agent",
        _tracked("jira_agent", jira_agent)
    )

    graph.add_node(
        "jira_failure_capture_agent",
        _tracked("jira_failure_capture_agent", _jira_failure_capture_agent)
    )

    graph.add_node(
        "git_commit_agent",
        _tracked("git_commit_agent", git_commit_agent)
    )

    graph.add_node(
        "spring_smoke_agent",
        _tracked("spring_smoke_agent", spring_smoke_agent)
    )

    graph.add_node(
        "jenkins_check_agent",
        _tracked("jenkins_check_agent", jenkins_check_agent)
    )

    graph.add_node(
        "jira_close_agent",
        _tracked("jira_close_agent", jira_close_agent)
    )

    graph.add_node(
        "source_ticket_in_progress_agent",
        _tracked("source_ticket_in_progress_agent", source_ticket_in_progress_agent)
    )

    graph.add_node(
        "source_ticket_finalize_agent",
        _tracked("source_ticket_finalize_agent", source_ticket_finalize_agent)
    )

    graph.add_edge(
        "project_generator",
        "source_ticket_in_progress_agent"
    )

    graph.add_edge(
        "source_ticket_in_progress_agent",
        "llm_code_generator"
    )

    graph.add_edge(
        "llm_code_generator",
        "llm_test_generator"
    )

    graph.add_edge(
        "llm_test_generator",
        "llm_file_writer"
    )

    graph.add_edge(
        "llm_file_writer",
        "build_agent"
    )

    graph.add_conditional_edges(
        "build_agent",
        build_router,
        {
            "success": "spring_smoke_agent",
            "failed": "jira_failure_capture_agent"
        }
    )

    graph.add_edge(
        "jira_failure_capture_agent",
        "llm_fix_agent"
    )

    graph.add_conditional_edges(
        "spring_smoke_agent",
        smoke_router,
        {
            "after_success": "git_commit_agent",
            "after_failure": "jira_agent",
        }
    )

    graph.add_conditional_edges(
        "llm_fix_agent",
        retry_router,
        {
            "retry": "llm_file_writer",
            "no_retry": "spring_smoke_agent"
        }
    )

    graph.add_edge(
        "git_commit_agent",
        "jenkins_check_agent"
    )

    graph.add_conditional_edges(
        "jenkins_check_agent",
        jenkins_router,
        {
            "ok": "jira_close_agent",
            "failed": "jira_agent"
        }
    )

    graph.add_edge(
        "jira_close_agent",
        "source_ticket_finalize_agent"
    )

    graph.add_edge(
        "jira_agent",
        "source_ticket_finalize_agent"
    )

    graph.add_edge(
        "source_ticket_finalize_agent",
        "__end__"
    )

    graph.set_entry_point(
        "project_generator"
    )

    return graph.compile()